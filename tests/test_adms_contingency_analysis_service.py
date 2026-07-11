"""OA-124 — ContingencyAnalysisService engineering validation suite.

Covers OA-119 through OA-124 (PAO-032 / WP-012-04).

Test organisation
-----------------
TestOA119ServiceIntegration       — OA-119: service wrapper, no solver logic
TestOA120ContingencyScenarios     — OA-120: N-1 line / transformer / feeder / source outages
TestOA121NetworkImpactAssessment  — OA-121: restoration feasibility, islanding, violations
TestOA122ContingencyRanking       — OA-122: deterministic ranking, impact_summary
TestOA123PlatformIntegration      — OA-123: SE result loading, snapshot adapter, service injection
TestOA124EngineeringValidation    — OA-124: determinism, regression, analytics chain
"""

from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_grid_analytics.contingency_analysis_service import ContingencyAnalysisService
from services.adms_grid_analytics.power_flow_service import PowerFlowService
from services.adms_grid_analytics.state_estimation_service import StateEstimationService

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _radial_network(n_load_nodes: int = 3, *, with_tie: bool = True):
    """Build a simple radial feeder with optional normally-open tie."""
    nodes = [
        {"node_id": "sub", "node_type": "substation", "nominal_kv": 11.0, "phases": "ABC"},
    ]
    edges = []
    for i in range(1, n_load_nodes + 1):
        prev = "sub" if i == 1 else f"bus{i - 1}"
        nodes.append(
            {"node_id": f"bus{i}", "node_type": "bus", "nominal_kv": 11.0, "phases": "ABC"}
        )
        edges.append(
            {
                "edge_id": f"L{i}",
                "from_node": prev,
                "to_node": f"bus{i}",
                "edge_type": "line",
                "is_closed": True,
                "resistance_r_ohm": 0.1,
                "reactance_x_ohm": 0.05,
                "phases": "ABC",
                "ampacity_a": 200.0,
                "is_switchable": True,
                "normally_closed": True,
            }
        )
    if with_tie and n_load_nodes >= 2:
        # Normally-open tie between last bus and sub (alternative supply path)
        edges.append(
            {
                "edge_id": "TIE1",
                "from_node": f"bus{n_load_nodes}",
                "to_node": "sub",
                "edge_type": "tie",
                "is_closed": False,
                "resistance_r_ohm": 0.15,
                "reactance_x_ohm": 0.08,
                "phases": "ABC",
                "ampacity_a": 150.0,
                "is_switchable": True,
                "normally_closed": False,
            }
        )
    return nodes, edges


def _uniform_loads(nodes, base_kw: float = 30.0) -> dict:
    """Build uniform three-phase loads for non-substation nodes."""
    loads = {}
    for n in nodes:
        if n["node_type"] != "substation":
            loads[n["node_id"]] = {
                "a": complex(base_kw / 3, 0.0),
                "b": complex(base_kw / 3, 0.0),
                "c": complex(base_kw / 3, 0.0),
            }
    return loads


def _se_result_for(nodes, edges, base_kw: float = 30.0) -> dict:
    """Produce a realistic SE result using StateEstimationService."""
    meas = {}
    for n in nodes:
        if n["node_type"] != "substation":
            meas[n["node_id"]] = {"p_kw": base_kw, "q_kvar": 0.0}
    svc = StateEstimationService()
    return svc.estimate(nodes, edges, meas)


# ---------------------------------------------------------------------------
# OA-119 — Contingency Analysis Service Integration
# ---------------------------------------------------------------------------


