"""WP-006-07 Objective 1 scaffolding tests."""

from __future__ import annotations

import importlib
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import import Settings, build_import_context  # noqa: E402
from services.adms_topology_import.config import _bool  # noqa: E402
from services.adms_topology_import.metrics import AdmsImportMetrics, _NoOpMetric  # noqa: E402


def test_package_exports_objective_one_context_builder():
    module = importlib.import_module("services.adms_topology_import")

    assert module.Settings is Settings
    assert module.build_import_context is build_import_context


def test_settings_snapshot_exposes_non_secret_defaults():
    assert Settings.snapshot() == {
        "service_name": "adms-topology-import",
        "contract_version": "1.0",
        "log_level": "INFO",
        "metrics_enabled": True,
    }


def test_bool_parser_accepts_common_true_values(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("ADMS_IMPORT_TEST_BOOL", raw)
        assert _bool("ADMS_IMPORT_TEST_BOOL", False) is True


def test_bool_parser_rejects_common_false_values(monkeypatch):
    for raw in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("ADMS_IMPORT_TEST_BOOL", raw)
        assert _bool("ADMS_IMPORT_TEST_BOOL", True) is False


def test_context_builder_uses_injected_dependencies():
    logger = logging.getLogger("test-adms-import")
    metrics = AdmsImportMetrics(enabled=False)

    context = build_import_context(logger=logger, metrics=metrics)

    assert context.settings is Settings
    assert context.logger is logger
    assert context.metrics is metrics


def test_context_builder_has_no_external_side_effects():
    context = build_import_context(metrics=AdmsImportMetrics(enabled=False))

    assert context.settings.CONTRACT_VERSION == "1.0"
    assert isinstance(context.metrics.imports_total, _NoOpMetric)
    assert isinstance(context.metrics.import_latency_seconds, _NoOpMetric)
    context.metrics.imports_total.labels(status="received").inc()
    context.metrics.import_latency_seconds.labels(stage="scaffold").observe(0.0)
