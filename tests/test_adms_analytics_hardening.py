"""WP-012-07 — Production Analytics Hardening validation suite (OA-142/143).

49 tests across 7 classes, one class per OA objective.

  TestOA137StructuredLogging       — OA-137 structured logging (7 tests)
  TestOA138PrometheusMetrics       — OA-138 Prometheus metrics (7 tests)
  TestOA139VoltVARDeviceGuard      — OA-139 VVO device-count guard (7 tests)
  TestOA140BoundaryValidation      — OA-140 boundary contract validation (7 tests)
  TestOA141DocumentationComplete   — OA-141 documentation completeness (7 tests)
  TestOA142RegressionValidation    — OA-142 regression validation (7 tests)
  TestOA143FinalValidation         — OA-143 final hardening validation (7 tests)

Total: 49 tests; 48 counted in regression (1 meta-test excluded by -k "not analytics_regression").
"""

from __future__ import annotations

import logging
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


# ------------------------------------------------------------------ #
# Shared network fixtures                                              #
# ------------------------------------------------------------------ #


def _minimal_network():
    """Minimal 1-bus network used across multiple test classes."""
    nodes = [
        {
            "node_id": "SUB",
            "node_type": "substation",
            "nominal_kv": 11.0,
            "phases": "ABC",
            "name": "SUB",
            "base_load_kw": 0.0,
            "base_load_kvar": 0.0,
            "attrs": {},
        },
        {
            "node_id": "BUS1",
            "node_type": "bus",
            "nominal_kv": 11.0,
            "phases": "ABC",
            "name": "BUS1",
            "base_load_kw": 50.0,
            "base_load_kvar": 20.0,
            "attrs": {},
        },
    ]
    edges = [
        {
            "edge_id": "L1",
            "from_node": "SUB",
            "to_node": "BUS1",
            "edge_type": "line",
            "is_closed": True,
            "is_switchable": False,
            "normally_closed": True,
            "resistance_r_ohm": 0.3,
            "reactance_x_ohm": 0.15,
            "phases": "ABC",
            "ampacity_a": 200.0,
            "length_km": 1.0,
            "attrs": {},
        }
    ]
    return nodes, edges


def _minimal_se_result(nodes):
    """Minimal SE result whose node_id set matches nodes."""
    return {
        "method": "WLS",
        "nodes": [
            {
                "node_id": n["node_id"],
                "energized": True,
                "estimated_p_kw": n.get("base_load_kw", 0.0),
                "estimated_q_kvar": n.get("base_load_kvar", 0.0),
                "v_pu": 1.0,
            }
            for n in nodes
        ],
        "branches": [],
        "bad_data": None,
        "max_normalized_residual": 0.1,
        "reference_node": "SUB",
    }


def _device(device_id: str, node_id: str = "BUS1") -> dict:
    return {
        "device_id": device_id,
        "node_id": node_id,
        "phases": "ABC",
        "q_injection_kvar": 60.0,
        "device_type": "capacitor",
    }


# ------------------------------------------------------------------ #
# OA-137 — Structured Analytics Logging                               #
# ------------------------------------------------------------------ #


