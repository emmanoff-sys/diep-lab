"""WP-006-04 — API tests for the atomic POST /topology/versions publish.

Same harness pattern as tests/test_readiness_api.py: imports the live
FastAPI app and drives it with TestClient, with the DB boundary replaced by
a fake psycopg2 connection (monkeypatched common.get_conn) that records
every statement — so transactional behaviour (single commit, rollback on
failure, advisory-lock-first ordering) is asserted directly without a live
Postgres.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = ROOT / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import app as diep_app  # noqa: E402
import common  # noqa: E402

client = TestClient(diep_app.app)

ADMIN = {"Authorization": "Bearer diep-admin-dev-key-CHANGE-ME"}
OPERATOR = {"Authorization": "Bearer diep-operator-dev-key-CHANGE-ME"}

VERSION_ROW = {
    "version": 7, "label": "test-publish", "description": None,
    "created_by": "api-admin", "is_current": True,
    "created_at": "2026-07-07T00:00:00+00:00",
}


class FakeCursor:
    def __init__(self, conn: "FakeConn"):
        self._conn = conn

    def execute(self, sql: str, params=None):
        if self._conn.fail_on and self._conn.fail_on in sql:
            raise psycopg2.IntegrityError(f"fake integrity violation on: {self._conn.fail_on}")
        self._conn.executed.append((sql, params))

    def fetchone(self):
        return dict(VERSION_ROW)

    def close(self):
        pass


class FakeConn:
    def __init__(self, fail_on: str | None = None):
        self.executed: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.fail_on = fail_on

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def fake_conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(common, "get_conn", lambda: conn)
    return conn


def _payload(**kw):
    return {"label": "test-publish", **kw}


# --- authorisation -------------------------------------------------------------
def test_operator_cannot_publish(fake_conn):
    r = client.post("/topology/versions", json=_payload(), headers=OPERATOR)
    assert r.status_code == 403
    assert fake_conn.executed == []  # never reached the DB


# --- metadata-only publish (backward-compatible surface) -----------------------
def test_metadata_only_publish_is_single_transaction(fake_conn):
    r = client.post("/topology/versions", json=_payload(), headers=ADMIN)
    assert r.status_code == 201, r.text
    body = r.json()
    # original flat version-row keys preserved for existing callers
    assert body["version"] == 7
    assert body["label"] == "test-publish"
    assert body["is_current"] is True
    assert body["nodes_written"] == 0 and body["edges_written"] == 0
    # exactly one commit, no rollback, connection closed
    assert fake_conn.commits == 1
    assert fake_conn.rollbacks == 0
    assert fake_conn.closed is True


def test_advisory_lock_taken_before_any_write(fake_conn):
    client.post("/topology/versions", json=_payload(), headers=ADMIN)
    first_sql = fake_conn.executed[0][0]
    assert "pg_advisory_xact_lock" in first_sql
    demote_sql = fake_conn.executed[1][0]
    assert "SET is_current = FALSE" in demote_sql


# --- content publish -----------------------------------------------------------
def test_content_publish_upserts_within_same_transaction(fake_conn):
    payload = _payload(
        site_name="Site-A",
        nodes=[
            {"node_id": "SUB-01", "node_type": "substation"},
            {"node_id": "BUS-01", "node_type": "bus", "parent_id": "SUB-01"},
        ],
        edges=[{"edge_id": "E-01", "from_node": "SUB-01", "to_node": "BUS-01"}],
    )
    r = client.post("/topology/versions", json=payload, headers=ADMIN)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["nodes_written"] == 2 and body["edges_written"] == 1

    sqls = [s for s, _ in fake_conn.executed]
    assert any("INSERT INTO sites" in s for s in sqls)
    node_inserts = [s for s in sqls if "INSERT INTO grid_nodes" in s]
    edge_inserts = [s for s in sqls if "INSERT INTO grid_edges" in s]
    parent_updates = [s for s in sqls if "SET parent_id" in s]
    assert len(node_inserts) == 2
    assert len(edge_inserts) == 1
    assert len(parent_updates) == 1  # second-pass parent stamping
    assert all("ON CONFLICT" in s for s in node_inserts + edge_inserts)  # idempotent re-import
    # content rides the same transaction as the version row
    assert fake_conn.commits == 1
    assert fake_conn.rollbacks == 0


def test_node_inherits_top_level_site_name(fake_conn):
    payload = _payload(site_name="Site-A",
                       nodes=[{"node_id": "BUS-01", "node_type": "bus"}])
    client.post("/topology/versions", json=payload, headers=ADMIN)
    node_params = next(p for s, p in fake_conn.executed if "INSERT INTO grid_nodes" in s)
    assert "Site-A" in node_params


# --- validation gate -----------------------------------------------------------
def test_invalid_payload_rejected_before_db(monkeypatch):
    called = []
    monkeypatch.setattr(common, "get_conn", lambda: called.append(1))
    payload = _payload(nodes=[
        {"node_id": "BUS-01", "node_type": "bus"},
        {"node_id": "BUS-01", "node_type": "bus"},
    ])
    r = client.post("/topology/versions", json=payload, headers=ADMIN)
    assert r.status_code == 422
    assert any("duplicate node_id" in e for e in r.json()["detail"]["errors"])
    assert called == []  # validation failed before any connection was opened


# --- failure atomicity ---------------------------------------------------------
def test_integrity_error_rolls_back_whole_publish(monkeypatch):
    conn = FakeConn(fail_on="INSERT INTO grid_edges")
    monkeypatch.setattr(common, "get_conn", lambda: conn)
    payload = _payload(
        nodes=[{"node_id": "BUS-01", "node_type": "bus"}],
        edges=[{"edge_id": "E-01", "from_node": "BUS-01", "to_node": "GHOST"}],
    )
    r = client.post("/topology/versions", json=payload, headers=ADMIN)
    assert r.status_code == 409
    assert conn.commits == 0       # nothing committed — version row not orphaned
    assert conn.rollbacks == 1     # explicit rollback
    assert conn.closed is True
