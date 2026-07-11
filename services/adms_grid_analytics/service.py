"""Grid Analytics service integration adapter for WP-012-01.

Bridges the ADMS platform services (WP-007 topology, WP-008 operational state,
WP-009 decision support, WP-010 operational intelligence) to the pure analytics
engines in this package. Callers interact with ``GridAnalyticsService`` rather
than invoking engines directly — this keeps the engines free of platform coupling
while giving service-layer callers a single, stable API surface.

Dependency direction: service.py → engine modules (within this package).
                      service.py ← WP-007/008/009/010 (injected at construction).

The integration adapters in this module convert the typed service-layer objects
(dataclasses, Pydantic models) produced by the platform services into the plain
dict inputs expected by the engines, then wrap engine outputs back in the
contract types defined in contracts.py.
"""

from __future__ import annotations

from typing import Any


class GridAnalyticsService:
    """Facade over the analytics engines, connected to the ADMS platform services.

    ``topology_repository`` — a WP-007 ``InMemoryTopologyRepository`` (or any object
        that exposes ``get_latest() -> TopologySnapshot``).
    ``operational_state`` — a WP-008 ``OperationalStateService`` (or any object
        that exposes ``get_current_state() -> dict[str, OperationalAssetState]``).
    ``operations_advisory`` — optional WP-009 ``OperatorDecisionSupport``.
    ``intelligence_service`` — optional WP-010 ``OperationalIntelligenceService``.
    """

    def __init__(
        self,
        topology_repository: Any | None = None,
        operational_state: Any | None = None,
        operations_advisory: Any | None = None,
        intelligence_service: Any | None = None,
    ) -> None:
        self._topo_repo = topology_repository
        self._op_state = operational_state
        self._advisory = operations_advisory
        self._intelligence = intelligence_service

    # ------------------------------------------------------------------ #
    # Topology helpers                                                      #
    # ------------------------------------------------------------------ #

    def _nodes_edges_from_snapshot(
        self, snapshot: Any | None = None
    ) -> tuple[list[dict], list[dict]]:
        """Convert a WP-007 TopologySnapshot into engine-compatible plain dicts (OA-129.5)."""
        from ._adapters import nodes_edges_from_snapshot
        return nodes_edges_from_snapshot(snapshot, self._topo_repo)

    def _measurements_from_op_state(self, op_state: Any | None = None) -> dict[str, dict]:
        """Convert WP-008 operational state into engine measurement dicts.

        Maps ``OperationalAssetState`` values to the ``{node_id: {p_kw, q_kvar,
        voltage_pu}}`` format expected by ``state_estimation.estimate()``.
        """
        if op_state is None and self._op_state is not None:
            op_state = self._op_state.get_current_state()
        if not op_state:
            return {}

        measurements: dict[str, dict] = {}
        for node_id, asset_state in op_state.items():
            m: dict[str, float] = {}
            # OperationalAssetState carries telemetry in its attributes dict
            attrs = getattr(asset_state, "attributes", {}) or {}
            if attrs.get("p_kw") is not None:
                m["p_kw"] = float(attrs["p_kw"])
            if attrs.get("q_kvar") is not None:
                m["q_kvar"] = float(attrs["q_kvar"])
            if attrs.get("voltage_pu") is not None:
                m["voltage_pu"] = float(attrs["voltage_pu"])
            if m:
                measurements[node_id] = m
        return measurements

    # ------------------------------------------------------------------ #
    # Engine API                                                            #
    # ------------------------------------------------------------------ #

    def estimate_state(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        measurements: dict | None = None,
        snapshot: Any | None = None,
        op_state: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """WLS distribution state estimation (P5-M2 / WP-012-02).

        Delegates to ``StateEstimationService`` which adds measurement
        processing, topology validation, and canonical output enrichment.
        Accepts explicit ``nodes``/``edges``/``measurements`` dicts or resolves
        them automatically from the configured platform services.
        """
        from .state_estimation_service import StateEstimationService

        svc = StateEstimationService(
            topology_repository=self._topo_repo,
            operational_state=self._op_state,
            options=options,
        )
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        if measurements is None:
            measurements = self._measurements_from_op_state(op_state)
        return svc.estimate(nodes, edges, measurements)

    def solve_power_flow(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        loads: dict | None = None,
        se_result: dict | None = None,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """Three-phase backward/forward power flow (P5-M3 / WP-012-03).

        Delegates to ``PowerFlowService`` which adds SE consistency validation
        (OA-114) and canonical output enrichment. When ``se_result`` is
        provided, the per-node estimated P/Q values are used as the load
        profile (OA-114); an explicit ``loads`` dict takes precedence.
        """
        from .power_flow_service import PowerFlowService

        svc = PowerFlowService(
            topology_repository=self._topo_repo,
            options=options,
        )
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return svc.solve(nodes, edges, loads=loads, se_result=se_result)

    def analyze_contingency(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        loads: dict | None = None,
        se_result: dict | None = None,
        customers_by_node: dict | None = None,
        load_floor: dict | None = None,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """N-1 contingency analysis (P5-M5 / WP-012-04). Delegates to ContingencyAnalysisService."""
        from .contingency_analysis_service import ContingencyAnalysisService

        svc = ContingencyAnalysisService(topology_repository=self._topo_repo, options=options)
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return svc.analyze(
            nodes,
            edges,
            loads=loads,
            se_result=se_result,
            customers_by_node=customers_by_node,
            load_floor=load_floor,
        )

    def analyze_volt_var(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        loads: dict | None = None,
        se_result: dict | None = None,
        devices: list[dict] | None = None,
        verify_contingency: bool = False,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """Volt/VAR optimisation (P5-M10 / WP-012-05). Delegates to VoltVARService."""
        from .volt_var_service import VoltVARService

        svc = VoltVARService(topology_repository=self._topo_repo, options=options)
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return svc.optimize(
            nodes,
            edges,
            loads=loads,
            se_result=se_result,
            devices=devices or [],
            verify_contingency=verify_contingency,
        )

    def locate_fault(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        fault_current_a: float | None = None,
        outage_nodes: list[str] | None = None,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """Impedance + topological fault location (P5-M6)."""
        from .fault_location import locate

        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return locate(nodes, edges, fault_current_a, outage_nodes, options)

    def recommend_reconfiguration(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        loads: dict | None = None,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """Optimal network reconfiguration (P5-M4)."""
        from .reconfiguration import recommend

        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return recommend(nodes, edges, loads or {}, options)

    def infer_outage(
        self,
        dark_meter_nodes: list[str],
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        customers_by_node: dict | None = None,
        se_dead_nodes: list[str] | None = None,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """AMI last-gasp outage inference (P6-M7)."""
        from .outage_inference import infer

        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return infer(nodes, edges, dark_meter_nodes, customers_by_node, options, se_dead_nodes)

    def validate_outage_inference(
        self,
        inferred_outages: list[dict],
        contingencies: list[dict],
        options: dict | None = None,
    ) -> dict:
        """Cross-check M7 outage inference vs M5 N-1 contingency (P6-M8)."""
        from .outage_validation import cross_check

        return cross_check(inferred_outages, contingencies, options)

    def recommend_crew_dispatch(
        self,
        inferred_outages: list[dict],
        contingencies: list[dict],
        options: dict | None = None,
    ) -> dict:
        """Prioritised crew dispatch recommendations (P6-M9)."""
        from .crew_dispatch import recommend

        return recommend(inferred_outages, contingencies, options)
