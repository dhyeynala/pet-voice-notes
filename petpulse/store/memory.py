"""In-memory store, and a JSON-file-backed variant for the demo container."""

from __future__ import annotations

import copy
import json
import operator
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Sequence

from petpulse.store.base import (
    ArrayUnion,
    NotFound,
    OrderBy,
    Where,
    collection_key,
    document_parts,
)

_MISSING = object()


def _lookup(doc: dict[str, Any], field: str) -> Any:
    """Resolve a dotted field path (``a.b``) or return ``_MISSING``."""
    current: Any = doc
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "array_contains": lambda actual, expected: isinstance(actual, list) and expected in actual,
    "in": lambda actual, expected: actual in expected,
}


def _matches(doc: dict[str, Any], clause: Where) -> bool:
    field, op, expected = clause
    compare = _OPS.get(op)
    if compare is None:
        raise ValueError(f"unsupported where operator {op!r}")
    actual = _lookup(doc, field)
    if actual is _MISSING:
        # Firestore semantics: documents without the field never match.
        return False
    try:
        return bool(compare(actual, expected))
    except TypeError:
        # Mismatched types (e.g. str vs int) never match, as in Firestore.
        return False


def _apply_transforms(existing: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, ArrayUnion):
            current = existing.get(key)
            merged = list(current) if isinstance(current, list) else []
            for item in value.values:
                if item not in merged:
                    merged.append(item)
            out[key] = merged
        else:
            out[key] = value
    return out


def _check_json(data: dict[str, Any]) -> None:
    try:
        json.dumps(data)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"store documents must be JSON-serialisable: {exc}") from exc


class MemoryStore:
    """Thread-safe dict-of-collections store. Single process only (fine for the demo)."""

    def __init__(self, data: Optional[dict[str, dict[str, dict[str, Any]]]] = None) -> None:
        self._lock = threading.RLock()
        self._collections: dict[str, dict[str, dict[str, Any]]] = copy.deepcopy(data) if data else {}
        self._batch_depth = 0
        self._batch_dirty = False

    # ------------------------------------------------------------------ hooks
    def _changed(self) -> None:
        """Called after every successful write. ``JsonFileStore`` persists here."""

    def _notify(self) -> None:
        if self._batch_depth:
            self._batch_dirty = True
        else:
            self._changed()

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Group many writes into one ``_changed()`` call (one file write for ``JsonFileStore``).

        Holds the store lock for the duration, so other threads see all of the batch or none.
        """
        with self._lock:
            self._batch_depth += 1
            try:
                yield
            finally:
                self._batch_depth -= 1
                if not self._batch_depth and self._batch_dirty:
                    self._batch_dirty = False
                    self._changed()

    # ------------------------------------------------------------------ Store API
    def get(self, path: str) -> Optional[dict[str, Any]]:
        coll, doc_id = document_parts(path)
        with self._lock:
            doc = self._collections.get(coll, {}).get(doc_id)
            return copy.deepcopy(doc) if doc is not None else None

    def set(self, path: str, data: dict[str, Any], merge: bool = False) -> None:
        coll, doc_id = document_parts(path)
        with self._lock:
            docs = self._collections.setdefault(coll, {})
            existing = docs.get(doc_id, {}) if merge else {}
            resolved = _apply_transforms(existing, data)
            new_doc = {**existing, **resolved} if merge else resolved
            _check_json(new_doc)
            docs[doc_id] = copy.deepcopy(new_doc)
            self._notify()

    def update(self, path: str, data: dict[str, Any]) -> None:
        """Merge into an existing document; raise ``NotFound`` if it does not exist."""
        if self.get(path) is None:
            raise NotFound(path)
        self.set(path, data, merge=True)

    def add(self, collection_path: str, data: dict[str, Any]) -> str:
        coll = collection_key(collection_path)
        doc_id = uuid.uuid4().hex
        self.set(f"{coll}/{doc_id}", data)
        return doc_id

    def query(
        self,
        collection_path: str,
        where: Sequence[Where] = (),
        order_by: Optional[Sequence[OrderBy]] = None,
        limit: Optional[int] = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        coll = collection_key(collection_path)
        with self._lock:
            rows = [
                (doc_id, copy.deepcopy(doc))
                for doc_id, doc in self._collections.get(coll, {}).items()
                if all(_matches(doc, clause) for clause in where)
            ]
        for field, direction in reversed(list(order_by or [])):
            # Documents missing the order field are dropped, as Firestore does.
            rows = [row for row in rows if _lookup(row[1], field) is not _MISSING]
            rows.sort(key=lambda row: _lookup(row[1], field), reverse=direction == "desc")
        if limit is not None:
            rows = rows[: max(limit, 0)]
        return rows

    def delete(self, path: str) -> None:
        coll, doc_id = document_parts(path)
        with self._lock:
            if self._collections.get(coll, {}).pop(doc_id, None) is not None:
                self._notify()

    # ------------------------------------------------------------------ helpers
    def collections(self) -> list[str]:
        with self._lock:
            return sorted(self._collections)

    def snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        with self._lock:
            return copy.deepcopy(self._collections)

    def clear(self) -> None:
        with self._lock:
            self._collections.clear()
            self._notify()


class JsonFileStore(MemoryStore):
    """``MemoryStore`` that loads ``path`` at startup and rewrites it atomically on every change."""

    FORMAT_VERSION = 1

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        super().__init__(self._load())

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict) or not isinstance(payload.get("collections"), dict):
            raise ValueError(f"{self.path} is not a PetPulse store file")
        collections: dict[str, dict[str, dict[str, Any]]] = payload["collections"]
        return collections

    def _changed(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format_version": self.FORMAT_VERSION, "collections": self._collections}
        fd, tmp_name = tempfile.mkstemp(prefix=".db-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=1, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
