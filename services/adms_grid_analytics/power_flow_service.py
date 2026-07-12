"""WP-012-03 — Power Flow service (OA-113 through OA-117).

Provides a production service wrapper around the validated three-phase
backward/forward sweep power flow engine (``powerflow.solve``). All
mathematical behaviour is preserved unchanged; this module adds only the
service-layer concerns:

  OA-113  Service integration — delegates all mathematics to the engine.
  OA-114  State Estimation integration — accepts validated SE results from
          WP-012-02 as the load profile source; validates SE/topology
          consistency before execution.
  OA-115  Power Flow computation — deterministic per-phase voltage, branch
          current, loading, and loss results via the engine.
  OA-116  Analytics service exposure — stable, enriched output consumable by
          downstream work packages (contingency analysis, Volt/VAR, operator
          applications).
  OA-117  Platform integration — WP-007 snapshot adapter; accepts injected
          state_estimation_service for the SE→PF consumption chain.

No power flow algorithm is implemented in this module. Do not add solver logic
here; that belongs in ``powerflow.py``.
"""

from __future__ import annotations

from typing import Any

from . import _observability as _obs

_SERVICE = "PowerFlowService"


def _phase_set(phases_str: str | None) -> list[str]:
    s = (phases_str or "ABC").lower()
    return [p for p in ("a", "b", "c") if p in s]