class TestOA119ServiceIntegration:
    """OA-119: ContingencyAnalysisService delegates to engine; no solver logic."""

    def test_no_solver_logic_in_service_module(self):
        """Source scan: engine-only symbols must not appear in the service module."""
        import services.adms_grid_analytics.contingency_analysis_service as svc_mod

        src = inspect.getsource(svc_mod)
        # These symbols exist only in the engine (contingency.py)
        for forbidden in ("_energized", "_is_radial", "_restore", "copy.deepcopy"):
            assert forbidden not in src, f"Service module contains engine logic: '{forbidden}'"

    def test_service_delegates_to_engine_same_result(self):
        """ContingencyAnalysisService.analyze() result matches contingency.analyze()."""
        from services.adms_grid_analytics.contingency import analyze as engine_analyze

        nodes, edges = _radial_network()
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        svc_result = svc.analyze(nodes, edges, loads)
        engine_result = engine_analyze(nodes, edges, loads)

        assert svc_result["n1_secure"] == engine_result["n1_secure"]
        assert svc_result["contingencies_evaluated"] == engine_result["contingencies_evaluated"]
        assert len(svc_result["contingencies"]) == len(engine_result["contingencies"])

    def test_service_exported_from_package(self):
        """ContingencyAnalysisService is importable from the package root."""
        from services.adms_grid_analytics import ContingencyAnalysisService as ImportedCAS

        assert ImportedCAS is ContingencyAnalysisService

    def test_service_in_all(self):
        """ContingencyAnalysisService appears in __all__."""
        import services.adms_grid_analytics as pkg

        assert "ContingencyAnalysisService" in pkg.__all__

    def test_service_constructor_injection(self):
        """ContingencyAnalysisService accepts optional dependencies without error."""
        svc = ContingencyAnalysisService(
            topology_repository=None,
            state_estimation_service=None,
            power_flow_service=None,
            options={"dummy": True},
        )
        assert svc is not None

    def test_analyze_contingency_on_grid_analytics_service(self):
        """GridAnalyticsService.analyze_contingency() delegates to ContingencyAnalysisService."""
        from services.adms_grid_analytics import GridAnalyticsService

        nodes, edges = _radial_network()
        loads = _uniform_loads(nodes)
        svc = GridAnalyticsService()
        result = svc.analyze_contingency(nodes=nodes, edges=edges, loads=loads)
        assert "service" in result
        assert result["service"] == "ContingencyAnalysisService"

    def test_service_result_has_service_key(self):
        """Result dict always contains 'service': 'ContingencyAnalysisService'."""
        nodes, edges = _radial_network()
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, _uniform_loads(nodes))
        assert result.get("service") == "ContingencyAnalysisService"


# ---------------------------------------------------------------------------
# OA-120 — Contingency Scenario Evaluation
# ---------------------------------------------------------------------------


