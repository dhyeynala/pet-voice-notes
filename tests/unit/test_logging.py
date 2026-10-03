"""petpulse.core.logging: one handler on the petpulse logger tree, level from LOG_LEVEL."""

from __future__ import annotations

import logging

from petpulse.core.config import Settings
from petpulse.core.logging import ROOT_LOGGER, configure_logging


def test_configure_logging_is_idempotent_and_sets_the_level():
    logger = configure_logging("debug")
    configure_logging("WARNING")
    handlers = [h for h in logger.handlers if h.get_name() == "petpulse-stream"]
    assert logger.name == ROOT_LOGGER and len(handlers) == 1
    assert logger.level == logging.WARNING
    assert logging.getLogger("petpulse.llm").getEffectiveLevel() == logging.WARNING
    configure_logging("INFO")


def test_log_level_setting_is_normalised(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", " debug ")
    assert Settings().log_level == "DEBUG"
    monkeypatch.setenv("LOG_LEVEL", "")
    assert Settings().log_level == "INFO"
