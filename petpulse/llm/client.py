"""The adapter every LLM call goes through, for the fake and the real provider alike.

Per call: render the versioned prompt -> provider ``complete_json`` with the strict schema ->
fail on truncation (``finish_reason == "length"``) -> parse and validate with Pydantic plus
task checks (e.g. every cited sentence exists) -> on a validation error, one repair attempt
that feeds the error back -> otherwise ``LLMFailure``.

Every attempt writes a call record (``llm_calls`` collection, and one structured log line):
task, prompt id/version/hash, provider, model, mode (demo|live), attempt, outcome, tokens,
latency and estimated cost. True cost per case includes the failed and repaired attempts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Literal, Mapping, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from petpulse.llm.config import MAX_REPAIR_ATTEMPTS, TASK_SETTINGS, estimate_cost_usd
from petpulse.llm.registry import RenderedPrompt, escape_markers, get_prompt
from petpulse.llm.schemas import strict_json_schema
from petpulse.providers.llm import REPAIR_MARKER, LLMError, LLMProvider, LLMRefusal, RawCompletion
from petpulse.store.base import Store
from petpulse.core.timeutil import to_iso, utc_now

logger = logging.getLogger("petpulse.llm")

T = TypeVar("T", bound=BaseModel)
Mode = Literal["demo", "live"]
FailureReason = Literal["provider_error", "refused", "truncated", "invalid_output"]
Outcome = Literal["ok", "invalid", "truncated", "provider_error", "refused"]
CALLS_COLLECTION = "llm_calls"


class LLMFailure(Exception):
    """The task produced no usable output. Callers take their explicit failure path."""

    def __init__(self, reason: FailureReason, detail: str, attempts: int, call_ids: Optional[list[str]] = None) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason: FailureReason = reason
        self.detail = detail
        self.attempts = attempts
        self.call_ids = call_ids or []


@dataclass(frozen=True)
class TaskSpec(Generic[T]):
    prompt_id: str
    version: int
    output: type[T]

    @property
    def key(self) -> str:
        return f"{self.prompt_id}.v{self.version}"


@dataclass
class LLMResult(Generic[T]):
    value: T
    provider: str
    model: str
    mode: Mode
    prompt_key: str
    prompt_sha256: str
    attempts: int
    call_ids: list[str] = field(default_factory=list)


Check = Callable[[Any], list[str]]


def provider_mode(provider: LLMProvider) -> Mode:
    return "demo" if provider.name == "fake" else "live"


def _schema_hash(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]


def _format_errors(exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors()[:10]:
        loc = ".".join(str(part) for part in err.get("loc", ())) or "(root)"
        out.append(f"{loc}: {err.get('msg', 'invalid')}")
    return out


def parse_and_validate(text: str, output: type[T], check: Optional[Check]) -> tuple[Optional[T], list[str]]:
    """Return ``(value, [])`` or ``(None, errors)``. Never raises on bad model output."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"output is not valid JSON: {exc.msg} at position {exc.pos}"]
    try:
        value = output.model_validate(payload)
    except ValidationError as exc:
        return None, _format_errors(exc)
    problems = check(value) if check else []
    return (value, []) if not problems else (None, problems[:10])


def repair_message(original_user: str, errors: list[str]) -> str:
    detail = escape_markers("\n".join(f"- {e}" for e in errors))
    return (
        f"{original_user}\n\n{REPAIR_MARKER}\n{detail}\n</validation_error>\n\n"
        "Your previous output did not match the schema or cited something that does not exist. "
        "Return corrected JSON only, following the same rules."
    )


