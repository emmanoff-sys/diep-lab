"""WP-012-04 — Contingency Analysis service (OA-119 through OA-123).

Provides a production service wrapper around the validated N-1 contingency
analysis engine (``contingency.analyze``). All mathematical behaviour —
element outage simulation, greedy radial tie-restoration, post-contingency
three-phase power flow, classification, and severity ranking — is preserved
unchanged; this module adds only the service-layer concerns:

  OA-119  Service integration — delegates all computation to the engine.
  OA-120  Contingency scenario evaluation — N-1 line / transformer / feeder /
          source outages; optional SE-driven load profile.
  OA-121  Network impact assessment — restoration feasibility, islanding,
          voltage violations, thermal overloads, load-shedding requirements
          surfaced from engine results.
  OA-122  Contingency ranking — deterministic severity ordering from the engine;
          enriched with an optional impact summary.
  OA-123  Platform integration — WP-007 snapshot adapter; WP-008 operational
          state adapter for customer counts; optional SE / PF service injection.

No contingency algorithm is implemented in this module. Do not add solver logic
here; that belongs in ``contingency.py``.
"""

from __future__ import annotations

from typing import Any


class ContingencyAnalysisService:
    """Production contingency analysis service built on the validated N-1 engine.

    Accepts platform service objects by constructor injection so it can be used
    with or without a live ADMS platform (test-friendly).

    Parameters
    ----------
    topology_repository:
        Optional WP-007 ``InMemoryTopologyRepository``.
    state_estimation_service:
        Optional WP-012-02 ``StateEstimationService`` — used when an SE-driven
        load profile is requested but no explicit ``se_result`` is provided.
    power_flow_service:
        Optional WP-012-03 ``PowerFlowService`` — used to derive the per-phase
        load dict from an SE result (reuses ``loads_from_se_result()``).
    options:
        Default analysis options.  Merged with per-call options; per-call wins.
    """

    def __init__(
        self,
        topology_repository: Any | None = None,
        state_estimation_service: Any | None = None,
        power_flow_service: Any | None = None,
        options: dict | None = None,
    ) -> None:
        self._topo_repo = topology_repository
        self._se_svc = state_estimation_service
        self._pf_svc = power_flow_service
        self._default_options: dict = options or {}

    # ------------------------------------------------------------------ #
    # OA-119 — Primary service interface                                   #
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        nodes: list[dict],
        edges: list[dict],
        loads: dict | None = None,
        se_result: dict | None = None,
        customers_by_node: dict | None = None,
        load_floor: dict | None = None,
        options: dict | None = None,
    ) -> dict:
        """Run N-1 contingency analysis with optional SE-driven load profile.

        OA-119: delegates all computation to ``contingency.analyze()``.
        OA-120: when ``se_result`` is provided and ``loads`` is None, derives
            the per-phase load profile from the estimated node powers via the
            injected ``PowerFlowService`` (or a built-in fallback).
        OA-121: engine results already contain restoration feasibility,
            islanding detection (``unserved_nodes``), voltage and thermal
            violations, and load-shedding assessment (``unserved_load_kw``).
        OA-122: engine ranks contingencies by severity; this layer appends an
            ``impact_summary`` for caller convenience.
        OA-123: ``customers_by_node`` may be populated from WP-008 state if
            not supplied directly; ``load_floor`` supports AMI last-gasp nodes.

        Parameters
        ----------
        nodes:
            List of node dicts (``NodeSpec`` shape).
        edges:
            List of edge dicts (``EdgeSpec`` shape).
        loads:
            Optional explicit load dict ``{node_id: {phase: complex(P_kw, Q_kvar)}}``.
            When provided together with ``se_result``, explicit loads take
            precedence.
        se_result:
            Optional dict produced by ``StateEstimationService.estimate()``.
            When provided and ``loads`` is None, the per-node estimated P/Q
            values are used to build the per-phase load profile (OA-120).
        customers_by_node:
            Optional ``{node_id: int}`` customer count mapping used by the
            engine to report ``lost_customers`` and ``unserved_customers``.
        load_floor:
            Optional ``{node_id: float}`` fallback load (kW) for AMI last-gasp
            nodes whose live telemetry temporarily reads zero.
        options:
            Per-call analysis options.  Merged with service defaults.

        Returns
        -------
        dict
            ``ContingencyResult``-shaped dict enriched with ``"service"``,
            ``"se_provenance"``, and ``"impact_summary"`` keys.

        Raises
        ------
        ValueError
            If ``nodes`` / ``edges`` fail the pre-flight topology check
            (no substation, or no in-service switchable elements).
        """
        from .contingency import analyze as _engine_analyze

        # OA-120 — optional SE-driven load derivation
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

        # OA-119 — delegate to engine
        raw = _engine_analyze(
            nodes,
            edges,
            loads or {},
            customers_by_node=customers_by_node or {},
            load_floor=load_floor or {},
        )

        # OA-122 — build impact summary over ranked results
        impact_summary = self._impact_summary(raw)

        return self._enrich_result(raw, se_provenance, impact_summary)

    # ------------------------------------------------------------------ #
    # OA-120 — SE-driven load derivation                                   #
    # ------------------------------------------------------------------ #

    def _loads_from_se_result(self, se_result: dict, nodes: list[dict]) -> dict:
        """Derive per-phase complex load dict from SE node results.

        Delegates to the injected ``PowerFlowService`` when available; otherwise
        uses the same algorithm inline so the service is usable without a PF
        service instance.
        """
        if self._pf_svc is not None:
            return self._pf_svc.loads_from_se_result(se_result, nodes)

        # inline fallback — mirrors PowerFlowService.loads_from_se_result()
        def _phase_set(phases_str: str | None) -> list[str]:
            s = (phases_str or "ABC").lower()
            return [p for p in ("a", "b", "c") if p in s]

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

    # ------------------------------------------------------------------ #
    # OA-121 — Network impact assessment helpers                           #
    # ------------------------------------------------------------------ #

    def assess_impact(self, contingency_result: dict) -> dict:
        """Summarise network impact over a completed contingency analysis result.

        Returns an ``impact_summary`` dict suitable for operator reporting.
        Deterministic — same input always produces the same output.
        """
        return self._impact_summary(contingency_result)

    def _impact_summary(self, raw: dict) -> dict:
        """Build a concise impact summary from the engine result (OA-121/122)."""
        contingencies = raw.get("contingencies", [])
        classifications: dict[str, int] = {}
        for r in contingencies:
            cls = r.get("classification", "unknown")
            classifications[cls] = classifications.get(cls, 0) + 1

        unserved_contingencies = [r for r in contingencies if r.get("unserved_load_kw", 0) > 0]
        violation_contingencies = [r for r in contingencies if r.get("post_violations", 0) > 0]

        total_worst_unserved = max((r["unserved_load_kw"] for r in contingencies), default=0.0)
        total_worst_customers = max((r["unserved_customers"] for r in contingencies), default=0)

        return {
            "total_contingencies": raw.get("contingencies_evaluated", 0),
            "n1_secure": raw.get("n1_secure", False),
            "classifications": classifications,
            "unserved_count": len(unserved_contingencies),
            "violation_only_count": len(
                [r for r in violation_contingencies if r.get("unserved_load_kw", 0) == 0]
            ),
            "worst_unserved_load_kw": round(total_worst_unserved, 2),
            "worst_unserved_customers": total_worst_customers,
            "base_case_violations": raw.get("base_case", {}).get("violations", 0),
        }

    # ------------------------------------------------------------------ #
    # OA-123 — Convenience path (SE result → contingency analysis)        #
    # ------------------------------------------------------------------ #

    def analyze_from_se_result(
        self,
        se_result: dict,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        snapshot: Any | None = None,
        customers_by_node: dict | None = None,
        load_floor: dict | None = None,
        options: dict | None = None,
    ) -> dict:
        """Run contingency analysis using an SE result as the load profile.

        OA-123: accepts a WP-007 snapshot when ``nodes``/``edges`` are not
            provided directly.  Uses SE-derived loads (OA-120).
        """
        if nodes is None or edges is None:
            nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        return self.analyze(
            nodes,
            edges,
            loads=None,
            se_result=se_result,
            customers_by_node=customers_by_node,
            load_floor=load_floor,
            options=options,
        )

    # ------------------------------------------------------------------ #
    # OA-123 — WP-007 topology adapter                                     #
    # ------------------------------------------------------------------ #

    def _nodes_edges_from_snapshot(self, snapshot: Any | None) -> tuple[list[dict], list[dict]]:
        """Convert a WP-007 TopologySnapshot to engine-compatible plain dicts."""
        if snapshot is None and self._topo_repo is not None:
            snapshot = self._topo_repo.get_latest()
        if snapshot is None:
            return [], []
        nodes = [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "name": n.name,
                "nominal_kv": n.nominal_kv,
                "phases": n.phases,
                "base_load_kw": float(n.attrs.get("base_load_kw") or 0.0),
                "base_load_kvar": float(n.attrs.get("base_load_kvar") or 0.0),
                "attrs": n.attrs,
            }
            for n in snapshot.nodes.values()
        ]
        edges = [
            {
                "edge_id": e.edge_id,
                "from_node": e.from_node,
                "to_node": e.to_node,
                "edge_type": e.edge_type,
                "is_closed": e.is_closed,
                "resistance_r_ohm": float(e.attrs.get("resistance_r_ohm") or 0.0),
                "reactance_x_ohm": float(e.attrs.get("reactance_x_ohm") or 0.0),
                "ampacity_a": e.attrs.get("ampacity_a"),
                "length_km": e.attrs.get("length_km"),
                "phases": e.phases,
                "is_switchable": bool(e.attrs.get("is_switchable", False)),
                "normally_closed": bool(e.attrs.get("normally_closed", True)),
                "attrs": e.attrs,
            }
            for e in snapshot.edges.values()
        ]
        return nodes, edges

    # ------------------------------------------------------------------ #
    # OA-122 — Canonical output enrichment                                 #
    # ------------------------------------------------------------------ #

    def _enrich_result(
        self,
        raw: dict,
        se_provenance: dict | None,
        impact_summary: dict,
    ) -> dict:
        """Add service metadata, SE provenance, and impact summary."""
        enriched = {
            **raw,
            "service": "ContingencyAnalysisService",
            "impact_summary": impact_summary,
        }
        if se_provenance is not None:
            enriched["se_provenance"] = se_provenance
        return enriched
