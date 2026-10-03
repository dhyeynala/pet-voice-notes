#!/usr/bin/env python3
"""PetPulse live smoke test: call each AI feature once through the app's real services.

    python scripts/smoke_live.py --dry-run     # show providers, models and the call cap; no calls
    python scripts/smoke_live.py               # run (needs a live provider, e.g. OPENAI_API_KEY)
    python scripts/smoke_live.py --allow-fake  # run against the deterministic fakes (CI)

Checks, in order (each is one provider call when everything works):

1. voice_transcription  bundled ~5 s clip -> petpulse.services.voice (validation + STT)
2. note_classification  transcript -> petpulse.services.notes.process_note(..., source="voice")
3. pdf_summary          bundled 1-page PDF -> POST /api/pets/{pet_id}/records (in-process)
4. chat_answer          5 fixed notes + "What medication is Max on?" -> POST /api/pets/{pet_id}/chat

Everything runs in this process on a temporary in-memory store (demo data is never touched)
and a temporary data dir. Every provider call goes through a ``CallBudget`` capped by
``LIVE_CALL_CAP`` (default 6); once the cap is reached the remaining checks are SKIPPED and
never called. A check whose route is not mounted is SKIPPED (not available). Keys are never
printed (only the last 4 characters).

Exit codes: 0 all checks passed or were skipped, 1 at least one FAIL, 2 configuration error
(invalid settings, or only fake providers without --allow-fake).
A JSON report is written to ``reports/smoke-live-<timestamp>.json`` (except with --dry-run).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_MAX_TOKENS = 600  # per LLM call; inputs are tiny
SMOKE_UID = "smoke_user"
SMOKE_TZ = "America/New_York"
FIXED_NOTE = "Max vomited twice this morning and there was some blood."
VOICE_KEYWORDS = ("vomit", "blood", "twice")
CHAT_QUESTION = "What medication is Max on?"
CHAT_RECORDS = (
    "Max had his usual thirty minute walk and finished all of his dinner.",
    "Vet visit today: Max started Apoquel 16 mg once daily for his itchy skin.",
    "Max slept well and was playful this morning.",
    "Max played fetch at the park for twenty minutes.",
    "Max ate all of his kibble and drank plenty of water.",
)
PASS, FAIL, SKIPPED = "PASS", "FAIL", "SKIPPED"


# ------------------------------------------------------------------------------ budget
class BudgetExhausted(RuntimeError):
    """The live call cap is reached; the call was not made."""


class NotAvailable(RuntimeError):
    """The service or route a check needs is not on this branch."""


class CheckFailed(AssertionError):
    """A pass criterion was not met."""


@dataclass
class CallBudget:
    cap: int
    used: int = 0
    log: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)

    def spend(self, what: str) -> None:
        if self.used >= self.cap:
            raise BudgetExhausted(f"call cap {self.cap} reached before {what}")
        self.used += 1
        self.log.append(what)


class BudgetedLLM:
    """Wraps an ``LLMProvider``: every call spends one unit of budget and max_tokens is clamped."""

    def __init__(self, inner: Any, budget: CallBudget, max_tokens: int) -> None:
        self._inner = inner
        self._budget = budget
        self._max_tokens = max_tokens

    name = property(lambda self: self._inner.name)
    model = property(lambda self: self._inner.model)

    async def complete_json(self, **kwargs: Any) -> Any:
        self._budget.spend(f"llm.complete_json:{kwargs.get('task', '?')}")
        kwargs["max_tokens"] = min(int(kwargs.get("max_tokens", self._max_tokens)), self._max_tokens)
        return await self._inner.complete_json(**kwargs)

    def __getattr__(self, item: str) -> Any:  # register(), calls, fail ... (fakes)
        return getattr(self._inner, item)


class BudgetedSTT:
    def __init__(self, inner: Any, budget: CallBudget) -> None:
        self._inner = inner
        self._budget = budget

    name = property(lambda self: self._inner.name)
    model = property(lambda self: self._inner.model)
    supported_mimes = property(lambda self: self._inner.supported_mimes)

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Any:
        self._budget.spend("stt.transcribe")
        return self._inner.transcribe(audio, mime, hint)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


# ------------------------------------------------------------------------------ context
@dataclass
class CheckResult:
    name: str
    status: str
    provider: str
    calls: int = 0
    seconds: float = 0.0
    detail: str = ""


@dataclass
class Context:
    settings: Any
    budget: CallBudget
    llm: Any
    stt: Any
    store: Any
    tmpdir: Path
    transcript: Optional[str] = None
    note_ids: set[str] = field(default_factory=set)
    _app: Any = None
    _client: Any = None
    _pet_id: Optional[str] = None
    _headers: dict[str, str] = field(default_factory=dict)
    _overrides: list[Any] = field(default_factory=list)

    # -- the app, a signed-in client and the smoke pet (created on first use) --
    @property
    def app(self) -> Any:
        if self._app is None:
            from petpulse import deps

            api_server = importlib.import_module("api_server")
            self._app = api_server.app
            overrides = {
                deps.get_store: lambda: self.store,
                deps.get_llm: lambda: self.llm,
                deps.get_stt: lambda: self.stt,
                deps.get_settings: lambda: self.settings,
            }
            for dependency, factory in overrides.items():
                self._app.dependency_overrides[dependency] = factory
                self._overrides.append(dependency)
        return self._app

    @property
    def pet_id(self) -> str:
        if self._pet_id is None:
            self._pet_id, self._headers = _create_identity(self)
        return self._pet_id

    @property
    def client(self) -> Any:
        if self._client is None:
            from fastapi.testclient import TestClient

            pet_id = self.pet_id  # identity first (may add auth overrides)
            self._client = TestClient(self.app, headers=self._headers)
            self._client.__enter__()
            assert pet_id
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
        if self._app is not None:
            for dependency in self._overrides:
                self._app.dependency_overrides.pop(dependency, None)


def _create_identity(ctx: Context) -> tuple[str, dict[str, str]]:
    """A temporary user and pet in the temporary store, signed in the app's real way."""
    from petpulse import auth, pets

    pets.save_user(ctx.store, SMOKE_UID, "Smoke Test")
    pet = pets.create_pet(ctx.store, SMOKE_UID, {"name": "Max", "animal_type": "dog", "breed": "Labrador"})
    token = auth.issue_token(SMOKE_UID, settings=ctx.settings)
    return str(pet["id"]), {"Authorization": f"Bearer {token}"}


