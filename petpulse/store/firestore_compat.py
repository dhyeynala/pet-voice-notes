"""Transitional Firestore-shaped facade over a ``Store``.

The legacy modules (``api_server``, ``firestore_store``, ``simple_rag_service``,
``intelligent_chatbot_service``) were written against ``firestore.client()``. This facade
lets them run unchanged on the demo store while later tracks move them to the ``Store``
API directly. It supports only what the legacy code uses:

``collection(...).document(...).collection(...)``, ``document().get().exists/.to_dict()/.id``,
``set(data, merge=)``, ``update``, ``delete``, ``collection.add``, ``where(f, op, v)``
(chainable), ``order_by``, ``limit``, ``stream()``, and ``ArrayUnion``.

The store is resolved on every call (through ``store_getter``), never captured at import,
so tests can swap it.

Delete this module once nothing imports it (target: end of the LLM/data tracks).
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Iterator, Optional

from petpulse.store.base import ArrayUnion, NotFound, Store

__all__ = ["ArrayUnion", "CompatClient", "DocumentSnapshot"]

StoreGetter = Callable[[], Store]

# Firestore's ``where`` uses ``array-contains``; our Store uses ``array_contains``.
_OP_ALIASES = {"array-contains": "array_contains"}


class DocumentSnapshot:
    def __init__(self, reference: "DocumentReference", data: Optional[dict[str, Any]]) -> None:
        self.reference = reference
        self.id = reference.id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[dict[str, Any]]:
        return dict(self._data) if self._data is not None else None

    def get(self, field: str) -> Any:
        return (self._data or {}).get(field)


class Query:
    def __init__(
        self,
        store_getter: StoreGetter,
        path: str,
        where: tuple[Any, ...] = (),
        order: tuple[tuple[str, str], ...] = (),
        limit_n: Optional[int] = None,
    ) -> None:
        self._store_getter = store_getter
        self._path = path
        self._where = where
        self._order = order
        self._limit = limit_n

    def where(self, field: str, op: str, value: Any) -> "Query":
        clause = (field, _OP_ALIASES.get(op, op), value)
        return Query(self._store_getter, self._path, self._where + (clause,), self._order, self._limit)

    def order_by(self, field: str, direction: str = "ASCENDING") -> "Query":
        norm = "desc" if str(direction).upper().startswith("DESC") else "asc"
        return Query(self._store_getter, self._path, self._where, self._order + ((field, norm),), self._limit)

    def limit(self, count: int) -> "Query":
        return Query(self._store_getter, self._path, self._where, self._order, count)

    def stream(self) -> Iterator[DocumentSnapshot]:
        where: list[Any] = list(self._where)
        order: list[Any] = list(self._order)
        rows = self._store_getter().query(self._path, where=where, order_by=order or None, limit=self._limit)
        for doc_id, data in rows:
            yield DocumentSnapshot(DocumentReference(self._store_getter, f"{self._path}/{doc_id}"), data)

    def get(self) -> list[DocumentSnapshot]:
        return list(self.stream())


class CollectionReference(Query):
    def __init__(self, store_getter: StoreGetter, path: str) -> None:
        super().__init__(store_getter, path)

    @property
    def id(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def document(self, doc_id: Optional[str] = None) -> "DocumentReference":
        if doc_id is None:
            doc_id = uuid.uuid4().hex
        return DocumentReference(self._store_getter, f"{self._path}/{doc_id}")

    def add(self, data: dict[str, Any]) -> tuple[None, "DocumentReference"]:
        doc_id = self._store_getter().add(self._path, data)
        return None, DocumentReference(self._store_getter, f"{self._path}/{doc_id}")


class DocumentReference:
    def __init__(self, store_getter: StoreGetter, path: str) -> None:
        self._store_getter = store_getter
        self.path = path
        self.id = path.rsplit("/", 1)[-1]

    def collection(self, name: str) -> CollectionReference:
        return CollectionReference(self._store_getter, f"{self.path}/{name}")

    def get(self) -> DocumentSnapshot:
        return DocumentSnapshot(self, self._store_getter().get(self.path))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        self._store_getter().set(self.path, data, merge=merge)

    def update(self, data: dict[str, Any]) -> None:
        store = self._store_getter()
        if store.get(self.path) is None:
            raise NotFound(self.path)
        store.set(self.path, data, merge=True)

    def delete(self) -> None:
        self._store_getter().delete(self.path)


class CompatClient:
    """Drop-in for the subset of ``google.cloud.firestore.Client`` the legacy code uses."""

    def __init__(self, store_getter: StoreGetter) -> None:
        self._store_getter = store_getter

    def collection(self, name: str) -> CollectionReference:
        return CollectionReference(self._store_getter, name)
