"""``Store`` and ``BlobStore`` on Firebase (Firestore + Cloud Storage for Firebase).

Same semantics as ``MemoryStore`` / ``LocalBlobStore``, so routes and services cannot tell them
apart:

- ``set(merge=True)`` is a *shallow* merge: each top-level key replaces the stored field (sent as
  an explicit field-path merge list; Firestore's ``merge=True`` would deep-merge nested maps).
- ``ArrayUnion`` maps to Firestore's ``ArrayUnion`` transform.
- ``add`` uses a uuid4 hex id, like the local stores.
- Documents must be JSON-serialisable (same check as ``MemoryStore``).

The SDK objects are injected (``client``, ``array_union``, ``field_filter``; ``bucket``), so the
classes are unit-tested with fakes; ``from_app`` does the lazy ``firebase_admin`` imports.
Not implemented on purpose: ``clear()`` (so ``POST /api/demo/reset`` can never wipe a real
project) and ``batch()`` (writes go straight to Firestore).
"""

from __future__ import annotations

import importlib
import io
import re
import uuid
from typing import Any, BinaryIO, Callable, Optional, Sequence

from petpulse.store.base import SUPPORTED_OPS, ArrayUnion, NotFound, OrderBy, Where, collection_key, document_parts
from petpulse.store.blobs import _KEY_SEGMENT
from petpulse.store.memory import _check_json

_SIMPLE_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _field_path(key: str) -> str:
    """A top-level field name as a Firestore field path (backtick-quoted unless simple)."""
    if _SIMPLE_FIELD.match(key):
        return key
    return "`" + key.replace("\\", "\\\\").replace("`", "\\`") + "`"


class FirestoreStore:
    def __init__(
        self,
        client: Any,
        *,
        array_union: Callable[[list[Any]], Any],
        field_filter: Callable[[str, str, Any], Any],
    ) -> None:
        self._client = client
        self._array_union = array_union
        self._field_filter = field_filter

    @classmethod
    def from_app(cls, app: Any) -> "FirestoreStore":
        firestore = importlib.import_module("firebase_admin.firestore")
        sdk = importlib.import_module("google.cloud.firestore")
        return cls(firestore.client(app), array_union=sdk.ArrayUnion, field_filter=sdk.FieldFilter)

    # ------------------------------------------------------------------ Store API
    def get(self, path: str) -> Optional[dict[str, Any]]:
        coll, doc_id = document_parts(path)
        snapshot = self._client.document(f"{coll}/{doc_id}").get()
        if not snapshot.exists:
            return None
        data: Any = snapshot.to_dict()
        return dict(data) if isinstance(data, dict) else {}

    def set(self, path: str, data: dict[str, Any], merge: bool = False) -> None:
        coll, doc_id = document_parts(path)
        plain = {key: list(value.values) if isinstance(value, ArrayUnion) else value for key, value in data.items()}
        _check_json(plain)
        converted = {
            key: self._array_union(list(value.values)) if isinstance(value, ArrayUnion) else value
            for key, value in data.items()
        }
        ref = self._client.document(f"{coll}/{doc_id}")
        if not merge:
            ref.set(converted)
        elif converted:
            ref.set(converted, merge=[_field_path(key) for key in converted])
        else:
            ref.set({}, merge=True)  # creates the document if missing, changes nothing otherwise

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
        if limit is not None and limit <= 0:
            return []
        query: Any = self._client.collection(coll)
        for field, op, value in where:
            if op not in SUPPORTED_OPS:
                raise ValueError(f"unsupported where operator {op!r}")
            query = query.where(filter=self._field_filter(field, op, value))
        for field, direction in order_by or []:
            query = query.order_by(field, direction="DESCENDING" if direction == "desc" else "ASCENDING")
        if limit is not None:
            query = query.limit(limit)
        rows: list[tuple[str, dict[str, Any]]] = []
        for snapshot in query.stream():
            data: Any = snapshot.to_dict()
            rows.append((str(snapshot.id), dict(data) if isinstance(data, dict) else {}))
        return rows

    def delete(self, path: str) -> None:
        coll, doc_id = document_parts(path)
        self._client.document(f"{coll}/{doc_id}").delete()


class FirebaseBlobStore:
    """Blobs in a Cloud Storage for Firebase bucket. Same key rules as ``LocalBlobStore``.

    Objects are private (no public URLs, no download tokens); files are served only through the
    owner-checked API routes.
    """

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    @classmethod
    def from_app(cls, app: Any) -> "FirebaseBlobStore":
        storage = importlib.import_module("firebase_admin.storage")
        return cls(storage.bucket(app=app))

    @staticmethod
    def _check(key: str) -> str:
        parts = key.split("/")
        if not parts or any(not _KEY_SEGMENT.match(part) for part in parts):
            raise ValueError(f"invalid blob key {key!r}")
        return key

    def put(self, key: str, data: bytes) -> None:
        content_type = "application/pdf" if key.endswith(".pdf") else "application/octet-stream"
        self._bucket.blob(self._check(key)).upload_from_string(data, content_type=content_type)

    def open(self, key: str) -> BinaryIO:
        blob = self._bucket.blob(self._check(key))
        try:
            data = blob.download_as_bytes()
        except Exception as exc:
            if _is_not_found(exc):
                raise FileNotFoundError(key) from None
            raise
        return io.BytesIO(data)

    def delete(self, key: str) -> None:
        try:
            self._bucket.blob(self._check(key)).delete()
        except Exception as exc:
            if not _is_not_found(exc):
                raise

    def exists(self, key: str) -> bool:
        return bool(self._bucket.blob(self._check(key)).exists())


def _is_not_found(exc: BaseException) -> bool:
    # google.api_core.exceptions.NotFound, matched without importing google-api-core.
    return type(exc).__name__ == "NotFound" or getattr(exc, "code", None) == 404
