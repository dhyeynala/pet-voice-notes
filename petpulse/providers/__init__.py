"""AI provider seams: ``LLMProvider`` and ``STTProvider`` with deterministic fakes.

Live adapters import their SDKs lazily (inside methods), so importing this package never
imports ``openai`` or ``google.cloud.speech``.
"""

from petpulse.providers.llm import FakeLLM, LLMError, LLMProvider, OpenAILLM, RawCompletion, UnsupportedTask
from petpulse.providers.stt import FakeSTT, GoogleSTT, OpenAISTT, STTProvider, Transcription

__all__ = [
    "FakeLLM",
    "FakeSTT",
    "GoogleSTT",
    "LLMError",
    "LLMProvider",
    "OpenAILLM",
    "OpenAISTT",
    "RawCompletion",
    "STTProvider",
    "Transcription",
    "UnsupportedTask",
]
