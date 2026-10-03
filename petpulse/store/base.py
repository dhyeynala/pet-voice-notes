"""The ``Store`` protocol.

Paths are slash-separated, Firestore style:

- a *collection path* has an odd number of segments: ``pets`` or ``pets/<id>/analytics``
- a *document path* has an even number of segments: ``pets/<id>`` or ``pets/<id>/analytics/<id>``

Documents are plain JSON-serialisable dicts. Implementations return copies, so callers can
mutate what they get back without touching stored data.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Optional, Protocol, Sequence, Tuple, runtime_checkable

Op = Literal["==", "!=", "<", "<=", ">", ">=", "array_contains", "in"]
Where = Tuple[str, Op, Any]
OrderBy = Tuple[str, Literal["asc", "desc"]]

SUPPORTED_OPS: frozenset[str] = frozenset({"==", "!=", "<", "<=", ">", ">=", "array_contains", "in"})


class NotFound(KeyError):
    """Raised by operations that require an existing document (e.g. ``update``)."""


class ArrayUnion:
    """Write transform: append ``values`` to a list field, skipping ones already present."""

    __slots__ = ("values",)

    def __init__(self, values: Iterable[Any]) -> None:
        self.values: Tuple[Any, ...] = tuple(values)

    def __repr__(self) -> str:
        return f"ArrayUnion({list(self.values)!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ArrayUnion) and other.values == self.values

    __hash__ = None  # type: ignore[assignment]


@runtime_checkable
class Store(Protocol):
    def get(self, path: str) -> Optional[dict[str, Any]]:
        """Return the document at ``path`` or ``None``."""

    def set(self, path: str, data: dict[str, Any], merge: bool = False) -> None:
        """Create or replace (``merge=False``) or shallow-merge (``merge=True``) a document."""

    def add(self, collection_path: str, data: dict[str, Any]) -> str:
        """Insert ``data`` under a new server-generated id and return the id."""

    def query(
        self,
        collection_path: str,
        where: Sequence[Where] = (),
        order_by: Optional[Sequence[OrderBy]] = None,
        limit: Optional[int] = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return ``(id, document)`` pairs matching every ``where`` clause."""

    def delete(self, path: str) -> None:
        """Delete a document (no error if it does not exist). Sub-collections are kept."""


def split_path(path: str) -> list[str]:
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("empty store path")
    for part in parts:
        if part in (".", ".."):
            raise ValueError(f"invalid path segment in {path!r}")
    return parts


def document_parts(path: str) -> tuple[str, str]:
    """Split a document path into ``(collection_path, doc_id)``."""
    parts = split_path(path)
    if len(parts) % 2:
        raise ValueError(f"{path!r} is a collection path, expected a document path")
    return "/".join(parts[:-1]), parts[-1]


def collection_key(path: str) -> str:
    parts = split_path(path)
    if not len(parts) % 2:
        raise ValueError(f"{path!r} is a document path, expected a collection path")
    return "/".join(parts)
