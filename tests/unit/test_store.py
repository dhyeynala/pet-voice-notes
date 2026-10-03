"""MemoryStore / JsonFileStore behaviour (the ``Store`` contract)."""

from __future__ import annotations

import json

import pytest

from petpulse.store import ArrayUnion, JsonFileStore, MemoryStore, NotFound, Store


@pytest.fixture(params=["memory", "json"])
def any_store(request, tmp_path):
    if request.param == "memory":
        return MemoryStore()
    return JsonFileStore(tmp_path / "db.json")


def test_implements_protocol(any_store):
    assert isinstance(any_store, Store)


def test_get_missing_returns_none(any_store):
    assert any_store.get("pets/nope") is None


def test_set_replace_and_merge(any_store):
    any_store.set("pets/p1", {"name": "Max", "age": 6})
    any_store.set("pets/p1", {"age": 7}, merge=True)
    assert any_store.get("pets/p1") == {"name": "Max", "age": 7}
    any_store.set("pets/p1", {"name": "Luna"})
    assert any_store.get("pets/p1") == {"name": "Luna"}


def test_update_requires_existing_document(any_store):
    with pytest.raises(NotFound):
        any_store.update("pets/p1", {"age": 1})
    any_store.set("pets/p1", {"name": "Max"})
    any_store.update("pets/p1", {"age": 1})
    assert any_store.get("pets/p1") == {"name": "Max", "age": 1}


def test_add_generates_unique_ids_in_subcollections(any_store):
    a = any_store.add("pets/p1/analytics", {"category": "diet"})
    b = any_store.add("pets/p1/analytics", {"category": "diet"})
    assert a != b
    assert any_store.get(f"pets/p1/analytics/{a}") == {"category": "diet"}
    assert any_store.query("pets/p2/analytics") == []


def test_returned_documents_are_copies(any_store):
    any_store.set("pets/p1", {"tags": ["a"]})
    doc = any_store.get("pets/p1")
    doc["tags"].append("b")
    assert any_store.get("pets/p1") == {"tags": ["a"]}
    _, row = any_store.query("pets")[0]
    row["tags"].append("c")
    assert any_store.get("pets/p1") == {"tags": ["a"]}


def test_query_operators(any_store):
    any_store.set("e/1", {"cat": "diet", "ts": "2026-10-01T08:00:00", "n": 1, "owners": ["alice"]})
    any_store.set("e/2", {"cat": "diet", "ts": "2026-10-02T08:00:00", "n": 2, "owners": ["bob"]})
    any_store.set("e/3", {"cat": "sleep", "ts": "2026-10-03T08:00:00", "n": "x", "owners": ["alice", "bob"]})
    any_store.set("e/4", {"cat": "diet"})  # no ts / n / owners

    def ids(**kw):
        return sorted(doc_id for doc_id, _ in any_store.query("e", **kw))

    assert ids(where=[("cat", "==", "diet")]) == ["1", "2", "4"]
    assert ids(where=[("cat", "==", "diet"), ("ts", ">=", "2026-10-02")]) == ["2"]
    assert ids(where=[("ts", "<=", "2026-10-02T23:59:59")]) == ["1", "2"]
    assert ids(where=[("ts", "<", "2026-10-02"), ("ts", ">", "2026-09-30")]) == ["1"]
    assert ids(where=[("owners", "array_contains", "alice")]) == ["1", "3"]
    assert ids(where=[("cat", "in", ["sleep"])]) == ["3"]
    assert ids(where=[("cat", "!=", "diet")]) == ["3"]
    # mismatched types never match (no TypeError), missing fields never match
    assert ids(where=[("n", ">", 0)]) == ["1", "2"]


def test_query_order_and_limit(any_store):
    for i, ts in enumerate(["2026-10-03", "2026-10-01", "2026-10-02"]):
        any_store.set(f"e/{i}", {"ts": ts})
    any_store.set("e/x", {"other": True})
    asc = [doc["ts"] for _, doc in any_store.query("e", order_by=[("ts", "asc")])]
    assert asc == ["2026-10-01", "2026-10-02", "2026-10-03"]
    top = any_store.query("e", order_by=[("ts", "desc")], limit=2)
    assert [doc["ts"] for _, doc in top] == ["2026-10-03", "2026-10-02"]


def test_unknown_operator_rejected(any_store):
    any_store.set("e/1", {"a": 1})
    with pytest.raises(ValueError):
        any_store.query("e", where=[("a", "~=", 1)])  # type: ignore[list-item]


def test_array_union_transform(any_store):
    any_store.set("users/u1", {"pets": ArrayUnion(["max"])}, merge=True)
    any_store.set("users/u1", {"pets": ArrayUnion(["max", "luna"])}, merge=True)
    assert any_store.get("users/u1") == {"pets": ["max", "luna"]}


def test_delete(any_store):
    any_store.set("pets/p1", {"a": 1})
    any_store.delete("pets/p1")
    any_store.delete("pets/p1")  # idempotent
    assert any_store.get("pets/p1") is None


@pytest.mark.parametrize("bad", ["", "pets", "pets/../x", "pets/./x", "pets/p1/notes"])
def test_document_paths_are_validated(any_store, bad):
    with pytest.raises(ValueError):
        any_store.set(bad, {"a": 1})


def test_collection_paths_are_validated(any_store):
    with pytest.raises(ValueError):
        any_store.add("pets/p1", {"a": 1})
    with pytest.raises(ValueError):
        any_store.query("pets/p1")


def test_non_json_values_rejected(any_store):
    with pytest.raises(TypeError):
        any_store.set("pets/p1", {"when": object()})
    assert any_store.get("pets/p1") is None


def test_json_store_persists_atomically(tmp_path):
    path = tmp_path / "nested" / "db.json"
    s1 = JsonFileStore(path)
    doc_id = s1.add("pets/p1/notes", {"text": "walked"})
    s1.set("pets/p1", {"name": "Max"})

    payload = json.loads(path.read_text())
    assert payload["format_version"] == 1
    assert sorted(p.name for p in path.parent.iterdir()) == ["db.json"]  # no temp files left

    s2 = JsonFileStore(path)
    assert s2.get("pets/p1") == {"name": "Max"}
    assert s2.get(f"pets/p1/notes/{doc_id}") == {"text": "walked"}


def test_json_store_rejects_foreign_file(tmp_path):
    path = tmp_path / "db.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(ValueError):
        JsonFileStore(path)


def test_memory_store_snapshot_and_clear():
    s = MemoryStore({"pets": {"p1": {"name": "Max"}}})
    assert s.collections() == ["pets"]
    assert s.snapshot() == {"pets": {"p1": {"name": "Max"}}}
    s.clear()
    assert s.get("pets/p1") is None
