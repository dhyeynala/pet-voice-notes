"""Typed application settings.

Every setting has a demo-safe default, so the app starts with no environment at all.
Providers default to ``auto``: the real OpenAI adapter is used when ``OPENAI_API_KEY`` is
set, the deterministic fake otherwise. An explicit ``fake`` / ``openai`` / ``google`` always
wins over ``auto``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from pydantic import PrivateAttr, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from petpulse.llm.config import DEFAULT_TIMEOUT_SECONDS, OPENAI_PINNED_MODEL, is_dated_snapshot

LLMChoice = Literal["auto", "fake", "openai"]
STTChoice = Literal["auto", "fake", "openai", "google"]
ResolvedLLM = Literal["fake", "openai"]
ResolvedSTT = Literal["fake", "openai", "google"]
FakeLLMMode = Literal["normal", "invalid_once", "truncate", "fail"]
StoreBackendChoice = Literal["auto", "json", "firestore"]
AuthProviderChoice = Literal["auto", "demo", "firebase"]
ResolvedStore = Literal["json", "memory", "firestore"]
ResolvedAuth = Literal["demo", "firebase"]


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

    # Firebase track (G): optional Firebase mode, kept as its own block (see docs/firebase.md).
    # ``auto`` uses Firebase only when it is configured; otherwise the local store / demo login.
    store_backend: StoreBackendChoice = "auto"  # auto | json (the local STORE) | firestore
    auth_provider: AuthProviderChoice = "auto"  # auto | demo | firebase (needs credentials + web API key)
    firebase_project_id: Optional[str] = None
    firebase_credentials_json: Optional[SecretStr] = None  # inline service-account JSON (else GOOGLE_APPLICATION_CREDENTIALS)
    firebase_storage_bucket: Optional[str] = None  # record PDFs go to Firebase Storage (Firestore store only)
    firebase_web_api_key: Optional[str] = None  # browser SDK config; public by design, not a secret
    firebase_auth_domain: Optional[str] = None  # default: <project>.firebaseapp.com
    _firebase_creds: Optional[tuple[Optional[dict[str, Any]], Optional[str]]] = PrivateAttr(default=None)

    @field_validator(
        "firebase_project_id",
        "firebase_credentials_json",
        "firebase_storage_bucket",
        "firebase_web_api_key",
        "firebase_auth_domain",
        mode="before",
    )
    @classmethod
    def _firebase_blank_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("store_backend", "auth_provider", mode="before")
    @classmethod
    def _firebase_normalise_choice(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower() or "auto"
        return value

    seed_on_start: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
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

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.strip().upper() or "INFO" if isinstance(value, str) else value

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
        problems = self._auth_problems() + self._firebase_problems()
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

    # ------------------------------------------------------------------ Firebase (track G)
    def firebase_credentials(self) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """``(service_account_info, problem)``; both ``None`` when no Firebase credentials are given.

        ``FIREBASE_CREDENTIALS_JSON`` (inline JSON) wins. ``GOOGLE_APPLICATION_CREDENTIALS`` (a file)
        counts only together with ``FIREBASE_PROJECT_ID``, so configuring Google STT alone never
        switches the app to Firebase.
        """
        if self._firebase_creds is None:
            self._firebase_creds = self._load_firebase_credentials()
        return self._firebase_creds

    def _load_firebase_credentials(self) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        if self.firebase_credentials_json is not None:
            return _service_account(self.firebase_credentials_json.get_secret_value(), "FIREBASE_CREDENTIALS_JSON")
        if self.google_application_credentials and self.firebase_project_id:
            path = Path(self.google_application_credentials)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                return None, f"GOOGLE_APPLICATION_CREDENTIALS file is not readable ({type(exc).__name__})"
            info, problem = _service_account(text, "GOOGLE_APPLICATION_CREDENTIALS")
            if info is not None and info.get("project_id") != self.firebase_project_id:
                # A key for another project (e.g. Google STT's) is not a Firebase credential.
                return None, None
            return info, problem
        return None, None

    def firebase_project(self) -> Optional[str]:
        info, _ = self.firebase_credentials()
        if self.firebase_project_id:
            return self.firebase_project_id
        return str(info["project_id"]) if info else None

    @property
    def firebase_admin_ready(self) -> bool:
        """Valid service-account credentials and a project id: enough for Firestore/Storage."""
        info, problem = self.firebase_credentials()
        return info is not None and problem is None and self.firebase_project() is not None

    def resolved_store(self) -> ResolvedStore:
        if self.store_backend == "firestore" or (self.store_backend == "auto" and self.firebase_admin_ready):
            return "firestore"
        return self.store

    def resolved_auth(self) -> ResolvedAuth:
        if self.auth_provider == "firebase":
            return "firebase"
        if self.auth_provider == "auto" and self.firebase_admin_ready and self.firebase_web_api_key is not None:
            return "firebase"
        return "demo"

    def resolved_blobs(self) -> Literal["local", "firebase"]:
        return "firebase" if self.resolved_store() == "firestore" and self.firebase_storage_bucket else "local"

    def firebase_web_config(self) -> Optional[dict[str, str]]:
        """The public browser config, only when sign-in goes through Firebase."""
        project = self.firebase_project()
        if self.resolved_auth() != "firebase" or project is None or self.firebase_web_api_key is None:
            return None
        config = {
            "apiKey": self.firebase_web_api_key,
            "authDomain": self.firebase_auth_domain or f"{project}.firebaseapp.com",
            "projectId": project,
        }
        emulator = firebase_auth_emulator()
        if emulator and project.startswith("demo-"):
            config["authEmulatorUrl"] = f"http://{emulator}"  # local Auth emulator (development only)
        return config

    def _firebase_problems(self) -> list[str]:
        """Firebase-track checks (G). Forced Firebase without what it needs fails; auto never does."""
        problems: list[str] = []
        info, cred_problem = self.firebase_credentials()
        if cred_problem is not None:
            # Credentials were given but are unusable: fail rather than silently run in demo mode.
            problems.append(f"Firebase credentials are invalid: {cred_problem}.")
        if self.store_backend == "firestore" and info is None and cred_problem is None:
            problems.append(
                "STORE_BACKEND=firestore requires service-account credentials: FIREBASE_CREDENTIALS_JSON, "
                "or GOOGLE_APPLICATION_CREDENTIALS together with FIREBASE_PROJECT_ID."
            )
        if info is not None and self.firebase_project_id and info.get("project_id") != self.firebase_project_id:
            problems.append("FIREBASE_PROJECT_ID does not match the project_id in the service-account credentials.")
        if self.auth_provider == "firebase":
            # The Admin SDK needs a service account even just to verify ID tokens (without one it
            # probes Application Default Credentials and every request fails).
            if info is None and cred_problem is None:
                problems.append(
                    "AUTH_PROVIDER=firebase requires service-account credentials: FIREBASE_CREDENTIALS_JSON, "
                    "or GOOGLE_APPLICATION_CREDENTIALS together with FIREBASE_PROJECT_ID."
                )
            if self.firebase_web_api_key is None:
                problems.append("AUTH_PROVIDER=firebase requires FIREBASE_WEB_API_KEY (the browser SDK needs it to sign in).")
        emulator = firebase_auth_emulator()
        project = self.firebase_project() or ""
        if emulator and self.resolved_auth() == "firebase" and not project.startswith("demo-"):
            # The Admin SDK accepts unsigned tokens when this is set; never allow it for a real project.
            problems.append("FIREBASE_AUTH_EMULATOR_HOST is only allowed with an emulator project id (demo-*).")
        uses_firebase = self.resolved_store() == "firestore" or self.resolved_auth() == "firebase"
        if uses_firebase and not firebase_admin_installed():
            problems.append(
                "Firebase mode needs the optional firebase-admin package: pip install -r requirements/live.txt "
                "(Docker: INSTALL_LIVE=true docker compose build)."
            )
        return problems


def firebase_auth_emulator() -> Optional[str]:
    """``FIREBASE_AUTH_EMULATOR_HOST`` (``host:port``), read by the Admin SDK from the process env."""
    value = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
    return value or None


def firebase_admin_installed() -> bool:
    """True when ``firebase_admin`` can be imported; never imports it."""
    if "firebase_admin" in sys.modules:
        return sys.modules["firebase_admin"] is not None
    try:
        return importlib.util.find_spec("firebase_admin") is not None
    except (ImportError, ValueError):
        return False


_SERVICE_ACCOUNT_FIELDS = ("project_id", "client_email", "private_key")


def _service_account(text: str, source: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Parse a service-account JSON document. The problem text never echoes the contents."""
    try:
        info = json.loads(text)
    except ValueError:
        return None, f"{source} is not valid JSON"
    if not isinstance(info, dict) or info.get("type") != "service_account":
        return None, f'{source} is not a service-account key (expected "type": "service_account")'
    missing = [key for key in _SERVICE_ACCOUNT_FIELDS if not isinstance(info.get(key), str) or not info[key].strip()]
    if missing:
        return None, f"{source} is missing {', '.join(missing)}"
    return info, None
