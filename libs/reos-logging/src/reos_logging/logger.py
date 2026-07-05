"""Pre-configured Structlog processor chain and logger factory.

Authority: WP-002-03 | LLD v2.0 §2.3 (Structured Logging Standard).

Processor chain (§15): ``merge_contextvars`` → redaction → ``TimeStamper(iso)``
→ ``add_log_level`` → renderer. The renderer is ``JSONRenderer`` in every
environment except ``local``, where a human-readable console renderer is used
(Roadmap v1.0 §11.2 — local dev optimizes for fast iteration).

Request-ID correlation: bind per-request context from FastAPI middleware via
``structlog.contextvars.bind_contextvars(request_id=...)``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, MutableMapping
from typing import Any

import structlog
from reos_config import ReosBaseSettings

__all__ = ["DEFAULT_REDACTED_FIELDS", "configure_logging", "get_logger"]

#: Sensitive event-dict keys masked by the redaction processor (WP-002-03 §25).
#: Extensible via ``configure_logging(extra_redacted_fields=...)`` — do not
#: rely on this list covering every future sensitive field name (§35).
DEFAULT_REDACTED_FIELDS: frozenset[str] = frozenset(
    {"password", "token", "secret", "authorization"}
)

_REDACTED = "***REDACTED***"


def _build_redaction_processor(
    redacted_fields: frozenset[str],
) -> structlog.types.Processor:
    """Return a processor that masks values of sensitive keys (case-insensitive)."""

    def redact(
        logger: logging.Logger | None,
        method_name: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        for key in event_dict:
            if key.lower() in redacted_fields:
                event_dict[key] = _REDACTED
        return event_dict

    return redact


def configure_logging(
    settings: ReosBaseSettings,
    *,
    extra_redacted_fields: Iterable[str] = (),
) -> None:
    """Configure Structlog once at service startup.

    Binds ``service_name`` and ``environment`` (from ``settings``, WP-002-01)
    into every log line via contextvars, sets the minimum level from
    ``settings.log_level``, and selects the renderer by environment.

    :param settings: the service's ``ReosBaseSettings`` instance.
    :param extra_redacted_fields: additional sensitive key names to mask,
        merged with :data:`DEFAULT_REDACTED_FIELDS`.
    """
    redacted = DEFAULT_REDACTED_FIELDS | {f.lower() for f in extra_redacted_fields}

    renderer: structlog.types.Processor
    if settings.environment == "local":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _build_redaction_processor(redacted),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(
        service_name=settings.service_name,
        environment=settings.environment,
    )


def get_logger(name: str) -> structlog.types.FilteringBoundLogger:
    """Return a Structlog logger pre-bound with service context.

    Call :func:`configure_logging` once at startup before first use; loggers
    obtained earlier still pick up the configuration lazily.
    """
    logger: structlog.types.FilteringBoundLogger = structlog.get_logger(name)
    return logger
