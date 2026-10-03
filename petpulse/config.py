"""Typed application settings.

Every setting has a demo-safe default, so the app starts with no environment at all.
Providers default to ``auto``: the real OpenAI adapter is used when ``OPENAI_API_KEY`` is
set, the deterministic fake otherwise. An explicit ``fake`` / ``openai`` / ``google`` always
wins over ``auto``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from petpulse.llm.config import DEFAULT_TIMEOUT_SECONDS, OPENAI_PINNED_MODEL, is_dated_snapshot

LLMChoice = Literal["auto", "fake", "openai"]
STTChoice = Literal["auto", "fake", "openai", "google"]
ResolvedLLM = Literal["fake", "openai"]
ResolvedSTT = Literal["fake", "openai", "google"]
FakeLLMMode = Literal["normal", "invalid_once", "truncate", "fail"]


class ConfigError(RuntimeError):
    """Raised at startup when the configuration asks for something it cannot have."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_mode: bool = True
    store: Literal["json", "memory"] = "json"
    data_dir: Path = Path("data")
    llm_provider: LLMChoice = "auto"
    stt_provider: STTChoice = "auto"
    openai_api_key: Optional[SecretStr] = None
    openai_model: str = OPENAI_PINNED_MODEL  # a dated snapshot; aliases are rejected by check()
    llm_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    fake_llm_mode: FakeLLMMode = "normal"  # failure drills for the fake provider (tests, demos)
    google_application_credentials: Optional[str] = None
    auth_secret: Optional[SecretStr] = None  # generated at startup when unset (auth track)

    # Auth track (A): kept as its own block so other tracks can append fields below.
    auth_token_ttl_minutes: int = 720  # demo login token lifetime

    seed_on_start: bool = True
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:8000"]
    live_call_cap: int = 6
    # Speech-to-text (voice track). The OpenAI model is a pinned dated snapshot.
    stt_openai_model: str = "gpt-4o-mini-transcribe-2025-12-15"
    stt_google_model: str = "default"
    stt_language: str = "en-US"
    stt_timeout_seconds: float = 30.0
    voice_max_bytes: int = 5 * 1024 * 1024
    voice_max_seconds: float = 60.0

    @field_validator("openai_api_key", "google_application_credentials", "auth_secret", mode="before")
    @classmethod
    def _blank_is_none(cls, value: Any) -> Any:
        # ``OPENAI_API_KEY=`` in .env (the documented default) means "not set".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("llm_provider", "stt_provider", "store", mode="before")
    @classmethod
    def _normalise_choice(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower() or "auto"
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # ------------------------------------------------------------------ resolution
    @property
    def has_openai_key(self) -> bool:
        return self.openai_api_key is not None and bool(self.openai_api_key.get_secret_value().strip())

    def resolved_llm(self) -> ResolvedLLM:
        if self.llm_provider == "auto":
            return "openai" if self.has_openai_key else "fake"
        return self.llm_provider

    def resolved_stt(self) -> ResolvedSTT:
        # Google is never picked by ``auto``: it needs STT_PROVIDER=google explicitly.
        if self.stt_provider == "auto":
            return "openai" if self.has_openai_key else "fake"
        return self.stt_provider

    def check(self) -> None:
        """Fail fast on contradictory configuration. Never falls back silently."""
        problems = self._auth_problems()
        if self.resolved_llm() == "openai" and not self.has_openai_key:
            problems.append("LLM_PROVIDER=openai requires OPENAI_API_KEY (or use LLM_PROVIDER=auto|fake).")
        stt = self.resolved_stt()
        if stt == "openai" and not self.has_openai_key:
            problems.append("STT_PROVIDER=openai requires OPENAI_API_KEY (or use STT_PROVIDER=auto|fake).")
        if stt == "google" and not self.google_application_credentials:
            problems.append("STT_PROVIDER=google requires GOOGLE_APPLICATION_CREDENTIALS (path to a service-account JSON).")
        if self.resolved_llm() == "openai" and not is_dated_snapshot(self.openai_model):
            problems.append(f"OPENAI_MODEL must be a dated snapshot such as {OPENAI_PINNED_MODEL}, not {self.openai_model!r}.")
        if not 0 < self.llm_timeout_seconds <= 120:
            problems.append("LLM_TIMEOUT_SECONDS must be in (0, 120].")
        if self.live_call_cap < 0:
            problems.append("LIVE_CALL_CAP must be >= 0.")
        if self.stt_timeout_seconds <= 0:
            problems.append("STT_TIMEOUT_SECONDS must be > 0.")
        if self.voice_max_bytes <= 0 or self.voice_max_seconds <= 0:
            problems.append("VOICE_MAX_BYTES and VOICE_MAX_SECONDS must be > 0.")
        if problems:
            raise ConfigError("Invalid PetPulse configuration:\n  - " + "\n  - ".join(problems))

    def _auth_problems(self) -> list[str]:
        """Auth-track checks (A), kept apart from ``check`` so other tracks' checks merge cleanly."""
        problems = []
        if self.auth_token_ttl_minutes <= 0:
            problems.append("AUTH_TOKEN_TTL_MINUTES must be > 0.")
        if "*" in self.allowed_origins:
            problems.append("ALLOWED_ORIGINS must list explicit origins; '*' is not allowed.")
        return problems

    def feature_modes(self) -> dict[str, dict[str, str]]:
        """Per-feature provider and Demo/Live mode, as reported by /api/health and the UI."""
        llm = self.resolved_llm()
        stt = self.resolved_stt()

        def entry(provider: str) -> dict[str, str]:
            return {"provider": provider, "mode": "demo" if provider == "fake" else "live"}

        return {
            "notes": entry(llm),
            "chat": entry(llm),
            "pdf_summary": entry(llm),
            "insights": entry(llm),
            "voice": entry(stt),
        }

    def overall_mode(self) -> str:
        modes = {feature["mode"] for feature in self.feature_modes().values()}
        if modes == {"demo"}:
            return "demo"
        if modes == {"live"}:
            return "live"
        return "mixed"
