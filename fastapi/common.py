"""Shared DB access helpers for the DIEP API.

Extracted from app.py (ADMS refactor) so the new APIRouter modules under
routers/ can reuse the exact same connection settings and query patterns
without importing app.py (which would create an import cycle, since app.py
includes the routers). app.py imports get_conn/DB_CONFIG from here.

Raw psycopg2 + RealDictCursor, matching the existing app.py style (no ORM).
"""
import os
import psycopg2
import psycopg2.extras

# Secrets from environment (Phase 9J S0); lab defaults keep the stack running.
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "diep-timescaledb"),
    "database": os.getenv("DB_NAME", "diep"),
    "user": os.getenv("DB_USER", "diep"),
    "password": os.getenv("DB_PASSWORD", "diep123"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return all rows as a list of dicts."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Run a SELECT and return the first row as a dict (or None)."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql: str, params: tuple = (), returning: bool = False):
    """Run an INSERT/UPDATE/DELETE, commit, and optionally return one row."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        result = cur.fetchone() if returning else None
        conn.commit()
        cur.close()
        return dict(result) if (returning and result) else None
    finally:
        conn.close()


def current_model_version() -> int | None:
    """The network_model_versions.version currently flagged is_current, or None
    on a fresh DB before sql/013's seed row exists. Audit-trail writers (FLISR,
    controls, OMS, automation) stamp this onto their own rows at write time so a
    later re-publish can be correlated with what was already recorded — mirrors
    the subquery topology.py/loader.py use to stamp grid_nodes/grid_edges."""
    row = query_one(
        "SELECT version FROM network_model_versions WHERE is_current = TRUE "
        "ORDER BY version DESC LIMIT 1")
    return row["version"] if row else None


def downstream_node_ids(start: str, energized_only: bool = True) -> list[str]:
    """BFS over the M1 grid_edges graph from `start`, following directed edges.

    Shared by topology (/downstream), OMS (affected-customer set), and DMS
    (state estimation / FLISR). When energized_only, traverses only CLOSED
    edges, so an open switch correctly severs the de-energized subtree.
    """
    edges = query_all("SELECT from_node, to_node, is_closed FROM grid_edges")
    adj: dict[str, list[str]] = {}
    for e in edges:
        if energized_only and not e["is_closed"]:
            continue
        adj.setdefault(e["from_node"], []).append(e["to_node"])
    seen, order, stack = {start}, [start], [start]
    while stack:
        cur = stack.pop()
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                order.append(nxt)
                stack.append(nxt)
    return order