class PowerFlowService:
    """Production power flow service built on the validated BFS sweep engine.

    Accepts platform service objects by constructor injection so it can be used
    with or without a live ADMS platform (test-friendly).

    Parameters
    ----------
    topology_repository:
        Optional WP-007 ``InMemoryTopologyRepository`` — any object exposing
        ``get_latest() -> TopologySnapshot``.
    state_estimation_service:
        Optional WP-012-02 ``StateEstimationService`` — used when the caller
        requests an SE-driven power flow without providing an explicit
        se_result.
    options:
        Default solver options (tol_pu, max_iter, v_min_pu, v_max_pu). Merged
        with per-call options; per-call wins on conflict.
    """

    def __init__(
        self,
        topology_repository: Any | None = None,
        state_estimation_service: Any | None = None,
        options: dict | None = None,
    ) -> None:
        self._topo_repo = topology_repository
        self._se_svc = state_estimation_service
        self._default_options: dict = options or {}

    # ------------------------------------------------------------------ #
    # OA-113 — Primary service interface                                   #
    # ------------------------------------------------------------------ #

    def solve(
        self,
        nodes: list[dict],
        edges: list[dict],
        loads: dict | None = None,
        se_result: dict | None = None,
        options: dict | None = None,
    ) -> dict:
        """Run three-phase power flow with optional SE-driven load profile.

        OA-113: delegates all mathematics to ``powerflow.solve()``.
        OA-114: when ``se_result`` is provided, validates SE/topology
            consistency and derives the per-phase load profile from the
            estimated node powers; an explicit ``loads`` overrides this.
        OA-115: returns deterministic per-phase voltage, branch current,
            equipment loading, and network loss results from the engine.
        OA-116: enriches engine output with service metadata and optional
            SE provenance for downstream consumers.

        Parameters
        ----------
        nodes:
            List of node dicts (``NodeSpec`` shape).
        edges:
            List of edge dicts (``EdgeSpec`` shape).
        loads:
            Optional explicit load dict ``{node_id: {phase: complex(P_kw,
            Q_kvar)}}``. When provided together with ``se_result``, the
            explicit loads take precedence.
        se_result:
            Optional dict produced by ``StateEstimationService.estimate()``.
            When provided and ``loads`` is None, the per-node estimated P/Q
            values are used to build the per-phase load profile (OA-114).
        options:
            Solver tuning overrides. Merged with service defaults; per-call
            wins.

        Returns
        -------
        dict
            ``PowerFlowResult``-shaped dict enriched with ``"service"`` and
            optionally ``"se_provenance"`` keys.

        Raises
        ------
        ValueError
            If ``se_result`` is provided and is inconsistent with the
            supplied topology (node-set mismatch or invalid SE topology).
        """
        from ._adapters import validate_nodes_edges, validate_se_result
        from .powerflow import solve as _engine_solve

        corr = (options or {}).get("correlation_id")
        t0 = _obs.record_start(
            _SERVICE, "solve", node_count=len(nodes), edge_count=len(edges), correlation_id=corr
        )
        try:
            # OA-140 — boundary contract validation
            validate_nodes_edges(nodes, edges)
            if se_result is not None:
                validate_se_result(se_result)

            # OA-114 — SE consistency check and load derivation
            se_provenance: dict | None = None
            if se_result is not None:
                consistency = self.validate_se_consistency(nodes, se_result)
                if not consistency["consistent"]:
                    raise ValueError(
                        "SE result inconsistent with topology: " + "; ".join(consistency["errors"])
                    )
                se_provenance = {
                    "method": se_result.get("method"),
                    "measurements": se_result.get("measurements"),
                    "states": se_result.get("states"),
                    "bad_data": se_result.get("bad_data"),
                    "chi2_ok": se_result.get("chi2_ok"),
                }
                if loads is None:
                    loads = self.loads_from_se_result(se_result, nodes)

            # merge options: service defaults < call-time overrides
            merged_options = {**self._default_options, **(options or {})} or None

            # OA-113 — delegate to engine (no solver logic here)
            raw = _engine_solve(nodes, edges, loads or {}, merged_options)

            # OA-116 — enrich output with service-layer metadata
            result = self._enrich_result(raw, se_provenance)
        except Exception as exc:
            _obs.record_failure(_SERVICE, "solve", t0, exc)
            raise
        _obs.record_pf_complete(_SERVICE, "solve", t0, result)
        return result

    # ------------------------------------------------------------------ #
    # OA-114 — State Estimation integration                                #
    # ------------------------------------------------------------------ #

    def loads_from_se_result(self, se_result: dict, nodes: list[dict]) -> dict:
        """Derive per-phase complex load dict from SE node results.

        Converts each energised node's ``estimated_p_kw`` / ``estimated_q_kvar``
        (balanced single-line equivalents) into the per-phase
        ``complex(P_kw, Q_kvar)`` format expected by the power flow engine.
        Load is distributed equally across the active phases of the node.

        Returns
        -------
        dict
            ``{node_id: {phase: complex(P_per_phase_kw, Q_per_phase_kvar)}}``
        """
        node_phases = {n["node_id"]: n.get("phases") for n in nodes}
        loads: dict[str, dict[str, complex]] = {}
        for se_node in se_result.get("nodes", []):
            if not se_node.get("energized", False):
                continue
            nid = se_node["node_id"]
            p = se_node.get("estimated_p_kw")
            q = float(se_node.get("estimated_q_kvar") or 0.0)
            if p is None:
                continue
            phases = _phase_set(node_phases.get(nid))
            if not phases:
                continue
            n_ph = len(phases)
            per_phase = complex(float(p) / n_ph, q / n_ph)
            loads[nid] = {ph: per_phase for ph in phases}
        return loads

    def validate_se_consistency(self, nodes: list[dict], se_result: dict) -> dict:
        """OA-114: check SE result is consistent with the supplied topology.

        Validates:
        - All topology nodes appear in the SE result.
        - No extra nodes in SE result that are not in the topology.
        - The SE topology validation (if present) was valid.

        Returns
        -------
        dict
            ``{consistent, errors, warnings}``
        """
        errors: list[str] = []
        warnings: list[str] = []
        node_ids = {n["node_id"] for n in nodes}
        se_node_ids = {n["node_id"] for n in se_result.get("nodes", [])}
        missing = node_ids - se_node_ids
        extra = se_node_ids - node_ids
        if missing:
            errors.append(f"SE result is missing topology nodes: {sorted(missing)}")
        if extra:
            errors.append(f"SE result contains nodes not in topology: {sorted(extra)}")
        topo = se_result.get("topology")
        if topo is not None and not topo.get("valid", True):
            errors.append("SE result was produced on an invalid topology")
        if se_result.get("bad_data") is not None:
            warnings.append(
                "SE result contains flagged bad-data measurements — "
                "power flow load profile may be less accurate"
            )
        return {"consistent": len(errors) == 0, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------ #
    # OA-114/117 — Convenience path (SE result → power flow)              #
    # ------------------------------------------------------------------ #

    def solve_from_se_result(
        self,
        se_result: dict | None = None,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        snapshot: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """Run power flow using a validated SE result as the load profile.

        OA-114: the SE result is the authoritative source for operating state.
        OA-117: accepts a WP-007 snapshot when ``nodes``/``edges`` are not
            provided directly.
        OA-129.4: when ``se_result`` is None and a ``state_estimation_service``
            was configured at construction, estimates state automatically from
            the provided nodes/edges (wires up the previously unused ``_se_svc``
            dependency).

        If ``nodes``/``edges`` are None and a ``topology_repository`` was
        configured at construction, fetches the latest snapshot automatically.

        Raises
        ------
        ValueError
            If ``se_result`` is None and no ``state_estimation_service`` was
            configured at construction.
        """
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        if se_result is None:
            if self._se_svc is not None:
                se_result = self._se_svc.estimate(nodes, edges)
            else:
                raise ValueError(
                    "se_result required: no state_estimation_service was configured "
                    "at construction and no se_result was provided"
                )
        return self.solve(nodes, edges, loads=None, se_result=se_result, options=options)

    # ------------------------------------------------------------------ #
    # OA-117 — WP-007 topology adapter                                     #
    # ------------------------------------------------------------------ #

    def _nodes_edges_from_snapshot(self, snapshot: Any | None) -> tuple[list[dict], list[dict]]:
        """Convert a WP-007 TopologySnapshot to engine-compatible plain dicts (OA-129.5)."""
        from ._adapters import nodes_edges_from_snapshot

        return nodes_edges_from_snapshot(snapshot, self._topo_repo)

    # ------------------------------------------------------------------ #
    # OA-116 — Canonical output enrichment                                 #
    # ------------------------------------------------------------------ #

    def _enrich_result(self, raw: dict, se_provenance: dict | None) -> dict:
        """Add service metadata and optional SE provenance to engine output."""
        enriched = {**raw, "service": "PowerFlowService"}
        if se_provenance is not None:
            enriched["se_provenance"] = se_provenance
        return enriched
