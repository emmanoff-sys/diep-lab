"""OA-079 / OA-073 — canonical test datasets.

Shared across all connector test suites (OA-073 §5). Using these
datasets ensures cross-connector regressions are caught: if a connector
produces an OperationalEvent that disrupts the two-feeder fixture's
detection, the integration test will surface it.
"""

from __future__ import annotations

import os
import sys

# Allow dataset use before tests/ path is added.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "tests"))

from services.adms_topology_import.mapping import MappedTopology  # noqa: E402

from ..translation import SCADAMessage  # noqa: E402

# --- Canonical two-feeder MappedTopology (OA-073 §5.1) -------------------


def _node(node_id: str, node_type: str, **attrs) -> dict:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "name": node_id,
        "latitude": 9.0,
        "longitude": 7.0,
        "nominal_kv": 11.0,
        "phases": "ABC",
        "attrs": {"external_id": node_id, "metadata": {}, **attrs},
    }


def _edge(
    edge_id: str,
    from_node: str,
    to_node: str,
    *,
    edge_type: str = "line",
    switchable: bool = False,
    closed: bool = True,
    rating_kw: float | None = 1000.0,
) -> dict:
    return {
        "edge_id": edge_id,
        "from_node": from_node,
        "to_node": to_node,
        "edge_type": edge_type,
        "is_switchable": switchable,
        "normally_closed": closed,
        "is_closed": closed,
        "rating_kw": rating_kw,
        "phases": "ABC",
        "attrs": {"external_id": edge_id, "metadata": {}},
    }


TWO_FEEDER_TOPOLOGY = MappedTopology(
    source_system="scada-connector-test",
    external_model_id="model-wp-011-02-test",
    external_model_version="2026.07.09",
    nodes=(
        _node("f1", "feeder"),
        _node("a", "bus"),
        _node("b", "bus"),
        _node("c", "load", base_load_kw=100.0, customer_count=40),
        _node("f2", "feeder"),
        _node("d", "bus"),
        _node("e", "load", base_load_kw=50.0, customer_count=10),
    ),
    edges=(
        _edge("e1", "f1", "a"),
        _edge("sw1", "a", "b", edge_type="switch", switchable=True, rating_kw=800.0),
        _edge("e2", "b", "c", rating_kw=500.0),
        _edge("tie1", "b", "d", edge_type="switch", switchable=True, closed=False, rating_kw=300.0),
        _edge("e3", "f2", "d"),
        _edge("e4", "d", "e", rating_kw=400.0),
    ),
)

# --- Canonical asset identity map for the two-feeder topology ----------
# External SCADA IDs → (asset_id, asset_kind)

CANONICAL_ASSET_MAP: dict[str, tuple[str, str]] = {
    "RTU-01:CB-E1": ("e1", "edge"),
    "RTU-01:CB-SW1": ("sw1", "edge"),
    "RTU-02:CB-TIE1": ("tie1", "edge"),
    "RTU-01:FEEDER-F1": ("f1", "node"),
    "RTU-02:FEEDER-F2": ("f2", "node"),
}

# --- Canonical fault event dataset (OA-073 §5.2) -----------------------

CANONICAL_FAULT_EVENT = SCADAMessage(
    message_id="RTU-01:CB-E1:001",
    external_asset_id="RTU-01:CB-E1",
    message_type="status_change",
    observed_at="2026-07-09T20:00:00Z",
    sequence=1,
    raw_payload={"status": "open", "available": False},
)


def make_scada_messages(
    *specs: tuple[str, str, int, dict],
) -> tuple[SCADAMessage, ...]:
    """Build a sequence of SCADAMessages from (ext_id, msg_type, seq, payload) tuples."""
    return tuple(
        SCADAMessage(
            message_id=f"{ext_id}:{seq:06d}",
            external_asset_id=ext_id,
            message_type=msg_type,
            observed_at=f"2026-07-09T20:{seq:02d}:00Z",
            sequence=seq,
            raw_payload=payload,
        )
        for ext_id, msg_type, seq, payload in specs
    )
