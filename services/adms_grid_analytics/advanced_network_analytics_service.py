"""DIEP ADMS P5-M11 — Advanced Network Analytics Service (OA-135).

Platform integration layer that exposes the four OA-131..134 engine modules
through a single service class. All analytical logic lives in the engine
modules; this class is routing and adapter plumbing only.

Design invariant
----------------
No analytical computation is duplicated here. If a loading, capacity,
criticality, or performance metric is needed, it is obtained by calling the
corresponding engine function — never re-implemented inline.
"""

from __future__ import annotations

from . import (
    asset_criticality,
    capacity_analysis,
    network_loading,
    performance_analytics,
)
from ._adapters import nodes_edges_from_snapshot


class AdvancedNetworkAnalyticsService:
    """High-level interface to the four OA-131..134 analytics engines.

    All four public methods accept either explicit ``nodes``/``edges`` +
    ``pf_result`` arguments, or a ``snapshot`` dict that is resolved via
    the shared adapter. When both are supplied, explicit arguments take
    precedence.

    Args:
        topology_repository: Optional topology repository (passed through to
            the shared adapter for snapshot resolution).
        power_flow_service: Optional power flow service (for snapshot
            resolution when pf_result is not supplied).
        state_estimation_service: Optional SE service (unused directly;
            retained for downstream integration).
        contingency_analysis_service: Optional CA service (unused directly).
        volt_var_service: Optional VVO service (unused directly).
        options: Optional dict of per-method option overrides.
    """

    def __init__(
        self,
        topology_repository=None,
        power_flow_service=None,
        state_estimation_service=None,
        contingency_analysis_service=None,
        volt_var_service=None,
        options: dict | None = None,
    ) -> None:
        self._topology_repository = topology_repository
        self._power_flow_service = power_flow_service
        self._state_estimation_service = state_estimation_service
        self._contingency_analysis_service = contingency_analysis_service
        self._volt_var_service = volt_var_service
        self._options: dict = options or {}

    def _resolve_nodes_edges(
        self,
        nodes: list[dict] | None,
        edges: list[dict] | None,
        snapshot: dict | None,
    ) -> tuple[list[dict], list[dict]]:
        if nodes is not None and edges is not None:
            return nodes, edges
        if snapshot is not None:
            return nodes_edges_from_snapshot(snapshot, self._topology_repository)
        return [], []

    def analyze_loading(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        pf_result: dict | None = None,
        snapshot: dict | None = None,
    ) -> dict:
        """Run OA-131 Network Loading Analytics.

        Returns the combined ``loading_report`` dict from
        ``network_loading.loading_report()``.
        """
        n, e = self._resolve_nodes_edges(nodes, edges, snapshot)
        pf = pf_result or {}
        return network_loading.loading_report(n, e, pf)

    def analyze_capacity(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        pf_result: dict | None = None,
        snapshot: dict | None = None,
    ) -> dict:
        """Run OA-132 Capacity and Constraint Analysis.

        Returns a dict with keys ``remaining_capacity``, ``bottlenecks``,
        and ``summary`` (from ``capacity_analysis.capacity_summary()``).
        """
        n, e = self._resolve_nodes_edges(nodes, edges, snapshot)
        pf = pf_result or {}
        return {
            "remaining_capacity": capacity_analysis.remaining_capacity(pf),
            "bottlenecks": capacity_analysis.bottlenecks(pf),
            "summary": capacity_analysis.capacity_summary(n, e, pf),
        }

    def rank_criticality(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        pf_result: dict | None = None,
        ca_result: dict | None = None,
        customers_by_node: dict[str, int] | None = None,
        snapshot: dict | None = None,
    ) -> dict:
        """Run OA-133 Asset Criticality Engine.

        Returns the ``rank_assets()`` result dict.
        """
        n, e = self._resolve_nodes_edges(nodes, edges, snapshot)
        pf = pf_result or {}
        return asset_criticality.rank_assets(
            n, e, pf, ca_result=ca_result, customers_by_node=customers_by_node
        )

    def compute_performance(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        pf_result: dict | None = None,
        ca_result: dict | None = None,
        vvo_result: dict | None = None,
        snapshot: dict | None = None,
    ) -> dict:
        """Run OA-134 Operational Performance Analytics.

        Returns the ``operational_performance()`` result dict.
        """
        n, e = self._resolve_nodes_edges(nodes, edges, snapshot)
        pf = pf_result or {}
        return performance_analytics.operational_performance(
            n, e, pf, ca_result=ca_result, vvo_result=vvo_result
        )
