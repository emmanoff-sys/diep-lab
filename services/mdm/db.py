"""Read-only DB access for device metadata enrichment (services/mdm/enrichment.py).

psycopg2 is imported lazily (mirrors drivers/diep_driver/mqtt_client.py's
pattern) so this module — and anything that imports it — stays importable in
an environment without psycopg2 installed; only actually calling query_one
requires it.

Same .env (DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) as fastapi/common.py — read
only, no schema change, no new credentials.
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
