"""Stable analytical contracts for the ADMS Grid Analytics service layer.

Defines the canonical input and output shapes for each engine in this package.
All engine functions accept and return plain dicts whose structure is documented
here as TypedDicts — callers and adapters should validate at boundary crossings,
not inside the engines.

These contracts version with the service package; breaking changes require a
new major version in the package docstring and a migration guide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

CONTRACT_VERSION: str = "1.1"
"""Version token for the contracts module (OA-129.3 / F-PAR003-03).

Increment the minor component (x.Y) for each work package that adds new
TypedDict fields without breaking existing callers. Increment the major
component (X.0) when a breaking change is made to an existing contract shape.
  1.0 — EPIC-012 / WP-012-05 (Volt/VAR Optimisation)
  1.1 — EPIC-012 / WP-012-06 (Advanced Network Analytics OA-131..136)
"""

if TYPE_CHECKING:
    from typing import TypedDict

    # ------------------------------------------------------------------ #
    # Input contracts                                                       #
    # ------------------------------------------------------------------ #

    class NodeSpec(TypedDict, total=False):
        """Minimum required keys for a network node dict consumed by engines."""

        node_id: str  # required — unique string identifier
        node_type: str  # required — "substation" | "bus" | "load" | "meter" | "transformer"
        nominal_kv: float  # required — line-to-line voltage base (kV)
        name: str | None
        phases: str | None  # "ABC" (default), "AB", "A", "B", "C" etc.
        base_load_kw: float  # pseudo-measurement fallback (state estimation)
        base_load_kvar: float
        attrs: dict[str, Any]  # pass-through for device metadata

    class EdgeSpec(TypedDict, total=False):
        """Minimum required keys for a network edge dict consumed by engines."""

        edge_id: str  # required — unique string identifier
        from_node: str  # required
        to_node: str  # required
        edge_type: str  # required — "line" | "switch" | "tie" | "transformer"
        is_closed: bool  # required — True = conducting
        resistance_r_ohm: float
        reactance_x_ohm: float
        ampacity_a: float  # thermal limit (amps)
        length_km: float  # used by fault_location impedance distance
        phases: str | None
        is_switchable: bool  # used by contingency / reconfiguration
        normally_closed: bool  # used by outage_inference structural pass
        attrs: dict[str, Any]

    class MeasurementMap(TypedDict, total=False):
        """Keyed by node_id; each value is a partial measurement dict."""

        # per-node measurement keys (all optional)
        p_kw: float
        q_kvar: float
        voltage_pu: float

    class PhaseLoad(TypedDict):
        """Per-phase complex load for three-phase power flow."""

        # keys are phase letters "a", "b", "c"; values are complex(P_kw, Q_kvar)
        pass  # documented only — TypedDict doesn't support dynamic keys

    # ------------------------------------------------------------------ #
    # Output contracts                                                      #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # WP-012-02 service-layer contracts                                    #
    # ------------------------------------------------------------------ #

    class SEConsistencyCheck(TypedDict):
        """Result of PowerFlowService.validate_se_consistency()."""

        consistent: bool
        errors: list[str]
        warnings: list[str]

    class StateEstimationConfig(TypedDict, total=False):
        """Tuning options accepted by StateEstimationService and the engine."""

        sigma_p_meter_kw: float
        sigma_q_meter_kvar: float
        sigma_v_meter_pu: float
        sigma_p_pseudo_kw: float
        sigma_q_pseudo_kvar: float
        bad_data_threshold: float
        confidence_ref_pu: float

    class MeasurementSummary(TypedDict):
        """Measurement processing summary produced by StateEstimationService."""

        monitored_nodes: int
        unmonitored_nodes: int
        total_measurement_values: int
        coverage_pct: float
        rejected: list[dict[str, Any]]

    class TopologyValidation(TypedDict):
        """Topology consistency check produced by StateEstimationService."""

        valid: bool
        node_count: int
        edge_count: int
        substation_count: int
        closed_edge_count: int
        errors: list[str]
        warnings: list[str]

    class EstimationResult(TypedDict, total=False):
        """Return type of state_estimation.estimate() / StateEstimationService.estimate()."""

        method: str
        nodes: list[dict[str, Any]]
        branches: list[dict[str, Any]]
        bad_data: dict[str, Any] | None
        max_normalized_residual: float
        reference_node: str
        # WP-012-02 enrichment fields (present when called via StateEstimationService)
        topology: TopologyValidation
        measurement_summary: MeasurementSummary
        service: str

    class PowerFlowConfig(TypedDict, total=False):
        """Tuning options accepted by PowerFlowService and the engine."""

        tol_pu: float
        max_iter: int
        v_min_pu: float
        v_max_pu: float

    class PowerFlowResult(TypedDict, total=False):
        """Return type of powerflow.solve() / PowerFlowService.solve()."""

        method: str
        converged: bool
        iterations: int
        max_mismatch_pu: float
        total_loss_kw: float
        tolerance_pu: float
        v_band_pu: list[float]
        violations: list[dict[str, Any]]
        violation_count: int
        nodes: list[dict[str, Any]]
        branches: list[dict[str, Any]]
        # WP-012-03 enrichment fields (present when called via PowerFlowService)
        service: str
        se_provenance: dict[str, Any] | None

    class ContingencyImpactSummary(TypedDict):
        """Operator-facing impact summary produced by ContingencyAnalysisService."""

        total_contingencies: int
        n1_secure: bool
        classifications: dict[str, int]
        unserved_count: int
        violation_only_count: int
        worst_unserved_load_kw: float
        worst_unserved_customers: int
        base_case_violations: int

    class ContingencyResult(TypedDict, total=False):
        """Return type of contingency.analyze() / ContingencyAnalysisService.analyze()."""

        method: str
        base_case: dict[str, Any]
        n1_secure: bool
        contingencies_evaluated: int
        worst: list[dict[str, Any]]
        contingencies: list[dict[str, Any]]
        # WP-012-04 enrichment fields (present when called via ContingencyAnalysisService)
        service: str
        se_provenance: dict[str, Any] | None
        impact_summary: dict[str, Any]

    class FaultLocationResult(TypedDict, total=False):
        """Return type of fault_location.locate()."""

        method: str
        inputs: dict[str, Any]
        impedance_candidates: list[dict[str, Any]]
        topological: dict[str, Any] | None
        best_estimate: dict[str, Any] | None

    class ReconfigurationResult(TypedDict, total=False):
        """Return type of reconfiguration.recommend()."""

        method: str
        reconfigurable_switches: list[str]
        evaluated: int
        feasible_count: int
        current: dict[str, Any] | None
        recommended: dict[str, Any] | None
        switching_plan: list[dict[str, Any]]
        action_required: bool
        loss_reduction_kw: float | None
        loss_reduction_pct: float | None
        note: str

    class OutageInferenceResult(TypedDict, total=False):
        """Return type of outage_inference.infer()."""

        method: str
        dark_meter_count: int
        inferred_outages: list[dict[str, Any]]
        outage_count: int
        silent_failure_suspected: bool
        silent_failure_nodes: list[str]

    class OutageValidationResult(TypedDict, total=False):
        """Return type of outage_validation.cross_check()."""

        method: str
        checks: list[dict[str, Any]]
        consistent: bool
        mismatch_count: int
        mismatches: list[dict[str, Any]]

    class CrewDispatchResult(TypedDict, total=False):
        """Return type of crew_dispatch.recommend()."""

        method: str
        candidates: list[dict[str, Any]]
        crew_dispatch_count: int
        remote_switch_count: int

    # ------------------------------------------------------------------ #
    # WP-012-05 service-layer contracts (OA-125 / OA-126)                  #
    # ------------------------------------------------------------------ #

    class ReactiveDeviceSpec(TypedDict, total=False):
        """Specification for a reactive compensation device (OA-126).

        Reactive device modelling protocol
        ------------------------------------
        Capacitor banks and shunt compensation are modelled as negative-Q loads.
        When a device is in the ON state, the engine adds the following
        contribution to the loads dict before each power flow evaluation:

            loads[node_id][phase] += complex(0, -q_injection_kvar / n_phases)

        where q_injection_kvar > 0 for capacitive (leading VAr injection) and
        q_injection_kvar < 0 for inductive shunt reactors (absorbing VArs).

        OLTC tap changes are modelled by adjusting the nominal_kv of the
        regulated node in the nodes list; the loads dict is unchanged by tap
        position.  The loads dict is the single point of entry for all reactive
        device state into the power flow and contingency analysis engines.

        See also: _adapters.py — dual-source reactive flow protocol (OA-129.2).
        """

        device_id: str
        node_id: str
        phases: str  # "ABC" (default), "A", "B", "C" etc.
        q_injection_kvar: float  # > 0 capacitive, < 0 inductive
        device_type: str  # "capacitor" | "reactor" | "oltc" | "shunt"

    class VoltVARConfig(TypedDict, total=False):
        """Tuning options accepted by VoltVARService and the volt_var engine."""

        v_target_pu: float  # target bus voltage (default 1.0)
        w_loss: float  # loss objective weight (default 1.0)
        w_viol: float  # voltage violation penalty weight (default 1000.0)

    class VoltVARResult(TypedDict, total=False):
        """Return type of volt_var.optimize() / VoltVARService.optimize()."""

        method: str
        devices_evaluated: int
        configurations_evaluated: int
        base_case: dict[str, Any]
        optimal_state: dict[str, bool]
        optimal_score: float
        optimal_case: dict[str, Any]
        configurations: list[dict[str, Any]]
        # WP-012-05 enrichment fields (present when called via VoltVARService)
        service: str
        se_provenance: dict[str, Any] | None
        contingency_verification: dict[str, Any] | None

    # ------------------------------------------------------------------ #
    # WP-012-06 service-layer contracts (OA-131..134)                      #
    # ------------------------------------------------------------------ #

    class NetworkLoadingReport(TypedDict, total=False):
        """Return type of network_loading.loading_report() / GAS.analyze_loading()."""

        feeders: list[dict[str, Any]]
        transformers: list[dict[str, Any]]
        source: dict[str, Any]
        utilisation_ranking: list[dict[str, Any]]
        total_loss_kw: float | None
        violation_count: int
        converged: bool

    class CapacityAnalysisResult(TypedDict, total=False):
        """Return type of AdvancedNetworkAnalyticsService.analyze_capacity()."""

        remaining_capacity: list[dict[str, Any]]
        bottlenecks: list[dict[str, Any]]
        summary: dict[str, Any]

    class AssetCriticalityResult(TypedDict, total=False):
        """Return type of asset_criticality.rank_assets() / GAS.rank_criticality()."""

        rankings: list[dict[str, Any]]
        weights_used: dict[str, float]
        total_assets: int
        most_critical: str | None
        dimensions_active: list[str]

    class OperationalPerformanceResult(TypedDict, total=False):
        """Return type of operational_performance() / GAS.compute_performance()."""

        voltage_quality: dict[str, Any]
        loading: dict[str, Any]
        contingency_exposure: dict[str, Any]
        optimisation_benefit: dict[str, Any]
        overall_health: str  # "green" | "amber" | "red"
