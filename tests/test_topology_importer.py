"""Phase 2 — topology/ GeoJSON importer tests.

Two tiers, matching the house convention (see tests/test_topology_smoke.py):
  * pure parser/orientation tests — no DB, always run;
  * DB-backed import tests — need a live Postgres with sql/000..023 applied
    (DB_HOST/DB_NAME/DB_USER/DB_PASSWORD env, matching fastapi/common.py's
    defaults), skipped cleanly if unreachable. Run against a throwaway DB,
    never the shared platform one (same protocol P5_M1's validation used).

Fixture: tests/fixtures/smartds_gso_rural_rdt2999.geojson — see
tests/fixtures/SOURCE.md for provenance (NREL/DOE SMART-DS, CC BY 4.0). It
is a real transformer-area extract: 10 "Node" points, 2 transformers (folded
into transformer edges), 3 loads (folded onto their bus node's base_load),
7 lines (one a normally-closed disconnect switch) — a connected 10-node,
9-edge tree rooted at `rdt2999-rhs3_1247x`, the fragment's upstream
connection point (it has no substation of its own — see SOURCE.md).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from topology import geojson  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "smartds_gso_rural_rdt2999.geojson"
ROOT_ID = "rdt2999-rhs3_1247x"
EXPECTED_NODE_IDS = {
    "rdt2999", "rdt2999lv", "rdt3000", "rdt3000lv", "p1rlv5418", "p1rlv5419",
    "p1rlv5420", "rdt2999-rhs3_1247x", "rdt2999-rhs3_1247x_b1_1", "rdt2999-rhs3_1247x_b2_1",
}


@pytest.fixture
def parsed():
    fc = json.loads(FIXTURE.read_text())
    return geojson.parse_feature_collection(fc)


@pytest.fixture
def oriented(parsed):
    return geojson.orient_radial(parsed["nodes"], parsed["edges"], root_id=ROOT_ID)


# --- pure parser/orientation (no DB) ------------------------------------------

def test_parser_resolves_every_feature(parsed):
    assert parsed["unresolved"] == []
    assert {n["node_id"] for n in parsed["nodes"]} == EXPECTED_NODE_IDS
    assert len(parsed["edges"]) == 9


def test_loads_fold_onto_their_bus_node_not_separate_vertices(parsed):
    by_id = {n["node_id"]: n for n in parsed["nodes"]}
    assert by_id["p1rlv5418"]["base_load_kw"] == pytest.approx(3.7829664635361904)
    assert by_id["p1rlv5420"]["base_load_kvar"] == pytest.approx(7.208697336034036)
    assert by_id["rdt2999"]["base_load_kw"] == 0  # no load directly on this bus


def test_transformers_become_edges_not_separate_vertices(parsed):
    tx_edges = [e for e in parsed["edges"] if e["edge_type"] == "transformer"]
    assert len(tx_edges) == 2
    assert {e["edge_id"] for e in tx_edges} == {
        "tr(r:rdt2999-rdt2999lv)", "tr(r:rdt3000-rdt3000lv)"}
    by_id = {n["node_id"]: n for n in parsed["nodes"]}
    assert by_id["rdt2999"]["nominal_kv"] == pytest.approx(7.2)
    assert by_id["rdt2999lv"]["nominal_kv"] == pytest.approx(0.12)


def test_nominal_kv_propagates_across_non_transformer_edges(parsed):
    by_id = {n["node_id"]: n for n in parsed["nodes"]}
    assert by_id["p1rlv5418"]["nominal_kv"] == pytest.approx(0.12)  # via rdt2999lv
    assert by_id["rdt2999-rhs3_1247x"]["nominal_kv"] == pytest.approx(7.2)  # via rdt2999


def test_disconnect_switch_parsed_as_switchable_closed_edge(parsed):
    sw = next(e for e in parsed["edges"] if e["edge_id"].endswith("_disconnect"))
    assert sw["edge_type"] == "switch"
    assert sw["is_switchable"] is True
    assert sw["is_closed"] is True  # source is_open=False


def test_orient_radial_reaches_every_node_with_no_loops(oriented, parsed):
    assert oriented["unreached"] == []
    assert len(oriented["edges"]) == len(parsed["nodes"]) - 1  # tree: n-1 edges
    by_id = {n["node_id"]: n for n in oriented["nodes"]}
    assert by_id[ROOT_ID].get("parent_id") is None
    for nid in EXPECTED_NODE_IDS - {ROOT_ID}:
        assert by_id[nid]["parent_id"] in EXPECTED_NODE_IDS


def test_imported_subgraph_is_a_single_connected_component(oriented):
    """The structural-validity bar the user specified: connected, no
    orphans unless expected. Checked here purely over the parsed/oriented
    output so it holds independent of whatever else lives in a target DB."""
    adj: dict[str, set] = {n["node_id"]: set() for n in oriented["nodes"]}
    for e in oriented["edges"]:
        adj[e["from_node"]].add(e["to_node"])
        adj[e["to_node"]].add(e["from_node"])
    seen, stack = {ROOT_ID}, [ROOT_ID]
    while stack:
        cur = stack.pop()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    assert seen == EXPECTED_NODE_IDS


# --- DB-backed import (skips cleanly if no DB reachable) ----------------------

def _db_reachable() -> bool:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fastapi"))
        import common
        conn = common.get_conn()
        conn.close()
        return True
    except Exception:
        return False


pytestmark_db = pytest.mark.skipif(not _db_reachable(), reason="no DB reachable for import test")


@pytest.fixture
def db_cleanup():
    """Imported rows, and any network_model_versions rows published during
    the test, are removed afterward regardless of outcome — these tests run
    against a real DB (a throwaway one for this session's own verification,
    but the fixture must still be safe if ever pointed at a shared dev
    stack) and must not leave behind extra version rows or a shifted
    is_current."""
    import common
    before = common.query_one(
        "SELECT version FROM network_model_versions WHERE is_current = TRUE")
    max_before = common.query_one("SELECT COALESCE(MAX(version), 0) AS v FROM network_model_versions")["v"]
    yield
    common.execute("DELETE FROM grid_edges WHERE attrs->>'source' = 'smart-ds'")
    common.execute("DELETE FROM grid_nodes WHERE attrs->>'source' = 'smart-ds'")
    common.execute("DELETE FROM network_model_versions WHERE version > %s", (max_before,))
    if before is not None:
        common.execute("UPDATE network_model_versions SET is_current = TRUE WHERE version = %s",
                        (before["version"],))


@pytestmark_db
def test_import_writes_expected_rows_and_is_idempotent(parsed, oriented, db_cleanup):
    from topology import loader

    label_1 = f"pytest-smartds-{uuid.uuid4().hex[:8]}"
    r1 = loader.import_parsed(parsed["nodes"], oriented["edges"], label=label_1,
                               created_by="pytest", site_name="smartds-test-fixture")
    assert r1["nodes_written"] == 10
    assert r1["edges_written"] == 9
    v1 = r1["version"]["version"]

    import common
    rows = common.query_all(
        "SELECT node_id, node_type, base_load_kw, parent_id, model_version "
        "FROM grid_nodes WHERE node_id = ANY(%s) ORDER BY node_id",
        (sorted(EXPECTED_NODE_IDS),),
    )
    assert {r["node_id"] for r in rows} == EXPECTED_NODE_IDS
    assert all(r["model_version"] == v1 for r in rows)
    root_row = next(r for r in rows if r["node_id"] == ROOT_ID)
    assert root_row["parent_id"] is None
    load_row = next(r for r in rows if r["node_id"] == "p1rlv5418")
    assert load_row["base_load_kw"] == pytest.approx(3.7829664635361904)

    edge_rows = common.query_all(
        "SELECT edge_id, edge_type, is_closed FROM grid_edges WHERE from_node = ANY(%s) "
        "OR to_node = ANY(%s)", (sorted(EXPECTED_NODE_IDS), sorted(EXPECTED_NODE_IDS)),
    )
    assert len(edge_rows) == 9

    # re-import (idempotent upsert, new version) must not duplicate rows
    label_2 = f"pytest-smartds-{uuid.uuid4().hex[:8]}"
    r2 = loader.import_parsed(parsed["nodes"], oriented["edges"], label=label_2,
                               created_by="pytest", site_name="smartds-test-fixture")
    v2 = r2["version"]["version"]
    assert v2 > v1

    rows_after = common.query_all(
        "SELECT node_id, model_version FROM grid_nodes WHERE node_id = ANY(%s)",
        (sorted(EXPECTED_NODE_IDS),),
    )
    assert len(rows_after) == 10  # still 10 — upsert, not duplicate insert
    assert all(r["model_version"] == v2 for r in rows_after)  # re-stamped to the new version

    edge_rows_after = common.query_all(
        "SELECT edge_id FROM grid_edges WHERE from_node = ANY(%s) OR to_node = ANY(%s)",
        (sorted(EXPECTED_NODE_IDS), sorted(EXPECTED_NODE_IDS)),
    )
    assert len(edge_rows_after) == 9

    current = common.query_one(
        "SELECT version FROM network_model_versions WHERE is_current = TRUE")
    assert current["version"] == v2  # latest publish wins


@pytestmark_db
def test_publish_version_flips_is_current(db_cleanup):
    from topology import loader

    a = loader.publish_version(f"pytest-a-{uuid.uuid4().hex[:6]}", created_by="pytest")
    b = loader.publish_version(f"pytest-b-{uuid.uuid4().hex[:6]}", created_by="pytest")
    assert b["version"] > a["version"]

    import common
    current = common.query_one(
        "SELECT version FROM network_model_versions WHERE is_current = TRUE")
    assert current["version"] == b["version"]
    a_row = common.query_one(
        "SELECT is_current FROM network_model_versions WHERE version = %s", (a["version"],))
    assert a_row["is_current"] is False
