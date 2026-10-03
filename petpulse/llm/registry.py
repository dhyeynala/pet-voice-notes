"""Versioned prompt registry (FDE: prompts are code; one registry plus a hash).

Each prompt lives in ``prompts/<id>.v<N>.md`` with a ``## SYSTEM`` and a ``## USER`` section.
The system layer is standing behaviour and identical on every call for a version. The user
layer carries the case; every variable is rendered with ``string.Template.substitute`` (a
missing variable raises) and has the marker tags escaped, so untrusted text cannot close its
own ``<note>``/``<records>``/``<question>``/``<document>`` block.

``prompts.lock`` records the sha256 of every released prompt file. A test fails if a file
changes without a new version, because an in-place edit silently invalidates every recorded
result (call records carry ``prompt_id``, ``prompt_version`` and the hash).
"""

from __future__ import annotations

import hashlib
import json
import re
import string
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
LOCK_FILE = PROMPTS_DIR / "prompts.lock"

# Tags used as data markers in user messages; never allowed to appear verbatim in variables.
MARKER_TAGS = ("note", "records", "question", "document", "validation_error")
_MARKER_RE = re.compile(r"<(\s*/?\s*)(" + "|".join(MARKER_TAGS) + r")\b", re.IGNORECASE)
_FILE_RE = re.compile(r"^(?P<id>[a-z][a-z0-9_]*)\.v(?P<version>[1-9][0-9]*)\.md$")


class PromptError(RuntimeError):
    """A prompt file is missing, malformed, or rendered with missing variables."""


def escape_markers(text: str) -> str:
    """Neutralise marker tags inside untrusted text (``</note>`` becomes ``&lt;/note``)."""
    return _MARKER_RE.sub(lambda m: "&lt;" + m.group(1) + m.group(2), text)


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_id: str
    version: int
    sha256: str
    system: str
    user: str

    @property
    def key(self) -> str:
        return f"{self.prompt_id}.v{self.version}"


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    version: int
    sha256: str
    system: str
    user_template: str

    @property
    def key(self) -> str:
        return f"{self.prompt_id}.v{self.version}"

    def render(self, variables: Mapping[str, str]) -> RenderedPrompt:
        """Fill the user template. Every value is escaped; a missing variable raises."""
        safe = {name: escape_markers(str(value)) for name, value in variables.items()}
        try:
            user = string.Template(self.user_template).substitute(safe)
        except (KeyError, ValueError) as exc:
            raise PromptError(f"cannot render {self.key}: missing or invalid variable {exc}") from exc
        return RenderedPrompt(self.prompt_id, self.version, self.sha256, self.system, user)


def _parse(path: Path) -> Prompt:
    match = _FILE_RE.match(path.name)
    if not match:
        raise PromptError(f"bad prompt file name {path.name!r} (expected <id>.v<N>.md)")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if not text.startswith("## SYSTEM\n") or text.count("\n## USER\n") != 1:
        raise PromptError(f"{path.name} must start with '## SYSTEM' and contain one '## USER' section")
    system, user = text[len("## SYSTEM\n") :].split("\n## USER\n")
    return Prompt(
        prompt_id=match.group("id"),
        version=int(match.group("version")),
        sha256=hashlib.sha256(raw).hexdigest(),
        system=system.strip(),
        user_template=user.strip(),
    )


@lru_cache(maxsize=None)
def get_prompt(prompt_id: str, version: int) -> Prompt:
    path = PROMPTS_DIR / f"{prompt_id}.v{version}.md"
    if not path.is_file():
        raise PromptError(f"no prompt {prompt_id}.v{version}")
    return _parse(path)


def all_prompts() -> list[Prompt]:
    return [_parse(path) for path in sorted(PROMPTS_DIR.glob("*.md"))]


def read_lock() -> dict[str, str]:
    data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PromptError("prompts.lock must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def compute_lock() -> dict[str, str]:
    return {prompt.key: prompt.sha256 for prompt in all_prompts()}
