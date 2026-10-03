"""Settings defaults, provider auto-selection and fail-fast checks."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from petpulse.core.config import ConfigError, Settings

FAKE_KEY = "sk-test-not-real"  # pragma: allowlist secret


def make(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_defaults_are_demo_safe(monkeypatch):
    for key in ("STORE", "LLM_PROVIDER", "STT_PROVIDER", "OPENAI_API_KEY", "DATA_DIR", "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(key, raising=False)
    s = make()
    assert s.demo_mode is True
    assert s.store == "json"
    assert s.llm_provider == "auto" and s.stt_provider == "auto"
    assert s.resolved_llm() == "fake" and s.resolved_stt() == "fake"
    assert s.overall_mode() == "demo"
    assert s.allowed_origins == ["http://localhost:8000"]
    s.check()  # zero config is valid


def test_blank_key_counts_as_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    s = make()
    assert s.openai_api_key is None
    assert s.resolved_llm() == "fake"


def test_auto_goes_live_when_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    s = make()
    assert s.resolved_llm() == "openai"
    assert s.resolved_stt() == "openai"
    assert s.overall_mode() == "live"
    assert all(f["mode"] == "live" for f in s.feature_modes().values())
    s.check()


def test_explicit_fake_overrides_auto_even_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    s = make()
    assert s.resolved_llm() == "fake"
    assert s.resolved_stt() == "openai"
    assert s.overall_mode() == "mixed"
    assert s.feature_modes()["notes"] == {"provider": "fake", "mode": "demo"}
    assert s.feature_modes()["voice"] == {"provider": "openai", "mode": "live"}


@pytest.mark.parametrize(
    "env, message",
    [
        ({"LLM_PROVIDER": "openai"}, "LLM_PROVIDER=openai requires OPENAI_API_KEY"),
        ({"STT_PROVIDER": "openai"}, "STT_PROVIDER=openai requires OPENAI_API_KEY"),
        ({"STT_PROVIDER": "google"}, "STT_PROVIDER=google requires GOOGLE_APPLICATION_CREDENTIALS"),
        ({"LIVE_CALL_CAP": "-1"}, "LIVE_CALL_CAP"),
    ],
)
def test_contradictory_config_fails_fast(monkeypatch, env, message):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError, match=message):
        make().check()


def test_google_stt_is_explicit_only(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/sa.json")
    assert make().resolved_stt() == "fake"  # auto never picks google
    monkeypatch.setenv("STT_PROVIDER", "google")
    s = make()
    assert s.resolved_stt() == "google"
    s.check()


def test_provider_names_are_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", " FAKE ")
    assert make().llm_provider == "fake"


def test_invalid_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(ValueError):
        make()


def test_allowed_origins_accepts_comma_list(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8000, http://127.0.0.1:8000")
    assert make().allowed_origins == ["http://localhost:8000", "http://127.0.0.1:8000"]


def test_secrets_are_not_rendered(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    s = make()
    assert FAKE_KEY not in repr(s)
    assert FAKE_KEY not in str(s.model_dump())


def test_env_example_lists_every_setting_and_defaults_to_demo():
    from pathlib import Path

    from dotenv import dotenv_values

    example = Path(__file__).resolve().parents[2] / ".env.example"
    keys = dotenv_values(example)
    missing = [name.upper() for name in Settings.model_fields if name.upper() not in keys]
    assert not missing, f".env.example is missing {missing}"
    assert keys["OPENAI_API_KEY"] == "" and keys["LLM_PROVIDER"] == "auto" and keys["STT_PROVIDER"] == "auto"
    s = Settings(_env_file=example)  # type: ignore[call-arg]
    s.check()
    assert s.overall_mode() == "demo"


# ------------------------------------------------- .env parsing (Docker Compose vs python-dotenv)
ENV_LINE = re.compile(r"^[A-Z][A-Z0-9_]*=[^\s#]*$")


def test_env_example_has_no_inline_comments():
    """Compose's env_file reads ``KEY=   # note`` as the value ``# note`` (python-dotenv drops
    it), which broke ``make smoke-live``. Every line is blank, a comment, or a bare KEY=value."""
    example = Path(__file__).resolve().parents[2] / ".env.example"
    bad = [
        f"{number}: {line}"
        for number, line in enumerate(example.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip() and not line.startswith("#") and not ENV_LINE.match(line)
    ]
    assert bad == [], "inline comment or stray whitespace in .env.example:\n" + "\n".join(bad)


def test_env_example_read_literally_like_compose_is_still_demo_safe(monkeypatch):
    """Each value exactly as written (no comment stripping) must give the same settings."""
    example = Path(__file__).resolve().parents[2] / ".env.example"
    from dotenv import dotenv_values

    literal = {}
    for line in example.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            literal[key] = value
    assert literal == dotenv_values(example)
    for key, value in literal.items():
        monkeypatch.setenv(key, value)
    s = make()
    s.check()
    assert s.overall_mode() == "demo"


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_whitespace_only_values_are_unset(monkeypatch, value):
    for key in ("FIREBASE_CREDENTIALS_JSON", "AUTH_SECRET", "LLM_TIMEOUT_SECONDS", "OPENAI_MODEL", "STORE_BACKEND"):
        monkeypatch.setenv(key, value)
    s = make()
    assert s.firebase_credentials_json is None and s.auth_secret is None
    assert s.llm_timeout_seconds == Settings.model_fields["llm_timeout_seconds"].default
    assert s.openai_model == Settings.model_fields["openai_model"].default
    s.check()


def test_a_comment_read_as_a_value_is_unset_with_a_warning(monkeypatch, caplog):
    """The exact live failure: FIREBASE_CREDENTIALS_JSON='# inline service-account JSON ...'
    made check() fail with 'FIREBASE_CREDENTIALS_JSON is not valid JSON'."""
    comment = "# inline service-account JSON (or GOOGLE_APPLICATION_CREDENTIALS + FIREBASE_PROJECT_ID)"
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", comment)
    monkeypatch.setenv("AUTH_SECRET", "# demo-login signing secret")
    monkeypatch.setenv("LLM_PROVIDER", "  # auto | fake | openai")
    with caplog.at_level(logging.WARNING, logger="petpulse.config"):
        s = make()
    s.check()
    assert s.firebase_credentials_json is None and s.auth_secret is None and s.llm_provider == "auto"
    assert s.resolved_store() != "firestore"
    warned = " ".join(r.getMessage() for r in caplog.records)
    for key in ("FIREBASE_CREDENTIALS_JSON", "AUTH_SECRET", "LLM_PROVIDER"):
        assert key in warned
    assert "service-account" not in warned and "signing" not in warned  # names the key, not the value


def test_real_values_are_kept_and_trimmed(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "  gpt-5.4-mini-2026-03-17  ")
    monkeypatch.setenv("LIVE_CALL_CAP", " 4 ")
    s = make()
    assert s.openai_model == "gpt-5.4-mini-2026-03-17" and s.live_call_cap == 4
