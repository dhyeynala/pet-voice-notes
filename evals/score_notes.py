"""Score note-extraction outputs against hand-written gold labels.

Everything is reported as counts with their denominator ("3/34"), never a bare percentage.
Bump ``SCORER_VERSION`` whenever a rule below changes, so old and new reports are not compared.

Flag rules (per case, per red flag):
- missed: the gold has the flag (any status), the prediction does not;
- invented: the prediction says present/ambiguous, the gold does not mention the flag;
- wrong_status: both have it, with different statuses;
- a predicted ``denied`` for a flag the gold does not mention is ignored (it changes nothing).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

SCORER_VERSION = "notes-1"


@dataclass
class CaseScore:
    id: str
    kind_ok: bool
    missed: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    wrong_status: list[str] = field(default_factory=list)
    urgent_fn: bool = False
    urgent_fp: bool = False
    review_fn: bool = False
    review_fp: bool = False
    unprocessed: bool = False

    @property
    def perfect(self) -> bool:
        return self.kind_ok and not (
            self.missed or self.invented or self.wrong_status or self.urgent_fn or self.urgent_fp or self.review_fn
        )


def score_case(gold: dict[str, Any], predicted: dict[str, Any]) -> CaseScore:
    pred_flags = {f["flag"]: f["status"] for f in predicted.get("red_flags", [])}
    gold_flags: dict[str, str] = gold["red_flags"]
    score = CaseScore(id=gold["id"], kind_ok=predicted.get("kind") == gold["kind"])
    for flag, status in sorted(gold_flags.items()):
        if flag not in pred_flags:
            score.missed.append(flag)
        elif pred_flags[flag] != status:
            score.wrong_status.append(f"{flag}:{pred_flags[flag]}!={status}")
    for flag, status in sorted(pred_flags.items()):
        if flag not in gold_flags and status in ("present", "ambiguous"):
            score.invented.append(flag)
    urgent, review = bool(predicted.get("urgent")), bool(predicted.get("needs_review"))
    score.urgent_fn, score.urgent_fp = gold["urgent"] and not urgent, urgent and not gold["urgent"]
    score.review_fn, score.review_fp = gold["needs_review"] and not review, review and not gold["needs_review"]
    score.unprocessed = predicted.get("status") == "unprocessed"
    return score


def summarize(scores: Iterable[CaseScore]) -> dict[str, Any]:
    rows = list(scores)
    n = len(rows)

    def frac(count: int, total: int = n) -> str:
        return f"{count}/{total}"

    return {
        "scorer_version": SCORER_VERSION,
        "cases": n,
        "kind_correct": frac(sum(r.kind_ok for r in rows)),
        "cases_with_missed_flag": frac(sum(bool(r.missed) for r in rows)),
        "cases_with_invented_flag": frac(sum(bool(r.invented) for r in rows)),
        "cases_with_wrong_flag_status": frac(sum(bool(r.wrong_status) for r in rows)),
        "urgent_false_negatives": frac(sum(r.urgent_fn for r in rows)),
        "urgent_false_positives": frac(sum(r.urgent_fp for r in rows)),
        "needs_review_false_negatives": frac(sum(r.review_fn for r in rows)),
        "needs_review_false_positives": frac(sum(r.review_fp for r in rows)),
        "unprocessed": frac(sum(r.unprocessed for r in rows)),
        "perfect_cases": frac(sum(r.perfect for r in rows)),
    }
