"""Structured logging configuration — mirrors reos-logging EPIC-002 pattern.

PII exclusion (AUD-SEC-008): actor_ip_address, actor_user_agent, actor_username
MUST NOT appear in any log line at any level. Enforced at call site — this module
provides the shared configure() call for consistency.
"""

from __future__ import annotations

import logging
from typing import cast

import structlog


def configure(log_level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return cast(structlog.BoundLogger, structlog.get_logger(name))
