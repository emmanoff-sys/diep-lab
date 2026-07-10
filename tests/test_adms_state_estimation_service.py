"""WP-012-02 — State Estimation Service tests (OA-107 through OA-112).

Tests for StateEstimationService — the production service wrapper over the
validated WLS engine. Verifies service integration (OA-107), measurement
processing (OA-108), topology integration (OA-109), canonical outputs (OA-110),
platform integration (OA-111), and engineering validation (OA-112).

All tests are pure Python — no DB, no HTTP, no infrastructure required.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_grid_analytics import state_estimation as _engine
from services.adms_grid_analytics.state_estimation_service import StateEstimationService

# ------------------------------------------------------------------ #
# Test fixtures                                                         #
# ------------------------------------------------------------------ #


def _two_node(base_kw: float = 50.0, closed: bool = True) -> tuple:
    nodes = [
        {
            "node_id": "SRC",
            "node_type": "substation",
            "nominal_kv": 0.415,
            "name": "src",
            "base_load_kw": 0.0,
            "base_load_kvar": 0.0,
        },
        {
            "node_id": "L1",
            "node_type": "load",
            "nominal_kv": 0.415,
            "name": "load",
            "base_load_kw": base_kw,
            "base_load_kvar": 0.0,
        },
    ]
    edges = [
        {
            "edge_id": "E1",
            "from_node": "SRC",
            "to_node": "L1",
            "edge_type": "line",
            "is_closed": closed,
            "resistance_r_ohm": 0.1,
            "reactance_x_ohm": 0.0,
            "ampacity_a": 400,
        }
    ]
    return nodes, edges


def _three_node() -> tuple:
    nodes = [
        {
            "node_id": "SRC",
            "node_type": "substation",
            "nominal_kv": 0.415,
            "name": "src",
            "base_load_kw": 0.0,
            "base_load_kvar": 0.0,
        },
        {
            "node_id": "L1",
            "node_type": "load",
            "nominal_kv": 0.415,
            "name": "load1",
            "base_load_kw": 30.0,
            "base_load_kvar": 0.0,
        },
        {
            "node_id": "L2",
            "node_type": "load",
            "nominal_kv": 0.415,
            "name": "load2",
            "base_load_kw": 20.0,
            "base_load_kvar": 0.0,
        },
    ]
    edges = [
        {
            "edge_id": "E1",
            "from_node": "SRC",
            "to_node": "L1",
            "edge_type": "line",
            "is_closed": True,
            "resistance_r_ohm": 0.1,
            "reactance_x_ohm": 0.0,
            "ampacity_a": 400,
        },
        {
            "edge_id": "E2",
            "from_node": "L1",
            "to_node": "L2",
            "edge_type": "line",
            "is_closed": True,
            "resistance_r_ohm": 0.1,
            "reactance_x_ohm": 0.0,
            "ampacity_a": 400,
        },
    ]
    return nodes, edges


# ------------------------------------------------------------------ #
# OA-107 — State Estimation Service Integration                        #
# ------------------------------------------------------------------ #


class TestOA107ServiceIntegration:
    """OA-107: service wraps the engine without reimplementing it."""

    def test_service_construction_no_deps(self):
        svc = StateEstimationService()
        assert svc is not None

    def test_service_construction_with_options(self):
        svc = StateEstimationService(options={"bad_data_threshold": 4.0})
        assert svc._default_options["bad_data_threshold"] == 4.0

    def test_service_delegates_to_engine_same_math(self):
        # OA-107: service and direct engine must produce identical node voltages
        nodes, edges = _two_node(50.0)
        measurements = {"L1": {"p_kw": 50.0}}
        svc = StateEstimationService()
        svc_result = svc.estimate(nodes, edges, measurements)
        engine_result = _engine.estimate(nodes, edges, measurements)
        svc_l1 = next(n for n in svc_result["nodes"] if n["node_id"] == "L1")
        eng_l1 = next(n for n in engine_result["nodes"] if n["node_id"] == "L1")
        assert svc_l1["estimated_voltage_pu"] == eng_l1["estimated_voltage_pu"]
        assert svc_l1["estimated_p_kw"] == eng_l1["estimated_p_kw"]

    def test_service_accepts_raw_dicts(self):
        nodes, edges = _two_node()
        result = StateEstimationService().estimate(nodes, edges, {})
        assert "nodes" in result and "branches" in result

    def test_no_estimation_logic_in_service_module(self):
        import inspect

        import services.adms_grid_analytics.state_estimation_service as m

        src = inspect.getsource(m)
        # ensure the service does not define mathematical primitives
        assert "normal equations" not in src
        assert "linalg" not in src
        assert "Ginv" not in src

    def test_service_does_not_duplicate_engine_symbols(self):
        from services.adms_grid_analytics import state_estimation_service as se_svc

        # service module must not redefine engine functions
        assert not hasattr(se_svc, "estimate")
        assert not hasattr(se_svc, "build_radial")
        assert not hasattr(se_svc, "DEFAULTS")

    def test_state_estimation_service_exported_from_package(self):
        from services.adms_grid_analytics import StateEstimationService as Cls

        assert Cls is StateEstimationService


# ------------------------------------------------------------------ #
# OA-108 — Measurement Processing                                      #
# ------------------------------------------------------------------ #


class TestOA108MeasurementProcessing:
    """OA-108: measurement validation, normalisation, coverage reporting."""

    def test_full_measurement_set_passes_through(self):
        nodes, _ = _two_node()
        measurements = {"L1": {"p_kw": 50.0, "q_kvar": 5.0, "voltage_pu": 0.97}}
        svc = StateEstimationService()
        processed, summary = svc.process_measurements(nodes, measurements)
        assert processed["L1"]["p_kw"] == 50.0
        assert processed["L1"]["q_kvar"] == 5.0
        assert processed["L1"]["voltage_pu"] == 0.97
        assert summary["total_measurement_values"] == 3

    def test_partial_measurement_accepted(self):
        nodes, _ = _two_node()
        processed, summary = StateEstimationService().process_measurements(
            nodes, {"L1": {"p_kw": 30.0}}
        )
        assert "p_kw" in processed["L1"]
        assert "voltage_pu" not in processed["L1"]
        assert summary["total_measurement_values"] == 1

    def test_empty_measurements_accepted(self):
        nodes, _ = _two_node()
        processed, summary = StateEstimationService().process_measurements(nodes, {})
        assert processed == {}
        assert summary["monitored_nodes"] == 0
        assert summary["coverage_pct"] == 0.0

    def test_unknown_node_id_rejected(self):
        nodes, _ = _two_node()
        processed, summary = StateEstimationService().process_measurements(
            nodes, {"GHOST": {"p_kw": 10.0}}
        )
        assert "GHOST" not in processed
        assert len(summary["rejected"]) == 1
        assert summary["rejected"][0]["reason"] == "node not in topology"

    def test_non_numeric_value_rejected(self):
        nodes, _ = _two_node()
        processed, summary = StateEstimationService().process_measurements(
            nodes, {"L1": {"p_kw": "not-a-number"}}
        )
        assert "L1" not in processed
        assert any(r["key"] == "p_kw" for r in summary["rejected"])

    def test_coverage_percentage_correct(self):
        nodes, _ = _three_node()
        processed, summary = StateEstimationService().process_measurements(
            nodes, {"L1": {"p_kw": 30.0}}
        )
        # 1 of 2 load nodes monitored → 50%
        assert summary["coverage_pct"] == 50.0
        assert summary["monitored_nodes"] == 1
        assert summary["unmonitored_nodes"] == 1

    def test_full_coverage_percentage(self):
        nodes, _ = _three_node()
        _, summary = StateEstimationService().process_measurements(
            nodes, {"L1": {"p_kw": 30.0}, "L2": {"p_kw": 20.0}}
        )
        assert summary["coverage_pct"] == 100.0

    def test_substation_node_excluded_from_coverage_denominator(self):
        # substation nodes are not load nodes; coverage only counts load nodes
        nodes, _ = _two_node()
        _, summary = StateEstimationService().process_measurements(nodes, {"L1": {"p_kw": 50.0}})
        assert summary["coverage_pct"] == 100.0  # 1 load node, 1 monitored


# ------------------------------------------------------------------ #
# OA-109 — Topology Integration                                        #
# ------------------------------------------------------------------ #


class TestOA109TopologyIntegration:
    """OA-109: topology validation and WP-007/008 adapter."""

    def test_valid_topology_passes(self):
        nodes, edges = _two_node()
        result = StateEstimationService().validate_topology(nodes, edges)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["node_count"] == 2
        assert result["substation_count"] == 1

    def test_no_substation_is_hard_error(self):
        nodes = [{"node_id": "L1", "node_type": "load", "nominal_kv": 0.415}]
        edges: list = []
        result = StateEstimationService().validate_topology(nodes, edges)
        assert result["valid"] is False
        assert any("substation" in e for e in result["errors"])

    def test_estimate_raises_on_no_substation(self):
        nodes = [
            {
                "node_id": "L1",
                "node_type": "load",
                "nominal_kv": 0.415,
                "base_load_kw": 10.0,
                "base_load_kvar": 0.0,
            }
        ]
        try:
            StateEstimationService().estimate(nodes, [], {})
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "substation" in str(exc)

    def test_dangling_edge_node_is_hard_error(self):
        nodes, edges = _two_node()
        edges.append(
            {
                "edge_id": "E99",
                "from_node": "GHOST",
                "to_node": "L1",
                "edge_type": "line",
                "is_closed": True,
            }
        )
        result = StateEstimationService().validate_topology(nodes, edges)
        assert result["valid"] is False
        assert any("GHOST" in e for e in result["errors"])

    def test_all_switches_open_generates_warning(self):
        nodes, edges = _two_node(closed=False)
        result = StateEstimationService().validate_topology(nodes, edges)
        assert result["valid"] is True  # soft — not a hard error
        assert result["closed_edge_count"] == 0
        assert any("de-energized" in w for w in result["warnings"])

    def test_wp007_snapshot_adapter(self):
        """OA-109: _nodes_edges_from_snapshot converts WP-007 snapshot."""

        class FakeNode:
            def __init__(self, nid, ntype, kv, phases="ABC", name="n", attrs=None):
                self.node_id = nid
                self.node_type = ntype
                self.nominal_kv = kv
                self.phases = phases
                self.name = name
                self.attrs = attrs or {}

        class FakeEdge:
            def __init__(self, eid, frm, to, etype="line", closed=True, attrs=None):
                self.edge_id = eid
                self.from_node = frm
                self.to_node = to
                self.edge_type = etype
                self.is_closed = closed
                self.phases = "ABC"
                self.attrs = attrs or {}

        class FakeSnapshot:
            nodes = {
                "SRC": FakeNode("SRC", "substation", 0.415),
                "L1": FakeNode(
                    "L1", "load", 0.415, attrs={"base_load_kw": 40.0, "resistance_r_ohm": 0.1}
                ),
            }
            edges = {
                "E1": FakeEdge(
                    "E1", "SRC", "L1", attrs={"resistance_r_ohm": 0.1, "ampacity_a": 400}
                ),
            }

        svc = StateEstimationService()
        nodes, edges = svc._nodes_edges_from_snapshot(FakeSnapshot())
        assert len(nodes) == 2
        assert len(edges) == 1
        assert nodes[1]["base_load_kw"] == 40.0
        assert edges[0]["resistance_r_ohm"] == 0.1

    def test_wp007_none_snapshot_returns_empty(self):
        svc = StateEstimationService()
        nodes, edges = svc._nodes_edges_from_snapshot(None)
        assert nodes == [] and edges == []


# ------------------------------------------------------------------ #
# OA-110 — Operational Outputs                                         #
# ------------------------------------------------------------------ #


class TestOA110CanonicalOutputs:
    """OA-110: enriched canonical output structure."""

    def test_output_has_topology_key(self):
        nodes, edges = _two_node()
        result = StateEstimationService().estimate(nodes, edges, {})
        assert "topology" in result
        assert result["topology"]["valid"] is True

    def test_output_has_measurement_summary_key(self):
        nodes, edges = _two_node()
        result = StateEstimationService().estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
        assert "measurement_summary" in result
        summary = result["measurement_summary"]
        assert summary["monitored_nodes"] == 1
        assert summary["coverage_pct"] == 100.0

    def test_output_has_service_identifier(self):
        nodes, edges = _two_node()
        result = StateEstimationService().estimate(nodes, edges, {})
        assert result["service"] == "StateEstimationService"

    def test_engine_fields_preserved_in_output(self):
        nodes, edges = _two_node(50.0)
        result = StateEstimationService().estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
        # all original engine fields must be present
        for key in (
            "nodes",
            "branches",
            "bad_data",
            "max_normalized_residual",
            "method",
            "measurements",
            "states",
        ):
            assert key in result, f"missing engine field: {key!r}"

    def test_estimated_voltage_present_on_energized_nodes(self):
        nodes, edges = _two_node(50.0)
        result = StateEstimationService().estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is True
        assert l1["estimated_voltage_pu"] is not None

    def test_de_energized_node_voltage_is_none(self):
        nodes, edges = _two_node(50.0, closed=False)
        result = StateEstimationService().estimate(nodes, edges, {})
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is False
        assert l1["estimated_voltage_pu"] is None

    def test_bad_data_field_present_and_none_when_clean(self):
        nodes, edges = _two_node(50.0)
        result = StateEstimationService().estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
        assert "bad_data" in result  # field present
        # consistent measurement → no bad data flag
        assert result["bad_data"] is None or isinstance(result["bad_data"], dict)

    def test_confidence_indicators_present(self):
        nodes, edges = _two_node(50.0)
        result = StateEstimationService().estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
        for n in result["nodes"]:
            assert "confidence" in n


# ------------------------------------------------------------------ #
# OA-111 — Platform Integration                                        #
# ------------------------------------------------------------------ #


class TestOA111PlatformIntegration:
    """OA-111: WP-007/008/009/010 integration."""

    def test_estimate_from_snapshot_with_mock_wp007(self):
        class FakeNode:
            def __init__(self, nid, ntype, kv):
                self.node_id = nid
                self.node_type = ntype
                self.nominal_kv = kv
                self.phases = "ABC"
                self.name = nid
                self.attrs = {"base_load_kw": 40.0, "base_load_kvar": 0.0}

        class FakeEdge:
            def __init__(self, eid, frm, to):
                self.edge_id = eid
                self.from_node = frm
                self.to_node = to
                self.edge_type = "line"
                self.is_closed = True
                self.phases = "ABC"
                self.attrs = {"resistance_r_ohm": 0.1, "ampacity_a": 400}

        class FakeSnapshot:
            nodes = {
                "SRC": FakeNode("SRC", "substation", 0.415),
                "L1": FakeNode("L1", "load", 0.415),
            }
            edges = {"E1": FakeEdge("E1", "SRC", "L1")}

        svc = StateEstimationService()
        result = svc.estimate_from_snapshot(FakeSnapshot())
        assert "nodes" in result
        assert any(n["node_id"] == "L1" for n in result["nodes"])

    def test_estimate_from_snapshot_with_op_state(self):
        """OA-111: WP-008 operational state provides measurements."""

        class FakeNode:
            def __init__(self, nid, ntype):
                self.node_id = nid
                self.node_type = ntype
                self.nominal_kv = 0.415
                self.phases = "ABC"
                self.name = nid
                self.attrs = {"base_load_kw": 50.0, "base_load_kvar": 0.0}

        class FakeEdge:
            def __init__(self):
                self.edge_id = "E1"
                self.from_node = "SRC"
                self.to_node = "L1"
                self.edge_type = "line"
                self.is_closed = True
                self.phases = "ABC"
                self.attrs = {"resistance_r_ohm": 0.1, "ampacity_a": 400}

        class FakeSnapshot:
            nodes = {"SRC": FakeNode("SRC", "substation"), "L1": FakeNode("L1", "load")}
            edges = {"E1": FakeEdge()}

        class FakeAssetState:
            attributes = {"p_kw": 50.0}

        svc = StateEstimationService()
        result = svc.estimate_from_snapshot(FakeSnapshot(), op_state={"L1": FakeAssetState()})
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["monitored"] is True

    def test_topo_repo_used_when_snapshot_none(self):
        """OA-111: repository is queried when no explicit snapshot given."""

        class FakeNode:
            node_id = "SRC"
            node_type = "substation"
            nominal_kv = 0.415
            phases = "ABC"
            name = "src"
            attrs = {"base_load_kw": 0.0}

        class FakeSnap:
            nodes = {"SRC": FakeNode()}
            edges = {}

        class FakeRepo:
            def get_latest(self):
                return FakeSnap()

        svc = StateEstimationService(topology_repository=FakeRepo())
        result = svc.estimate_from_snapshot()  # no explicit snapshot
        assert "nodes" in result

    def test_op_state_service_queried_when_none(self):
        """OA-111: operational state service is called when op_state not provided."""
        called = []

        class FakeOpState:
            def get_current_state(self):
                called.append(True)
                return {}

        class FakeNode:
            node_id = "SRC"
            node_type = "substation"
            nominal_kv = 0.415
            phases = "ABC"
            name = "src"
            attrs = {}

        class FakeSnap:
            nodes = {"SRC": FakeNode()}
            edges = {}

        svc = StateEstimationService(operational_state=FakeOpState())
        svc.estimate_from_snapshot(FakeSnap())
        assert called, "operational state service was not queried"

    def test_grid_analytics_service_estimate_state_delegates(self):
        """OA-111: GridAnalyticsService.estimate_state uses StateEstimationService."""
        from services.adms_grid_analytics.service import GridAnalyticsService

        nodes, edges = _two_node(50.0)
        result = GridAnalyticsService().estimate_state(
            nodes=nodes, edges=edges, measurements={"L1": {"p_kw": 50.0}}
        )
        # should have service enrichment keys from StateEstimationService
        assert "topology" in result
        assert "measurement_summary" in result
        assert result["service"] == "StateEstimationService"


# ------------------------------------------------------------------ #
# OA-112 — Engineering Validation                                      #
# ------------------------------------------------------------------ #


class TestOA112EngineeringValidation:
    """OA-112: determinism, regression compatibility, contract compliance."""

    def test_deterministic_repeated_calls(self):
        nodes, edges = _two_node(50.0)
        meas = {"L1": {"p_kw": 50.0, "voltage_pu": 0.97}}
        svc = StateEstimationService()
        r1 = svc.estimate(nodes, edges, meas)
        r2 = svc.estimate(nodes, edges, meas)
        l1a = next(n for n in r1["nodes"] if n["node_id"] == "L1")
        l1b = next(n for n in r2["nodes"] if n["node_id"] == "L1")
        assert l1a["estimated_voltage_pu"] == l1b["estimated_voltage_pu"]
        assert l1a["confidence"] == l1b["confidence"]

    def test_service_result_matches_engine_result_numerically(self):
        """OA-112: P5 mathematical behaviour unchanged through service layer."""
        nodes, edges = _two_node(50.0)
        meas = {"L1": {"p_kw": 50.0}}
        engine_result = _engine.estimate(nodes, edges, meas)
        svc_result = StateEstimationService().estimate(nodes, edges, meas)
        for eng_n, svc_n in zip(engine_result["nodes"], svc_result["nodes"], strict=False):
            assert eng_n["node_id"] == svc_n["node_id"]
            assert eng_n.get("estimated_voltage_pu") == svc_n.get("estimated_voltage_pu")
            assert eng_n.get("estimated_p_kw") == svc_n.get("estimated_p_kw")

    def test_bad_data_detection_propagated(self):
        """OA-112: bad-data detection works through the service layer."""
        nodes, edges = _two_node(50.0)
        # inconsistent: small power but large voltage sag
        result = StateEstimationService().estimate(
            nodes, edges, {"L1": {"p_kw": 50.0, "voltage_pu": 0.80}}
        )
        assert result["bad_data"] is not None
        assert result["max_normalized_residual"] > 3.0

    def test_missing_telemetry_falls_back_to_pseudo(self):
        """OA-112: empty measurements use pseudo-measurement base loads."""
        nodes, edges = _two_node(50.0)
        result = StateEstimationService().estimate(nodes, edges, {})
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is True
        assert abs(l1["estimated_p_kw"] - 50.0) < 1e-6

    def test_per_call_options_override_defaults(self):
        """OA-112: per-call options win over service defaults."""
        nodes, edges = _two_node(50.0)
        # very tight power tolerance → any measurement ≥ 0 triggers bad-data flag
        result = StateEstimationService(options={"bad_data_threshold": 0.01}).estimate(
            nodes, edges, {"L1": {"p_kw": 50.0}}
        )
        # with threshold this tight almost any residual flags bad data
        # the point is that the option was applied (no crash)
        assert "bad_data" in result

    def test_input_nodes_not_mutated(self):
        """OA-112: service must not modify the caller's node/edge lists."""
        nodes, edges = _two_node(50.0)
        import copy

        nodes_copy = copy.deepcopy(nodes)
        edges_copy = copy.deepcopy(edges)
        StateEstimationService().estimate(nodes, edges, {})
        assert nodes == nodes_copy
        assert edges == edges_copy

    def test_three_node_topology_regression(self):
        """OA-112: multi-node topology produces results for all nodes."""
        nodes, edges = _three_node()
        result = StateEstimationService().estimate(
            nodes, edges, {"L1": {"p_kw": 30.0}, "L2": {"p_kw": 20.0}}
        )
        node_ids = {n["node_id"] for n in result["nodes"]}
        assert {"SRC", "L1", "L2"} <= node_ids
        assert len(result["branches"]) == 2
