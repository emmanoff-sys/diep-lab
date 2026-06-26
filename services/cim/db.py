"""Read-only DB access for the CIM service — mirrors services/mdm/db.py
exactly (same lazy-psycopg2 pattern, same .env). CIM never writes to this
database; every query here is a SELECT.
"""
from __future__ import annotations

from .config import Settings


def get_conn():
    import psycopg2

    return psycopg2.connect(
        host=Settings.DB_HOST,
        dbname=Settings.DB_NAME,
        user=Settings.DB_USER,
        password=Settings.DB_PASSWORD,
    )


def query_one(sql: str, params: tuple = ()) -> dict | None:
    import psycopg2.extras

    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    finally:
        conn.close()


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    import psycopg2.extras

    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def build_filter(conditions: list[tuple[str, object]]) -> tuple[list[str], tuple]:
    """Dynamic WHERE-clause building, mirroring the pattern already used in
    fastapi/routers/topology.py and routers/der.py: only conditions whose
    value is not None are included, so optional query filters don't need
    "%s IS NULL OR ..." clutter at every call site.

    conditions: list of (sql_fragment_with_one_%s, value) pairs.
    Returns (list_of_included_fragments, params_tuple) -- join the
    fragments with " AND " and prefix "WHERE " yourself if non-empty.
    """
    clauses = [frag for frag, val in conditions if val is not None]
    params = tuple(val for _, val in conditions if val is not None)
    return clauses, params
