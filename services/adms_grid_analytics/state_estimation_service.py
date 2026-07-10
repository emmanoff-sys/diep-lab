"""WP-012-02 — State Estimation service (OA-107 through OA-111).

Provides a production service wrapper around the validated WLS state estimation
engine (``state_estimation.estimate``). All mathematical behaviour is preserved
unchanged; this module adds only the service-layer concerns:

  OA-107  Service integration — delegates all mathematics to the engine.
  OA-108  Measurement processing — validates and normalises inputs at the
          service boundary before engine ingestion.
  OA-109  Topology integration — topology consistency check; WP-007/008 adapters.
  OA-110  Canonical outputs — enriches raw engine output with topology and
          measurement metadata.
  OA-111  Platform integration — accepts WP-007/008/009/010 platform services by
          constructor injection; ``estimate_from_snapshot`` convenience path.

No estimation algorithm is implemented in this module. Do not add estimation
logic here; that belongs in ``state_estimation.py``.
"""

from __future__ import annotations

from typing import Any


class StateEstimationService:
    """Production state estimation service built on the validated WLS engine.

    Accepts platform service objects by constructor injection so it can be used
    with or without a live ADMS platform (test-friendly).

    Parameters
    ----------
    topology_repository:
        Optional WP-007 ``InMemoryTopologyRepository`` — any object exposing
        ``get_latest() -> TopologySnapshot``. Used by ``estimate_from_snapshot``
        when no explicit snapshot is provided.
    operational_state:
        Optional WP-008 ``OperationalStateService`` — any object exposing
        ``get_current_state() -> dict[str, OperationalAssetState]``.
    options:
        Default WLS tuning options (sigma values, bad-data threshold). Merged
        with per-call options; per-call wins on conflict.
    """

    def __init__(
        self,
        topology_repository: Any | None = None,
        operational_state: Any | None = None,
        options: dict | None = None,
    ) -> None:
        self._topo_repo = topology_repository
        self._op_state_svc = operational_state
        self._default_options: dict = options or {}

    # ------------------------------------------------------------------ #
    # OA-107 — Primary service interface                                   #
    # ------------------------------------------------------------------ #

    def estimate(
        self,
        nodes: list[dict],
        edges: list[dict],
        measurements: dict | None = None,
        options: dict | None = None,
    ) -> dict:
        """Run WLS state estimation with measurement validation and topology check.

        OA-107: delegates all mathematics to ``state_estimation.estimate()``.
        OA-108: validates and normalises ``measurements`` before the engine sees them.
        OA-109: validates topology consistency; raises ``ValueError`` on hard errors.
        OA-110: enriches engine output with topology and measurement metadata.

        Parameters
        ----------
        nodes:
            List of node dicts (``NodeSpec`` shape) describing the feeder.
        edges:
            List of edge dicts (``EdgeSpec`` shape).
        measurements:
            Optional dict keyed by ``node_id``; each value may carry any of
            ``{p_kw, q_kvar, voltage_pu}``.  Missing entries fall back to the
            engine's pseudo-measurement (base_load_kw/kvar from the node dict).
        options:
            WLS tuning overrides.  Merged with the service-level defaults; per-
            call values win.

        Returns
        -------
        dict
            ``EstimationResult``-shaped dict enriched with ``"topology"`` and
            ``"measurement_summary"`` keys.

        Raises
        ------
        ValueError
            If topology validation finds a hard error (e.g. no substation node).
        """
        from .state_estimation import estimate as _engine_estimate

        # OA-109 — topology validation (hard errors raise; warnings are recorded)
        topo_status = self.validate_topology(nodes, edges)
        if not topo_status["valid"]:
            raise ValueError("topology validation failed: " + "; ".join(topo_status["errors"]))

        # OA-108 — measurement processing and validation
        processed, meas_summary = self.process_measurements(nodes, measurements or {})

        # merge options: service defaults < call-time overrides
        merged_options = {**self._default_options, **(options or {})} or None

        # OA-107 — delegate to engine (no estimation logic here)
        raw = _engine_estimate(nodes, edges, processed, merged_options)

        # OA-110 — enrich output with service-layer metadata
        return self._enrich_result(raw, topo_status, meas_summary)

    # ------------------------------------------------------------------ #
    # OA-108 — Measurement processing                                      #
    # ------------------------------------------------------------------ #

    def process_measurements(
        self,
        nodes: list[dict],
        measurements: dict,
    ) -> tuple[dict, dict]:
        """Validate and normalise measurement inputs at the service boundary.

        Rejects entries for unknown node IDs and non-numeric values. All valid
        numeric values are coerced to ``float``.

        Returns
        -------
        tuple[processed, summary]
            ``processed`` — cleaned measurement dict suitable for the engine.
            ``summary`` — ``MeasurementSummary``-shaped dict reporting coverage
            and any rejected entries.
        """
        node_ids = {n["node_id"] for n in nodes}
        load_nodes = [n for n in nodes if n.get("node_type") != "substation"]
        processed: dict[str, dict] = {}
        rejected: list[dict] = []
        total_values = 0

        for node_id, meas in measurements.items():
            if node_id not in node_ids:
                rejected.append({"node_id": node_id, "reason": "node not in topology"})
                continue
            clean: dict[str, float] = {}
            for key in ("p_kw", "q_kvar", "voltage_pu"):
                val = meas.get(key)
                if val is None:
                    continue
                try:
                    clean[key] = float(val)
                    total_values += 1
                except (TypeError, ValueError):
                    rejected.append({"node_id": node_id, "key": key, "reason": "non-numeric value"})
            if clean:
                processed[node_id] = clean

        monitored = len(processed)
        total_load = len(load_nodes)
        coverage = round(100.0 * monitored / total_load, 1) if total_load else 100.0

        summary = {
            "monitored_nodes": monitored,
            "unmonitored_nodes": max(0, total_load - monitored),
            "total_measurement_values": total_values,
            "coverage_pct": coverage,
            "rejected": rejected,
        }
        return processed, summary

    # ------------------------------------------------------------------ #
    # OA-109 — Topology validation                                         #
    # ------------------------------------------------------------------ #

    def validate_topology(self, nodes: list[dict], edges: list[dict]) -> dict:
        """Check topology consistency before estimation.

        Hard errors (``"valid": False``) cause ``estimate()`` to raise
        ``ValueError``.  Warnings are recorded for soft issues.

        Returns
        -------
        dict
            ``TopologyValidation``-shaped dict with ``valid``, ``errors``,
            ``warnings``, and topology statistics.
        """
        errors: list[str] = []
        warnings: list[str] = []
        node_ids = {n["node_id"] for n in nodes}
        substations = [n for n in nodes if n.get("node_type") == "substation"]

        if not substations:
            errors.append("no substation/source node found")

        for e in edges:
            if e.get("from_node") not in node_ids:
                errors.append(
                    f"edge {e.get('edge_id')!r}: "
                    f"from_node {e.get('from_node')!r} not in node list"
                )
            if e.get("to_node") not in node_ids:
                errors.append(
                    f"edge {e.get('edge_id')!r}: " f"to_node {e.get('to_node')!r} not in node list"
                )

        closed_count = sum(1 for e in edges if e.get("is_closed", True))
        if closed_count == 0 and len(nodes) > 1:
            warnings.append("no closed edges — all non-source nodes will be de-energized")

        return {
            "valid": len(errors) == 0,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "substation_count": len(substations),
            "closed_edge_count": closed_count,
            "errors": errors,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------ #
    # OA-109/111 — WP-007/008 convenience path                            #
    # ------------------------------------------------------------------ #

    def estimate_from_snapshot(
        self,
        snapshot: Any | None = None,
        op_state: Any | None = None,
        options: dict | None = None,
    ) -> dict:
        """Estimate state from a WP-007 TopologySnapshot + WP-008 OperationalState.

        OA-109: converts platform service objects to engine-compatible dicts.
        OA-111: allows WP-009/010 callers to invoke SE without constructing
        raw node/edge lists.

        If ``snapshot`` is None and a ``topology_repository`` was configured at
        construction, fetches the latest snapshot automatically.
        """
        if snapshot is None and self._topo_repo is not None:
            snapshot = self._topo_repo.get_latest()
        nodes, edges = self._nodes_edges_from_snapshot(snapshot)
        measurements = self._measurements_from_op_state(op_state)
        return self.estimate(nodes, edges, measurements, options)

    # ------------------------------------------------------------------ #
    # OA-109 — WP-007 topology adapter                                     #
    # ------------------------------------------------------------------ #

    def _nodes_edges_from_snapshot(self, snapshot: Any | None) -> tuple[list[dict], list[dict]]:
        """Convert a WP-007 TopologySnapshot to engine-compatible plain dicts."""
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
    # OA-109 — WP-008 operational state adapter                           #
    # ------------------------------------------------------------------ #

    def _measurements_from_op_state(self, op_state: Any | None = None) -> dict[str, dict]:
        """Convert WP-008 OperationalState to measurement dict.

        Tries ``get_current_state()`` on the configured service when
        ``op_state`` is None; otherwise uses the provided dict/mapping directly.
        """
        if op_state is None and self._op_state_svc is not None:
            op_state = self._op_state_svc.get_current_state()
        if not op_state:
            return {}
        measurements: dict[str, dict] = {}
        for node_id, asset_state in op_state.items():
            attrs = getattr(asset_state, "attributes", {}) or {}
            m: dict[str, float] = {}
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
    # OA-110 — Canonical output enrichment                                 #
    # ------------------------------------------------------------------ #

    def _enrich_result(
        self,
        raw: dict,
        topo_status: dict,
        meas_summary: dict,
    ) -> dict:
        """Add topology and measurement metadata to the engine's raw output."""
        return {
            **raw,
            "topology": topo_status,
            "measurement_summary": meas_summary,
            "service": "StateEstimationService",
        }
