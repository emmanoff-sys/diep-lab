"""WP-012-05 — Volt/VAR Optimisation service (OA-125 through OA-128).

Provides a production service wrapper around the validated VoltVAR optimisation
engine (``volt_var.optimize``). All optimisation mathematics are preserved
unchanged; this module adds only the service-layer concerns:

  OA-125  Service integration — delegates all optimisation to the engine.
          No solver or power flow logic is implemented here.
  OA-126  Reactive device modelling — accepts ReactiveDeviceSpec dicts for
          capacitor banks, shunt compensation, and OLTC representation;
          injects device state into the loads dict consumed by the engine
          via the shared _apply_device_state utility (see volt_var.py).
  OA-127  VoltVAR engine consumption — the engine enumerates device
          configurations and scores each via the three-phase PF engine.
  OA-128  Platform integration — SE result → load profile derivation (via
          the shared loads_from_se_result adapter or the injected
          PowerFlowService); optional N-1 security verification of the
          optimal dispatch via ContingencyAnalysisService; WP-007 snapshot
          adapter for topology input.

No power flow, state estimation, or contingency algorithm is implemented in
this module. Do not add solver logic here.
"""

from __future__ import annotations

from typing import Any

from . import _observability as _obs

_SERVICE = "VoltVARService"


class VoltVARService:
    """Production Volt/VAR optimisation service.

    Accepts platform services by constructor injection so it can be used with
    or without a live ADMS platform (test-friendly).

    Parameters
    ----------
    topology_repository:
        Optional WP-007 ``InMemoryTopologyRepository``.
    state_estimation_service:
        Optional WP-012-02 ``StateEstimationService``.
    power_flow_service:
        Optional WP-012-03 ``PowerFlowService`` — used to derive the per-phase
        load dict from an SE result (reuses ``loads_from_se_result()``).
    contingency_analysis_service:
        Optional WP-012-04 ``ContingencyAnalysisService`` — used when
        ``verify_contingency=True`` to confirm N-1 security of the optimal
        reactive dispatch.
    options:
        Default VoltVARConfig options. Merged with per-call options.
    """

    def __init__(
        self,
        topology_repository: Any | None = None,
        state_estimation_service: Any | None = None,
        power_flow_service: Any | None = None,
        contingency_analysis_service: Any | None = None,
        options: dict | None = None,
    ) -> None:
        self._topo_repo = topology_repository
        self._se_svc = state_estimation_service
        self._pf_svc = power_flow_service
        self._ca_svc = contingency_analysis_service
        self._default_options: dict = options or {}

    # ------------------------------------------------------------------ #
    # OA-125 — Primary service interface                                   #
    # ------------------------------------------------------------------ #

    def optimize(
        self,
        nodes: list[dict],
        edges: list[dict],
        loads: dict | None = None,
        se_result: dict | None = None,
        devices: list[dict] | None = None,
        verify_contingency: bool = False,
        options: dict | None = None,
    ) -> dict:
        """Run Volt/VAR optimisation over the supplied reactive devices.

        OA-125: delegates all optimisation to ``volt_var.optimize()``.
        OA-126: device injections applied via ``_apply_device_state()``
            in the engine; the loads dict is not mutated.
        OA-128: when ``se_result`` is provided and ``loads`` is None,
            derives the per-phase load profile from the estimated node
            powers.  When ``verify_contingency=True`` and a
            ``contingency_analysis_service`` is configured, runs N-1
            analysis on the optimal reactive dispatch as a security check.

        Parameters
        ----------
        nodes:
            List of node dicts (``NodeSpec`` shape).
        edges:
            List of edge dicts (``EdgeSpec`` shape).
        loads:
            Optional explicit base-case load dict.  When provided together
            with ``se_result``, the explicit loads take precedence.
        se_result:
            Optional dict from ``StateEstimationService.estimate()``.
            When provided and ``loads`` is None, used to derive the load
            profile (OA-128).
        devices:
            List of ``ReactiveDeviceSpec`` dicts.
        verify_contingency:
            When True and ``contingency_analysis_service`` is configured,
            the optimal dispatch is verified against N-1 security (OA-128).
        options:
            ``VoltVARConfig`` overrides.

        Returns
        -------
        dict
            ``VoltVARResult``-shaped dict enriched with ``"service"`` and
            optionally ``"se_provenance"`` and ``"contingency_verification"``.
        """
        from ._adapters import validate_nodes_edges, validate_se_result
        from .volt_var import _apply_device_state
        from .volt_var import optimize as _engine_optimize

        corr = (options or {}).get("correlation_id")
        n_devices = len(devices or [])
        t0 = _obs.record_start(
            _SERVICE,
            "optimize",
            node_count=len(nodes),
            edge_count=len(edges),
            correlation_id=corr,
        )
        try:
            # OA-140 — boundary contract validation
            validate_nodes_edges(nodes, edges)
            if se_result is not None:
                validate_se_result(se_result)

            se_provenance: dict | None = None
            if se_result is not None:
                se_provenance = {
                    "method": se_result.get("method"),
                    "measurements": se_result.get("measurements"),
                    "states": se_result.get("states"),
                    "bad_data": se_result.get("bad_data"),
                    "chi2_ok": se_result.get("chi2_ok"),
                }
                if loads is None:
                    loads = self._loads_from_se_result(se_result, nodes)

            merged: dict | None = {**self._default_options, **(options or {})} or None
            raw = _engine_optimize(nodes, edges, loads or {}, devices or [], merged)

            contingency_result: dict | None = None
            if verify_contingency and self._ca_svc is not None:
                optimal_loads = _apply_device_state(
                    loads or {}, devices or [], raw["optimal_state"]
                )
                contingency_result = self._ca_svc.analyze(nodes, edges, loads=optimal_loads)

            result = self._enrich_result(raw, se_provenance, contingency_result)
        except Exception as exc:
            _obs.record_failure(_SERVICE, "optimize", t0, exc)
            raise
        n_configs = result.get("configurations_evaluated", 0)
        _obs.record_complete(
            _SERVICE,
            "optimize",
            t0,
            extra=f"devices_evaluated={n_devices} configurations_evaluated={n_configs}",
        )
        return result

    # ------------------------------------------------------------------ #
    # OA-128 — SE-driven load derivation                                   #
    # ------------------------------------------------------------------ #

    def _loads_from_se_result(self, se_result: dict, nodes: list[dict]) -> dict:
        """Derive per-phase load dict from SE result.

        Delegates to the injected PowerFlowService when available; falls back
        to the shared adapter implementation (OA-129.5 / F-PAR003-06).
        """
        if self._pf_svc is not None:
            return self._pf_svc.loads_from_se_result(se_result, nodes)
        from ._adapters import loads_from_se_result

        return loads_from_se_result(se_result, nodes)

    # ------------------------------------------------------------------ #
    # OA-128 — Convenience path (SE result → VVO)                         #
    # ------------------------------------------------------------------ #

    def optimize_from_se_result(
        self,
        se_result: dict,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        snapshot: Any | None = None,
        devices: list[dict] | None = None,
        verify_contingency: bool = False,
        options: dict | None = None,
    ) -> dict:
        """Run VVO using a validated SE result as the load profile.

        OA-128: the SE result is the authoritative operating state source.
        If ``nodes``/``edges`` are None and a ``topology_repository`` was
        configured at construction, fetches the latest snapshot automatically.
        """
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return self.optimize(
            nodes,
            edges,
            loads=None,
            se_result=se_result,
            devices=devices,
            verify_contingency=verify_contingency,
            options=options,
        )

    # ------------------------------------------------------------------ #
    # OA-128 — WP-007 topology adapter (shared — OA-129.5)                #
    # ------------------------------------------------------------------ #

    def _nodes_edges_from_snapshot(
        self, snapshot: Any | None = None
    ) -> tuple[list[dict], list[dict]]:
        """Convert a WP-007 TopologySnapshot to engine-compatible plain dicts."""
        from ._adapters import nodes_edges_from_snapshot

        return nodes_edges_from_snapshot(snapshot, self._topo_repo)

    # ------------------------------------------------------------------ #
    # OA-125 — Canonical output enrichment                                 #
    # ------------------------------------------------------------------ #

    def _enrich_result(
        self,
        raw: dict,
        se_provenance: dict | None,
        contingency_result: dict | None,
    ) -> dict:
        """Add service metadata and optional provenance to engine output."""
        enriched = {**raw, "service": "VoltVARService"}
        if se_provenance is not None:
            enriched["se_provenance"] = se_provenance
        if contingency_result is not None:
            enriched["contingency_verification"] = contingency_result
        return enriched
