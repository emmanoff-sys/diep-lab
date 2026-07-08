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


def build_runtime_coordinator(
    *,
    context: ImportContext | None = None,
    publish_gateway=None,
    idempotency_store=None,
):
    """Build the runtime coordinator without opening external resources."""

    from .runtime import build_import_coordinator, build_runtime_dependencies

    resolved_context = context or build_import_context()
    dependencies = build_runtime_dependencies(
        settings=resolved_context.settings,
        logger=resolved_context.logger,
        metrics=resolved_context.metrics,
        publish_gateway=publish_gateway,
        idempotency_store=idempotency_store,
    )
    return build_import_coordinator(dependencies)
