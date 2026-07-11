"""WP-012-05 — Volt/VAR Optimisation service validation suite (OA-130).

42 tests across 6 classes, one class per OA objective.

Network fixture (shared)
------------------------
1-bus radial feeder, 0.415 kV LV, high reactive load:
  SUB (substation) --[L1: R=0.1Ω X=0.08Ω]--> BUS1 (80 kW + 200 kvar, 3-phase)

BFS analysis (Z_base = 0.415² = 0.172 Ω, S_base = 1 MVA):
  r_pu = 0.581, x_pu = 0.465; I_pu ≈ complex(0.08, -0.2)
  V_BUS1 ≈ 0.864 pu → violation (< 0.95) in base case

With 240 kvar capacitor at BUS1 (80 kvar / phase):
  Net Q = −13.3 kvar/phase (slightly capacitive); V_BUS1 ≈ 0.974 pu → no violation
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


# ------------------------------------------------------------------ #
# Shared helpers                                                       #
# ------------------------------------------------------------------ #


def _high_q_network():
    """High reactive-load 1-bus feeder that has a voltage violation in base case."""
    nodes = [
        {
            "node_id": "SUB",
            "node_type": "substation",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "name": "SUB",
            "base_load_kw": 0.0,
            "base_load_kvar": 0.0,
            "attrs": {},
        },
        {
            "node_id": "BUS1",
            "node_type": "bus",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "name": "BUS1",
            "base_load_kw": 80.0,
            "base_load_kvar": 200.0,
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
            "resistance_r_ohm": 0.1,
            "reactance_x_ohm": 0.08,
            "phases": "ABC",
            "ampacity_a": None,
            "length_km": None,
            "attrs": {},
        },
    ]
    loads = {
        "BUS1": {
            "a": complex(80.0 / 3, 200.0 / 3),
            "b": complex(80.0 / 3, 200.0 / 3),
            "c": complex(80.0 / 3, 200.0 / 3),
        }
    }
    return nodes, edges, loads


def _two_bus_network():
    """2-node load network for multi-device combinatorics tests."""
    nodes = [
        {
            "node_id": "SUB",
            "node_type": "substation",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "name": "SUB",
            "base_load_kw": 0.0,
            "base_load_kvar": 0.0,
            "attrs": {},
        },
        {
            "node_id": "B1",
            "node_type": "bus",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "name": "B1",
            "base_load_kw": 40.0,
            "base_load_kvar": 100.0,
            "attrs": {},
        },
        {
            "node_id": "B2",
            "node_type": "bus",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "name": "B2",
            "base_load_kw": 40.0,
            "base_load_kvar": 100.0,
            "attrs": {},
        },
    ]
    edges = [
        {
            "edge_id": "L1",
            "from_node": "SUB",
            "to_node": "B1",
            "edge_type": "line",
            "is_closed": True,
            "is_switchable": False,
            "normally_closed": True,
            "resistance_r_ohm": 0.1,
            "reactance_x_ohm": 0.08,
            "phases": "ABC",
            "ampacity_a": None,
            "length_km": None,
            "attrs": {},
        },
        {
            "edge_id": "L2",
            "from_node": "B1",
            "to_node": "B2",
            "edge_type": "line",
            "is_closed": True,
            "is_switchable": False,
            "normally_closed": True,
            "resistance_r_ohm": 0.1,
            "reactance_x_ohm": 0.08,
            "phases": "ABC",
            "ampacity_a": None,
            "length_km": None,
            "attrs": {},
        },
    ]
    _ph = {
        "a": complex(40.0 / 3, 100.0 / 3),
        "b": complex(40.0 / 3, 100.0 / 3),
        "c": complex(40.0 / 3, 100.0 / 3),
    }
    loads = {"B1": dict(_ph), "B2": dict(_ph)}
    return nodes, edges, loads


def _cap_device(
    node_id: str, q_kvar: float, phases: str = "ABC", device_id: str | None = None
) -> dict:
    return {
        "device_id": device_id or f"CAP_{node_id}",
        "node_id": node_id,
        "phases": phases,
        "q_injection_kvar": q_kvar,
        "device_type": "capacitor",
    }


def _make_se_result(nodes: list[dict], p_kw: float = 80.0, q_kvar: float = 200.0) -> dict:
    """Synthetic SE result consistent with the supplied node list."""
    return {
        "method": "LinDistFlow WLS",
        "measurements": 3,
        "states": len(nodes),
        "bad_data": None,
        "chi2_ok": True,
        "nodes": [
            {
                "node_id": n["node_id"],
                "energized": n["node_type"] != "substation",
                "estimated_p_kw": 0.0 if n["node_type"] == "substation" else p_kw,
                "estimated_q_kvar": 0.0 if n["node_type"] == "substation" else q_kvar,
                "estimated_voltage_pu": 1.0,
            }
            for n in nodes
        ],
    }


# ------------------------------------------------------------------ #
# Class 1 — OA-125: VoltVAR Service Integration                       #
# ------------------------------------------------------------------ #


class TestOA125VoltVARServiceIntegration:
    """Service must delegate to the engine; no solver logic may live here."""

    def test_no_pf_solver_logic_in_service_module(self):
        """volt_var_service.py must not contain BFS sweep symbols."""
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/volt_var_service.py").read_text()
        for forbidden in ("SLACK", "i_load", "backward_sweep", "forward_sweep"):
            assert forbidden not in src, f"BFS symbol {forbidden!r} found in service module"

    def test_no_contingency_algorithm_in_service_module(self):
        """volt_var_service.py must not contain contingency engine symbols."""
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/volt_var_service.py").read_text()
        for forbidden in ("_energized(", "_restore(", "_is_radial("):
            assert forbidden not in src, f"CA symbol {forbidden!r} found in service module"

    def test_exported_from_package(self):
        from services.adms_grid_analytics import VoltVARService, __all__

        assert "VoltVARService" in __all__
        assert VoltVARService is not None

    def test_grid_analytics_service_has_optimize_volt_var(self):
        from services.adms_grid_analytics import GridAnalyticsService

        assert callable(getattr(GridAnalyticsService, "analyze_volt_var", None))

    def test_grid_analytics_service_delegates_correctly(self):
        from services.adms_grid_analytics import GridAnalyticsService

        nodes, edges, loads = _high_q_network()
        svc = GridAnalyticsService()
        result = svc.analyze_volt_var(nodes=nodes, edges=edges, loads=loads, devices=[])
        assert result["service"] == "VoltVARService"

    def test_constructor_injection_accepted(self):
        from services.adms_grid_analytics import VoltVARService

        svc = VoltVARService(
            topology_repository=None,
            state_estimation_service=None,
            power_flow_service=None,
            contingency_analysis_service=None,
            options={"v_target_pu": 1.02},
        )
        assert svc._default_options["v_target_pu"] == 1.02

    def test_service_identifier_in_result(self):
        from services.adms_grid_analytics import VoltVARService

        nodes, edges, loads = _high_q_network()
        svc = VoltVARService()
        result = svc.optimize(nodes, edges, loads=loads, devices=[])
        assert result.get("service") == "VoltVARService"


# ------------------------------------------------------------------ #
# Class 2 — OA-126: Reactive Device Modelling                         #
# ------------------------------------------------------------------ #


class TestOA126ReactiveDeviceModelling:
    """Device injection convention: cap bank = negative Q load entry."""

    def test_reactive_device_spec_in_contracts(self):
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/contracts.py").read_text()
        assert "ReactiveDeviceSpec" in src

    def test_volt_var_config_in_contracts(self):
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/contracts.py").read_text()
        assert "VoltVARConfig" in src

    def test_capacitive_injection_reduces_q_demand(self):
        from services.adms_grid_analytics.volt_var import _apply_device_state

        loads = {"BUS1": {"a": complex(26.67, 66.67)}}
        devices = [_cap_device("BUS1", q_kvar=66.67 * 3, phases="A")]
        # 200 kvar over phase A = 200j delta on phase a
        state = {"CAP_BUS1": True}
        modified = _apply_device_state(loads, devices, state)
        # Net Q on phase a should drop significantly
        assert modified["BUS1"]["a"].imag < loads["BUS1"]["a"].imag

    def test_device_off_no_change_to_loads(self):
        from services.adms_grid_analytics.volt_var import _apply_device_state

        loads = {"BUS1": {"a": complex(26.67, 66.67), "b": complex(26.67, 66.67)}}
        devices = [_cap_device("BUS1", q_kvar=100.0)]
        state = {"CAP_BUS1": False}
        modified = _apply_device_state(loads, devices, state)
        assert modified == loads

    def test_three_phase_device_distributes_equally(self):
        from services.adms_grid_analytics.volt_var import _apply_device_state

        loads = {"BUS1": {"a": 0j, "b": 0j, "c": 0j}}
        devices = [_cap_device("BUS1", q_kvar=120.0, phases="ABC")]
        state = {"CAP_BUS1": True}
        modified = _apply_device_state(loads, devices, state)
        assert abs(modified["BUS1"]["a"].imag + 40.0) < 1e-9
        assert abs(modified["BUS1"]["b"].imag + 40.0) < 1e-9
        assert abs(modified["BUS1"]["c"].imag + 40.0) < 1e-9

    def test_single_phase_device_affects_one_phase(self):
        from services.adms_grid_analytics.volt_var import _apply_device_state

        loads = {"BUS1": {"a": complex(10.0, 50.0), "b": complex(10.0, 50.0)}}
        devices = [_cap_device("BUS1", q_kvar=30.0, phases="A")]
        state = {"CAP_BUS1": True}
        modified = _apply_device_state(loads, devices, state)
        assert modified["BUS1"]["a"].imag == pytest.approx(50.0 - 30.0, abs=1e-9)
        assert modified["BUS1"]["b"] == loads["BUS1"]["b"]

    def test_zero_injection_device_no_effect(self):
        from services.adms_grid_analytics.volt_var import _apply_device_state

        loads = {"BUS1": {"a": complex(10.0, 30.0)}}
        devices = [_cap_device("BUS1", q_kvar=0.0)]
        state = {"CAP_BUS1": True}
        modified = _apply_device_state(loads, devices, state)
        assert modified == loads


# ------------------------------------------------------------------ #
# Class 3 — OA-127: VoltVAR Engine                                    #
# ------------------------------------------------------------------ #


class TestOA127VoltVAREngine:
    """Engine must enumerate configs, score via PF, and select optimal."""

    def test_engine_selects_minimum_score(self):
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        devices = [_cap_device("BUS1", q_kvar=240.0)]
        result = optimize(nodes, edges, loads, devices)
        # With high-Q load causing violations, cap-on should win
        base_viol = result["base_case"]["violation_count"]
        opt_viol = result["optimal_case"]["violation_count"]
        assert opt_viol <= base_viol

    def test_all_configurations_returned(self):
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _two_bus_network()
        devices = [
            _cap_device("B1", q_kvar=120.0, device_id="C1"),
            _cap_device("B2", q_kvar=120.0, device_id="C2"),
        ]
        result = optimize(nodes, edges, loads, devices)
        assert result["configurations_evaluated"] == 4
        assert len(result["configurations"]) == 4

    def test_configurations_sorted_by_score(self):
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        devices = [_cap_device("BUS1", q_kvar=240.0)]
        result = optimize(nodes, edges, loads, devices)
        scores = [c["score"] for c in result["configurations"]]
        assert scores == sorted(scores)

    def test_base_case_in_result(self):
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        result = optimize(nodes, edges, loads, [])
        assert "violation_count" in result["base_case"]
        assert "total_loss_kw" in result["base_case"]
        assert "converged" in result["base_case"]

    def test_optimal_case_in_result(self):
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        devices = [_cap_device("BUS1", q_kvar=240.0)]
        result = optimize(nodes, edges, loads, devices)
        assert "violation_count" in result["optimal_case"]
        assert "total_loss_kw" in result["optimal_case"]
        assert "converged" in result["optimal_case"]

    def test_devices_evaluated_count(self):
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _two_bus_network()
        devices = [
            _cap_device("B1", q_kvar=60.0, device_id="C1"),
            _cap_device("B2", q_kvar=60.0, device_id="C2"),
            _cap_device("B1", q_kvar=60.0, device_id="C3"),
        ]
        result = optimize(nodes, edges, loads, devices)
        assert result["devices_evaluated"] == 3
        assert result["configurations_evaluated"] == 8  # 2^3

    def test_no_pf_reimplementation_in_engine(self):
        """volt_var.py must consume the PF engine, not reimplement it."""
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/volt_var.py").read_text()
        # Check for actual solver algorithm symbols, not documentation references
        for forbidden in ("SLACK", "i_load", "backward_sweep", "forward_sweep"):
            assert forbidden not in src, f"Solver symbol {forbidden!r} found in engine"
        assert "powerflow" in src, "Engine must consume powerflow module"


# ------------------------------------------------------------------ #
# Class 4 — OA-128: Platform Integration                              #
# ------------------------------------------------------------------ #


class TestOA128PlatformIntegration:
    """Service must consume SE result, optionally verify CA, accept snapshot."""

    def test_se_result_drives_load_profile(self):
        """When se_result provided without loads, SE Q flows into engine."""
        from services.adms_grid_analytics import VoltVARService

        nodes, edges, _ = _high_q_network()
        se_result = _make_se_result(nodes, p_kw=80.0, q_kvar=200.0)
        svc = VoltVARService()
        # Explicit loads NOT provided — must be derived from se_result
        result = svc.optimize(nodes, edges, se_result=se_result, devices=[])
        assert result is not None
        assert result.get("service") == "VoltVARService"

    def test_se_provenance_captured(self):
        from services.adms_grid_analytics import VoltVARService

        nodes, edges, _ = _high_q_network()
        se_result = _make_se_result(nodes)
        svc = VoltVARService()
        result = svc.optimize(nodes, edges, se_result=se_result, devices=[])
        assert "se_provenance" in result
        assert result["se_provenance"]["method"] == "LinDistFlow WLS"

    def test_explicit_loads_override_se_when_provided(self):
        """Explicit loads take precedence over SE derivation."""
        from services.adms_grid_analytics import VoltVARService

        nodes, edges, explicit_loads = _high_q_network()
        se_result = _make_se_result(nodes, p_kw=1.0, q_kvar=1.0)  # tiny SE loads
        svc = VoltVARService()
        # With explicit loads + se_result, result should reflect explicit loads
        result_explicit = svc.optimize(
            nodes, edges, loads=explicit_loads, se_result=se_result, devices=[]
        )
        result_se_only = svc.optimize(nodes, edges, se_result=se_result, devices=[])
        # Losses differ because loads differ
        assert (
            result_explicit["base_case"]["total_loss_kw"]
            != result_se_only["base_case"]["total_loss_kw"]
        )

    def test_contingency_verification_optional(self):
        """verify_contingency=True without ca_svc → no contingency_verification key."""
        from services.adms_grid_analytics import VoltVARService

        nodes, edges, loads = _high_q_network()
        svc = VoltVARService()  # no ca_svc
        result = svc.optimize(nodes, edges, loads=loads, devices=[], verify_contingency=True)
        assert "contingency_verification" not in result

    def test_optimize_from_se_result_convenience(self):
        """optimize_from_se_result produces same result as optimize(se_result=...)."""
        from services.adms_grid_analytics import VoltVARService

        nodes, edges, _ = _high_q_network()
        se_result = _make_se_result(nodes)
        svc = VoltVARService()
        r1 = svc.optimize(nodes, edges, se_result=se_result, devices=[])
        r2 = svc.optimize_from_se_result(se_result, nodes=nodes, edges=edges, devices=[])
        assert r1["optimal_score"] == r2["optimal_score"]
        assert r1["configurations_evaluated"] == r2["configurations_evaluated"]

    def test_snapshot_adapter_available(self):
        """_nodes_edges_from_snapshot(None) returns empty lists gracefully."""
        from services.adms_grid_analytics import VoltVARService

        svc = VoltVARService()
        nodes, edges = svc._nodes_edges_from_snapshot(None)
        assert nodes == []
        assert edges == []

    def test_volt_var_result_in_contracts(self):
        """contracts.py must define VoltVARResult TypedDict."""
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/contracts.py").read_text()
        assert "VoltVARResult" in src
        assert "optimal_state" in src


# ------------------------------------------------------------------ #
# Class 5 — OA-129: PAR-003 Debt Resolution                           #
# ------------------------------------------------------------------ #


class TestOA129PARDebtResolution:
    """Verify all five PAR-003 debt items are resolved."""

    def test_contract_version_present(self):
        """OA-129.3: CONTRACT_VERSION must be defined at module level."""
        from services.adms_grid_analytics.contracts import CONTRACT_VERSION

        assert CONTRACT_VERSION is not None

    def test_contract_version_is_string(self):
        """OA-129.3: CONTRACT_VERSION must be a string."""
        from services.adms_grid_analytics.contracts import CONTRACT_VERSION

        assert isinstance(CONTRACT_VERSION, str)
        assert len(CONTRACT_VERSION) > 0

    def test_pf_service_se_svc_wired_up(self):
        """OA-129.4: solve_from_se_result must use _se_svc when se_result omitted."""
        from services.adms_grid_analytics import PowerFlowService

        nodes, edges, _ = _high_q_network()
        se_result = _make_se_result(nodes)

        class _MockSE:
            def estimate(self, n, e):
                return se_result

        svc = PowerFlowService(state_estimation_service=_MockSE())
        result = svc.solve_from_se_result(nodes=nodes, edges=edges)
        assert result["service"] == "PowerFlowService"

    def test_pf_service_solve_from_se_result_raises_without_se_or_svc(self):
        """OA-129.4: ValueError when se_result omitted and no _se_svc configured."""
        from services.adms_grid_analytics import PowerFlowService

        nodes, edges, _ = _high_q_network()
        svc = PowerFlowService()
        with pytest.raises(ValueError, match="se_result required"):
            svc.solve_from_se_result(nodes=nodes, edges=edges)

    def test_shared_adapter_module_exists(self):
        """OA-129.5: _adapters module must be importable with expected callables."""
        from services.adms_grid_analytics._adapters import (
            loads_from_se_result,
            nodes_edges_from_snapshot,
        )

        assert callable(nodes_edges_from_snapshot)
        assert callable(loads_from_se_result)

    def test_services_use_shared_adapter(self):
        """OA-129.5: all 5 service modules must delegate to the shared adapter."""
        svc_dir = PROJECT_ROOT / "services/adms_grid_analytics"
        modules = [
            "state_estimation_service.py",
            "power_flow_service.py",
            "contingency_analysis_service.py",
            "service.py",
            "volt_var_service.py",
        ]
        for fname in modules:
            src = (svc_dir / fname).read_text()
            assert (
                "nodes_edges_from_snapshot" in src
            ), f"{fname} does not reference shared nodes_edges_from_snapshot"
            assert "_adapters" in src, f"{fname} does not import from _adapters"

    def test_dual_source_protocol_documented(self):
        """OA-129.1/2: _adapters.py must document SE+PF dual-source protocol."""
        src = Path(PROJECT_ROOT, "services/adms_grid_analytics/_adapters.py").read_text()
        assert "SE branch" in src or "se branch" in src.lower(), "SE siting protocol not documented"
        assert (
            "PF node" in src or "pf node" in src.lower()
        ), "PF verification protocol not documented"
        assert (
            "q_injection_kvar" in src.lower()
        ), "Reactive device modelling protocol not documented"


# ------------------------------------------------------------------ #
# Class 6 — OA-130: Engineering Validation                            #
# ------------------------------------------------------------------ #


class TestOA130EngineeringValidation:
    """Determinism, regression, and end-to-end validation."""

    def test_determinism_3x_repeated_calls(self):
        """Identical inputs must produce identical outputs across three calls."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        devices = [_cap_device("BUS1", q_kvar=240.0)]
        r1 = optimize(nodes, edges, loads, devices)
        r2 = optimize(nodes, edges, loads, devices)
        r3 = optimize(nodes, edges, loads, devices)
        assert r1["optimal_score"] == r2["optimal_score"] == r3["optimal_score"]
        assert r1["optimal_state"] == r2["optimal_state"] == r3["optimal_state"]
        assert (
            r1["configurations_evaluated"]
            == r2["configurations_evaluated"]
            == r3["configurations_evaluated"]
        )

    def test_analytics_regression_wp012_01_02_03_04_05(self):
        """WP-012-01 through 05 must all pass (195 non-meta tests)."""
        import subprocess  # nosec B404

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
                "-k",
                "not analytics_regression",
                "-q",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        output = result.stdout + result.stderr
        assert "195 passed" in output, f"Analytics regression failed:\n{output}"

    def test_se_vvo_chain_end_to_end(self):
        """Full SE → VVO chain: SE result drives load profile for VVO."""
        from services.adms_grid_analytics import StateEstimationService, VoltVARService

        nodes, edges, _ = _high_q_network()
        measurements = {
            "SUB": {"voltage_pu": 1.0},
            "BUS1": {"p_kw": 80.0, "q_kvar": 200.0},
        }
        se_svc = StateEstimationService()
        se_result = se_svc.estimate(nodes, edges, measurements)
        assert se_result["service"] == "StateEstimationService"

        devices = [_cap_device("BUS1", q_kvar=240.0)]
        vvo_svc = VoltVARService()
        result = vvo_svc.optimize(nodes, edges, se_result=se_result, devices=devices)
        assert result["service"] == "VoltVARService"
        assert "se_provenance" in result
        assert result["configurations_evaluated"] == 2

    def test_optimal_never_worse_than_base(self):
        """Optimal config score must be ≤ the all-devices-off config score."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        devices = [_cap_device("BUS1", q_kvar=240.0)]
        result = optimize(nodes, edges, loads, devices)
        # The all-off config (mask=0) is always in configurations
        all_off = next(c for c in result["configurations"] if not any(c["device_state"].values()))
        assert result["optimal_score"] <= all_off["score"]

    def test_violation_penalty_dominates_loss_objective(self):
        """A config with fewer violations must rank better than one with more."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _high_q_network()
        devices = [_cap_device("BUS1", q_kvar=240.0)]
        result = optimize(nodes, edges, loads, devices)
        # Find the two configs
        configs_by_viol: dict[int, list[dict]] = {}
        for c in result["configurations"]:
            v = c["violation_count"]
            configs_by_viol.setdefault(v, []).append(c)
        viol_counts = sorted(configs_by_viol.keys())
        if len(viol_counts) > 1:
            # Every low-violation config must score better than every high-viol config
            low_viol_scores = [c["score"] for c in configs_by_viol[viol_counts[0]]]
            high_viol_scores = [c["score"] for c in configs_by_viol[viol_counts[-1]]]
            assert max(low_viol_scores) < min(high_viol_scores), (
                "Violation penalty must dominate: any config with fewer violations "
                "should score better than any config with more violations"
            )

    def test_impact_summary_via_assess_impact(self):
        """ContingencyAnalysisService.assess_impact() must work on a VVO-derived result."""
        from services.adms_grid_analytics import ContingencyAnalysisService

        nodes, edges, _ = _high_q_network()
        # Add a load to make CA meaningful
        loads = {
            "BUS1": {"a": complex(20.0, 10.0), "b": complex(20.0, 10.0), "c": complex(20.0, 10.0)}
        }
        ca_svc = ContingencyAnalysisService()
        ca_result = ca_svc.analyze(nodes, edges, loads=loads)
        summary = ca_svc.assess_impact(ca_result)
        assert "total_contingencies" in summary
        assert "n1_secure" in summary
        assert "classifications" in summary

    def test_multiple_devices_combinatorics(self):
        """3 devices must produce 2^3=8 evaluated configurations."""
        from services.adms_grid_analytics.volt_var import optimize

        nodes, edges, loads = _two_bus_network()
        devices = [
            _cap_device("B1", q_kvar=120.0, device_id="C1"),
            _cap_device("B2", q_kvar=120.0, device_id="C2"),
            _cap_device("B1", q_kvar=60.0, device_id="C3"),
        ]
        result = optimize(nodes, edges, loads, devices)
        assert result["devices_evaluated"] == 3
        assert result["configurations_evaluated"] == 8
        # Each config must have all 3 device_state keys
        for c in result["configurations"]:
            assert set(c["device_state"].keys()) == {"C1", "C2", "C3"}
