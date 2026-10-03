"""PDF text extraction, page by page (PyMuPDF, in memory).

Used by ``petpulse.routers.records``; the summary itself is ``petpulse.services.pdf``. PDFs are
opened from memory only: nothing is written to a client-chosen path (review C3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pymupdf

PDF_MAGIC = b"%PDF-"


class PdfError(ValueError):
    """The bytes are not a readable PDF (corrupt, encrypted, or over the page limit)."""


@dataclass(frozen=True)
class PdfText:
    text: str
    pages: int
    page_texts: tuple[str, ...] = ()  # per page, in order (the PDF summary cites pages)


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
            page_texts = tuple(str(page.get_text()) for page in doc)
        except (RuntimeError, ValueError) as exc:
            raise PdfError("could not read the PDF's text") from exc
    finally:
        doc.close()
    return PdfText(text="\n".join(page_texts), pages=pages, page_texts=page_texts)
