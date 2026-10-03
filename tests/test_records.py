"""PDF records (review C3): safe upload, private storage, owner-only download."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from petpulse.auth import issue_token


def as_user(uid: str) -> dict[str, str]:
    """Real demo-token headers for ``uid`` (overrides the ``client`` fixture's alice token)."""
    return {"Authorization": f"Bearer {issue_token(uid)}"}


RECORD_KEYS = {"id", "pet_id", "filename", "pages", "summary", "status", "created_at"}
BLOB_KEY = re.compile(r"^pets/[A-Za-z0-9_-]+/records/[0-9a-f]{32}\.pdf$")


def make_pdf(text: str = "Apoquel 16 mg daily. Recheck in 2 weeks.", pages: int = 1) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data: bytes = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pets(make_pet):
    """Alice's Max and Bob's Max: distinct uuid4 pets (C2)."""
    return make_pet("alice", "Max"), make_pet("bob", "Max")


@pytest.fixture
def alice_pet(pets):
    return pets[0]


@pytest.fixture
def bob_pet(pets):
    return pets[1]


def upload(client, pet_id, data, filename="visit.pdf", uid="alice", content_type="application/pdf"):
    return client.post(
        f"/api/pets/{pet_id}/records",
        files={"file": (filename, data, content_type)},
        headers=as_user(uid),
    )


def all_files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()} if root.exists() else set()


def test_upload_stores_private_blob_and_returns_record(client, store, blobs, alice_pet):
    response = upload(client, alice_pet, make_pdf())
    assert response.status_code == 201, response.text
    record = response.json()
    assert set(record) == RECORD_KEYS
    assert record["pet_id"] == alice_pet and record["filename"] == "visit.pdf"
    assert record["pages"] == 1 and record["status"] == "summarized"
    assert "Apoquel 16 mg daily" in record["summary"]

    stored = store.get(f"pets/{alice_pet}/records/{record['id']}")
    assert BLOB_KEY.match(stored["blob_key"]) and stored["blob_key"].startswith(f"pets/{alice_pet}/records/")
    assert blobs.exists(stored["blob_key"])


@pytest.mark.parametrize(
    "filename",
    ["../../../../evil.pdf", "..\\..\\evil.pdf", "/etc/cron.d/evil.pdf", "records/../../evil.pdf"],
)
def test_upload_filename_is_display_only_and_cannot_traverse(client, store, blobs, alice_pet, tmp_path, filename):
    before = all_files(tmp_path)
    response = upload(client, alice_pet, make_pdf(), filename=filename)
    assert response.status_code == 201, response.text
    assert response.json()["filename"] == "evil.pdf"

    stored = store.get(f"pets/{alice_pet}/records/{response.json()['id']}")
    assert BLOB_KEY.match(stored["blob_key"]) and "evil" not in stored["blob_key"]
    # Exactly one new file, and it is inside the blob root.
    new_files = all_files(tmp_path) - before
    assert len(new_files) == 1
    [new_file] = new_files
    assert blobs.root in new_file.resolve().parents
    assert not list(tmp_path.rglob("evil.pdf"))


def test_display_filename_is_sanitised_and_bounded():
    from petpulse.routers.records import MAX_DISPLAY_NAME, display_filename

    assert display_filename(None) == "document.pdf"
    assert display_filename("..") == "document.pdf"
    assert display_filename("a\x00b\r\n.pdf") == "ab.pdf"
    long_name = display_filename("x" * 500 + ".pdf")
    assert len(long_name) == MAX_DISPLAY_NAME and long_name.endswith(".pdf")


@pytest.mark.parametrize(
    "data, content_type",
    [
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "application/pdf"),  # lies about its type
        (b"<html><script>alert(1)</script></html>", "application/pdf"),
        (b"", "application/pdf"),
        (b"  %PDF-1.4 magic not at the start", "application/pdf"),
    ],
)
def test_non_pdf_is_rejected_with_415_and_nothing_is_stored(client, store, blobs, alice_pet, data, content_type):
    response = upload(client, alice_pet, data, content_type=content_type)
    assert response.status_code == 415
    assert store.query(f"pets/{alice_pet}/records") == []
    assert all_files(blobs.root) == set()


