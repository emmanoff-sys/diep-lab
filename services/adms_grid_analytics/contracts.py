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

    class ContingencyResult(TypedDict, total=False):
        """Return type of contingency.analyze()."""

        method: str
        base_case: dict[str, Any]
        n1_secure: bool
        contingencies_evaluated: int
        worst: list[dict[str, Any]]
        contingencies: list[dict[str, Any]]

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
