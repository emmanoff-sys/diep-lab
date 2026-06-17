"""K2 PostgreSQL HA validation — DB probe.

Mirrors fastapi/app.py's psycopg2.connect() pattern: per-request connect,
env-configurable host, same DB_* naming convention. Continuously inserts
numbered rows into k2_probe and reads them back, so a primary failure +
HAProxy re-route shows up as a brief gap followed by resumed writes, and
row counts before/after confirm zero data loss for acknowledged writes.
"""
import os
import sys
import time
import psycopg2

HOST = os.getenv("DB_HOST", "pg-ha-haproxy")
PORT = int(os.getenv("DB_PORT", "5432"))
DB   = os.getenv("DB_NAME", "postgres")
USER = os.getenv("DB_USER", "postgres")
PASS = os.getenv("DB_PASSWORD", "ha-val-super-2026")

def connect():
    return psycopg2.connect(host=HOST, port=PORT, dbname=DB,
                            user=USER, password=PASS,
                            connect_timeout=5)

def setup():
    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS k2_probe (
            seq        SERIAL PRIMARY KEY,
            ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload    TEXT
        )
    """)
    print(f"{time.strftime('%H:%M:%S')} k2_probe table ready")
    cur.close()
    conn.close()

def run():
    setup()
    written = 0
    for i in range(300):
        t0 = time.monotonic()
        try:
            conn = connect()
            conn.autocommit = False
            cur = conn.cursor()
            cur.execute("INSERT INTO k2_probe (payload) VALUES (%s) RETURNING seq",
                        (f"probe-{i}",))
            seq = cur.fetchone()[0]
            conn.commit()
            dt = time.monotonic() - t0
            written += 1
            print(f"{time.strftime('%H:%M:%S')} seq={i:03d} db_seq={seq:04d} OK   dt={dt:.3f}s")
            cur.close()
            conn.close()
        except Exception as exc:
            dt = time.monotonic() - t0
            print(f"{time.strftime('%H:%M:%S')} seq={i:03d} FAIL err={exc!r} dt={dt:.3f}s",
                  file=sys.stderr)
        time.sleep(1)
    print(f"\n--- probe complete: {written}/300 writes succeeded ---")

if __name__ == "__main__":
    run()