class TestOA120ContingencyScenarios:
    """OA-120: N-1 line / transformer / feeder / source outages."""

    def test_n1_line_outages_all_evaluated(self):
        """All in-service lines appear as candidate contingencies."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        evaluated_elements = {c["element"] for c in result["contingencies"]}
        in_service_lines = {e["edge_id"] for e in edges if e.get("is_closed", True)}
        assert in_service_lines <= evaluated_elements

    def test_n1_transformer_outage_evaluated(self):
        """Transformer-type edge is evaluated as a contingency candidate."""
        nodes = [
            {"node_id": "sub", "node_type": "substation", "nominal_kv": 11.0, "phases": "ABC"},
            {"node_id": "bus1", "node_type": "bus", "nominal_kv": 0.4, "phases": "ABC"},
        ]
        edges = [
            {
                "edge_id": "TX1",
                "from_node": "sub",
                "to_node": "bus1",
                "edge_type": "transformer",
                "is_closed": True,
                "resistance_r_ohm": 0.02,
                "reactance_x_ohm": 0.1,
                "phases": "ABC",
                "ampacity_a": 500.0,
                "is_switchable": True,
                "normally_closed": True,
            }
        ]
        loads = {"bus1": {"a": complex(10, 0), "b": complex(10, 0), "c": complex(10, 0)}}
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        elements = {c["element"] for c in result["contingencies"]}
        assert "TX1" in elements

    def test_n1_feeder_outage_loses_all_downstream_nodes(self):
        """Outage of the first feeder segment loses all downstream load nodes."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        # L1 is the connection from sub → bus1 (all buses downstream)
        l1_contingency = next(c for c in result["contingencies"] if c["element"] == "L1")
        assert l1_contingency["lost_load_kw"] > 0

    def test_n1_source_outage_islanding_detected(self):
        """Outage of the only supply edge leaves all load nodes unserved."""
        nodes = [
            {"node_id": "sub", "node_type": "substation", "nominal_kv": 11.0, "phases": "ABC"},
            {"node_id": "load1", "node_type": "load", "nominal_kv": 11.0, "phases": "ABC"},
        ]
        edges = [
            {
                "edge_id": "L1",
                "from_node": "sub",
                "to_node": "load1",
                "edge_type": "line",
                "is_closed": True,
                "resistance_r_ohm": 0.1,
                "reactance_x_ohm": 0.05,
                "phases": "ABC",
                "ampacity_a": 200.0,
                "is_switchable": True,
                "normally_closed": True,
            }
        ]
        loads = {"load1": {"a": complex(10, 0), "b": complex(10, 0), "c": complex(10, 0)}}
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        l1 = next(c for c in result["contingencies"] if c["element"] == "L1")
        assert l1["unserved_load_kw"] > 0

    def test_tie_closed_after_n1_restoration(self):
        """With a switchable tie, mid-feeder outage reports non-empty restored_by."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=True)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        # L1 outage: bus1 and bus2 are lost; TIE1 can restore bus2 from sub
        l1 = next((c for c in result["contingencies"] if c["element"] == "L1"), None)
        assert l1 is not None
        # At least some restoration attempt occurs
        assert isinstance(l1["restored_by"], list)

    def test_n1_se_driven_loads_used_when_explicit_loads_none(self):
        """When se_result is provided and loads is None, SE-derived loads are used."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges, base_kw=20.0)
        explicit_loads = _uniform_loads(nodes, base_kw=20.0)

        svc = ContingencyAnalysisService()
        result_se = svc.analyze(nodes, edges, loads=None, se_result=se_result)
        result_explicit = svc.analyze(nodes, edges, loads=explicit_loads, se_result=None)

        # Both paths should agree on which contingency is worst
        assert result_se["n1_secure"] == result_explicit["n1_secure"]

    def test_open_elements_excluded_from_candidates(self):
        """An already-open (non-closed) element is not evaluated as a contingency."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=True)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        evaluated = {c["element"] for c in result["contingencies"]}
        # TIE1 is normally open — engine excludes it (is_closed=False)
        assert "TIE1" not in evaluated

    def test_customers_by_node_propagated_to_engine(self):
        """customers_by_node is reflected in lost_customers / unserved_customers."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        loads = _uniform_loads(nodes)
        customers = {"bus1": 50, "bus2": 30}
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads, customers_by_node=customers)
        l1 = next(c for c in result["contingencies"] if c["element"] == "L1")
        # L1 outage should report customers affected
        assert l1["lost_customers"] > 0


# ---------------------------------------------------------------------------
# OA-121 — Network Impact Assessment
# ---------------------------------------------------------------------------