class TestOA137StructuredLogging:
    """Structured logging emitted at service boundaries (OA-137)."""

    def test_se_service_start_log_emitted(self, caplog):
        """StateEstimationService.estimate emits a [service.start] record."""
        from services.adms_grid_analytics.state_estimation_service import StateEstimationService

        nodes, edges = _minimal_network()
        with caplog.at_level(logging.INFO, logger="diep.analytics"):
            StateEstimationService().estimate(nodes, edges)
        start_msgs = [r.message for r in caplog.records if "[service.start]" in r.message]
        assert start_msgs, "No [service.start] record found for StateEstimationService.estimate"

    def test_se_service_complete_log_emitted(self, caplog):
        """StateEstimationService.estimate emits a [service.complete] record."""
        from services.adms_grid_analytics.state_estimation_service import StateEstimationService

        nodes, edges = _minimal_network()
        with caplog.at_level(logging.INFO, logger="diep.analytics"):
            StateEstimationService().estimate(nodes, edges)
        complete_msgs = [r.message for r in caplog.records if "[service.complete]" in r.message]
        assert complete_msgs, "No [service.complete] record found"

    def test_pf_service_start_log_emitted(self, caplog):
        """PowerFlowService.solve emits a [service.start] record."""
        from services.adms_grid_analytics.power_flow_service import PowerFlowService

        nodes, edges = _minimal_network()
        loads = {
            "BUS1": {
                "a": complex(50 / 3, 20 / 3),
                "b": complex(50 / 3, 20 / 3),
                "c": complex(50 / 3, 20 / 3),
            }
        }
        with caplog.at_level(logging.INFO, logger="diep.analytics"):
            PowerFlowService().solve(nodes, edges, loads=loads)
        assert any("[service.start]" in r.message for r in caplog.records)

    def test_ca_service_start_log_emitted(self, caplog):
        """ContingencyAnalysisService.analyze emits a [service.start] record."""
        from services.adms_grid_analytics.contingency_analysis_service import (
            ContingencyAnalysisService,
        )

        nodes, edges = _minimal_network()
        with caplog.at_level(logging.INFO, logger="diep.analytics"):
            ContingencyAnalysisService().analyze(nodes, edges)
        assert any("[service.start]" in r.message for r in caplog.records)

    def test_vvo_service_start_log_emitted(self, caplog):
        """VoltVARService.optimize emits a [service.start] record."""
        from services.adms_grid_analytics.volt_var_service import VoltVARService

        nodes, edges = _minimal_network()
        with caplog.at_level(logging.INFO, logger="diep.analytics"):
            VoltVARService().optimize(nodes, edges, devices=[_device("CAP1")])
        assert any("[service.start]" in r.message for r in caplog.records)

    def test_ana_service_start_log_emitted(self, caplog):
        """AdvancedNetworkAnalyticsService.analyze_loading emits [service.start]."""
        from services.adms_grid_analytics.advanced_network_analytics_service import (
            AdvancedNetworkAnalyticsService,
        )

        nodes, edges = _minimal_network()
        with caplog.at_level(logging.INFO, logger="diep.analytics"):
            AdvancedNetworkAnalyticsService().analyze_loading(nodes, edges)
        assert any("[service.start]" in r.message for r in caplog.records)

    def test_service_failure_log_emitted(self, caplog):
        """When SE raises ValueError (bad topology) a [service.failure] record is emitted."""
        from services.adms_grid_analytics.state_estimation_service import StateEstimationService

        # Empty nodes list → no substation → topology validation fails
        with caplog.at_level(logging.WARNING, logger="diep.analytics"):
            with pytest.raises(ValueError):
                StateEstimationService().estimate([], [])
        failure_msgs = [r.message for r in caplog.records if "[service.failure]" in r.message]
        assert failure_msgs, "No [service.failure] record found after topology ValueError"


# ------------------------------------------------------------------ #
# OA-138 — Prometheus Analytics Metrics                               #
# ------------------------------------------------------------------ #


class TestOA138PrometheusMetrics:
    """Prometheus-compatible metrics present with no-op fallback (OA-138)."""

    def test_analytics_metrics_has_all_required_attributes(self):
        """AnalyticsMetrics exposes every metric attribute required by OA-138."""
        from services.adms_grid_analytics._observability import AnalyticsMetrics

        try:
            from prometheus_client import CollectorRegistry

            m = AnalyticsMetrics(registry=CollectorRegistry())
        except ImportError:
            m = AnalyticsMetrics()
        required = [
            "requests_total",
            "request_duration_seconds",
            "convergence_failures_total",
            "topology_validation_failures_total",
            "boundary_validation_failures_total",
            "vvo_guard_rejections_total",
            "vvo_configurations_evaluated_total",
        ]
        for attr in required:
            assert hasattr(m, attr), f"AnalyticsMetrics missing attribute: {attr}"

    def test_noop_metric_api_complete(self):
        """_NoOpMetric supports the full prometheus_client Counter/Histogram/Gauge API."""
        from services.adms_grid_analytics._observability import _NoOpMetric

        noop = _NoOpMetric()
        noop.inc()
        noop.inc(2.5)
        noop.observe(0.003)
        noop.set(42.0)
        chained = noop.labels(service="X", method="Y")
        chained.inc()

    def test_record_start_returns_float(self):
        """record_start returns a positive float (monotonic timer)."""
        from services.adms_grid_analytics._observability import record_start

        t0 = record_start("StateEstimationService", "estimate", node_count=2, edge_count=1)
        assert isinstance(t0, float)
        assert t0 > 0

    def test_record_complete_does_not_raise(self):
        """record_complete with a fresh AnalyticsMetrics instance does not raise."""
        import time

        from services.adms_grid_analytics._observability import AnalyticsMetrics, record_complete

        try:
            from prometheus_client import CollectorRegistry

            metrics = AnalyticsMetrics(registry=CollectorRegistry())
        except ImportError:
            metrics = AnalyticsMetrics()
        t0 = time.monotonic()
        record_complete("PowerFlowService", "solve", t0, metrics=metrics)

    def test_record_failure_does_not_raise(self):
        """record_failure with a fresh AnalyticsMetrics instance does not raise."""
        import time

        from services.adms_grid_analytics._observability import AnalyticsMetrics, record_failure

        try:
            from prometheus_client import CollectorRegistry

            metrics = AnalyticsMetrics(registry=CollectorRegistry())
        except ImportError:
            metrics = AnalyticsMetrics()
        t0 = time.monotonic()
        record_failure(
            "ContingencyAnalysisService", "analyze", t0, ValueError("test"), metrics=metrics
        )

    def test_vvo_guard_rejection_path_does_not_raise_observability_error(self):
        """The VVO guard rejection path runs the metrics code without error."""
        from services.adms_grid_analytics.volt_var import optimize

        devices = [_device(f"D{i}", "BUS1") for i in range(5)]
        nodes, edges = _minimal_network()
        with pytest.raises(ValueError, match="max_devices"):
            optimize(nodes, edges, {}, devices, options={"max_devices": 3})

    def test_module_level_metrics_singleton_is_analytics_metrics(self):
        """The module-level _metrics singleton is an AnalyticsMetrics instance."""
        from services.adms_grid_analytics import _observability

        assert isinstance(_observability._metrics, _observability.AnalyticsMetrics)


