"""Configuration for the ADMS topology import foundation.

This module deliberately uses only the Python standard library so importing
the package cannot fail because optional runtime dependencies are absent.
"""

from __future__ import annotations

import os


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Environment-backed settings for WP-006-07 scaffolding.

    Objective 1 captures the stable configuration surface only. Authentication,
    transport, topology writes, and lifecycle state are introduced by later
    authorised objectives.
    """

    SERVICE_NAME = os.getenv("ADMS_IMPORT_SERVICE_NAME", "adms-topology-import")
    CONTRACT_VERSION = os.getenv("ADMS_IMPORT_CONTRACT_VERSION", "1.0")
    LOG_LEVEL = os.getenv("ADMS_IMPORT_LOG_LEVEL", "INFO")
    METRICS_ENABLED = _bool("ADMS_IMPORT_METRICS_ENABLED", True)

    @classmethod
    def snapshot(cls) -> dict[str, str | bool]:
        """Return non-secret operational settings for diagnostics/tests."""
        return {
            "service_name": cls.SERVICE_NAME,
            "contract_version": cls.CONTRACT_VERSION,
            "log_level": cls.LOG_LEVEL,
            "metrics_enabled": cls.METRICS_ENABLED,
        }
