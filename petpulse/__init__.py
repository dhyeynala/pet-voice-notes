"""PetPulse demo foundation: config, storage and AI provider seams.

Layout (see CONTRIBUTING.md for track ownership):

- ``config``     typed settings (pydantic-settings) and provider auto-selection
- ``deps``       cached factories: get_settings / get_store / get_blobs / get_llm / get_stt
- ``store``      ``Store`` protocol, ``MemoryStore`` / ``JsonFileStore``, ``LocalBlobStore``,
                 and a transitional Firestore-shaped facade for the legacy modules
- ``providers``  ``LLMProvider`` / ``STTProvider`` protocols, deterministic fakes,
                 lazily imported live adapters
- ``routers``    FastAPI routers; each track adds its own module here
"""

__version__ = "0.1.0"
