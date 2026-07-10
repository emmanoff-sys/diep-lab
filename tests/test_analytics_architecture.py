"""WP-012-01 OA-106 — Analytics Architecture validation tests.

Two concerns tested here:

1. Compatibility-shim validation — legacy callers that do
       sys.path.insert(0, ".../fastapi")
       from dms import state_estimation as se
   must receive exactly the same public symbols as before, with no circular
   imports introduced.

2. GridAnalyticsService service-layer validation — the new facade must:
   * construct with WP-007/008/009/010 dependencies (by injection)
   * accept raw topology dicts directly
   * delegate to each of the eight analytics engines
   * produce contract-compliant output structures
   * not mutate input topology
   * return deterministic repeated results
   * raise meaningful errors for invalid inputs

Run:  python3 -m pytest tests/test_analytics_architecture.py -v
"""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_grid_analytics import GridAnalyticsService  # noqa: E402

# ---------------------------------------------------------------------------
# Shared network fixtures
# ---------------------------------------------------------------------------


def _two_node(r_ohm=0.1, x_ohm=0.0, ampacity=400, node_b_type="load"):
    nodes = [
        {
            "node_id": "SRC",
            "node_type": "substation",
            "nominal_kv": 0.415,
            "name": "src",
            "base_load_kw": 0.0,
            "base_load_kvar": 0.0,
            "phases": "ABC",
        },
        {
            "node_id": "L1",
            "node_type": node_b_type,
            "nominal_kv": 0.415,
            "name": "load",
            "base_load_kw": 50.0,
            "base_load_kvar": 0.0,
            "phases": "ABC",
        },
    ]
    edges = [
        {
            "edge_id": "E1",
            "from_node": "SRC",
            "to_node": "L1",
            "edge_type": "line",
            "is_closed": True,
            "resistance_r_ohm": r_ohm,
            "reactance_x_ohm": x_ohm,
            "ampacity_a": ampacity,
            "phases": "ABC",
            "is_switchable": False,
            "normally_closed": True,
        }
    ]
    return nodes, edges


# ---------------------------------------------------------------------------
# Section 1 — Compatibility-shim validation
# ---------------------------------------------------------------------------


class TestCompatibilityShims:
    """Legacy fastapi/dms imports must resolve to the same objects."""

    def _import_via_legacy_path(self, module_name: str) -> types.ModuleType:
        """Simulate legacy import: sys.path with fastapi/ prefix."""
        fastapi_dir = os.path.join(os.path.dirname(__file__), "..", "fastapi")
        # temporarily push the fastapi path
        sys.path.insert(0, fastapi_dir)
        try:
            import importlib

            full = f"dms.{module_name}"
            if full in sys.modules:
                del sys.modules[full]
            mod = importlib.import_module(f"dms.{module_name}")
        finally:
            sys.path.pop(0)
        return mod

    def test_state_estimation_shim_exposes_build_radial_and_estimate(self):
        mod = self._import_via_legacy_path("state_estimation")
        assert callable(mod.build_radial)
        assert callable(mod.estimate)
        assert isinstance(mod.SBASE_KW, float)
        assert isinstance(mod.SQRT3, float)
        assert isinstance(mod.DEFAULTS, dict)

    def test_powerflow_shim_exposes_solve(self):
        mod = self._import_via_legacy_path("powerflow")
        assert callable(mod.solve)
        assert "tol_pu" in mod.DEFAULTS
        assert isinstance(mod.PHASES, tuple)

    def test_contingency_shim_exposes_analyze(self):
        mod = self._import_via_legacy_path("contingency")
        assert callable(mod.analyze)

    def test_fault_location_shim_exposes_locate(self):
        mod = self._import_via_legacy_path("fault_location")
        assert callable(mod.locate)

    def test_reconfiguration_shim_exposes_recommend(self):
        mod = self._import_via_legacy_path("reconfiguration")
        assert callable(mod.recommend)

    def test_outage_inference_shim_exposes_infer(self):
        mod = self._import_via_legacy_path("outage_inference")
        assert callable(mod.infer)

    def test_outage_validation_shim_exposes_cross_check(self):
        mod = self._import_via_legacy_path("outage_validation")
        assert callable(mod.cross_check)

    def test_crew_dispatch_shim_exposes_recommend(self):
        mod = self._import_via_legacy_path("crew_dispatch")
        assert callable(mod.recommend)

    def test_linalg_shim_exposes_all_functions(self):
        mod = self._import_via_legacy_path("linalg")
        for name in ("zeros", "identity", "transpose", "matmul", "matvec", "solve", "inverse"):
            assert callable(getattr(mod, name)), f"missing: {name}"

    def test_shim_and_canonical_are_same_function(self):
        """The shim must point to the exact same function object as the canonical."""
        from services.adms_grid_analytics.state_estimation import build_radial as canonical

        mod = self._import_via_legacy_path("state_estimation")
        assert mod.build_radial is canonical

    def test_shim_produces_correct_output(self):
        """Shim state_estimation.estimate() returns correct structure."""
        mod = self._import_via_legacy_path("state_estimation")
        nodes, edges = _two_node()
        result = mod.estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
        assert "nodes" in result
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is True
        assert abs(l1["estimated_p_kw"] - 50.0) < 2.0

    def test_no_circular_import(self):
        """Importing the shim package must not raise ImportError."""
        import importlib

        fastapi_dir = os.path.join(os.path.dirname(__file__), "..", "fastapi")
        sys.path.insert(0, fastapi_dir)
        try:
            for name in (
                "state_estimation",
                "powerflow",
                "contingency",
                "fault_location",
                "reconfiguration",
                "outage_inference",
                "outage_validation",
                "crew_dispatch",
                "linalg",
            ):
                importlib.import_module(f"dms.{name}")
        finally:
            sys.path.pop(0)


