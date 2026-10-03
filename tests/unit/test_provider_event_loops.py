"""Live providers must survive more than one event loop (live smoke regression).

``scripts/smoke_live.py`` runs some checks with ``asyncio.run`` and others through a
``TestClient`` (its own loop). The OpenAI LLM adapter used to cache one ``AsyncOpenAI`` client
for its lifetime, so the second loop reused a pooled connection opened on the first, closed
loop and failed with ``RuntimeError: Event loop is closed``. These tests talk to a local
keep-alive HTTP server (the real SDK and the real httpx pool, no network), so pooled
connections behave exactly like they do against api.openai.com.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Iterator

import pytest

from petpulse.providers.llm import OpenAILLM
from petpulse.providers.stt import OpenAISTT
from petpulse.services.voice import AudioInput, transcribe_audio
from tests.audio_fixtures import wav
from tests.openai_stub import chat_completion, openai_stub
from tests.unit.test_openai_contract import FAKE_KEY, GOOD

REQUESTS: list[str] = []


def _reply(path: str, body: dict[str, Any]) -> dict[str, Any]:
    if path.endswith("/audio/transcriptions"):
        return {"text": "Max vomited twice this morning."}
    return chat_completion(json.dumps(GOOD))


@pytest.fixture
def base_url() -> Iterator[str]:
    with openai_stub(_reply) as (url, paths):
        global REQUESTS
        REQUESTS = paths
        yield url


def _complete(llm: OpenAILLM) -> Any:
    return llm.complete_json(task="note_extract.v1", system="s", user="u", schema={"type": "object"})


def test_one_llm_instance_works_across_sequential_asyncio_runs(base_url):
    llm = OpenAILLM(api_key=FAKE_KEY, max_retries=0, base_url=base_url)
    for _ in range(3):
        raw = asyncio.run(_complete(llm))
        assert raw.finish_reason == "stop" and raw.input_tokens == 321
    assert len(REQUESTS) == 3


def test_llm_works_on_a_new_loop_after_the_first_one_closed(base_url):
    """asyncio.run (loop 1, now closed), then a long-lived loop like TestClient's portal."""
    llm = OpenAILLM(api_key=FAKE_KEY, max_retries=0, base_url=base_url)
    asyncio.run(_complete(llm))
    loop = asyncio.new_event_loop()
    try:
        for _ in range(2):  # reused within the same loop is fine and expected
            assert loop.run_until_complete(_complete(llm)).finish_reason == "stop"
    finally:
        loop.close()
    assert asyncio.run(_complete(llm)).finish_reason == "stop"


def test_llm_keeps_one_client_per_loop():
    llm = OpenAILLM(api_key=FAKE_KEY, max_retries=0, base_url="http://127.0.0.1:9/v1")

    async def client() -> Any:
        return llm._async_client()

    async def twice() -> tuple[Any, Any]:
        return llm._async_client(), llm._async_client()

    first, again = asyncio.run(twice())
    assert first is again  # one client (and pool) per loop
    assert asyncio.run(client()) is not first  # a new loop never sees the old loop's pool


def test_one_stt_instance_works_across_sequential_asyncio_runs(base_url):
    """OpenAISTT uses the sync SDK client (run in a worker thread), so it is loop-independent."""
    import openai

    sdk = openai.OpenAI(api_key=FAKE_KEY, base_url=base_url, max_retries=0)
    stt = OpenAISTT(api_key=FAKE_KEY, max_retries=0, client=sdk)
    audio = AudioInput(data=wav(seconds=1.0), mime="audio/wav", hint="clip.wav")
    for _ in range(3):
        result = asyncio.run(transcribe_audio(audio, stt))
        assert result.status == "ok" and "vomited" in result.text
    assert len(REQUESTS) == 3
