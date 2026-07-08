"""Logging helpers for the ADMS topology import package."""

from __future__ import annotations

import logging

from .config import Settings


def configure_logging(level: str | None = None) -> logging.Logger:
    """Configure package logging and return the package logger.

    The helper is intentionally explicit; importing the package does not mutate
    global logging configuration.
    """

    logging.basicConfig(
        level=getattr(logging, (level or Settings.LOG_LEVEL).upper(), logging.INFO),
        format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
    )
    return logging.getLogger("diep-adms-topology-import")
