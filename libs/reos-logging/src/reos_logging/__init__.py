"""reos-logging — DAEP / RE-OS shared structured logging framework.

Authority: WP-002-03 | LLD v2.0 §2.3 (Structured Logging Standard),
LLD v2.0 §2.2 (structured-log call pattern used by the exception handler).

Usage::

    from reos_logging import configure_logging, get_logger

    configure_logging(settings)          # once, at service startup
    log = get_logger(__name__)
    log.info("topology.import_started", version_id=42)
"""

from reos_logging.logger import (
    DEFAULT_REDACTED_FIELDS,
    configure_logging,
    get_logger,
)

__all__ = ["DEFAULT_REDACTED_FIELDS", "configure_logging", "get_logger"]
