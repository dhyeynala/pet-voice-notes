"""Logging for the ``petpulse.*`` loggers: one stream handler, level from ``LOG_LEVEL``.

Uvicorn configures its own loggers; this only touches the ``petpulse`` logger tree, so running
under uvicorn, pytest or a script gives the same format. Calling it again just updates the level.
"""

from __future__ import annotations

import logging

ROOT_LOGGER = "petpulse"
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_HANDLER_NAME = "petpulse-stream"


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Attach the stream handler once and set the level. Returns the ``petpulse`` logger."""
    logger = logging.getLogger(ROOT_LOGGER)
    if not any(h.get_name() == _HANDLER_NAME for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    return logger
