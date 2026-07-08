"""Dependency container for ADMS topology import orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from .config import Settings
from .metrics import AdmsImportMetrics


class MetricsRecorder(Protocol):
    imports_total: object
    import_latency_seconds: object


@dataclass(frozen=True)
class ImportContext:
    """Runtime dependencies shared by later WP-006-07 objectives."""

    settings: type[Settings]
    logger: logging.Logger
    metrics: MetricsRecorder


def build_import_context(
    *,
    settings: type[Settings] = Settings,
    logger: logging.Logger | None = None,
    metrics: MetricsRecorder | None = None,
) -> ImportContext:
    """Build an import context without opening network or database resources."""

    return ImportContext(
        settings=settings,
        logger=logger or logging.getLogger("diep-adms-topology-import"),
        metrics=metrics or AdmsImportMetrics(enabled=settings.METRICS_ENABLED),
    )
