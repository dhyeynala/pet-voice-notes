"""Pinned model facts and per-task call settings (FDE: pin dated versions, not aliases).

Sources, checked 2026-10-03 (verify again before quoting any number):
- model id and snapshot date: OpenAI model page for GPT-5.4 mini
  (https://developers.openai.com/api/docs/models/gpt-5.4-mini); alias ``gpt-5.4-mini`` is NOT
  used, the dated snapshot is.
- prices: same page, USD per 1M tokens, standard tier (input 0.75, output 4.50).
- ``reasoning_effort="none"`` is the model's default and is what allows ``temperature``.

Review triggers: the snapshot enters deprecation, prices move, or the offline eval / live
smoke test regresses. Override with ``OPENAI_MODEL`` (must still be a dated snapshot).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

OPENAI_PINNED_MODEL = "gpt-5.4-mini-2026-03-17"
DEFAULT_TIMEOUT_SECONDS = 30.0
# Transport retries inside the SDK (429/5xx/connection). Schema repair is separate and is
# done (and recorded) by the client.
OPENAI_SDK_MAX_RETRIES = 1

_DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def is_dated_snapshot(model: str) -> bool:
    return bool(_DATED_SNAPSHOT.search(model))


@dataclass(frozen=True)
class ModelFacts:
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    reasoning_effort: Optional[str]  # sent only for models that accept the parameter
    checked: str


MODEL_FACTS: dict[str, ModelFacts] = {
    OPENAI_PINNED_MODEL: ModelFacts(0.75, 4.50, "none", "2026-10-03"),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Cost of one attempt from the price table; ``None`` when the model is not in the table."""
    facts = MODEL_FACTS.get(model)
    if facts is None:
        return None
    cost = input_tokens * facts.input_usd_per_mtok / 1_000_000 + output_tokens * facts.output_usd_per_mtok / 1_000_000
    return round(cost, 6)


@dataclass(frozen=True)
class TaskSettings:
    temperature: float
    max_tokens: int  # sized from the largest legitimate schema output, not a target


# Extraction, routing and grounded answers all run at temperature 0 (stable, not deterministic).
TASK_SETTINGS: dict[str, TaskSettings] = {
    "note_extract": TaskSettings(temperature=0.0, max_tokens=1200),
    "chat_answer": TaskSettings(temperature=0.0, max_tokens=900),
    "pdf_summary": TaskSettings(temperature=0.0, max_tokens=1600),
}

MAX_REPAIR_ATTEMPTS = 1
