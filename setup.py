#!/usr/bin/env python3
"""PetPulse setup helper: writes a ``.env`` from ``.env.example``.

Everything is optional. With no ``.env`` the app runs in demo mode (fake AI, local JSON store,
demo login). This script only fills in the optional live settings you choose:

- ``OPENAI_API_KEY`` for live AI,
- Firebase (Firestore + Firebase sign-in): a service-account key file and the web API key.
  The browser gets its Firebase config from ``GET /api/auth/config``; there is no client config
  file. See docs/firebase.md.
"""

from __future__ import annotations

import getpass
import json
import subprocess  # nosec B404 - runs pip with fixed arguments
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLE = ROOT / ".env.example"
ENV = ROOT / ".env"


def ask(prompt: str, secret: bool = False) -> str:
    reader = getpass.getpass if secret else input
    return reader(f"{prompt}: ").strip()


def render_env(template: str, values: dict[str, str]) -> str:
    """``.env.example`` with ``KEY=...`` replaced for every key in ``values`` (comments dropped there)."""
    lines = []
    for line in template.splitlines():
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in values:
            line = f"{key}={values[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def firebase_values() -> dict[str, str]:
    print("\nFirebase (optional; see docs/firebase.md). Leave the key path empty to skip.")
    key_path = ask("Path to the service-account key JSON")
    if not key_path:
        return {}
    path = Path(key_path).expanduser()
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Could not read a JSON key from {path} ({type(exc).__name__}); skipping Firebase.")
        return {}
    project = info.get("project_id") if isinstance(info, dict) else None
    if not project or info.get("type") != "service_account":
        print("That file is not a service-account key; skipping Firebase.")
        return {}
    web_key = ask("Firebase Web API key (Project settings > General > Your apps)")
    bucket = ask(f"Storage bucket for record PDFs (optional, e.g. {project}.firebasestorage.app)")
    values = {"FIREBASE_PROJECT_ID": project, "GOOGLE_APPLICATION_CREDENTIALS": str(path.resolve())}
    if web_key:
        values["FIREBASE_WEB_API_KEY"] = web_key
    else:
        print("No web API key: Firestore will be used, sign-in stays the demo login.")
    if bucket:
        values["FIREBASE_STORAGE_BUCKET"] = bucket
    return values


def main() -> None:
    print("PetPulse setup: every step is optional; the demo needs none of them.\n")
    if ENV.exists() and ask(".env already exists. Overwrite? (y/N)").lower() != "y":
        print("Keeping the existing .env.")
        return

    values: dict[str, str] = {}
    openai_key = ask("OpenAI API key for live AI (empty = demo AI)", secret=True)
    if openai_key:
        values["OPENAI_API_KEY"] = openai_key
    values.update(firebase_values())

    ENV.write_text(render_env(EXAMPLE.read_text(encoding="utf-8"), values), encoding="utf-8")
    print(f"\nWrote {ENV.name} (never commit it).")

    requirements = ["-r", "requirements.txt"]
    if "FIREBASE_PROJECT_ID" in values:
        requirements += ["-r", "requirements-live.txt"]
    if ask(f"Install Python dependencies now ({' '.join(requirements)})? (Y/n)").lower() != "n":
        subprocess.run([sys.executable, "-m", "pip", "install", *requirements], check=False, cwd=ROOT)  # nosec B603

    print("\nNext: uvicorn api_server:app --reload, then open http://localhost:8000")
    print("GET /api/health shows which AI, store and sign-in modes are active.")


if __name__ == "__main__":
    main()
