"""The real entrypoints: bare import with no env, and uvicorn serving /api/health."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bare_env(tmp_path: Path) -> dict[str, str]:
    # No OPENAI/GOOGLE/FIREBASE variables at all, run from an unrelated directory.
    return {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "PYTHONPATH": str(ROOT)}


def test_import_app_with_no_env_and_no_key_files(tmp_path):
    code = (
        "import sys, petpulse.app\n"
        "bad = [m for m in ('openai', 'google.cloud.speech', 'firebase_admin', 'pandas', 'numpy', 'pyaudio') "
        "if m in sys.modules]\n"
        "print('LIVE_MODULES=' + ','.join(bad))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=_bare_env(tmp_path), capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "LIVE_MODULES=\n" in result.stdout


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_uvicorn_starts_and_serves_health(tmp_path):
    port = _free_port()
    env = {**_bare_env(tmp_path), "DATA_DIR": str(tmp_path / "data")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "petpulse.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        body = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:  # nosec B310
                    assert resp.status == 200
                    body = json.load(resp)
                    break
            except OSError:
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
        assert body is not None, proc.stdout.read() if proc.poll() is not None else "server did not answer"
        assert body["mode"] == "demo" and body["store"] == "json" and body["llm"] == "fake" and body["stt"] == "fake"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
