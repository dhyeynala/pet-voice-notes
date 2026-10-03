"""Cross-cutting pieces every router and service uses.

- ``config``    typed settings (pydantic-settings) and provider auto-selection
- ``deps``      cached factories: get_settings / get_store / get_blobs / get_llm / get_stt
- ``auth``      demo bearer tokens (or Firebase ID tokens) and the ownership dependencies
- ``errors``    the one error envelope (``{"detail", "request_id"}``) and typed HTTP errors
- ``firebase``  the optional Firebase Admin app (imported lazily)
- ``timeutil``  time-zone aware parsing and local dates
"""
