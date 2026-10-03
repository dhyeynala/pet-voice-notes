"""PDF summary with page citations (review M12). Callable by the records router (Track B).

- Text is passed per page. Less than ``MIN_TEXT_CHARS`` overall means a scanned or empty
  document: ``needs_ocr``, and no provider call (no fluent summary of nothing).
- Pages are included whole, in order, until ``PAGE_BUDGET_CHARS``; the prompt says how many
  pages were left out. No silent ``text[:12000]`` cut mid-sentence.
- ``pdf_summary.v1`` runs at temperature 0. Code rejects citations to pages that were not sent.
- On failure the result is ``summary_failed`` with no placeholder text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

from petpulse.llm.client import LLMClient, LLMFailure, TaskSpec, provider_mode
from petpulse.llm.schemas import PdfItem, PdfMedication, PdfSummary
from petpulse.providers.llm import LLMProvider
from petpulse.store.base import Store

PDF_TASK: TaskSpec[PdfSummary] = TaskSpec("pdf_summary", 1, PdfSummary)
MIN_TEXT_CHARS = 200
# Conservative character budget for whole pages (the live smoke test documents real token use).
PAGE_BUDGET_CHARS = 40_000
PdfStatus = Literal["summarized", "needs_ocr", "summary_failed"]
Mode = Literal["demo", "live"]


@dataclass
class PdfResult:
    status: PdfStatus
    summary: Optional[PdfSummary]
    pages_total: int
    pages_included: int
    mode: Mode
    failure_reason: Optional[str] = None
    call_ids: list[str] = field(default_factory=list)


def select_pages(pages: Sequence[str], budget: int = PAGE_BUDGET_CHARS) -> list[str]:
    """Whole pages in order while they fit the budget (always at least the first page)."""
    chosen: list[str] = []
    used = 0
    for text in pages:
        if chosen and used + len(text) > budget:
            break
        chosen.append(text if len(text) <= budget else text[:budget])
        used += len(text)
    return chosen


def page_problems(summary: PdfSummary, page_count: int) -> list[str]:
    problems = []
    groups: tuple[tuple[str, Sequence[PdfItem | PdfMedication]], ...] = (
        ("findings", summary.findings),
        ("medications", summary.medications),
        ("follow_ups", summary.follow_ups),
    )
    for where, items in groups:
        for index, item in enumerate(items):
            bad = [p for p in item.pages if not 1 <= p <= page_count]
            if bad:
                problems.append(f"{where}.{index}.pages: {bad} not in 1..{page_count}")
    return problems


async def summarize_pdf(
    pages: Sequence[str], *, pet_id: str, uid: str, store: Optional[Store], llm: LLMProvider, record_id: Optional[str] = None
) -> PdfResult:
    mode = provider_mode(llm)
    total = len(pages)
    if sum(len(p.strip()) for p in pages) < MIN_TEXT_CHARS:
        return PdfResult("needs_ocr", None, total, 0, mode)
    included = select_pages(pages)
    omitted = total - len(included)
    document = "\n\n".join(f"[P{n}]\n{text.strip()}" for n, text in enumerate(included, start=1))
    client = LLMClient(llm, store, meta={"pet_id": pet_id, "uid": uid, "feature": "pdf_summary", "record_id": record_id})
    try:
        result = await client.run(
            PDF_TASK,
            {
                "document": document,
                "page_count": str(len(included)),
                "omitted_note": f" {omitted} later pages were left out because of length." if omitted else "",
            },
            check=lambda value: page_problems(value, len(included)),
        )
    except LLMFailure as failure:
        return PdfResult("summary_failed", None, total, len(included), mode, failure.reason, failure.call_ids)
    return PdfResult("summarized", result.value, total, len(included), result.mode, None, result.call_ids)
