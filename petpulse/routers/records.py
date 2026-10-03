"""Vet-record PDF uploads (review C3): upload, list and owner-only download.

- The upload is read into memory with a hard cap (``MAX_PDF_BYTES + 1`` bytes at most; 413
  above the cap), must start with the ``%PDF-`` magic bytes (415) and must open in PyMuPDF
  from memory with at most ``MAX_PDF_PAGES`` pages (422).
- The bytes are stored in the private blob store under a server-generated key
  ``pets/<pet>/records/<uuid>.pdf``. The client filename is kept for display only
  (basename, at most 120 characters) and never touches the filesystem.
- There is no public URL. ``GET .../records/{record_id}/file`` checks pet ownership and that
  the record belongs to that pet, then returns the bytes.

The summary comes from ``petpulse.services.pdf`` (``pdf_summary.v1``: whole pages, page
citations checked by code, temperature 0). The structured result (findings, medications and
follow-ups with their pages) is stored on the record as ``summary_detail``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.datastructures import UploadFile  # fastapi.UploadFile subclasses this

from pdf_parser import PDF_MAGIC, PdfError, extract_pdf_text
from petpulse.auth import current_user, require_pet_access
from petpulse.deps import get_blobs, get_llm, get_store
from petpulse.providers.llm import LLMProvider
from petpulse.services.pdf import summarize_pdf
from petpulse.store.base import Store
from petpulse.store.blobs import BlobStore, new_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["records"])

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 50
MAX_DISPLAY_NAME = 120
# Multipart framing around the file part; a Content-Length above cap + this is refused early.
_MULTIPART_OVERHEAD = 64 * 1024
_RECORD_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

RecordStatus = Literal["summarized", "no_text", "summary_failed"]


class Record(BaseModel):
    id: str
    pet_id: str
    filename: str
    pages: Optional[int]
    summary: Optional[str]
    status: str
    created_at: str


def display_filename(raw: Optional[str]) -> str:
    """A display-only name: last path component, no control characters, at most 120 chars."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip().strip(".")
    if not name:
        return "document.pdf"
    if len(name) > MAX_DISPLAY_NAME:
        stem, dot, ext = name.rpartition(".")
        keep = f".{ext}" if dot and len(ext) <= 8 else ""
        name = name[: MAX_DISPLAY_NAME - len(keep)] + keep
    return name


