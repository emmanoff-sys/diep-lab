"""WP-006-04 — pure unit tests for the publish-version payload validator.

No DB, no app import: fastapi/topology_publish.py is stdlib-only (the same
pure-logic split fastapi/readiness.py uses), so this file runs in the
python-only unit validation profile.
"""
from __future__ import annotations

import sys
from pathlib import Path

FASTAPI_DIR = Path(__file__).resolve().parent.parent / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

from topology_publish import validate_publish_payload  # noqa: E402


def _node(node_id: str, **kw) -> dict:
    return {"node_id": node_id, "node_type": kw.pop("node_type", "bus"), **kw}


def _edge(edge_id: str, frm: str, to: str, **kw) -> dict:
    return {"edge_id": edge_id, "from_node": frm, "to_node": to, **kw}


def test_empty_payload_is_valid():
    assert validate_publish_payload([], []) == []


def test_valid_payload_passes():
    nodes = [_node("SUB-01", node_type="substation"), _node("BUS-01")]
    edges = [_edge("E-01", "SUB-01", "BUS-01")]
    assert validate_publish_payload(nodes, edges) == []


def test_missing_node_id_rejected():
    errors = validate_publish_payload([{"node_type": "bus"}], [])
    assert len(errors) == 1
    assert "node_id is required" in errors[0]


def test_missing_node_type_rejected():
    errors = validate_publish_payload([{"node_id": "BUS-01"}], [])
    assert len(errors) == 1
    assert "node_type is required" in errors[0]


def test_duplicate_node_id_rejected():
    errors = validate_publish_payload([_node("BUS-01"), _node("BUS-01")], [])
    assert any("duplicate node_id 'BUS-01'" in e for e in errors)


def test_missing_edge_id_rejected():
    errors = validate_publish_payload([], [{"from_node": "A", "to_node": "B"}])
    assert any("edge_id is required" in e for e in errors)


def test_duplicate_edge_id_rejected():
    edges = [_edge("E-01", "A", "B"), _edge("E-01", "B", "C")]
    errors = validate_publish_payload([_node("A"), _node("B"), _node("C")], edges)
    assert any("duplicate edge_id 'E-01'" in e for e in errors)


def test_edge_missing_endpoint_rejected():
    errors = validate_publish_payload([], [{"edge_id": "E-01", "from_node": "A"}])
    assert any("from_node and to_node are required" in e for e in errors)


def test_self_loop_edge_rejected():
    errors = validate_publish_payload([_node("A")], [_edge("E-01", "A", "A")])
    assert any("self-loop" in e for e in errors)


def test_edge_referencing_node_outside_payload_is_allowed():
    """Edges may reference nodes already in the DB (partial re-import); the
    grid_edges FK is authoritative for truly unknown endpoints."""
    assert validate_publish_payload([], [_edge("E-01", "EXISTING-A", "EXISTING-B")]) == []


def test_multiple_errors_all_reported():
    nodes = [{"node_id": "A"}, {"node_id": "A", "node_type": "bus"}]
    edges = [_edge("E-01", "A", "A")]
    errors = validate_publish_payload(nodes, edges)
    assert len(errors) == 3  # missing node_type, duplicate node_id, self-loop
