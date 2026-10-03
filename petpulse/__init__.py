"""PetPulse backend. ``uvicorn petpulse.app:app`` runs it; see CONTRIBUTING.md for the layout.

- ``app``        app factory: middleware, startup, router registration (no route bodies)
- ``core``       config, deps, auth, errors, logging, firebase, timeutil
- ``routers``    FastAPI routers, one module per domain
- ``services``   application logic: notes, chat, insights, events, records, voice, pets
- ``llm``        prompts, schemas, fake rules and the validating LLM client
- ``providers``  ``LLMProvider`` / ``STTProvider`` protocols, fakes, lazily imported live adapters
- ``store``      ``Store`` protocol, JSON/memory/Firestore stores and blob stores
- ``schemas``    shared request/response models
- ``seed``       demo data and the bundled voice/PDF samples
"""

__version__ = "0.1.0"