class LLMClient:
    """Validating adapter around one provider. ``store=None`` logs records without persisting."""

    def __init__(
        self, provider: LLMProvider, store: Optional[Store] = None, *, meta: Optional[Mapping[str, Any]] = None
    ) -> None:
        self.provider = provider
        self.store = store
        self.meta = dict(meta or {})

    @property
    def mode(self) -> Mode:
        return provider_mode(self.provider)

    def _record(
        self,
        rendered: RenderedPrompt,
        schema_hash: str,
        attempt: int,
        outcome: Outcome,
        started: float,
        raw: Optional[RawCompletion] = None,
        error: Optional[str] = None,
    ) -> str:
        model = raw.model if raw else getattr(self.provider, "model", "")
        input_tokens = raw.input_tokens if raw else 0
        output_tokens = raw.output_tokens if raw else 0
        cost = 0.0 if self.mode == "demo" else estimate_cost_usd(model, input_tokens, output_tokens)
        record = {
            "task": rendered.key,
            "prompt_id": rendered.prompt_id,
            "prompt_version": rendered.version,
            "prompt_sha256": rendered.sha256,
            "schema_hash": schema_hash,
            "provider": self.provider.name,
            "model": model,
            "mode": self.mode,
            "attempt": attempt,
            "outcome": outcome,
            "finish_reason": raw.finish_reason if raw else None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "cost_usd": cost,
            "error": error[:500] if error else None,
            "created_at": to_iso(utc_now()),
            **self.meta,
        }
        call_id = self.store.add(CALLS_COLLECTION, record) if self.store is not None else ""
        logger.info("llm_call %s", json.dumps({"id": call_id, **record}, sort_keys=True, default=str))
        return call_id

    async def run(
        self,
        spec: TaskSpec[T],
        variables: Mapping[str, str],
        *,
        check: Optional[Check] = None,
    ) -> LLMResult[T]:
        rendered = get_prompt(spec.prompt_id, spec.version).render(variables)
        schema = strict_json_schema(spec.output)
        schema_hash = _schema_hash(schema)
        settings = TASK_SETTINGS[spec.prompt_id]
        user = rendered.user
        call_ids: list[str] = []
        errors: list[str] = []
        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 2):
            started = time.perf_counter()
            try:
                raw = await self.provider.complete_json(
                    task=rendered.key,
                    system=rendered.system,
                    user=user,
                    schema=schema,
                    temperature=settings.temperature,
                    max_tokens=settings.max_tokens,
                )
            except LLMRefusal as exc:
                call_ids.append(self._record(rendered, schema_hash, attempt, "refused", started, error=str(exc)))
                raise LLMFailure("refused", str(exc), attempt, call_ids) from exc
            except LLMError as exc:
                call_ids.append(self._record(rendered, schema_hash, attempt, "provider_error", started, error=str(exc)))
                raise LLMFailure("provider_error", str(exc), attempt, call_ids) from exc
            if raw.finish_reason == "length":
                # Hitting max_tokens mid-JSON is an error, never something to "repair".
                call_ids.append(self._record(rendered, schema_hash, attempt, "truncated", started, raw))
                raise LLMFailure("truncated", "output hit max_tokens", attempt, call_ids)
            if raw.finish_reason not in ("stop", ""):
                detail = f"unexpected finish_reason {raw.finish_reason!r}"
                call_ids.append(self._record(rendered, schema_hash, attempt, "provider_error", started, raw, detail))
                raise LLMFailure("provider_error", detail, attempt, call_ids)
            value, errors = parse_and_validate(raw.text, spec.output, check)
            if value is not None:
                call_ids.append(self._record(rendered, schema_hash, attempt, "ok", started, raw))
                return LLMResult(
                    value=value,
                    provider=self.provider.name,
                    model=raw.model,
                    mode=self.mode,
                    prompt_key=rendered.key,
                    prompt_sha256=rendered.sha256,
                    attempts=attempt,
                    call_ids=call_ids,
                )
            call_ids.append(self._record(rendered, schema_hash, attempt, "invalid", started, raw, "; ".join(errors)))
            user = repair_message(rendered.user, errors)
        raise LLMFailure("invalid_output", "; ".join(errors), MAX_REPAIR_ATTEMPTS + 1, call_ids)