def test_too_large_is_rejected_with_413(client, store, blobs, alice_pet):
    from petpulse.routers.records import MAX_PDF_BYTES

    data = b"%PDF-1.4\n" + b"0" * (MAX_PDF_BYTES + 1 - len(b"%PDF-1.4\n"))
    assert len(data) == MAX_PDF_BYTES + 1
    response = upload(client, alice_pet, data)
    assert response.status_code == 413
    assert store.query(f"pets/{alice_pet}/records") == []
    assert all_files(blobs.root) == set()


def test_oversized_body_is_refused_before_parsing(client, alice_pet, monkeypatch):
    from petpulse.routers import records

    monkeypatch.setattr(records, "MAX_PDF_BYTES", 1024)
    monkeypatch.setattr(records, "_MULTIPART_OVERHEAD", 512)

    def must_not_parse(*_args, **_kwargs):
        raise AssertionError("body should not be parsed")

    monkeypatch.setattr(records, "read_capped", must_not_parse)
    response = upload(client, alice_pet, b"%PDF-" + b"0" * 4096)
    assert response.status_code == 413


def test_read_capped_reads_at_most_cap_plus_one_bytes():
    import asyncio

    from fastapi import HTTPException

    from petpulse.routers.records import read_capped

    class FakeUpload:
        def __init__(self) -> None:
            self.requested: list[int] = []

        async def read(self, size: int = -1) -> bytes:
            self.requested.append(size)
            return b"x" * size

    fake = FakeUpload()
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(read_capped(fake, cap=10))  # type: ignore[arg-type]
    assert excinfo.value.status_code == 413 and fake.requested == [11]


def test_upload_at_the_cap_is_accepted(alice_pet, store, blobs, monkeypatch):
    from petpulse.routers import records

    data = make_pdf()
    monkeypatch.setattr(records, "MAX_PDF_BYTES", len(data))
    record = asyncio.run(records.create_record(store, blobs, alice_pet, data, "visit.pdf"))
    assert record["status"] == "summarized"


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7\n this is not really a pdf \n%%EOF",
        b"%PDF-" + bytes(range(256)) * 8,
    ],
)
def test_corrupt_pdf_is_rejected_with_422(client, store, blobs, alice_pet, data):
    response = upload(client, alice_pet, data)
    assert response.status_code == 422
    assert store.query(f"pets/{alice_pet}/records") == []
    assert all_files(blobs.root) == set()


def test_pdf_over_page_limit_is_rejected_with_422(client, store, alice_pet):
    from petpulse.routers.records import MAX_PDF_PAGES

    response = upload(client, alice_pet, make_pdf("page", pages=MAX_PDF_PAGES + 1))
    assert response.status_code == 422 and str(MAX_PDF_PAGES) in response.json()["detail"]
    assert upload(client, alice_pet, make_pdf("page", pages=MAX_PDF_PAGES)).status_code == 201


def test_encrypted_pdf_is_rejected_with_422(client, alice_pet):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    assert upload(client, alice_pet, data).status_code == 422


def test_missing_file_field_is_422(client, alice_pet):
    response = client.post(f"/api/pets/{alice_pet}/records", data={"x": "1"}, headers=as_user("alice"))
    assert response.status_code == 422


def test_scanned_pdf_without_text_is_flagged_not_summarized(client, fake_llm, alice_pet):
    record = upload(client, alice_pet, make_pdf(text="")).json()
    assert record["status"] == "no_text" and record["summary"] is None
    assert not [c for c in fake_llm.calls if "pdf" in c["task"]]


def test_summary_outage_is_reported_not_stored_as_text(client, store, fake_llm, alice_pet):
    fake_llm.fail = True
    record = upload(client, alice_pet, make_pdf()).json()
    assert record["status"] == "summary_failed" and record["summary"] is None
    assert store.get(f"pets/{alice_pet}/records/{record['id']}")["summary"] is None