def _routes(routes: list[Any], prefix: str = "") -> Iterator[tuple[str, set[str], str]]:
    """(path, methods, endpoint module) for every route, including included routers."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            yield from _routes(list(original.routes), prefix + str(getattr(context, "prefix", "") or ""))
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None and hasattr(route, "path"):
            yield prefix + route.path, set(getattr(route, "methods", None) or ()), str(endpoint.__module__)


def require_route(ctx: Context, method: str, path: str, owner: str) -> None:
    """The contract route must exist and be served by a new-style ``petpulse`` router."""
    for route_path, methods, module in _routes(list(ctx.app.routes)):
        if route_path == path and method in methods and module.startswith("petpulse."):
            return
    raise NotAvailable(f"{method} {path} ({owner}) is not on this branch")


def call_process_note(ctx: Context, text: str, llm: Any = None) -> dict[str, Any]:
    """``petpulse.services.notes.process_note(..., source="voice")`` on the temporary store."""
    from petpulse.services import notes

    pet_id = ctx.pet_id
    note = asyncio.run(notes.process_note(pet_id, SMOKE_UID, text, "voice", SMOKE_TZ, store=ctx.store, llm=llm or ctx.llm))
    return dict(note.model_dump(mode="json"))


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def _walk(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


# ------------------------------------------------------------------------------- checks
def check_voice(ctx: Context) -> str:
    from petpulse.samples import SMOKE_AUDIO_ID, audio_manifest
    from petpulse.services import voice

    sample = audio_manifest().get(SMOKE_AUDIO_ID)
    _expect(sample is not None, f"bundled sample {SMOKE_AUDIO_ID!r} is missing")
    assert sample is not None
    audio = voice.validate_audio(sample.read_bytes(), sample.mime, sample.file, ctx.settings, ctx.stt)
    result = asyncio.run(voice.transcribe_audio(audio, ctx.stt))
    _expect(result.status == "ok", f"status={result.status} error={result.error}")
    words = result.text.lower()
    hits = [w for w in VOICE_KEYWORDS if w in words]
    _expect(len(hits) >= 2, f"transcript has {hits} of {list(VOICE_KEYWORDS)}: {result.text[:80]!r}")
    ctx.transcript = result.text
    confidence = f" conf={result.confidence}" if result.confidence is not None else ""
    return f'"{result.text[:48]}{"..." if len(result.text) > 48 else ""}"{confidence}'


def check_note(ctx: Context) -> str:
    note = call_process_note(ctx, ctx.transcript or FIXED_NOTE)
    if note.get("id"):
        ctx.note_ids.add(str(note["id"]))
    flags = [f for f in note.get("red_flags") or [] if isinstance(f, dict)]
    shown = ",".join(f"{f.get('flag')}:{f.get('status')}" for f in flags)
    summary = f"kind={note.get('kind')} urgent={note.get('urgent')} flags=[{shown}]"
    _expect(note.get("status") not in ("unprocessed", "failed", "error"), f"note status={note.get('status')} ({summary})")
    _expect(note.get("kind") in ("MEDICAL", "MIXED"), f"kind={note.get('kind')} ({summary})")
    present = {f.get("flag") for f in flags if f.get("status") == "present"}
    _expect(bool(present & {"blood", "repeated_vomiting"}), f"no blood/repeated_vomiting flag present ({summary})")
    _expect(note.get("urgent") is True, f"urgent is not True ({summary})")
    return summary


def check_pdf(ctx: Context) -> str:
    from petpulse.samples import SMOKE_PDF_PATH

    path = "/api/pets/{pet_id}/records"
    require_route(ctx, "POST", path, "bug-fix track")
    response = ctx.client.post(
        path.format(pet_id=ctx.pet_id),
        files={"file": ("smoke_record.pdf", SMOKE_PDF_PATH.read_bytes(), "application/pdf")},
    )
    _expect(200 <= response.status_code < 300, f"HTTP {response.status_code}: {response.text[:120]}")
    record = response.json()
    if record.get("id"):
        ctx.note_ids.add(str(record["id"]))
    summary = record.get("summary")
    _expect(summary not in (None, "", {}), f"no summary (status={record.get('status')})")
    _expect("apoquel" in json.dumps(summary).lower(), "no medication matched 'apoquel'")
    pages = [v for k, v in _walk(summary) if k in ("page", "pages") and isinstance(v, (int, list))]
    flat = [p for v in pages for p in (v if isinstance(v, list) else [v])]
    _expect(all(p == 1 for p in flat), f"cited pages {sorted(set(flat))} outside the 1-page document")
    return f"status={record.get('status')} apoquel=found pages={sorted(set(flat)) or [1]}"


def check_chat(ctx: Context) -> str:
    from petpulse.providers.llm import FakeLLM

    path = "/api/pets/{pet_id}/chat"
    require_route(ctx, "POST", path, "LLM track")
    # Seed the 5 fixed records with the deterministic fake: no live calls, the app's own schema.
    seeding = FakeLLM()
    apoquel_ids: set[str] = set()
    for text in CHAT_RECORDS:
        note_id = str(call_process_note(ctx, text, llm=seeding).get("id", ""))
        ctx.note_ids.add(note_id)
        if "Apoquel" in text:
            apoquel_ids.add(note_id)
    response = ctx.client.post(path.format(pet_id=ctx.pet_id), json={"message": CHAT_QUESTION, "tz": SMOKE_TZ})
    _expect(200 <= response.status_code < 300, f"HTTP {response.status_code}: {response.text[:120]}")
    body = response.json()
    citations = [c for c in body.get("citations") or [] if isinstance(c, dict)]
    cited = [str(c.get("id")) for c in citations]
    summary = f"status={body.get('status')} citations={cited}"
    _expect(body.get("status") == "answered", summary)
    _expect(bool(citations), f"no citations ({summary})")
    _expect(all(c in ctx.note_ids for c in cited), f"citation outside the given records ({summary})")
    cites_apoquel = bool(set(cited) & apoquel_ids) or any("apoquel" in str(c.get("snippet", "")).lower() for c in citations)
    _expect(cites_apoquel, f"does not cite the Apoquel record ({summary})")
    return summary


Check = tuple[str, str, Callable[[Context], str]]  # (name, provider kind "llm"|"stt", fn)
CHECKS: list[Check] = [
    ("voice_transcription", "stt", check_voice),
    ("note_classification", "llm", check_note),
    ("pdf_summary", "llm", check_pdf),
    ("chat_answer", "llm", check_chat),
]


# ------------------------------------------------------------------------------- runner
def mask(secret: Optional[str]) -> str:
    if not secret:
        return "(not set)"
    return f"…{secret[-4:]}" if len(secret) > 8 else "…"


def _provider_label(provider: Any) -> str:
    return f"{provider.name}:{provider.model}"


def run_checks(ctx: Context, checks: list[Check]) -> list[CheckResult]:
    results = []
    for name, kind, fn in checks:
        provider = _provider_label(ctx.stt if kind == "stt" else ctx.llm)
        if ctx.budget.remaining == 0:
            results.append(CheckResult(name, SKIPPED, provider, detail=f"cap: {ctx.budget.cap} calls used"))
            continue
        before, started = ctx.budget.used, time.monotonic()
        try:
            status, detail = PASS, fn(ctx)
        except BudgetExhausted as exc:
            status, detail = SKIPPED, f"cap: {exc}"
        except NotAvailable as exc:
            status, detail = SKIPPED, f"not available: {exc}"
        except CheckFailed as exc:
            status, detail = FAIL, str(exc)
        except Exception as exc:  # a crash in a check is a FAIL, never a traceback with secrets
            status, detail = FAIL, f"{type(exc).__name__}: {_scrub(str(exc), ctx)[:160]}"
        results.append(
            CheckResult(name, status, provider, ctx.budget.used - before, round(time.monotonic() - started, 2), detail)
        )
    return results


def _scrub(text: str, ctx: Context) -> str:
    key = ctx.settings.openai_api_key.get_secret_value() if ctx.settings.openai_api_key else None
    if key:
        text = text.replace(key, mask(key))
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-…", text)


def _print_header(out: TextIO, settings: Any, llm: Any, stt: Any, cap: int) -> None:
    now = datetime.now().astimezone()
    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    creds = settings.google_application_credentials
    print(f"PetPulse live smoke test   {now:%Y-%m-%d %H:%M %Z}", file=out)
    print(
        f"mode={settings.overall_mode()}  llm={_provider_label(llm)}  stt={_provider_label(stt)}  call_cap={cap}",
        file=out,
    )
    print(f"OPENAI_API_KEY={mask(key)}  GOOGLE_APPLICATION_CREDENTIALS={Path(creds).name if creds else '(not set)'}", file=out)


def run(
    argv: Optional[list[str]] = None,
    *,
    checks: Optional[list[Check]] = None,
    llm: Any = None,
    stt: Any = None,
    out: TextIO = sys.stdout,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="show what would be called; make no calls")
    parser.add_argument("--allow-fake", action="store_true", help="run even when every provider is the fake (CI)")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports", help="where the JSON report goes")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="max_tokens clamp per LLM call")
    args = parser.parse_args(argv)
    os.chdir(ROOT)  # .env is read from the repo root

    from petpulse import deps
    from petpulse.config import ConfigError

    saved_env = {k: os.environ.get(k) for k in ("STORE", "SEED_ON_START", "DATA_DIR")}
    tmp = tempfile.TemporaryDirectory(prefix="petpulse-smoke-")
    # A temporary store and data dir; provider settings come from the environment / .env.
    os.environ.update({"STORE": "memory", "SEED_ON_START": "false", "DATA_DIR": tmp.name})
    deps.reset()
    ctx: Optional[Context] = None
    try:
        try:
            settings = deps.get_settings()
            settings.check()
            real_llm = llm if llm is not None else deps.get_llm()
            real_stt = stt if stt is not None else deps.get_stt()
        except (ConfigError, ValueError) as exc:
            print(f"configuration error: {exc}", file=out)
            return 2
        cap = settings.live_call_cap
        _print_header(out, settings, real_llm, real_stt, cap)
        all_fake = real_llm.name == "fake" and real_stt.name == "fake"
        selected = checks if checks is not None else CHECKS
        if args.dry_run:
            for name, kind, _fn in selected:
                print(f"  would run {name:<20} via {_provider_label(real_stt if kind == 'stt' else real_llm)}", file=out)
            note = " (all providers are fakes: a real run needs --allow-fake)" if all_fake else ""
            print(f"dry run: no provider calls made; at most {cap} calls would be made{note}", file=out)
            return 0
        if all_fake and not args.allow_fake:
            print("refusing to run: every provider is the fake (set OPENAI_API_KEY or pass --allow-fake)", file=out)
            return 2
        budget = CallBudget(cap)
        store = deps.get_store()
        ctx = Context(
            settings=settings,
            budget=budget,
            llm=BudgetedLLM(real_llm, budget, args.max_tokens),
            stt=BudgetedSTT(real_stt, budget),
            store=store,
            tmpdir=Path(tmp.name),
        )
        deps.override(store=store, llm=ctx.llm, stt=ctx.stt)
        results = run_checks(ctx, selected)
        for r in results:
            calls = f"{r.calls} call{'s' if r.calls != 1 else ''}"
            print(f"{'[' + r.status + ']':<9} {r.name:<20} {calls:<8} {r.seconds:>5.1f}s   {r.detail}", file=out)
        code = 1 if any(r.status == FAIL for r in results) else 0
        print(f"calls used: {budget.used}/{cap}   est. cost: not estimated (check the provider's pricing page)", file=out)
        print(f"exit code: {code}" + (" (one or more FAIL)" if code else ""), file=out)
        report = _write_report(args.report_dir, settings, real_llm, real_stt, budget, results, code)
        print(f"report: {report}", file=out)
        return code
    finally:
        if ctx is not None:
            ctx.close()
        deps.reset()
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tmp.cleanup()


def _write_report(
    report_dir: Path, settings: Any, llm: Any, stt: Any, budget: CallBudget, results: list[CheckResult], code: int
) -> Path:
    now = datetime.now().astimezone()
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"smoke-live-{now:%Y%m%d-%H%M%S}.json"
    payload = {
        "started_at": now.isoformat(timespec="seconds"),
        "mode": settings.overall_mode(),
        "llm": _provider_label(llm),
        "stt": _provider_label(stt),
        "call_cap": budget.cap,
        "calls_used": budget.used,
        "calls": budget.log,
        "exit_code": code,
        "checks": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
