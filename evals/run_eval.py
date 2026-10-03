"""Run the frozen note-extraction cases through the real pipeline and score them.

    python -m evals.run_eval                    # fake provider (default): a PIPELINE TEST
    python -m evals.run_eval --provider openai --i-accept-cost   # live model, billed

With the fake provider this checks plumbing, schemas and the decision rules end to end; the
keyword rules are expected to miss the "hard" cases. It is not a model evaluation. A live run
needs OPENAI_API_KEY and the explicit cost flag, and calls the model once per case (plus at
most one repair each).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from evals.score_notes import CaseScore, score_case, summarize

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases" / "note_extract.jsonl"
GOLD = ROOT / "gold" / "note_extract.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_provider(name: str) -> Any:
    from petpulse.providers.llm import FakeLLM, OpenAILLM

    if name == "fake":
        return FakeLLM()
    from petpulse.config import Settings

    settings = Settings(llm_provider="openai")
    settings.check()
    assert settings.openai_api_key is not None
    return OpenAILLM(settings.openai_api_key.get_secret_value(), model=settings.openai_model)


async def evaluate(provider: Any) -> tuple[list[CaseScore], list[dict[str, Any]]]:
    from petpulse.services.notes import process_note
    from petpulse.store.memory import MemoryStore

    store = MemoryStore()
    gold = {row["id"]: row for row in read_jsonl(GOLD)}
    scores, outputs = [], []
    for case in read_jsonl(CASES):
        note = await process_note("eval-pet", "eval", case["text"], "text", "UTC", store=store, llm=provider)
        predicted = note.model_dump()
        outputs.append({"id": case["id"], "category": case["category"], **predicted})
        scores.append(score_case(gold[case["id"]], predicted))
    return scores, outputs


def report(provider: str, scores: Sequence[CaseScore]) -> str:
    header = (
        "PIPELINE TEST, not a model evaluation (fake keyword provider)"
        if provider == "fake"
        else "MODEL EVALUATION (live provider)"
    )
    lines = [header, json.dumps(summarize(scores), indent=2)]
    for s in scores:
        if not s.perfect:
            problems = [
                *(["kind"] if not s.kind_ok else []),
                *(f"missed:{f}" for f in s.missed),
                *(f"invented:{f}" for f in s.invented),
                *s.wrong_status,
                *(["urgent_fn"] if s.urgent_fn else []),
                *(["urgent_fp"] if s.urgent_fp else []),
                *(["review_fn"] if s.review_fn else []),
            ]
            lines.append(f"  {s.id}: {', '.join(problems)}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=["fake", "openai"], default="fake")
    parser.add_argument("--i-accept-cost", action="store_true", help="required for --provider openai")
    parser.add_argument("--out", type=Path, help="write per-case outputs and the summary as JSON")
    args = parser.parse_args(argv)
    if args.provider == "openai" and not args.i_accept_cost:
        parser.error("--provider openai calls a billed API; add --i-accept-cost")
    scores, outputs = asyncio.run(evaluate(build_provider(args.provider)))
    print(report(args.provider, scores))
    if args.out:
        payload = {"provider": args.provider, "summary": summarize(scores), "outputs": outputs}
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
