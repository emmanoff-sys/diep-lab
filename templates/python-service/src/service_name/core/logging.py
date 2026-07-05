from __future__ import annotations

from reos_logging import configure_logging, get_logger

# Thin re-export of the shared logging library (WP-002-03).
# All configuration lives in libs/reos-logging — do not add processors here.


__all__ = ["configure_logging", "get_logger"]