# ---------------------------------------------------------------------------
# Section 2 — GridAnalyticsService service-layer validation
# ---------------------------------------------------------------------------


class TestGridAnalyticsService:
    """Service facade validation per OA-106 §7."""

    def test_construction_no_dependencies(self):
        svc = GridAnalyticsService()
        assert svc is not None

    def test_construction_with_mocked_dependencies(self):
        """Accepts WP-007/008/009/010 objects by constructor injection."""

        class FakeTopo:
            pass

        class FakeOpState:
            pass

        class FakeAdvisory:
            pass

        class FakeIntelligence:
            pass

        svc = GridAnalyticsService(
            topology_repository=FakeTopo(),
            operational_state=FakeOpState(),
            operations_advisory=FakeAdvisory(),
            intelligence_service=FakeIntelligence(),
        )
        assert svc._topo_repo is not None
        assert svc._op_state is not None
        assert svc._advisory is not None
        assert svc._intelligence is not None

    def test_estimate_state_with_raw_dicts(self):
        nodes, edges = _two_node()
        svc = GridAnalyticsService()
        result = svc.estimate_state(nodes=nodes, edges=edges, measurements={"L1": {"p_kw": 50.0}})
        assert "nodes" in result
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is True
        assert abs(l1["estimated_p_kw"] - 50.0) < 2.0

    def test_solve_power_flow_with_raw_dicts(self):
        nodes, edges = _two_node()
        loads = {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
        svc = GridAnalyticsService()
        result = svc.solve_power_flow(nodes=nodes, edges=edges, loads=loads)
        assert result["converged"] is True
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is True
        assert l1["v_min_pu"] < 1.0

    def test_analyze_contingency_with_raw_dicts(self):
        nodes, edges = _two_node()
        loads = {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
        svc = GridAnalyticsService()
        result = svc.analyze_contingency(nodes=nodes, edges=edges, loads=loads)
        assert "contingencies" in result
        assert isinstance(result["n1_secure"], bool)

    def test_locate_fault_with_raw_dicts(self):
        nodes, edges = _two_node()
        svc = GridAnalyticsService()
        result = svc.locate_fault(nodes=nodes, edges=edges, fault_current_a=500.0)
        assert "impedance_candidates" in result
        assert "best_estimate" in result

    def test_recommend_reconfiguration_with_raw_dicts(self):
        nodes, edges = _two_node()
        # make E1 switchable so there's something to reconfig
        edges[0]["is_switchable"] = True
        edges[0]["edge_type"] = "switch"
        loads = {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
        svc = GridAnalyticsService()
        result = svc.recommend_reconfiguration(nodes=nodes, edges=edges, loads=loads)
        assert "switching_plan" in result
        assert isinstance(result["action_required"], bool)

    def test_infer_outage_with_raw_dicts(self):
        nodes, edges = _two_node(node_b_type="meter")
        svc = GridAnalyticsService()
        result = svc.infer_outage(
            dark_meter_nodes=["L1"], nodes=nodes, edges=edges, customers_by_node={"L1": 10}
        )
        assert "inferred_outages" in result
        assert result["dark_meter_count"] == 1

    def test_validate_outage_inference(self):
        svc = GridAnalyticsService()
        inferred = [
            {
                "probable_device": {
                    "edge_id": "E1",
                    "edge_type": "line",
                    "from_node": "SRC",
                    "to_node": "L1",
                    "is_switchable": False,
                },
                "section_node": "L1",
                "estimated_customers_affected": 10,
                "confidence": 0.9,
            }
        ]
        contingencies = [
            {
                "element": "E1",
                "element_type": "line",
                "lost_customers": 10,
                "classification": "unserved",
                "restored_by": [],
                "post_violations": 0,
            }
        ]
        result = svc.validate_outage_inference(inferred, contingencies)
        assert "checks" in result
        assert isinstance(result["consistent"], bool)

    def test_recommend_crew_dispatch(self):
        svc = GridAnalyticsService()
        inferred = [
            {
                "probable_device": {
                    "edge_id": "E1",
                    "edge_type": "line",
                    "from_node": "SRC",
                    "to_node": "L1",
                    "is_switchable": False,
                },
                "section_node": "L1",
                "section_name": "Main feeder",
                "feeding_transformer": None,
                "estimated_customers_affected": 10,
                "confidence": 0.9,
            }
        ]
        contingencies = [
            {
                "element": "E1",
                "element_type": "line",
                "lost_customers": 10,
                "classification": "unserved",
                "restored_by": [],
                "post_violations": 0,
            }
        ]
        result = svc.recommend_crew_dispatch(inferred, contingencies)
        assert "candidates" in result
        assert len(result["candidates"]) == 1

    def test_deterministic_repeated_calls(self):
        """Same inputs must produce identical outputs on repeated calls."""
        nodes, edges = _two_node()
        svc = GridAnalyticsService()
        r1 = svc.estimate_state(nodes=nodes, edges=edges, measurements={"L1": {"p_kw": 50.0}})
        r2 = svc.estimate_state(nodes=nodes, edges=edges, measurements={"L1": {"p_kw": 50.0}})
        l1_r1 = next(n for n in r1["nodes"] if n["node_id"] == "L1")
        l1_r2 = next(n for n in r2["nodes"] if n["node_id"] == "L1")
        assert l1_r1["estimated_p_kw"] == l1_r2["estimated_p_kw"]
        assert l1_r1["estimated_voltage_pu"] == l1_r2["estimated_voltage_pu"]

    def test_does_not_mutate_input_nodes(self):
        """Engines must not modify the caller's node list."""
        import copy

        nodes, edges = _two_node()
        nodes_copy = copy.deepcopy(nodes)
        svc = GridAnalyticsService()
        svc.estimate_state(nodes=nodes, edges=edges, measurements={})
        assert nodes == nodes_copy

    def test_does_not_mutate_input_edges(self):
        """Engines must not modify the caller's edge list."""
        import copy

        nodes, edges = _two_node()
        edges_copy = copy.deepcopy(edges)
        loads = {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
        svc = GridAnalyticsService()
        svc.solve_power_flow(nodes=nodes, edges=edges, loads=loads)
        assert edges == edges_copy

    def test_invalid_topology_raises_meaningful_error(self):
        """No substation node → build_radial raises ValueError, not a crash."""
        import pytest

        nodes = [{"node_id": "X", "node_type": "load", "nominal_kv": 0.415}]
        edges = []
        svc = GridAnalyticsService()
        with pytest.raises(ValueError, match="no substation"):
            svc.estimate_state(nodes=nodes, edges=edges, measurements={})

    def test_op_state_adaptation_empty_state(self):
        """No operational state → empty measurement map → uses pseudo-measurements."""
        nodes, edges = _two_node()
        svc = GridAnalyticsService()
        result = svc.estimate_state(nodes=nodes, edges=edges, measurements={})
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        # Without telemetry, falls back to base_load_kw = 50.0
        assert abs(l1["estimated_p_kw"] - 50.0) < 1e-6

    def test_op_state_adaptation_from_wp008_mock(self):
        """WP-008 OperationalStateService mock feeds measurements correctly."""

        class MockAssetState:
            def __init__(self, p_kw, voltage_pu):
                self.attributes = {"p_kw": p_kw, "voltage_pu": voltage_pu}

        class MockOpState:
            def get_current_state(self):
                return {"L1": MockAssetState(p_kw=45.0, voltage_pu=0.97)}

        nodes, edges = _two_node()
        svc = GridAnalyticsService(operational_state=MockOpState())
        result = svc.estimate_state(nodes=nodes, edges=edges)
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["monitored"] is True

    def test_wp007_topology_snapshot_adaptation(self):
        """WP-007 TopologySnapshot mock is converted to engine dicts correctly."""
        from dataclasses import dataclass, field

        @dataclass
        class MockNetworkNode:
            node_id: str
            node_type: str
            name: str | None
            nominal_kv: float | None
            phases: str | None
            attrs: dict = field(default_factory=dict)

        @dataclass
        class MockNetworkEdge:
            edge_id: str
            from_node: str
            to_node: str
            edge_type: str
            is_closed: bool
            phases: str | None
            attrs: dict = field(default_factory=dict)

        @dataclass
        class MockSnapshot:
            nodes: dict
            edges: dict

        snapshot = MockSnapshot(
            nodes={
                "SRC": MockNetworkNode("SRC", "substation", "src", 0.415, "ABC"),
                "L1": MockNetworkNode(
                    "L1",
                    "load",
                    "load",
                    0.415,
                    "ABC",
                    attrs={
                        "base_load_kw": 50.0,
                        "resistance_r_ohm": 0.1,
                        "reactance_x_ohm": 0.0,
                        "base_load_kvar": 0.0,
                    },
                ),
            },
            edges={
                "E1": MockNetworkEdge(
                    "E1",
                    "SRC",
                    "L1",
                    "line",
                    True,
                    "ABC",
                    attrs={
                        "resistance_r_ohm": 0.1,
                        "reactance_x_ohm": 0.0,
                        "ampacity_a": 400,
                        "is_switchable": False,
                        "normally_closed": True,
                    },
                )
            },
        )

        class MockRepo:
            def get_latest(self):
                return snapshot

        svc = GridAnalyticsService(topology_repository=MockRepo())
        result = svc.estimate_state(measurements={"L1": {"p_kw": 50.0}})
        assert "nodes" in result
        l1 = next(n for n in result["nodes"] if n["node_id"] == "L1")
        assert l1["energized"] is True
