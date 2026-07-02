from __future__ import annotations

# Thin re-export of the shared logging library (WP-002-03).
# All configuration lives in libs/reos-logging — do not add processors here.

from reos_logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
