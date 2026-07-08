"""WP-006-05 — pure unit tests for the version history/diff logic.

No DB, no app import: fastapi/topology_history.py is stdlib-only, so this
file runs in the python-only unit validation profile.
"""
from __future__ import annotations

import sys
from pathlib import Path

FASTAPI_DIR = Path(__file__).resolve().parent.parent / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

from topology_history import DIFF_SEMANTICS, summarize_diff, validate_diff_range  # noqa: E402


# --- validate_diff_range -------------------------------------------------------
def test_valid_range_passes():
    assert validate_diff_range(1, 2) == []
    assert validate_diff_range(3, 10) == []


def test_from_below_one_rejected():
    errors = validate_diff_range(0, 2)
    assert any("from_version must be >= 1" in e for e in errors)


def test_to_below_one_rejected():
    errors = validate_diff_range(1, 0)
    assert any("to_version must be >= 1" in e for e in errors)


def test_equal_versions_rejected():
    errors = validate_diff_range(2, 2)
    assert any("must be lower than" in e for e in errors)


def test_inverted_range_rejected():
    errors = validate_diff_range(5, 2)
    assert any("must be lower than" in e for e in errors)


# --- summarize_diff -------------------------------------------------------------
def _version(v: int) -> dict:
    return {"version": v, "label": f"v{v}", "is_current": False}


def test_empty_diff_summary():
    out = summarize_diff([], [], [])
    assert out["semantics"] == DIFF_SEMANTICS == "write-stamp"
    assert out["counts"] == {"versions": 0, "nodes_touched": 0, "edges_touched": 0}
    assert out["versions_in_range"] == []


def test_rows_grouped_by_stamping_version():
    versions = [_version(2), _version(3)]
    nodes = [
        {"node_id": "A", "model_version": 2},
        {"node_id": "B", "model_version": 3},
        {"node_id": "C", "model_version": 3},
    ]
    edges = [{"edge_id": "E1", "model_version": 2}]
    out = summarize_diff(versions, nodes, edges)
    by_version = {v["version"]: v for v in out["versions_in_range"]}
    assert by_version[2]["nodes_touched"] == 1
    assert by_version[2]["edges_touched"] == 1
    assert by_version[3]["nodes_touched"] == 2
    assert by_version[3]["edges_touched"] == 0
    assert out["counts"] == {"versions": 2, "nodes_touched": 3, "edges_touched": 1}


def test_rows_outside_range_do_not_break_counts():
    """Defensive: a row stamped by a version not in range is passed through
    the row lists but never crashes per-version counting."""
    out = summarize_diff([_version(2)], [{"node_id": "X", "model_version": 99}], [])
    assert out["versions_in_range"][0]["nodes_touched"] == 0
    assert out["counts"]["nodes_touched"] == 1  # row still reported in the list


def test_version_metadata_preserved_in_summary():
    out = summarize_diff([_version(4)], [], [])
    v = out["versions_in_range"][0]
    assert v["label"] == "v4"
    assert v["nodes_touched"] == 0 and v["edges_touched"] == 0
