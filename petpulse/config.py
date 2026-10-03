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

LLMChoice = Literal["auto", "fake", "openai"]
STTChoice = Literal["auto", "fake", "openai", "google"]
ResolvedLLM = Literal["fake", "openai"]
ResolvedSTT = Literal["fake", "openai", "google"]


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
    google_application_credentials: Optional[str] = None
    auth_secret: Optional[SecretStr] = None  # generated at startup when unset (auth track)
    seed_on_start: bool = True
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:8000"]
    live_call_cap: int = 6

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
        problems = []
        if self.resolved_llm() == "openai" and not self.has_openai_key:
            problems.append("LLM_PROVIDER=openai requires OPENAI_API_KEY (or use LLM_PROVIDER=auto|fake).")
        stt = self.resolved_stt()
        if stt == "openai" and not self.has_openai_key:
            problems.append("STT_PROVIDER=openai requires OPENAI_API_KEY (or use STT_PROVIDER=auto|fake).")
        if stt == "google" and not self.google_application_credentials:
            problems.append("STT_PROVIDER=google requires GOOGLE_APPLICATION_CREDENTIALS (path to a service-account JSON).")
        if self.live_call_cap < 0:
            problems.append("LIVE_CALL_CAP must be >= 0.")
        if problems:
            raise ConfigError("Invalid PetPulse configuration:\n  - " + "\n  - ".join(problems))

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
