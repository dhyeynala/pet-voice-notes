"""The frozen note eval runs end to end on the fake provider.

This fails on pipeline or schema breaks only (a case that errors, a stored note that is not
the contract shape, cases and gold out of step). Extraction quality is not asserted here: the
fake is a keyword stand-in, and the report says so.
"""

from __future__ import annotations

import asyncio

from evals.run_eval import CASES, GOLD, evaluate, read_jsonl, report
from evals.score_notes import SCORER_VERSION, summarize
from petpulse.providers.llm import FakeLLM
from petpulse.services.notes import Note


def test_cases_and_gold_are_in_step():
    cases, gold = read_jsonl(CASES), read_jsonl(GOLD)
    assert [c["id"] for c in cases] == [g["id"] for g in gold] and len(cases) >= 30
    assert len({c["id"] for c in cases}) == len(cases)
    categories = {c["category"] for c in cases}
    assert {"routine", "medical", "mixed", "red_flag", "negated", "ambiguous", "injection", "hard"} <= categories


def test_fake_eval_runs_every_case_through_the_pipeline():
    scores, outputs = asyncio.run(evaluate(FakeLLM()))
    assert len(scores) == len(read_jsonl(CASES))
    for output in outputs:
        Note.model_validate({k: v for k, v in output.items() if k != "category"})
        assert output["status"] == "processed"
    summary = summarize(scores)
    assert summary["scorer_version"] == SCORER_VERSION and summary["unprocessed"] == f"0/{len(scores)}"
    assert report("fake", scores).startswith("PIPELINE TEST, not a model evaluation")
