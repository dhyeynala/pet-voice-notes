# pdf_parser.py
"""PDF text extraction and the (legacy-prompt) record summary.

Used by ``petpulse.routers.records`` until the LLM track's PDF service replaces it. PDFs are
opened from memory only: nothing is written to a client-chosen path (review C3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import pymupdf

from petpulse.deps import get_llm
from petpulse.providers.llm import LegacyTask

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


class PdfError(ValueError):
    """The bytes are not a readable PDF (corrupt, encrypted, or over the page limit)."""


@dataclass(frozen=True)
class PdfText:
    text: str
    pages: int


def extract_pdf_text(data: bytes, max_pages: int) -> PdfText:
    """Open ``data`` in memory with PyMuPDF and return its text and page count."""
    try:
        # PyMuPDF's Document is only partially annotated; treat it as Any.
        doc: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except (RuntimeError, ValueError) as exc:  # pymupdf.FileDataError is a RuntimeError
        raise PdfError("file is not a readable PDF") from exc
    try:
        if doc.needs_pass:
            raise PdfError("encrypted PDFs are not supported")
        pages = doc.page_count
        if pages < 1:
            raise PdfError("PDF has no pages")
        if pages > max_pages:
            raise PdfError(f"PDF has {pages} pages; the limit is {max_pages}")
        try:
            text = "\n".join(str(page.get_text()) for page in doc)
        except (RuntimeError, ValueError) as exc:
            raise PdfError("could not read the PDF's text") from exc
    finally:
        doc.close()
    return PdfText(text=text, pages=pages)


def summarize_pdf_text(text: str) -> Optional[str]:
    """Summarize extracted record text. Returns ``None`` when no summary could be generated.

    A failure is reported as ``None`` (the caller marks the record), never stored as if it
    were a summary (review H2/M12).
    """
    if not text.strip():
        return None
    try:
        response = get_llm().legacy_chat(
            LegacyTask.PDF_SUMMARY,
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a veterinary assistant AI. Summarize this medical document. "
                        "Extract key points like symptoms, diagnosis, treatments, medications, and vet advice. "
                        "Keep it concise and useful for a pet health timeline."
                    ),
                },
                {"role": "user", "content": text[:12000]},
            ],
            temperature=0.5,
        )
        content = response.choices[0].message.content
    except Exception:  # provider outage, timeout, unsupported task: no summary, no fake text
        logger.exception("PDF summary failed")
        return None
    summary = content.strip() if isinstance(content, str) else ""
    return summary or None
