"""Engineering validation tests for WP-012-06 Advanced Network Analytics (OA-136).

Test matrix:
  TestOA131NetworkLoading          — OA-131 network loading analytics (7 tests)
  TestOA132CapacityAnalysis        — OA-132 capacity and constraint analysis (7 tests)
  TestOA133AssetCriticality        — OA-133 asset criticality engine (7 tests)
  TestOA134PerformanceAnalytics    — OA-134 operational performance analytics (7 tests)
  TestOA135PlatformIntegration     — OA-135 platform integration (7 tests)
  TestOA136EngineeringValidation   — OA-136 engineering validation (7 tests)

Total: 42 tests; 41 counted in regression (1 meta-test excluded by -k "not analytics_regression").
"""

from __future__ import annotations

import pathlib
import subprocess  # nosec B404
import sys
from copy import deepcopy

from services.adms_grid_analytics import (
    AdvancedNetworkAnalyticsService,
    GridAnalyticsService,
    asset_criticality,
    capacity_analysis,
    contingency,
    network_loading,
    performance_analytics,
    powerflow,
)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


# --------------------------------------------------------------------------- #
# Shared test fixtures                                                          #
# --------------------------------------------------------------------------- #

def _std_nodes() -> list[dict]:
    return [
        {"node_id": "SUB", "node_type": "substation", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "BUS1", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "BUS2", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "BUS3", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "BUS4", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
    ]


def _std_edges() -> list[dict]:
    return [
        {
            "edge_id": "L1", "from_node": "SUB", "to_node": "BUS1",
            "edge_type": "line", "is_closed": True,
            "resistance_r_ohm": 0.1, "reactance_x_ohm": 0.08,
            "ampacity_a": 200.0, "phases": "ABC",
        },
        {
            "edge_id": "L2", "from_node": "BUS1", "to_node": "BUS2",
            "edge_type": "line", "is_closed": True,
            "resistance_r_ohm": 0.1, "reactance_x_ohm": 0.08,
            "ampacity_a": 150.0, "phases": "ABC",
        },
        {
            "edge_id": "TX1", "from_node": "SUB", "to_node": "BUS3",
            "edge_type": "transformer", "is_closed": True,
            "resistance_r_ohm": 0.01, "reactance_x_ohm": 0.05,
            "rating_kw": 100.0, "phases": "ABC",
        },
        {
            "edge_id": "L3", "from_node": "BUS3", "to_node": "BUS4",
            "edge_type": "line", "is_closed": True,
            "resistance_r_ohm": 0.08, "reactance_x_ohm": 0.06,
            "ampacity_a": 100.0, "phases": "ABC",
        },
    ]


def _std_loads() -> dict:
    p2, q2 = 50 / 3, 20 / 3
    p4, q4 = 60 / 3, 25 / 3
    return {
        "BUS2": {"a": complex(p2, q2), "b": complex(p2, q2), "c": complex(p2, q2)},
        "BUS4": {"a": complex(p4, q4), "b": complex(p4, q4), "c": complex(p4, q4)},
    }


def _std_pf() -> dict:
    return powerflow.solve(_std_nodes(), _std_edges(), _std_loads())


def _std_ca() -> dict:
    return contingency.analyze(_std_nodes(), _std_edges(), _std_loads())


def _overloaded_pf() -> dict:
    """Synthetic PF result with one overloaded branch (loading_pct > 100)."""
    return {
        "converged": True,
        "total_loss_kw": 5.0,
        "violation_count": 2,
        "nodes": [
            {"node_id": "SUB", "v_avg_pu": 1.0, "unbalance_pct": 0.0, "energized": True},
            {"node_id": "BUS1", "v_avg_pu": 0.94, "unbalance_pct": 0.5, "energized": True},
        ],
        "branches": [
            {
                "edge_id": "L1", "from": "SUB", "to": "BUS1", "edge_type": "line",
                "s_kva": 250.0, "loss_kw": 3.0, "loading_pct": 125.0,
                "loading_basis": "ampacity",
            },
            {
                "edge_id": "L2", "from": "BUS1", "to": "BUS2", "edge_type": "line",
                "s_kva": 60.0, "loss_kw": 1.0, "loading_pct": 40.0,
                "loading_basis": "ampacity",
            },
            {
                "edge_id": "TX1", "from": "SUB", "to": "BUS3", "edge_type": "transformer",
                "s_kva": 30.0, "loss_kw": 0.5, "loading_pct": 30.0,
                "loading_basis": "rating",
            },
        ],
    }


def _low_voltage_pf() -> dict:
    """Synthetic PF result with a node outside the ±5 % voltage band."""
    return {
        "converged": True,
        "total_loss_kw": 2.0,
        "violation_count": 1,
        "nodes": [
            {"node_id": "SUB", "v_avg_pu": 1.0, "unbalance_pct": 0.0, "energized": True},
            {"node_id": "BUS1", "v_avg_pu": 1.02, "unbalance_pct": 0.1, "energized": True},
            {"node_id": "BUS2", "v_avg_pu": 0.90, "unbalance_pct": 2.0, "energized": True},
        ],
        "branches": [
            {
                "edge_id": "L1", "from": "SUB", "to": "BUS1", "edge_type": "line",
                "s_kva": 80.0, "loss_kw": 1.0, "loading_pct": 50.0,
                "loading_basis": "ampacity",
            },
        ],
    }


def _light_pf() -> dict:
    """PF result with minimal loads (all bus voltages stay within the ±5 % band)."""
    p, q = 5 / 3, 2 / 3
    loads = {
        "BUS2": {"a": complex(p, q), "b": complex(p, q), "c": complex(p, q)},
        "BUS4": {"a": complex(p, q), "b": complex(p, q), "c": complex(p, q)},
    }
    return powerflow.solve(_std_nodes(), _std_edges(), loads)


def _synthetic_vvo_result(violation_reduction: int = 1, loss_reduction: float = 2.5) -> dict:
    return {
        "method": "exhaustive",
        "optimal_state": {"CAP1": True},
        "optimal_score": 5.0,
        "base_case": {"violation_count": 2, "total_loss_kw": 10.0},
        "optimal_case": {
            "violation_count": 2 - violation_reduction,
            "total_loss_kw": 10.0 - loss_reduction,
        },
        "configurations": [{"state": {"CAP1": False}}, {"state": {"CAP1": True}}],
    }


# --------------------------------------------------------------------------- #
# OA-131 Network Loading Analytics                                              #
# --------------------------------------------------------------------------- #

class TestOA131NetworkLoading:

    def test_feeder_loading_returns_list(self):
        result = network_loading.feeder_loading(_std_nodes(), _std_edges(), _std_pf())
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_two_feeders_identified(self):
        result = network_loading.feeder_loading(_std_nodes(), _std_edges(), _std_pf())
        assert len(result) == 2
        head_edges = {f["feeder_head_edge"] for f in result}
        assert "L1" in head_edges
        assert "TX1" in head_edges

    def test_feeder_loading_sorted_desc_by_peak(self):
        result = network_loading.feeder_loading(_std_nodes(), _std_edges(), _std_pf())
        peaks = [f["peak_loading_pct"] for f in result if f["peak_loading_pct"] is not None]
        assert peaks == sorted(peaks, reverse=True)

    def test_transformer_loading_identified(self):
        result = network_loading.transformer_loading(_std_pf())
        edge_ids = [t["edge_id"] for t in result]
        assert "TX1" in edge_ids

    def test_source_loading_total_positive(self):
        result = network_loading.source_loading(_std_nodes(), _std_pf())
        assert result["source_id"] == "SUB"
        assert result["total_load_kva"] > 0.0
        assert result["feeder_count"] == 2

    def test_utilisation_ranking_sorted_desc(self):
        result = network_loading.utilisation_ranking(_std_pf())
        assert len(result) >= 1
        loadings = [r["loading_pct"] for r in result]
        assert loadings == sorted(loadings, reverse=True)

    def test_loading_report_keys(self):
        result = network_loading.loading_report(_std_nodes(), _std_edges(), _std_pf())
        for key in ("feeders", "transformers", "source", "utilisation_ranking",
                    "total_loss_kw", "violation_count", "converged"):
            assert key in result, f"missing key: {key}"


# --------------------------------------------------------------------------- #
# OA-132 Capacity and Constraint Analysis                                       #
# --------------------------------------------------------------------------- #

class TestOA132CapacityAnalysis:

    def test_remaining_capacity_sorted_asc(self):
        result = capacity_analysis.remaining_capacity(_std_pf())
        remaining = [r["remaining_pct"] for r in result]
        assert remaining == sorted(remaining)

    def test_remaining_capacity_excludes_unrated_branches(self):
        pf = deepcopy(_std_pf())
        for b in pf["branches"]:
            b.pop("loading_pct", None)
            b["loading_pct"] = None
        result = capacity_analysis.remaining_capacity(pf)
        assert result == []

    def test_bottlenecks_lower_threshold_returns_more(self):
        pf = _std_pf()
        bn_50 = capacity_analysis.bottlenecks(pf, threshold_pct=50.0)
        bn_80 = capacity_analysis.bottlenecks(pf, threshold_pct=80.0)
        assert len(bn_50) >= len(bn_80)

    def test_overloaded_branch_severity_critical(self):
        pf = _overloaded_pf()
        bns = capacity_analysis.bottlenecks(pf, threshold_pct=80.0)
        overloaded = [b for b in bns if b["overloaded"]]
        assert overloaded, "expected at least one overloaded branch"
        for b in overloaded:
            assert b["severity"] == "critical"

    def test_capacity_summary_keys(self):
        result = capacity_analysis.capacity_summary(_std_nodes(), _std_edges(), _std_pf())
        for key in (
            "total_branches", "rated_branches", "unrated_branches",
            "overloaded_count", "near_limit_count", "spare_count",
            "headroom_pct", "most_constrained_edge",
        ):
            assert key in result, f"missing key: {key}"

    def test_overloaded_count_in_summary(self):
        result = capacity_analysis.capacity_summary(_std_nodes(), _std_edges(), _overloaded_pf())
        assert result["overloaded_count"] >= 1

    def test_headroom_non_negative_on_healthy_network(self):
        result = capacity_analysis.capacity_summary(_std_nodes(), _std_edges(), _std_pf())
        if result["headroom_pct"] is not None:
            assert result["headroom_pct"] >= 0.0


# --------------------------------------------------------------------------- #
# OA-133 Asset Criticality Engine                                               #
# --------------------------------------------------------------------------- #

class TestOA133AssetCriticality:

    def test_rank_assets_returns_dict(self):
        result = asset_criticality.rank_assets(_std_nodes(), _std_edges(), _std_pf())
        expected = (
            "rankings", "weights_used", "total_assets", "most_critical", "dimensions_active"
        )
        for key in expected:
            assert key in result, f"missing key: {key}"

    def test_all_closed_edges_ranked(self):
        edges = _std_edges()
        closed_count = sum(1 for e in edges if e.get("is_closed", True))
        result = asset_criticality.rank_assets(_std_nodes(), edges, _std_pf())
        assert result["total_assets"] == closed_count
        assert len(result["rankings"]) == closed_count

    def test_feeder_head_high_topology_score(self):
        result = asset_criticality.rank_assets(_std_nodes(), _std_edges(), _std_pf())
        idx = {r["edge_id"]: r for r in result["rankings"]}
        # L1 serves BUS1 and BUS2 (2 downstream), L2 serves only BUS2 (1 downstream)
        assert idx["L1"]["topology_score"] > idx["L2"]["topology_score"]

    def test_determinism_three_runs(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        results = [
            asset_criticality.rank_assets(n, e, pf)["rankings"]
            for _ in range(3)
        ]
        assert results[0] == results[1] == results[2]

    def test_ca_result_activates_contingency_dimension(self):
        result = asset_criticality.rank_assets(
            _std_nodes(), _std_edges(), _std_pf(), ca_result=_std_ca()
        )
        assert "contingency" in result["dimensions_active"]

    def test_no_ca_contingency_score_zero(self):
        result = asset_criticality.rank_assets(_std_nodes(), _std_edges(), _std_pf())
        for r in result["rankings"]:
            assert r["contingency_score"] == 0.0

    def test_custom_weights_reflected(self):
        custom = {"topology": 0.5, "loading": 0.5, "contingency": 0.0, "customer": 0.0}
        result = asset_criticality.rank_assets(
            _std_nodes(), _std_edges(), _std_pf(), weights=custom
        )
        w = result["weights_used"]
        assert abs(w.get("topology", 0.0) - 0.5) < 1e-5
        assert abs(w.get("loading", 0.0) - 0.5) < 1e-5


# --------------------------------------------------------------------------- #
# OA-134 Operational Performance Analytics                                      #
# --------------------------------------------------------------------------- #

class TestOA134PerformanceAnalytics:

    def test_voltage_quality_keys(self):
        result = performance_analytics.voltage_profile_quality(_std_pf())
        for key in (
            "energised_nodes", "mean_v_pu", "std_v_pu", "min_v_pu", "max_v_pu",
            "nodes_in_band", "nodes_out_of_band", "band_compliance_pct", "max_unbalance_pct",
        ):
            assert key in result, f"missing key: {key}"

    def test_clean_network_all_in_band(self):
        result = performance_analytics.voltage_profile_quality(_light_pf())
        assert result["energised_nodes"] > 0
        assert result["nodes_out_of_band"] == 0
        assert result["band_compliance_pct"] == 100.0

    def test_out_of_band_voltage_detected(self):
        result = performance_analytics.voltage_profile_quality(_low_voltage_pf())
        assert result["nodes_out_of_band"] >= 1

    def test_loading_distribution_buckets_sum_to_rated(self):
        result = performance_analytics.loading_distribution(_std_pf())
        buckets = result["buckets"]
        total_in_buckets = sum(buckets.values())
        assert total_in_buckets == result["rated_branches"]

    def test_contingency_exposure_n1_secure_present(self):
        ca = _std_ca()
        result = performance_analytics.contingency_exposure(ca)
        assert "n1_secure" in result

    def test_vvo_violation_reduction_computed(self):
        vvo = _synthetic_vvo_result(violation_reduction=1)
        result = performance_analytics.optimisation_benefit(vvo)
        assert result["violation_reduction"] == 1
        assert result["optimisation_effective"] is True

    def test_overloaded_network_health_red(self):
        result = performance_analytics.operational_performance(
            _std_nodes(), _std_edges(), _overloaded_pf()
        )
        assert result["overall_health"] == "red"


# --------------------------------------------------------------------------- #
# OA-135 Platform Integration                                                   #
# --------------------------------------------------------------------------- #

class TestOA135PlatformIntegration:

    def test_network_loading_no_duplicate_powerflow_solve(self):
        import services.adms_grid_analytics.network_loading as mod
        assert "powerflow" not in vars(mod), "network_loading must not import powerflow"

    def test_capacity_analysis_no_duplicate_powerflow_solve(self):
        import services.adms_grid_analytics.capacity_analysis as mod
        assert "powerflow" not in vars(mod), "capacity_analysis must not import powerflow"

    def test_asset_criticality_no_duplicate_powerflow_solve(self):
        import services.adms_grid_analytics.asset_criticality as mod
        assert "powerflow" not in vars(mod), "asset_criticality must not import powerflow"

    def test_performance_analytics_no_duplicate_powerflow_solve(self):
        import services.adms_grid_analytics.performance_analytics as mod
        assert "powerflow" not in vars(mod), "performance_analytics must not import powerflow"

    def test_advanced_analytics_exported_from_package(self):
        from services.adms_grid_analytics import __all__ as pkg_all
        assert "AdvancedNetworkAnalyticsService" in pkg_all

    def test_gas_has_analyze_loading_method(self):
        assert hasattr(GridAnalyticsService, "analyze_loading")
        assert callable(GridAnalyticsService.analyze_loading)

    def test_advanced_network_analytics_service_has_all_methods(self):
        svc = AdvancedNetworkAnalyticsService()
        methods = ("analyze_loading", "analyze_capacity", "rank_criticality", "compute_performance")
        for method in methods:
            assert hasattr(svc, method), f"missing method: {method}"
            assert callable(getattr(svc, method)), f"not callable: {method}"


# --------------------------------------------------------------------------- #
# OA-136 Engineering Validation                                                 #
# --------------------------------------------------------------------------- #

class TestOA136EngineeringValidation:

    def test_loading_determinism(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        r1 = network_loading.loading_report(n, e, pf)
        r2 = network_loading.loading_report(n, e, pf)
        r3 = network_loading.loading_report(n, e, pf)
        assert r1 == r2 == r3

    def test_capacity_determinism(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        r1 = capacity_analysis.capacity_summary(n, e, pf)
        r2 = capacity_analysis.capacity_summary(n, e, pf)
        r3 = capacity_analysis.capacity_summary(n, e, pf)
        assert r1 == r2 == r3

    def test_criticality_determinism(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        r1 = asset_criticality.rank_assets(n, e, pf)
        r2 = asset_criticality.rank_assets(n, e, pf)
        r3 = asset_criticality.rank_assets(n, e, pf)
        assert r1 == r2 == r3

    def test_performance_determinism(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        r1 = performance_analytics.operational_performance(n, e, pf)
        r2 = performance_analytics.operational_performance(n, e, pf)
        r3 = performance_analytics.operational_performance(n, e, pf)
        assert r1 == r2 == r3

    def test_service_end_to_end(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        svc = GridAnalyticsService()
        loading = svc.analyze_loading(n, e, pf_result=pf)
        capacity = svc.analyze_capacity(n, e, pf_result=pf)
        criticality = svc.rank_criticality(n, e, pf_result=pf)
        performance = svc.compute_performance(n, e, pf_result=pf)
        assert loading["feeders"]
        assert "summary" in capacity
        assert criticality["rankings"]
        assert "overall_health" in performance

    def test_service_compute_performance_all_sub_keys(self):
        n, e = _std_nodes(), _std_edges()
        pf = _std_pf()
        ca = _std_ca()
        vvo = _synthetic_vvo_result()
        result = AdvancedNetworkAnalyticsService().compute_performance(
            n, e, pf_result=pf, ca_result=ca, vvo_result=vvo
        )
        for key in ("voltage_quality", "loading", "contingency_exposure", "optimisation_benefit"):
            assert key in result, f"missing key: {key}"

    def test_analytics_regression_wp012_01_to_06(self):  # nosec B404/B603
        """Meta-test: full WP-012-01..06 non-meta regression must pass with 236 tests."""
        result = subprocess.run(  # nosec B603
            [
                sys.executable, "-m", "pytest",
                "tests/test_analytics_architecture.py",
                "tests/test_adms_state_estimation_service.py",
                "tests/test_adms_power_flow_service.py",
                "tests/test_adms_contingency_analysis_service.py",
                "tests/test_adms_volt_var_service.py",
                "tests/test_adms_advanced_network_analytics_service.py",
                "-k", "not analytics_regression",
                "-q", "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        combined = result.stdout + result.stderr
        assert "236 passed" in combined, (
            f"Expected '236 passed' in regression output.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