# ------------------------------------------------------------------ #
# OA-139 — Volt/VAR Device-Count Guard                                #
# ------------------------------------------------------------------ #


class TestOA139VoltVARDeviceGuard:
    """VVO exhaustive-search guard bounds 2^n growth (OA-139)."""

    def test_zero_devices_accepted(self):
        """optimize with no devices succeeds (1 base-case evaluation, guard is not triggered)."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges = _minimal_network()
        result = optimize(nodes, edges, {}, [])
        assert result["devices_evaluated"] == 0
        # 2^0 = 1: the empty-state configuration is always evaluated once
        assert result["configurations_evaluated"] == 1

    def test_one_device_accepted_and_correct(self):
        """optimize with 1 device (2^1=2 evaluations) is accepted and returns optimal_state."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges = _minimal_network()
        devices = [_device("CAP1")]
        result = optimize(nodes, edges, {}, devices)
        assert "optimal_state" in result
        assert "CAP1" in result["optimal_state"]
        assert result["devices_evaluated"] == 1
        assert result["configurations_evaluated"] == 2

    def test_default_max_is_32(self):
        """The default device-count limit constant is 32."""
        from services.adms_grid_analytics.volt_var import _VVO_DEVICE_COUNT_DEFAULT_MAX

        assert _VVO_DEVICE_COUNT_DEFAULT_MAX == 32

    def test_default_warn_threshold_is_16(self):
        """The performance-warning threshold constant is 16."""
        from services.adms_grid_analytics.volt_var import _VVO_DEVICE_COUNT_WARN

        assert _VVO_DEVICE_COUNT_WARN == 16

    def test_exceeding_default_limit_raises_value_error(self):
        """33 devices (> default 32) raises ValueError before any PF evaluation."""
        from services.adms_grid_analytics.volt_var import optimize

        devices = [_device(f"D{i}") for i in range(33)]
        nodes, edges = _minimal_network()
        with pytest.raises(ValueError, match="max_devices"):
            optimize(nodes, edges, {}, devices)

    def test_custom_max_devices_option_rejects(self):
        """max_devices=2 in options rejects 3 devices with a deterministic message."""
        from services.adms_grid_analytics.volt_var import optimize

        devices = [_device(f"D{i}") for i in range(3)]
        nodes, edges = _minimal_network()
        with pytest.raises(ValueError) as exc_info:
            optimize(nodes, edges, {}, devices, options={"max_devices": 2})
        msg = str(exc_info.value)
        assert "3" in msg, "Error message should name the actual device count"
        assert "max_devices=2" in msg, "Error message should name the configured limit"

    def test_at_custom_limit_accepted(self):
        """Exactly max_devices devices (not exceeding) runs without guard error."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges = _minimal_network()
        devices = [_device(f"D{i}") for i in range(3)]
        result = optimize(nodes, edges, {}, devices, options={"max_devices": 3})
        assert result["devices_evaluated"] == 3
        assert result["configurations_evaluated"] == 2**3


# ------------------------------------------------------------------ #
# OA-140 — Boundary Contract Validation                               #
# ------------------------------------------------------------------ #


class TestOA140BoundaryValidation:
    """Boundary contract validation at service entry points (OA-140)."""

    def test_valid_nodes_edges_returns_none(self):
        """validate_nodes_edges with conformant inputs returns None (no error)."""
        from services.adms_grid_analytics._adapters import validate_nodes_edges

        nodes, edges = _minimal_network()
        result = validate_nodes_edges(nodes, edges)
        assert result is None

    def test_nodes_not_list_raises_type_error(self):
        """Passing a dict for nodes raises TypeError with an actionable message."""
        from services.adms_grid_analytics._adapters import validate_nodes_edges

        with pytest.raises(TypeError, match="nodes must be a list"):
            validate_nodes_edges({"node_id": "A"}, [])

    def test_edges_not_list_raises_type_error(self):
        """Passing None for edges raises TypeError."""
        from services.adms_grid_analytics._adapters import validate_nodes_edges

        nodes, _ = _minimal_network()
        with pytest.raises(TypeError, match="edges must be a list"):
            validate_nodes_edges(nodes, None)

    def test_node_missing_node_id_raises_value_error(self):
        """A node dict missing 'node_id' raises ValueError naming the index."""
        from services.adms_grid_analytics._adapters import validate_nodes_edges

        bad_nodes = [{"node_type": "substation", "nominal_kv": 11.0}]
        with pytest.raises(ValueError, match="nodes\\[0\\]"):
            validate_nodes_edges(bad_nodes, [])

    def test_edge_missing_from_node_raises_value_error(self):
        """An edge dict missing 'from_node' raises ValueError naming the field."""
        from services.adms_grid_analytics._adapters import validate_nodes_edges

        nodes, _ = _minimal_network()
        bad_edges = [{"edge_id": "E1", "to_node": "BUS1"}]
        with pytest.raises(ValueError, match="from_node"):
            validate_nodes_edges(nodes, bad_edges)

    def test_valid_se_result_returns_none(self):
        """validate_se_result with a conformant SE result returns None."""
        from services.adms_grid_analytics._adapters import validate_se_result

        nodes, _ = _minimal_network()
        se = _minimal_se_result(nodes)
        result = validate_se_result(se)
        assert result is None

    def test_se_result_missing_nodes_key_raises_value_error(self):
        """An SE result dict without a 'nodes' key raises ValueError."""
        from services.adms_grid_analytics._adapters import validate_se_result

        with pytest.raises(ValueError, match="'nodes'"):
            validate_se_result({"method": "WLS", "branches": []})


# ------------------------------------------------------------------ #
# OA-141 — Analytics Documentation Completeness                       #
# ------------------------------------------------------------------ #


class TestOA141DocumentationComplete:
    """Documentation completeness for feeder heuristic, weights, and contracts (OA-141)."""

    def test_feeder_loading_docstring_mentions_radial(self):
        """feeder_loading docstring documents the radial-topology assumption."""
        from services.adms_grid_analytics.network_loading import feeder_loading

        doc = feeder_loading.__doc__ or ""
        assert "radial" in doc.lower(), "feeder_loading docstring must mention 'radial'"

    def test_feeder_loading_docstring_mentions_single_source_limitation(self):
        """feeder_loading docstring documents the single-source limitation."""
        from services.adms_grid_analytics.network_loading import feeder_loading

        doc = feeder_loading.__doc__ or ""
        assert "single" in doc.lower() or "one source" in doc.lower() or "first" in doc.lower()

    def test_feeder_loading_docstring_documents_open_switch_behavior(self):
        """feeder_loading docstring documents open-switch partitioning."""
        from services.adms_grid_analytics.network_loading import feeder_loading

        doc = feeder_loading.__doc__ or ""
        assert "closed" in doc.lower() or "open" in doc.lower()

    def test_asset_criticality_module_documents_redistribution_formula(self):
        """asset_criticality module docstring contains the redistribution formula."""
        import services.adms_grid_analytics.asset_criticality as ac

        doc = ac.__doc__ or ""
        assert "redistribution" in doc.lower() or "redistribute" in doc.lower()
        assert "normalise" in doc.lower() or "normalized" in doc.lower() or "sum" in doc.lower()

    def test_contracts_module_has_migration_guide(self):
        """contracts module docstring contains a contract migration guide section."""
        import services.adms_grid_analytics.contracts as c

        doc = c.__doc__ or ""
        assert "migration" in doc.lower()
        assert "additive" in doc.lower() or "breaking" in doc.lower()

    def test_contract_version_is_1_2(self):
        """CONTRACT_VERSION was bumped to 1.2 for WP-012-07 additions."""
        from services.adms_grid_analytics.contracts import CONTRACT_VERSION

        assert CONTRACT_VERSION == "1.2", f"Expected 1.2, got {CONTRACT_VERSION}"

    def test_contract_version_docstring_records_12(self):
        """The CONTRACT_VERSION token docstring records the 1.2 history entry."""
        import inspect

        import services.adms_grid_analytics.contracts as c

        source = inspect.getsource(c)
        assert "1.2" in source
        assert "WP-012-07" in source


# ------------------------------------------------------------------ #
# OA-142 — Integration and Regression Validation                      #
# ------------------------------------------------------------------ #


class TestOA142RegressionValidation:
    """Hardening changes preserve all existing analytical outputs (OA-142)."""

    def test_se_service_output_fields_unchanged(self):
        """StateEstimationService.estimate still returns EstimationResult-shaped dict."""
        from services.adms_grid_analytics.state_estimation_service import StateEstimationService

        nodes, edges = _minimal_network()
        result = StateEstimationService().estimate(nodes, edges)
        for key in ("method", "nodes", "topology", "measurement_summary", "service"):
            assert key in result, f"SE result missing expected key: {key}"
        assert result["service"] == "StateEstimationService"

    def test_pf_service_output_fields_unchanged(self):
        """PowerFlowService.solve still returns PowerFlowResult-shaped dict."""
        from services.adms_grid_analytics.power_flow_service import PowerFlowService

        nodes, edges = _minimal_network()
        loads = {
            "BUS1": {
                "a": complex(50 / 3, 20 / 3),
                "b": complex(50 / 3, 20 / 3),
                "c": complex(50 / 3, 20 / 3),
            }
        }
        result = PowerFlowService().solve(nodes, edges, loads=loads)
        for key in ("method", "converged", "nodes", "branches", "service"):
            assert key in result, f"PF result missing expected key: {key}"
        assert result["service"] == "PowerFlowService"

    def test_ca_service_output_fields_unchanged(self):
        """ContingencyAnalysisService.analyze still returns ContingencyResult-shaped dict."""
        from services.adms_grid_analytics.contingency_analysis_service import (
            ContingencyAnalysisService,
        )

        nodes, edges = _minimal_network()
        result = ContingencyAnalysisService().analyze(nodes, edges)
        for key in ("method", "contingencies", "service", "impact_summary"):
            assert key in result, f"CA result missing expected key: {key}"
        assert result["service"] == "ContingencyAnalysisService"

    def test_vvo_service_output_fields_unchanged(self):
        """VoltVARService.optimize still returns VoltVARResult-shaped dict."""
        from services.adms_grid_analytics.volt_var_service import VoltVARService

        nodes, edges = _minimal_network()
        result = VoltVARService().optimize(nodes, edges, devices=[_device("CAP1")])
        for key in ("method", "optimal_state", "optimal_score", "service"):
            assert key in result, f"VVO result missing expected key: {key}"
        assert result["service"] == "VoltVARService"

    def test_ana_loading_output_fields_unchanged(self):
        """AdvancedNetworkAnalyticsService.analyze_loading returns expected keys."""
        from services.adms_grid_analytics.advanced_network_analytics_service import (
            AdvancedNetworkAnalyticsService,
        )

        nodes, edges = _minimal_network()
        result = AdvancedNetworkAnalyticsService().analyze_loading(nodes, edges)
        for key in ("feeders", "transformers", "source", "utilisation_ranking"):
            assert key in result, f"Loading report missing expected key: {key}"

    def test_se_determinism_preserved_after_instrumentation(self):
        """SE returns identical results on repeated calls with the same inputs."""
        from services.adms_grid_analytics.state_estimation_service import StateEstimationService

        nodes, edges = _minimal_network()
        svc = StateEstimationService()
        r1 = svc.estimate(nodes, edges)
        r2 = svc.estimate(nodes, edges)
        assert r1["method"] == r2["method"]
        assert r1["max_normalized_residual"] == r2["max_normalized_residual"]
        for n1, n2 in zip(r1["nodes"], r2["nodes"], strict=True):
            assert n1["node_id"] == n2["node_id"]
            assert n1.get("v_pu") == n2.get("v_pu")

    def test_contract_version_accessible_from_package(self):
        """contracts.CONTRACT_VERSION is importable from the package."""
        from services.adms_grid_analytics.contracts import CONTRACT_VERSION

        assert isinstance(CONTRACT_VERSION, str)
        major, minor = CONTRACT_VERSION.split(".")
        assert int(major) >= 1
        assert int(minor) >= 2


# ------------------------------------------------------------------ #
# OA-143 — Final Production Hardening Validation                      #
# ------------------------------------------------------------------ #


class TestOA143FinalValidation:
    """Confirm all PAR-004 blockers resolved; architecture frozen (OA-143)."""

    def test_blocker_01_resolved_logging_present(self):
        """BLOCKER-01: structured logging is present across the analytics service layer."""
        import services.adms_grid_analytics._observability as obs

        assert callable(obs.record_start)
        assert callable(obs.record_complete)
        assert callable(obs.record_failure)

    def test_blocker_02_resolved_metrics_present(self):
        """BLOCKER-02: AnalyticsMetrics has all seven required metric attributes."""
        from services.adms_grid_analytics._observability import AnalyticsMetrics

        try:
            from prometheus_client import CollectorRegistry

            m = AnalyticsMetrics(registry=CollectorRegistry())
        except ImportError:
            m = AnalyticsMetrics()
        attrs = vars(m)
        assert len(attrs) == 7, f"Expected 7 metric attrs, got {len(attrs)}: {list(attrs)}"

    def test_blocker_03_resolved_vvo_guard_present(self):
        """BLOCKER-03: VVO device-count guard constants and enforcement are in place."""
        from services.adms_grid_analytics.volt_var import (
            _VVO_DEVICE_COUNT_DEFAULT_MAX,
            _VVO_DEVICE_COUNT_WARN,
            optimize,
        )

        assert _VVO_DEVICE_COUNT_DEFAULT_MAX == 32
        assert _VVO_DEVICE_COUNT_WARN == 16
        # Guard fires before any PF work even on empty topology
        with pytest.raises(ValueError, match="max_devices"):
            optimize([], [], {}, [_device(f"D{i}") for i in range(33)])

    def test_observability_module_importable(self):
        """_observability module imports without error and exposes expected API."""
        from services.adms_grid_analytics import _observability

        assert hasattr(_observability, "AnalyticsMetrics")
        assert hasattr(_observability, "_metrics")
        assert hasattr(_observability, "record_start")
        assert hasattr(_observability, "record_complete")
        assert hasattr(_observability, "record_failure")

    def test_boundary_validation_functions_in_adapters(self):
        """validate_nodes_edges and validate_se_result are present in _adapters."""
        from services.adms_grid_analytics._adapters import validate_nodes_edges, validate_se_result

        assert callable(validate_nodes_edges)
        assert callable(validate_se_result)

    def test_architecture_frozen_no_new_engine_modules(self):
        """No new analytical engine modules introduced under WP-012-07."""
        import services.adms_grid_analytics as pkg

        expected_engines = {
            "linalg",
            "state_estimation",
            "powerflow",
            "reconfiguration",
            "contingency",
            "fault_location",
            "outage_inference",
            "outage_validation",
            "crew_dispatch",
            "volt_var",
            "network_loading",
            "capacity_analysis",
            "asset_criticality",
            "performance_analytics",
        }
        pkg_path = Path(pkg.__file__).parent
        actual_engines = {
            p.stem
            for p in pkg_path.glob("*.py")
            if not p.stem.startswith("_")
            and not p.stem.endswith("_service")
            and p.stem != "service"
            and p.stem != "contracts"
        }
        new = actual_engines - expected_engines
        assert not new, f"Unexpected new engine modules introduced: {new}"

    def test_analytics_regression_wp012_01_to_07(self):  # nosec B404/B603
        """Meta-test: full WP-012-01..07 non-meta regression must pass with 284 tests."""
        result = subprocess.run(  # nosec B603
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_analytics_architecture.py",
                "tests/test_adms_state_estimation_service.py",
                "tests/test_adms_power_flow_service.py",
                "tests/test_adms_contingency_analysis_service.py",
                "tests/test_adms_volt_var_service.py",
                "tests/test_adms_advanced_network_analytics_service.py",
                "tests/test_adms_analytics_hardening.py",
                "-k",
                "not analytics_regression",
                "-q",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        combined = result.stdout + result.stderr
        assert "284 passed" in combined, (
            f"Expected '284 passed' in regression output.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
