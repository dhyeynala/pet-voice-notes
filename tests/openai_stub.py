"""A local keep-alive HTTP server that speaks just enough of the OpenAI API for tests.

The real SDK and the real httpx connection pool talk to it (``base_url``), so pooled
connections, event loops and threads behave as they do against api.openai.com, with no
network and no key. ``reply(path, body)`` returns the JSON response for one request.
"""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterator

Reply = Callable[[str, dict[str, Any]], dict[str, Any]]


@contextmanager
def openai_stub(reply: Reply) -> Iterator[tuple[str, list[str]]]:
    """Yields ``(base_url, paths)``; ``paths`` lists every request path in order."""
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive: the client pools and reuses the connection

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            paths.append(self.path)
            is_json = (self.headers.get("Content-Type") or "").startswith("application/json")
            body = json.dumps(reply(self.path, json.loads(raw) if is_json else {})).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", paths
    finally:
        server.shutdown()
        server.server_close()


def chat_completion(content: str, model: str = "gpt-5.4-mini-2026-03-17") -> dict[str, Any]:
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 1_790_000_000,
        "model": model,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 321, "completion_tokens": 45, "total_tokens": 366},
    }


def fake_backed_reply(transcript: str) -> Reply:
    """Answers chat completions with what the deterministic FakeLLM would say for that prompt
    (task from the json_schema name), and transcriptions with ``transcript``."""
    from petpulse.providers.llm import FakeLLM

    fake = FakeLLM()

    def reply(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path.endswith("/audio/transcriptions"):
            return {"text": transcript}
        fmt = body["response_format"]["json_schema"]
        task = fmt["name"].rsplit("_v", 1)[0] + ".v" + fmt["name"].rsplit("_v", 1)[1]
        system, user = (m["content"] for m in body["messages"])
        raw = asyncio.run(fake.complete_json(task=task, system=system, user=user, schema=fmt["schema"]))
        return chat_completion(raw.text, model=body["model"])

    return reply