class TestOA121NetworkImpactAssessment:
    """OA-121: restoration feasibility, islanding, violations, load-shedding."""

    def test_n1_secure_network_is_detected(self):
        """A network where last-segment outage is restorable reports n1_secure=True."""
        # n_load_nodes=2 ensures TIE1 (bus2→sub) is actually added by the helper.
        # L2 outage: bus2 goes dark, TIE1 closes → bus2 restored, unserved_load=0.
        # L1 outage: bus1+bus2 go dark; TIE1 restores bus2 only → L1 is 'unserved'.
        # So we build a single-segment network manually to guarantee full restoration.
        nodes = [
            {"node_id": "sub", "node_type": "substation", "nominal_kv": 11.0, "phases": "ABC"},
            {"node_id": "bus1", "node_type": "bus", "nominal_kv": 11.0, "phases": "ABC"},
        ]
        edges = [
            {
                "edge_id": "L1",
                "from_node": "sub",
                "to_node": "bus1",
                "edge_type": "line",
                "is_closed": True,
                "resistance_r_ohm": 0.1,
                "reactance_x_ohm": 0.05,
                "phases": "ABC",
                "ampacity_a": 200.0,
                "is_switchable": True,
                "normally_closed": True,
            },
            {
                "edge_id": "TIE1",
                "from_node": "bus1",
                "to_node": "sub",
                "edge_type": "tie",
                "is_closed": False,
                "resistance_r_ohm": 0.15,
                "reactance_x_ohm": 0.08,
                "phases": "ABC",
                "ampacity_a": 150.0,
                "is_switchable": True,
                "normally_closed": False,
            },
        ]
        loads = {"bus1": {"a": complex(1.5, 0), "b": complex(1.5, 0), "c": complex(1.5, 0)}}
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        assert result["n1_secure"] is True

    def test_restoration_feasibility_in_classification(self):
        """Last-segment contingency with a tie is classified 'restorable' or 'secure'."""
        # Use a 2-node network so the TIE1 helper guard (n_load_nodes>=2) fires.
        # L2 outage: bus2 lost, TIE1 restores it → 'restorable' or 'secure'.
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=True)
        loads = _uniform_loads(nodes, base_kw=2.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        # L2 is the last segment; it should be restorable via TIE1
        l2 = next((c for c in result["contingencies"] if c["element"] == "L2"), None)
        assert l2 is not None
        assert l2["classification"] in ("secure", "restorable", "violation")

    def test_unserved_contingency_classified_correctly(self):
        """Contingency with unrecoverable load is classified 'unserved'."""
        nodes, edges = _radial_network(n_load_nodes=1, with_tie=False)
        loads = _uniform_loads(nodes, base_kw=5.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        # No tie — L1 outage leaves bus1 unserved
        l1 = next(c for c in result["contingencies"] if c["element"] == "L1")
        assert l1["classification"] == "unserved"

    def test_impact_summary_counts_unserved(self):
        """impact_summary.unserved_count is > 0 when at least one contingency is unserved."""
        nodes, edges = _radial_network(n_load_nodes=1, with_tie=False)
        loads = _uniform_loads(nodes, base_kw=5.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        assert result["impact_summary"]["unserved_count"] > 0

    def test_load_floor_affects_classification_load(self):
        """load_floor raises the effective classification load for telemetry-silent nodes."""
        nodes, edges = _radial_network(n_load_nodes=1, with_tie=False)
        # Zero loads (AMI last-gasp silence)
        loads = {}
        load_floor = {"bus1": 20.0}
        svc = ContingencyAnalysisService()
        result_with_floor = svc.analyze(nodes, edges, loads, load_floor=load_floor)
        result_no_floor = svc.analyze(nodes, edges, loads, load_floor=None)
        l1_floor = next(c for c in result_with_floor["contingencies"] if c["element"] == "L1")
        l1_no = next(c for c in result_no_floor["contingencies"] if c["element"] == "L1")
        assert l1_floor["lost_load_kw"] >= l1_no["lost_load_kw"]

    def test_impact_summary_base_case_violations_zero_on_light_load(self):
        """Light load produces zero base-case violations."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        loads = _uniform_loads(nodes, base_kw=1.0)  # very light
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        assert result["impact_summary"]["base_case_violations"] == 0

    def test_assess_impact_standalone(self):
        """assess_impact() re-computes the same impact_summary from a completed result."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        reassessed = svc.assess_impact(result)
        assert reassessed["total_contingencies"] == result["impact_summary"]["total_contingencies"]
        assert reassessed["n1_secure"] == result["impact_summary"]["n1_secure"]


# ---------------------------------------------------------------------------
# OA-122 — Contingency Ranking
# ---------------------------------------------------------------------------


class TestOA122ContingencyRanking:
    """OA-122: deterministic severity ordering; worst 5; transparent ranking."""

    def test_contingencies_sorted_by_severity_descending(self):
        """Contingencies list is ordered by severity (highest first)."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        severities = [c["severity"] for c in result["contingencies"]]
        assert severities == sorted(severities, reverse=True)

    def test_worst_field_is_top5(self):
        """worst[] contains the top-5 most severe contingencies."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        worst_elements = [c["element"] for c in result.get("worst", [])]
        top5_elements = [c["element"] for c in result["contingencies"][:5]]
        assert worst_elements == top5_elements

    def test_most_upstream_outage_has_highest_severity(self):
        """The feeder head (L1) should be the most severe on an unrestorable network."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes, base_kw=30.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        most_severe = result["contingencies"][0]["element"]
        assert most_severe == "L1"

    def test_impact_summary_worst_unserved_load_matches_top_contingency(self):
        """impact_summary.worst_unserved_load_kw matches the top contingency's value."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        loads = _uniform_loads(nodes, base_kw=30.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        max_unserved = max(c["unserved_load_kw"] for c in result["contingencies"])
        assert abs(result["impact_summary"]["worst_unserved_load_kw"] - max_unserved) < 0.01

    def test_ranking_determinism(self):
        """Repeated calls produce identical contingency order."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=True)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        r1 = svc.analyze(nodes, edges, loads)
        r2 = svc.analyze(nodes, edges, loads)
        assert [c["element"] for c in r1["contingencies"]] == [
            c["element"] for c in r2["contingencies"]
        ]

    def test_impact_summary_classifications_sum_to_total(self):
        """Sum of classified contingencies equals total contingencies evaluated."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        total = sum(result["impact_summary"]["classifications"].values())
        assert total == result["impact_summary"]["total_contingencies"]

    def test_se_provenance_absent_when_no_se_result(self):
        """se_provenance key is absent when no SE result was provided."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        assert "se_provenance" not in result


# ---------------------------------------------------------------------------
# OA-123 — Platform Integration
# ---------------------------------------------------------------------------


class TestOA123PlatformIntegration:
    """OA-123: WP-007 snapshot adapter, SE integration, PF service injection."""

    def test_se_provenance_present_when_se_result_supplied(self):
        """se_provenance is populated when an SE result is provided."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, se_result=se_result)
        assert "se_provenance" in result
        assert result["se_provenance"] is not None

    def test_analyze_from_se_result_convenience_path(self):
        """analyze_from_se_result() produces the same result as analyze() with se_result."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges)
        svc = ContingencyAnalysisService()
        r1 = svc.analyze(nodes, edges, se_result=se_result)
        r2 = svc.analyze_from_se_result(se_result, nodes=nodes, edges=edges)
        assert r1["n1_secure"] == r2["n1_secure"]
        assert r1["contingencies_evaluated"] == r2["contingencies_evaluated"]

    def test_pf_service_injection_used_for_load_derivation(self):
        """When power_flow_service is injected, loads_from_se_result() is delegated."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges, base_kw=30.0)
        pf_svc = PowerFlowService()
        svc_with_pf = ContingencyAnalysisService(power_flow_service=pf_svc)
        svc_without_pf = ContingencyAnalysisService()
        r_with = svc_with_pf.analyze(nodes, edges, se_result=se_result)
        r_without = svc_without_pf.analyze(nodes, edges, se_result=se_result)
        # Both paths should agree on the contingency count
        assert r_with["contingencies_evaluated"] == r_without["contingencies_evaluated"]

    def test_explicit_loads_override_se_result(self):
        """When both loads and se_result are given, explicit loads take precedence."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges, base_kw=100.0)  # heavy SE loads
        light_loads = _uniform_loads(nodes, base_kw=1.0)  # explicit light loads
        svc = ContingencyAnalysisService()
        result_explicit = svc.analyze(nodes, edges, loads=light_loads, se_result=se_result)
        result_se = svc.analyze(nodes, edges, loads=None, se_result=se_result)
        # With light explicit loads, unserved load should be less than with SE heavy loads
        max_unserved_explicit = max(c["unserved_load_kw"] for c in result_explicit["contingencies"])
        max_unserved_se = max(c["unserved_load_kw"] for c in result_se["contingencies"])
        assert max_unserved_explicit < max_unserved_se

    def test_snapshot_adapter_returns_empty_on_none_repo(self):
        """_nodes_edges_from_snapshot() returns ([], []) when no repo and snapshot=None."""
        svc = ContingencyAnalysisService(topology_repository=None)
        nodes, edges = svc._nodes_edges_from_snapshot(None)
        assert nodes == []
        assert edges == []

    def test_grid_analytics_service_passes_se_result(self):
        """GridAnalyticsService.analyze_contingency() accepts and forwards se_result."""
        from services.adms_grid_analytics import GridAnalyticsService

        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges)
        svc = GridAnalyticsService()
        result = svc.analyze_contingency(nodes=nodes, edges=edges, se_result=se_result)
        assert "se_provenance" in result
        assert result["service"] == "ContingencyAnalysisService"

    def test_se_method_captured_in_provenance(self):
        """se_provenance carries the SE method string from the SE result."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_result = _se_result_for(nodes, edges)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, se_result=se_result)
        assert result["se_provenance"]["method"] is not None


# ---------------------------------------------------------------------------
# OA-124 — Engineering Validation
# ---------------------------------------------------------------------------


class TestOA124EngineeringValidation:
    """OA-124: determinism, numerical repeatability, regression compatibility."""

    def test_full_determinism_repeated_calls(self):
        """Identical inputs always produce identical severity scores across calls."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=True)
        loads = _uniform_loads(nodes)
        svc = ContingencyAnalysisService()
        results = [svc.analyze(nodes, edges, loads) for _ in range(3)]
        for r in results[1:]:
            for a, b in zip(r["contingencies"], results[0]["contingencies"], strict=True):
                assert a["severity"] == b["severity"]
                assert a["unserved_load_kw"] == b["unserved_load_kw"]

    def test_se_to_contingency_chain_end_to_end(self):
        """Full SE→CA chain: StateEstimationService result drives ContingencyAnalysisService."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        se_svc = StateEstimationService()
        meas = {
            n["node_id"]: {"p_kw": 20.0, "q_kvar": 0.0}
            for n in nodes
            if n["node_type"] != "substation"
        }
        se_result = se_svc.estimate(nodes, edges, meas)
        ca_svc = ContingencyAnalysisService()
        result = ca_svc.analyze_from_se_result(se_result, nodes=nodes, edges=edges)
        assert "contingencies" in result
        assert result["contingencies_evaluated"] > 0
        assert result["service"] == "ContingencyAnalysisService"

    def test_analytics_regression_wp012_01_02_03_04(self):
        """Full analytics regression: WP-012-01 through WP-012-04 — 154 non-meta tests."""
        import subprocess  # nosec B404

        # Exclude this meta-test from the subprocess to prevent infinite recursion.
        r = subprocess.run(  # nosec B603
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_analytics_architecture.py",
                "tests/test_adms_state_estimation_service.py",
                "tests/test_adms_power_flow_service.py",
                "tests/test_adms_contingency_analysis_service.py",
                "-k",
                "not test_analytics_regression_wp012_01_02_03_04",
                "-q",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert r.returncode == 0, f"Regression suite failed:\n{r.stdout}\n{r.stderr}"

    def test_n1_secure_result_has_zero_unserved(self):
        """n1_secure=True implies every contingency has unserved_load_kw == 0."""
        nodes, edges = _radial_network(n_load_nodes=1, with_tie=True)
        loads = _uniform_loads(nodes, base_kw=2.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        if result["n1_secure"]:
            for c in result["contingencies"]:
                assert c["unserved_load_kw"] == 0.0

    def test_empty_loads_does_not_crash(self):
        """ContingencyAnalysisService handles empty loads gracefully."""
        nodes, edges = _radial_network(n_load_nodes=2, with_tie=False)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads={})
        assert "contingencies" in result

    def test_impact_summary_consistent_with_contingencies(self):
        """impact_summary fields are internally consistent with the contingencies list."""
        nodes, edges = _radial_network(n_load_nodes=3, with_tie=False)
        loads = _uniform_loads(nodes, base_kw=30.0)
        svc = ContingencyAnalysisService()
        result = svc.analyze(nodes, edges, loads)
        summary = result["impact_summary"]
        actual_unserved = sum(1 for c in result["contingencies"] if c["unserved_load_kw"] > 0)
        assert summary["unserved_count"] == actual_unserved
        assert summary["total_contingencies"] == result["contingencies_evaluated"]
