"""Direct-DB writer for the topology importer (Phase 2, Gap 1 + idempotent
upsert).

Writes straight to grid_nodes/grid_edges/network_model_versions via
fastapi/common.py — the same psycopg2/RealDictCursor path every other write
path in this app uses (fastapi/routers/dms.py, and the sql/013/015/017 seed
migrations), not the /topology HTTP API. Chosen over the API because:
  * every existing populator of this schema (migration seed files, dms.py)
    writes directly to Postgres — there is no precedent in this codebase of
    one part of the app calling another part's REST API to write structural
    data;
  * a real GIS extract is bulk (tens to thousands of rows) and needs one
    transaction per entity type, not one HTTP round-trip per row;
  * upserting (ON CONFLICT DO UPDATE) is a single statement here; over the
    API it would mean POST-then-catch-409-then-PUT for every row.
The new POST /topology/versions endpoint (fastapi/routers/topology.py)
stays a real, separately-callable surface for other future callers (e.g. a
portal "publish" button) — this loader runs the same SQL inline instead of
calling its own app over HTTP.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_FASTAPI_DIR = Path(__file__).resolve().parent.parent / "fastapi"
if str(_FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(_FASTAPI_DIR))

import common  # noqa: E402  (after sys.path setup, matching tests/test_p5_*.py)

_NODE_COLS = ["node_id", "node_type", "name", "site_name", "latitude", "longitude",
              "nominal_kv", "phases", "base_load_kw", "base_load_kvar", "attrs", "model_version"]
_EDGE_COLS = ["edge_id", "from_node", "to_node", "edge_type", "is_switchable",
              "normally_closed", "is_closed", "resistance_r_ohm", "reactance_x_ohm",
              "length_km", "ampacity_a", "phases", "attrs", "model_version"]


def publish_version(label: str, description: str | None = None,
                     created_by: str = "topology-importer") -> dict:
    """Insert a new network_model_versions row and mark it current (Gap 1 —
    previously nothing ever did this; the table held exactly one row since
    the original sql/013 seed). Mirrors POST /topology/versions' SQL
    exactly, so a direct-DB import and an API-driven publish agree."""
    conn = common.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE network_model_versions SET is_current = FALSE WHERE is_current = TRUE")
        cur.execute(
            "INSERT INTO network_model_versions (label, description, created_by, is_current) "
            "VALUES (%s, %s, %s, TRUE) "
            "RETURNING version, label, description, created_by, is_current, created_at",
            (label, description, created_by),
        )
        cols = ["version", "label", "description", "created_by", "is_current", "created_at"]
        row = dict(zip(cols, cur.fetchone()))
        conn.commit()
        return row
    finally:
        conn.close()


def ensure_site(site_name: str, site_type: str = "feeder") -> None:
    conn = common.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sites (site_name, site_type) VALUES (%s, %s) "
            "ON CONFLICT (site_name) DO NOTHING",
            (site_name, site_type),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_nodes(nodes: list[dict], version: int, site_name: str | None = None) -> int:
    """INSERT ... ON CONFLICT (node_id) DO UPDATE — idempotent re-import (see
    module docstring for why this, not GET-then-POST/PUT against the API).

    parent_id is deliberately written in a second pass: grid_nodes.parent_id
    is a self-FK, and the node list isn't guaranteed to be in parent-before-
    child order, so inserting it inline could violate the FK on a row whose
    parent hasn't been written yet."""
    conn = common.get_conn()
    try:
        cur = conn.cursor()
        for n in nodes:
            row = (
                n["node_id"], n["node_type"], n.get("name"), site_name,
                n.get("latitude"), n.get("longitude"), n.get("nominal_kv"),
                n.get("phases", "ABC"), n.get("base_load_kw", 0.0), n.get("base_load_kvar", 0.0),
                json.dumps(n.get("attrs") or {}), version,
            )
            cur.execute(
                f"INSERT INTO grid_nodes ({', '.join(_NODE_COLS)}) "
                f"VALUES ({', '.join(['%s'] * len(_NODE_COLS))}) "
                "ON CONFLICT (node_id) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in _NODE_COLS if c != "node_id"),
                row,
            )
        for n in nodes:
            if n.get("parent_id"):
                cur.execute("UPDATE grid_nodes SET parent_id = %s WHERE node_id = %s",
                            (n["parent_id"], n["node_id"]))
        conn.commit()
        return len(nodes)
    finally:
        conn.close()


def upsert_edges(edges: list[dict], version: int) -> int:
    conn = common.get_conn()
    try:
        cur = conn.cursor()
        for e in edges:
            row = (
                e["edge_id"], e["from_node"], e["to_node"], e.get("edge_type", "line"),
                e.get("is_switchable", False), e.get("normally_closed", True),
                e.get("is_closed", True), e.get("resistance_r_ohm"), e.get("reactance_x_ohm"),
                e.get("length_km"), e.get("ampacity_a"), e.get("phases", "ABC"),
                json.dumps(e.get("attrs") or {}), version,
            )
            cur.execute(
                f"INSERT INTO grid_edges ({', '.join(_EDGE_COLS)}) "
                f"VALUES ({', '.join(['%s'] * len(_EDGE_COLS))}) "
                "ON CONFLICT (edge_id) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in _EDGE_COLS if c != "edge_id"),
                row,
            )
        conn.commit()
        return len(edges)
    finally:
        conn.close()


def import_parsed(nodes: list[dict], edges: list[dict], *, label: str,
                   created_by: str = "topology-importer",
                   description: str | None = None, site_name: str | None = None) -> dict:
    """Publish a new version, ensure the site row exists if given, then
    upsert nodes before edges (grid_edges.from_node/to_node FK grid_nodes)."""
    if site_name:
        ensure_site(site_name)
    version_row = publish_version(label, description, created_by)
    version = version_row["version"]
    n_count = upsert_nodes(nodes, version, site_name)
    e_count = upsert_edges(edges, version)
    return {"version": version_row, "nodes_written": n_count, "edges_written": e_count}
