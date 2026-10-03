"""In-process fakes for the Firebase Admin SDK (no network, no firebase_admin install needed).

- ``FakeFirestoreClient``: the slice of ``google.cloud.firestore.Client`` that ``FirestoreStore``
  uses, with Firestore's own semantics where they differ from ours (``merge=True`` deep-merges,
  a merge field list replaces whole fields, arrays may not directly contain arrays).
- ``FakeBucket``: the slice of ``google.cloud.storage.Bucket`` used by ``FirebaseBlobStore``.
- ``install(monkeypatch, ...)``: puts fake ``firebase_admin`` (+ ``auth``, ``credentials``,
  ``firestore``, ``storage``) and ``google.cloud.firestore`` modules into ``sys.modules``.
"""

from __future__ import annotations

import copy
import operator
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pytest

FAKE_SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "petpulse-test",
    "client_email": "petpulse@petpulse-test.iam.gserviceaccount.com",
    "private_key": "not-a-real-key",  # pragma: allowlist secret
}


# ---------------------------------------------------------------------------- Firestore
class FakeArrayUnion:
    def __init__(self, values: list[Any]) -> None:
        self.values = list(values)


@dataclass(frozen=True)
class FakeFieldFilter:
    field_path: str
    op_string: str
    value: Any


class FakeNotFound(Exception):
    code = 404


_MISSING = object()


def _lookup(doc: dict[str, Any], path: str) -> Any:
    current: Any = doc
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _check_value(value: Any, inside_array: bool = False) -> None:
    if isinstance(value, list):
        if inside_array:
            raise ValueError("Firestore: an array cannot directly contain another array")
        for item in value:
            _check_value(item, True)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Firestore: map keys must be non-empty strings")
            _check_value(item)
    elif isinstance(value, FakeArrayUnion):
        for item in value.values:
            _check_value(item, True)


def _resolve(existing: Any, value: Any) -> Any:
    if isinstance(value, FakeArrayUnion):
        merged = list(existing) if isinstance(existing, list) else []
        merged.extend(v for v in value.values if v not in merged)
        return merged
    return copy.deepcopy(value)


def _deep_merge(existing: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(existing)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = _resolve(out.get(key), value)
    return out


def _unquote(field_path: str) -> str:
    if field_path.startswith("`") and field_path.endswith("`"):
        return field_path[1:-1].replace("\\`", "`").replace("\\\\", "\\")
    if "." in field_path:
        raise NotImplementedError("fake supports top-level merge fields only")
    return field_path


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


class FakeSnapshot:
    def __init__(self, doc_id: str, data: Optional[dict[str, Any]]) -> None:
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._data)


class FakeDocumentRef:
    def __init__(self, client: "FakeFirestoreClient", path: str) -> None:
        assert len(path.split("/")) % 2 == 0, path
        self._client = client
        self.path = path
        self.id = path.rsplit("/", 1)[-1]

    def get(self) -> FakeSnapshot:
        self._client.calls.append(("get", self.path))
        return FakeSnapshot(self.id, self._client.docs.get(self.path))

    def set(self, data: dict[str, Any], merge: Any = False) -> None:
        self._client.calls.append(("set", self.path, merge))
        _check_value(data)
        existing = self._client.docs.get(self.path, {})
        if merge is True:
            new = _deep_merge(existing, data)
        elif merge:
            fields = [_unquote(f) for f in merge]
            assert set(fields) <= set(data), "merge fields must be in the data"
            new = copy.deepcopy(existing)
            for name in fields:
                new[name] = _resolve(existing.get(name), data[name])
        else:
            new = {key: _resolve(None, value) for key, value in data.items()}
        self._client.docs[self.path] = new

    def delete(self) -> None:
        self._client.calls.append(("delete", self.path))
        self._client.docs.pop(self.path, None)


class FakeQuery:
    def __init__(
        self,
        client: "FakeFirestoreClient",
        path: str,
        filters: tuple[FakeFieldFilter, ...] = (),
        orders: tuple[tuple[str, str], ...] = (),
        limit_n: Optional[int] = None,
    ) -> None:
        self._client, self._path, self._filters, self._orders, self._limit = client, path, filters, orders, limit_n

    def where(self, *args: Any, filter: Optional[FakeFieldFilter] = None) -> "FakeQuery":
        assert not args and isinstance(filter, FakeFieldFilter), "use where(filter=FieldFilter(...))"
        assert filter.op_string in _OPS, filter.op_string
        return FakeQuery(self._client, self._path, self._filters + (filter,), self._orders, self._limit)

    def order_by(self, field_path: str, direction: str = "ASCENDING") -> "FakeQuery":
        assert direction in ("ASCENDING", "DESCENDING")
        return FakeQuery(self._client, self._path, self._filters, self._orders + ((field_path, direction),), self._limit)

    def limit(self, count: int) -> "FakeQuery":
        assert count > 0, "Firestore rejects limit(0)"
        return FakeQuery(self._client, self._path, self._filters, self._orders, count)

    def stream(self) -> list[FakeSnapshot]:
        self._client.calls.append(("query", self._path, self._filters, self._orders, self._limit))
        depth = len(self._path.split("/")) + 1
        rows = []
        for path, doc in self._client.docs.items():
            if not path.startswith(self._path + "/") or len(path.split("/")) != depth:
                continue
            ok = True
            for f in self._filters:
                actual = _lookup(doc, f.field_path)
                try:
                    ok = actual is not _MISSING and bool(_OPS[f.op_string](actual, f.value))
                except TypeError:
                    ok = False
                if not ok:
                    break
            if ok:
                rows.append(FakeSnapshot(path.rsplit("/", 1)[-1], doc))
        for name, direction in reversed(self._orders):
            rows = [r for r in rows if _lookup(r._data or {}, name) is not _MISSING]
            rows.sort(key=lambda r: _lookup(r._data or {}, name), reverse=direction == "DESCENDING")
        return rows[: self._limit] if self._limit is not None else rows


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[Any, ...]] = []

    def document(self, path: str) -> FakeDocumentRef:
        return FakeDocumentRef(self, path)

    def collection(self, path: str) -> FakeQuery:
        assert len(path.split("/")) % 2 == 1, path
        return FakeQuery(self, path)