def test_record_is_never_public(client, anon_client, store, blobs, alice_pet):
    import api_server

    response = upload(client, alice_pet, make_pdf())
    body = response.json()
    assert not any("url" in key.lower() for key in body)
    stored = store.get(f"pets/{alice_pet}/records/{body['id']}")
    assert not any("url" in key.lower() or "public" in key.lower() for key in stored)

    blob_path = blobs.root / stored["blob_key"]
    assert blob_path.is_file()
    assert api_server.PUBLIC_DIR.resolve() not in blob_path.resolve().parents
    # Neither the blob key nor the data dir is reachable through the static mount.
    assert client.get(f"/{stored['blob_key']}").status_code == 404
    assert client.get(f"/data/blobs/{stored['blob_key']}").status_code == 404
    # The only way to the bytes is the authenticated download route.
    assert anon_client.get(f"/api/pets/{alice_pet}/records/{body['id']}/file").status_code == 401


def test_owner_can_download_the_original(client, alice_pet):
    data = make_pdf()
    record = upload(client, alice_pet, data, filename="visit 2026.pdf").json()
    response = client.get(f"/api/pets/{alice_pet}/records/{record['id']}/file", headers=as_user("alice"))
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="visit 2026.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_other_user_cannot_download_or_list(client, alice_pet, bob_pet):
    record = upload(client, alice_pet, make_pdf()).json()
    # Bob on Alice's pet: 404 (ids can't be probed).
    assert client.get(f"/api/pets/{alice_pet}/records/{record['id']}/file", headers=as_user("bob")).status_code == 404
    assert client.get(f"/api/pets/{alice_pet}/records", headers=as_user("bob")).status_code == 404
    # Bob on his own pet with Alice's record id: still 404 (the record must belong to the pet).
    assert client.get(f"/api/pets/{bob_pet}/records/{record['id']}/file", headers=as_user("bob")).status_code == 404
    # Bob cannot upload to Alice's pet either.
    assert upload(client, alice_pet, make_pdf(), uid="bob").status_code == 404


def test_record_pointing_outside_its_pet_is_not_served(client, store, alice_pet, bob_pet):
    bob_record = upload(client, bob_pet, make_pdf(), uid="bob").json()
    bob_key = store.get(f"pets/{bob_pet}/records/{bob_record['id']}")["blob_key"]
    store.set(f"pets/{alice_pet}/records/forged", {"blob_key": bob_key, "filename": "x.pdf"})
    assert client.get(f"/api/pets/{alice_pet}/records/forged/file", headers=as_user("alice")).status_code == 404


@pytest.mark.parametrize("record_id", ["..", "nope", "a.b", "x" * 65])
def test_unknown_or_malformed_record_id_is_404(client, alice_pet, record_id):
    assert client.get(f"/api/pets/{alice_pet}/records/{record_id}/file", headers=as_user("alice")).status_code == 404


def test_requests_without_credentials_are_401(anon_client, alice_pet):
    assert anon_client.get(f"/api/pets/{alice_pet}/records").status_code == 401
    response = anon_client.post(f"/api/pets/{alice_pet}/records", files={"file": ("a.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 401


def test_list_records_newest_first_including_legacy_rows(client, store, alice_pet):
    store.set(
        f"pets/{alice_pet}/records/legacy1",
        {"summary": "old", "file_name": "old.pdf", "file_url": None, "timestamp": "2025-01-01T00:00:00"},
    )
    new = upload(client, alice_pet, make_pdf()).json()
    records = client.get(f"/api/pets/{alice_pet}/records", headers=as_user("alice")).json()
    assert [r["id"] for r in records] == [new["id"], "legacy1"]
    assert all(set(r) == RECORD_KEYS for r in records)
    assert records[1] == {
        "id": "legacy1",
        "pet_id": alice_pet,
        "filename": "old.pdf",
        "pages": None,
        "summary": "old",
        "status": "summarized",
        "created_at": "2025-01-01T00:00:00",
    }


def test_legacy_upload_route_delegates_to_the_safe_path(client_as, store, make_pet):
    pet_id = make_pet("alice", "Max")
    client = client_as("alice")
    bad = client.post(
        "/api/upload_pdf", data={"uid": "alice", "pet": pet_id}, files={"file": ("x.pdf", b"not a pdf", "application/pdf")}
    )
    assert bad.status_code == 415
    missing = client.post(
        "/api/upload_pdf",
        data={"uid": "alice", "pet": "no-such-pet"},
        files={"file": ("x.pdf", make_pdf(), "application/pdf")},
    )
    assert missing.status_code == 404
    assert store.query(f"pets/{pet_id}/records") == []