async def read_capped(upload: UploadFile, cap: Optional[int] = None) -> bytes:
    """Read at most ``cap + 1`` bytes; 413 if the upload is larger than ``cap``."""
    limit = MAX_PDF_BYTES if cap is None else cap
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"file too large; the limit is {limit // (1024 * 1024)} MB")
    return data


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _to_record(record_id: str, pet_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Shape a stored record (new or legacy ``store_pdf_summary`` row) as a ``Record``."""
    pages = doc.get("pages")
    return {
        "id": record_id,
        "pet_id": pet_id,
        "filename": str(doc.get("filename") or doc.get("file_name") or "document.pdf"),
        "pages": pages if isinstance(pages, int) else None,
        "summary": doc.get("summary") if isinstance(doc.get("summary"), str) else None,
        "status": str(doc.get("status") or "summarized"),
        "created_at": str(doc.get("created_at") or doc.get("timestamp") or ""),
    }


async def create_record(
    store: Store,
    blobs: BlobStore,
    pet_id: str,
    data: bytes,
    filename: Optional[str],
    *,
    uid: str = "",
    llm: Optional[LLMProvider] = None,
) -> dict[str, Any]:
    """Validate, store and summarize one uploaded PDF. Returns the ``Record`` as a dict."""
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if not data.startswith(PDF_MAGIC):
        raise HTTPException(status_code=415, detail="only PDF files are accepted")
    try:
        parsed = extract_pdf_text(data, max_pages=MAX_PDF_PAGES)
    except PdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record_id = uuid.uuid4().hex
    blob_key = new_key("pets", pet_id, "records", suffix=".pdf")
    blobs.put(blob_key, data)

    # A scanned PDF (no text layer) is ``no_text`` without a provider call; OCR is out of scope.
    result = await summarize_pdf(
        parsed.page_texts or (parsed.text,),
        pet_id=pet_id,
        uid=uid,
        store=store,
        llm=llm if llm is not None else get_llm(),
        record_id=record_id,
    )
    status: RecordStatus = result.status
    summary = result.summary.summary if result.summary else None

    now = _utc_now_iso()
    doc: dict[str, Any] = {
        "pet_id": pet_id,
        "filename": display_filename(filename),
        "pages": parsed.pages,
        "summary": summary,
        "status": status,
        "created_at": now,
        "size_bytes": len(data),
        "blob_key": blob_key,
        "content_type": "application/pdf",
        "summary_detail": result.summary.model_dump() if result.summary else None,
        "summary_pages_included": result.pages_included,
        "summary_failure_reason": result.failure_reason,
        "summary_call_ids": result.call_ids,
        "summary_mode": result.mode,
        # Legacy readers (chat/RAG) read these names.
        "file_name": display_filename(filename),
        "timestamp": now,
    }
    try:
        store.set(f"pets/{pet_id}/records/{record_id}", doc)
    except Exception:
        blobs.delete(blob_key)
        raise
    return _to_record(record_id, pet_id, doc)


def create_record_sync(
    store: Store, blobs: BlobStore, pet_id: str, data: bytes, filename: Optional[str], **kwargs: Any
) -> dict[str, Any]:
    """``create_record`` for synchronous callers (the demo seed).

    Outside an event loop it simply runs the coroutine. Inside one (seeding at app startup) it
    must not block on a thread: the seed holds the store's batch lock. There it drives the
    coroutine inline, which works for providers that never suspend (the fake one, the only
    provider the seed uses) and raises otherwise.
    """
    coro = create_record(store, blobs, pet_id, data, filename, **kwargs)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    try:
        coro.send(None)
    except StopIteration as done:
        result: dict[str, Any] = done.value
        return result
    coro.close()
    raise RuntimeError("create_record_sync inside an event loop needs a non-suspending provider; await create_record")


def _reject_oversized_body(request: Request) -> None:
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_PDF_BYTES + _MULTIPART_OVERHEAD:
        raise HTTPException(status_code=413, detail="file too large")


@router.post(
    "/api/pets/{pet_id}/records",
    response_model=Record,
    status_code=201,
    dependencies=[Depends(require_pet_access)],
)
async def upload_record(
    pet_id: str,
    request: Request,
    user: Any = Depends(current_user),
    store: Store = Depends(get_store),
    blobs: BlobStore = Depends(get_blobs),
    llm: LLMProvider = Depends(get_llm),
) -> dict[str, Any]:
    """``multipart/form-data`` with one ``file`` part (a PDF)."""
    # The body is parsed here, after the ownership check, and only if it is not obviously too big.
    _reject_oversized_body(request)
    form = await request.form(max_files=1, max_fields=4)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(status_code=422, detail="multipart field 'file' is required")
        data = await read_capped(upload)
        return await create_record(store, blobs, pet_id, data, upload.filename, uid=str(user.uid), llm=llm)
    finally:
        await form.close()


@router.get(
    "/api/pets/{pet_id}/records",
    response_model=list[Record],
    dependencies=[Depends(require_pet_access)],
)
def list_records(pet_id: str, store: Store = Depends(get_store)) -> list[dict[str, Any]]:
    records = [_to_record(rid, pet_id, doc) for rid, doc in store.query(f"pets/{pet_id}/records")]
    records.sort(key=lambda r: str(r["created_at"]), reverse=True)
    return records


@router.get(
    "/api/pets/{pet_id}/records/{record_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    dependencies=[Depends(require_pet_access)],
)
def download_record(
    pet_id: str,
    record_id: str,
    store: Store = Depends(get_store),
    blobs: BlobStore = Depends(get_blobs),
) -> Response:
    """The original PDF, for an owner of the pet the record belongs to (404 otherwise)."""
    not_found = HTTPException(status_code=404, detail="record not found")
    if not _RECORD_ID.match(record_id):
        raise not_found
    doc = store.get(f"pets/{pet_id}/records/{record_id}")
    blob_key = doc.get("blob_key") if doc else None
    # The key must sit under this pet's prefix, so a record can never point at another pet's blob.
    if not isinstance(blob_key, str) or not blob_key.startswith(f"pets/{pet_id}/records/"):
        raise not_found
    try:
        with blobs.open(blob_key) as fh:
            data = fh.read()
    except (FileNotFoundError, ValueError):
        raise not_found from None
    filename = display_filename(str(doc.get("filename") if doc else "")).replace('"', "")
    ascii_name = filename.encode("ascii", "ignore").decode() or "document.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