# ---------------------------------------------------------------------------- Storage
class FakeBlob:
    def __init__(self, bucket: "FakeBucket", name: str) -> None:
        self._bucket, self.name = bucket, name

    def upload_from_string(self, data: bytes, content_type: str = "") -> None:
        self._bucket.objects[self.name] = (bytes(data), content_type)

    def download_as_bytes(self) -> bytes:
        if self.name not in self._bucket.objects:
            raise FakeNotFound(self.name)
        return self._bucket.objects[self.name][0]

    def delete(self) -> None:
        if self.name not in self._bucket.objects:
            raise FakeNotFound(self.name)
        del self._bucket.objects[self.name]

    def exists(self) -> bool:
        return self.name in self._bucket.objects


class FakeBucket:
    def __init__(self, name: str = "petpulse-test.firebasestorage.app") -> None:
        self.name = name
        self.objects: dict[str, tuple[bytes, str]] = {}

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)


# ---------------------------------------------------------------------------- firebase_admin
class FakeFirebaseError(Exception):
    pass


class InvalidIdTokenError(FakeFirebaseError):
    pass


class ExpiredIdTokenError(InvalidIdTokenError):
    pass


class CertificateFetchError(FakeFirebaseError):
    pass


@dataclass
class FakeFirebase:
    """Handles to what the fake SDK was asked to do."""

    tokens: dict[str, Any] = field(default_factory=dict)  # token -> claims dict, or an exception to raise
    client: FakeFirestoreClient = field(default_factory=FakeFirestoreClient)
    bucket: FakeBucket = field(default_factory=FakeBucket)
    apps: list[dict[str, Any]] = field(default_factory=list)
    verify_calls: list[dict[str, Any]] = field(default_factory=list)

    def verify_id_token(self, token: str, app: Any = None, check_revoked: bool = False) -> dict[str, Any]:
        self.verify_calls.append({"token": token, "app": app, "check_revoked": check_revoked})
        if not isinstance(token, str) or not token:
            raise ValueError("Illegal ID token provided")
        outcome = self.tokens.get(token)
        if outcome is None:
            raise InvalidIdTokenError("Could not verify token signature")
        if isinstance(outcome, BaseException):
            raise outcome
        claims = dict(outcome)
        claims.setdefault("uid", claims.get("sub"))
        return claims


def install(monkeypatch: pytest.MonkeyPatch, fake: Optional[FakeFirebase] = None) -> FakeFirebase:
    fake = fake or FakeFirebase()

    root = types.ModuleType("firebase_admin")
    auth = types.ModuleType("firebase_admin.auth")
    credentials = types.ModuleType("firebase_admin.credentials")
    firestore = types.ModuleType("firebase_admin.firestore")
    storage = types.ModuleType("firebase_admin.storage")
    gfirestore = types.ModuleType("google.cloud.firestore")

    def initialize_app(credential: Any = None, options: Optional[dict[str, Any]] = None, name: str = "[DEFAULT]") -> Any:
        app = types.SimpleNamespace(name=name, credential=credential, options=dict(options or {}))
        fake.apps.append({"name": name, "credential": credential, "options": dict(options or {}), "app": app})
        return app

    root.initialize_app = initialize_app  # type: ignore[attr-defined]
    root.delete_app = lambda app: None  # type: ignore[attr-defined]
    for attr, module in (("auth", auth), ("credentials", credentials), ("firestore", firestore), ("storage", storage)):
        setattr(root, attr, module)
    auth.verify_id_token = fake.verify_id_token  # type: ignore[attr-defined]
    auth.InvalidIdTokenError = InvalidIdTokenError  # type: ignore[attr-defined]
    auth.ExpiredIdTokenError = ExpiredIdTokenError  # type: ignore[attr-defined]
    auth.CertificateFetchError = CertificateFetchError  # type: ignore[attr-defined]
    credentials.Certificate = lambda info: ("certificate", dict(info))  # type: ignore[attr-defined]
    firestore.client = lambda app=None: fake.client  # type: ignore[attr-defined]
    storage.bucket = lambda name=None, app=None: fake.bucket  # type: ignore[attr-defined]
    gfirestore.ArrayUnion = FakeArrayUnion  # type: ignore[attr-defined]
    gfirestore.FieldFilter = FakeFieldFilter  # type: ignore[attr-defined]

    for name, module in {
        "firebase_admin": root,
        "firebase_admin.auth": auth,
        "firebase_admin.credentials": credentials,
        "firebase_admin.firestore": firestore,
        "firebase_admin.storage": storage,
        "google.cloud.firestore": gfirestore,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return fake
