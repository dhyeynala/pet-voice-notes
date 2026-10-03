"""scripts/smoke_live.py against the fakes (and a mocked OpenAI transport): no live calls."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter, File, UploadFile

from petpulse.providers.llm import FakeLLM
from petpulse.providers.stt import FakeSTT, OpenAISTT

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "sk-test-not-real-key-wxyz"  # pragma: allowlist secret


@pytest.fixture
def smoke(monkeypatch) -> Any:
    spec = importlib.util.spec_from_file_location("smoke_live", ROOT / "scripts" / "smoke_live.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "smoke_live", module)  # dataclasses resolve their module
    spec.loader.exec_module(module)
    return module


def _run(smoke: Any, tmp_path: Path, *args: str, **kwargs: Any) -> tuple[int, str, dict[str, Any] | None]:
    out = io.StringIO()
    code = smoke.run([*args, "--report-dir", str(tmp_path / "reports")], out=out, **kwargs)
    reports = sorted((tmp_path / "reports").glob("smoke-live-*.json"))
    return code, out.getvalue(), json.loads(reports[-1].read_text()) if reports else None


def _statuses(report: dict[str, Any]) -> dict[str, str]:
    return {c["name"]: c["status"] for c in report["checks"]}


def test_fake_run_passes_or_reports_unavailable(smoke, tmp_path):
    code, output, report = _run(smoke, tmp_path, "--allow-fake")
    assert code == 0, output
    assert report is not None and report["exit_code"] == 0 and report["call_cap"] == 6
    assert [c["name"] for c in report["checks"]] == [
        "voice_transcription",
        "note_classification",
        "pdf_summary",
        "chat_answer",
    ]
    assert _statuses(report)["voice_transcription"] == "PASS"
    for check in report["checks"]:
        assert check["status"] in ("PASS", "SKIPPED"), check
        if check["status"] == "SKIPPED":
            assert check["detail"].startswith("not available"), check
    assert report["calls_used"] <= 6 and report["llm"] == "fake:fake-llm-v1" and report["stt"] == "fake:fake-stt-v1"
    assert "[PASS]    voice_transcription" in output


def test_refuses_to_run_on_fakes_without_the_flag(smoke, tmp_path):
    code, output, report = _run(smoke, tmp_path)
    assert code == 2 and "refusing to run" in output and report is None


def test_explicit_openai_without_key_is_a_config_error(smoke, tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    code, output, report = _run(smoke, tmp_path, "--allow-fake")
    assert code == 2 and "LLM_PROVIDER=openai requires OPENAI_API_KEY" in output and report is None


def test_dry_run_masks_the_key_and_makes_no_calls(smoke, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setitem(sys.modules, "openai", None)  # any SDK use would raise
    code, output, report = _run(smoke, tmp_path, "--dry-run")
    assert code == 0, output
    assert FAKE_KEY not in output and "OPENAI_API_KEY=…wxyz" in output
    assert "llm=openai:" in output and "stt=openai:gpt-4o-mini-transcribe-2025-12-15" in output
    assert "dry run: no provider calls made; at most 6 calls" in output
    assert report is None


def _one_llm_call_check(name: str) -> Any:
    def check(ctx: Any) -> str:
        import asyncio

        asyncio.run(ctx.llm.complete_json(task=name, system="s", user="u", schema={"type": "object"}))
        return "ok"

    return (name, "llm", check)


def test_call_cap_skips_the_remaining_checks(smoke, tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_CALL_CAP", "2")
    llm = FakeLLM()
    checks = [_one_llm_call_check(f"c{i}") for i in range(4)]
    code, output, report = _run(smoke, tmp_path, "--allow-fake", checks=checks, llm=llm)
    assert code == 0
    assert report is not None and [c["status"] for c in report["checks"]] == ["PASS", "PASS", "SKIPPED", "SKIPPED"]
    assert all(c["detail"].startswith("cap") for c in report["checks"][2:])
    assert len(llm.calls) == 2 and report["calls_used"] == 2
    assert "calls used: 2/2" in output


def test_cap_reached_inside_a_check_never_makes_the_call(smoke, tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_CALL_CAP", "1")
    llm = FakeLLM()

    def two_calls(ctx: Any) -> str:
        import asyncio

        for _ in range(2):
            asyncio.run(ctx.llm.complete_json(task="t", system="s", user="u", schema={}, max_tokens=5000))
        return "ok"

    code, _output, report = _run(smoke, tmp_path, "--allow-fake", checks=[("two", "llm", two_calls)], llm=llm)
    assert code == 0 and report is not None and report["checks"][0]["status"] == "SKIPPED"
    assert len(llm.calls) == 1


def test_real_cap_with_the_real_checks(smoke, tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_CALL_CAP", "1")
    stt = FakeSTT()
    code, _output, report = _run(smoke, tmp_path, "--allow-fake", stt=stt)
    assert code == 0 and report is not None
    assert _statuses(report)["voice_transcription"] == "PASS" and len(stt.calls) == 1
    assert all(c["status"] == "SKIPPED" for c in report["checks"][1:])


def test_stt_failure_is_a_fail_and_exit_1(smoke, tmp_path):
    code, output, report = _run(smoke, tmp_path, "--allow-fake", stt=FakeSTT(fail=True))
    assert code == 1 and report is not None and report["exit_code"] == 1
    assert _statuses(report)["voice_transcription"] == "FAIL" and "simulated STT outage" in output


def test_live_openai_stt_path_with_mocked_http(smoke, tmp_path):
    """The voice check through the real OpenAI adapter and SDK, over a mocked transport."""
    import httpx2

    requests: list[Any] = []

    def handler(request: Any) -> Any:
        requests.append(request)
        return httpx2.Response(200, json={"text": "Max vomited twice this morning and there was some blood."})

    stt = OpenAISTT(api_key=FAKE_KEY, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    code, output, report = _run(smoke, tmp_path, "--allow-fake", stt=stt)
    assert code == 0, output
    assert report is not None and report["stt"] == "openai:gpt-4o-mini-transcribe-2025-12-15"
    assert _statuses(report)["voice_transcription"] == "PASS"
    assert len(requests) == 1 and requests[0].url.path == "/v1/audio/transcriptions"
    assert FAKE_KEY not in output and FAKE_KEY not in json.dumps(report)


def test_script_runs_as_a_subprocess(tmp_path):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "OPENAI_API_KEY": "",
        "LLM_PROVIDER": "auto",
        "STT_PROVIDER": "auto",
        "GOOGLE_APPLICATION_CREDENTIALS": "",
    }
    result = subprocess.run(
        [sys.executable, "scripts/smoke_live.py", "--allow-fake", "--report-dir", str(tmp_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(tmp_path.glob("smoke-live-*.json"))


# ------------------------------------------------------- the four checks end to end (stand-ins)
@pytest.fixture
def contract_stand_ins(monkeypatch):
    """Minimal stand-ins for the LLM/bug-fix tracks' contract services, each making one LLM call.

    They let the note, PDF and chat checks run end to end before those tracks are merged.
    """
    import asyncio

    import api_server
    from petpulse import deps
    from petpulse.services import voice

    def llm_call(task: str) -> None:
        asyncio.run(deps.get_llm().complete_json(task=task, system="s", user="u", schema={"type": "object"}))

    def process_note(pet_id: str, uid: str, text: str, source: str, tz: str) -> dict[str, Any]:
        llm_call("note_extract")
        bloody = "blood" in text.lower()
        note = {
            "pet_id": pet_id,
            "source": source,
            "text": text,
            "kind": "MEDICAL" if bloody else "DAILY_ACTIVITY",
            "urgent": bloody,
            "red_flags": [{"flag": "blood", "status": "present", "sentences": [1]}] if bloody else [],
            "status": "processed",
        }
        note["id"] = deps.get_store().add(f"pets/{pet_id}/notes", note)
        return note

    router = APIRouter()

    async def records(pet_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        await deps.get_llm().complete_json(task="pdf_summary", system="s", user="u", schema={})
        assert (await file.read()).startswith(b"%PDF-")
        return {
            "id": "r1",
            "pages": 1,
            "status": "summarized",
            "summary": {"medications": [{"name": "Apoquel 16 mg", "pages": [1]}]},
        }

    async def chat(pet_id: str, body: dict[str, Any]) -> dict[str, Any]:
        await deps.get_llm().complete_json(task="chat_answer", system="s", user=body["message"], schema={})
        notes = deps.get_store().query(f"pets/{pet_id}/notes")
        cited = [{"id": i, "snippet": n["text"]} for i, n in notes if "Apoquel" in n["text"]]
        return {"answer": "Apoquel 16 mg", "status": "answered", "citations": cited, "chart": None, "mode": "demo"}

    for fn in (records, chat):
        fn.__module__ = "petpulse.routers.stand_in"
    router.add_api_route("/api/pets/{pet_id}/records", records, methods=["POST"])
    router.add_api_route("/api/pets/{pet_id}/chat", chat, methods=["POST"])
    before = list(api_server.app.router.routes)
    # Ahead of the legacy chat route, so the stand-in answers.
    api_server.app.include_router(router)
    api_server.app.router.routes.insert(0, api_server.app.router.routes.pop())
    monkeypatch.setattr(voice, "resolve_process_note", lambda: process_note)
    yield
    api_server.app.router.routes[:] = before


def test_all_four_checks_pass_end_to_end(smoke, tmp_path, contract_stand_ins):
    llm = FakeLLM()
    code, output, report = _run(smoke, tmp_path, "--allow-fake", llm=llm)
    assert code == 0, output
    assert report is not None and set(_statuses(report).values()) == {"PASS"}, output
    # 1 STT + 1 note + 1 PDF + 1 chat; the 5 seeded chat records go to an unbudgeted fake.
    assert report["calls_used"] == 4 and [c["calls"] for c in report["checks"]] == [1, 1, 1, 1]
    assert [c["task"] for c in llm.calls] == ["note_extract", "pdf_summary", "chat_answer"]
    assert "kind=MEDICAL urgent=True flags=[blood:present]" in output


def test_cap_two_runs_two_checks_and_skips_two(smoke, tmp_path, contract_stand_ins, monkeypatch):
    monkeypatch.setenv("LIVE_CALL_CAP", "2")
    llm, stt = FakeLLM(), FakeSTT()
    code, _output, report = _run(smoke, tmp_path, "--allow-fake", llm=llm, stt=stt)
    assert code == 0 and report is not None
    assert [c["status"] for c in report["checks"]] == ["PASS", "PASS", "SKIPPED", "SKIPPED"]
    assert len(stt.calls) + len(llm.calls) == 2


def test_a_wrong_note_is_a_fail(smoke, tmp_path, contract_stand_ins, monkeypatch):
    from petpulse.services import voice

    monkeypatch.setattr(voice, "resolve_process_note", lambda: lambda *a: {"id": "n", "kind": "OTHER", "urgent": False})
    code, output, report = _run(smoke, tmp_path, "--allow-fake")
    assert code == 1 and report is not None and _statuses(report)["note_classification"] == "FAIL"
    assert "kind=OTHER" in output
