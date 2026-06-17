# K2 — PostgreSQL/TimescaleDB HA Validation Report

**Phase:** 17, Stage 5 (K2)
**Date:** 2026-06-16
**Environment:** Side-by-side validation stack
(`docker-compose-postgres-ha-validation.yml`, project `diep-pg-ha-val`),
entirely separate containers/volumes/data from production.
**Production impact:** **None.** `diep-timescaledb` was never started,
reconfigured, or referenced; the production volume
`diep-lab_timescale-data` (created 2026-06-08) is intact and unmodified
throughout and after the test.

---

## 1. Summary

| Check | Result |
|---|---|
| HA solution evaluation (Patroni vs repmgr vs pg_auto_failover) | ✅ PASS — Patroni selected (see §3) |
| Cluster formation (3-node KRaft — etcd DCS + 3 Patroni nodes) | ✅ PASS |
| Streaming replication — 1 sync standby + 1 async replica | ✅ PASS |
| Replica lag at steady state | ✅ PASS — lag ≈ 0 on both standbys |
| TimescaleDB extension preserved (hypertable, compression, retention) | ✅ PASS |
| Primary failure — automatic detection and promotion | ✅ PASS |
| Standby promotion (pg-ha-2, sync standby → new primary) | ✅ PASS |
| HAProxy routing to new primary | ✅ PASS |
| Application reconnection (psycopg2 via HAProxy) | ✅ PASS |
| Data durability — RPO = 0 (no committed-row loss) | ✅ PASS |
| Original primary self-heal / rejoin as standby | ✅ PASS |
| PITR compatibility (archive_mode=on through failover, timeline 2 WAL) | ✅ PASS |
| Production data untouched | ✅ PASS |

**Overall: PASS.** The Patroni topology designed in
`K2_POSTGRES_HA_IMPLEMENTATION_PLAN.md` is validated end-to-end, with
measured RTO = 28s (≤35s target) and RPO = 0 (synchronous commit).

---

## 2. Test Environment

### 2.1 Validation Stack Components

| Container | Image | Role |
|---|---|---|
| `diep-pg-ha-etcd` | `quay.io/coreos/etcd:v3.5.16` | Patroni DCS (single-node etcd, sufficient for validation) |
| `diep-pg-ha-val-1` | `timescale/timescaledb-ha:pg16` | Patroni + TimescaleDB + PG 16.14, initial async replica |
| `diep-pg-ha-val-2` | `timescale/timescaledb-ha:pg16` | Patroni + TimescaleDB + PG 16.14, initial sync standby → promoted primary |
| `diep-pg-ha-val-3` | `timescale/timescaledb-ha:pg16` | Patroni + TimescaleDB + PG 16.14, initial primary |
| `diep-pg-ha-haproxy` | `haproxy:alpine` | Routes port 5432 → Patroni primary (via `GET :8008/primary`), port 5433 → replicas |
| `diep-pg-ha-probe` | `python:3.12-slim` + psycopg2 | Write probe mirroring `fastapi/app.py`'s `psycopg2.connect()` pattern |

### 2.2 Cluster Configuration

- Patroni 4.1.3, PostgreSQL 16.14 (same PG version as production), TimescaleDB 2.27.2
- Patroni scope: `diep-pg-ha-val`, DCS: etcd3 @ `pg-ha-etcd:2379`
- Replication: `synchronous_mode: true`, `synchronous_mode_strict: false`
  — Patroni automatically set `synchronous_standby_names = "pg-ha-2"` and
  `synchronous_commit = on` on the primary
- Archive mode: `archive_mode = on`, `archive_command = "test ! -f
  /wal-archive/%f && cp %p /wal-archive/%f"`, `archive_timeout = 60`
  (K1 PITR settings applied via Patroni bootstrap DCS config)
- HAProxy health check: `GET :8008/primary` (HTTP 200 only from current
  Patroni leader) — `inter: 2s, fall: 3, rise: 2`
- All containers on `diep-lab_diep-net`; production containers
  not started/referenced.

### 2.3 Probe Script

`postgres-ha-validation/scripts/db_probe.py` — mirrors `fastapi/app.py`'s
connection pattern:
```python
psycopg2.connect(host=DB_HOST, port=5432, dbname=DB_NAME,
                 user=DB_USER, password=DB_PASSWORD, connect_timeout=5)
```
`DB_HOST=pg-ha-haproxy` — the probe connects through HAProxy, identically
to how the production `fastapi` would connect via `DB_HOST` env-var after
migration. 300 iterations at 1 write/second.

---

## 3. HA Solution Evaluation — Patroni Selected

| Criterion | Patroni | repmgr | pg_auto_failover |
|---|---|---|---|
| Image compatibility | `timescale/timescaledb-ha:pg16` — official Timescale HA image, PG16 + TimescaleDB 2.27.2 + Patroni 4.1.3 pre-installed; **zero custom image build** | Requires custom build (Alpine base, no apt packages) | Requires custom build (Alpine base, no pg_auto_failover packages) |
| External DCS | etcd v3 (or Patroni raft for simple cases) | None (uses postgres catalog) | Separate monitor node (plain postgres) |
| Synchronous RPO=0 | `synchronous_mode: true` — Patroni manages `synchronous_standby_names` dynamically | Manual `postgresql.conf` only | Monitor handles config |
| Kubernetes path | CNPG (CloudNativePG) is Patroni-based; directly ports to `k8s/postgres-cnpg.yaml` | Incompatible with CNPG | Incompatible with CNPG |
| TimescaleDB features | Full — official image preserves all extensions | Full (if custom build correct) | Full (if custom build correct) |

**Selected: Patroni** — eliminates custom image build, provides RPO=0
via automatic synchronous standby management, and maps directly onto
the CNPG topology in `k8s/postgres-cnpg.yaml`.

---

## 4. Test Sequence and Results

### 4.1 Cluster Formation — ✅ PASS

All 3 Patroni nodes started and registered with etcd successfully.
Initial election via Patroni DCS (etcd TTL=30s):

```
Initial cluster:
  pg-ha-3   role=leader         state=running      timeline=1
  pg-ha-2   role=sync_standby   state=streaming    lag=0
  pg-ha-1   role=replica        state=streaming    lag=0
```

`synchronous_standby_names = "pg-ha-2"` set automatically by Patroni
(`synchronous_mode: true`). Both walsenders visible in
`pg_stat_replication` from the primary:

```sql
-- pg_stat_replication on primary (pg-ha-3):
 client_addr |   state   | sync_state | write_lag  | replay_lag
 172.18.0.4  | streaming | sync       | 0.000454s  | 0.001076s   -- pg-ha-2
 172.18.0.3  | streaming | async      | 0.000409s  | 0.001794s   -- pg-ha-1
```

### 4.2 TimescaleDB Features Verified — ✅ PASS

```sql
-- extension on primary:
timescaledb | 2.27.2

-- hypertable:
 hypertable_name | num_dimensions
 k2_probe        |              1

-- policies:
 hypertable_name |     proc_name
 k2_probe        | policy_compression    (compress after 7 days)
 k2_probe        | policy_retention      (drop after 90 days)
```

Hypertable definition and both policies verified on **both standbys**
(pg-ha-1 and pg-ha-2) via streaming replication — all
TimescaleDB catalog metadata replicates identically.

*API note:* TimescaleDB 2.27.2 (vs. production's older version) renamed
compression setup to require `ALTER TABLE ... SET (timescaledb.compress)`
before `add_compression_policy()`. The underlying mechanism
(`policy_compression`, WAL-replicated catalog) is identical to
production; this is a DDL API change, not a schema or replication
incompatibility.

### 4.3 PITR / WAL Archive Compatibility — ✅ PASS

```
archive_mode:    on
archive_command: test ! -f /wal-archive/%f && cp %p /wal-archive/%f
archive_timeout: 1min
```

Applied via Patroni bootstrap DCS config (`postgresql.parameters`) —
Patroni propagates these settings to `postgresql.conf` on all nodes.
WAL segments appeared in `/wal-archive` (shared volume) starting
immediately after cluster startup:

```
000000010000000000000001   (timeline 1, primary pg-ha-3)
000000010000000000000002
...
000000020000000000000006   (timeline 2, promoted pg-ha-2, post-failover)
000000020000000000000007
...
```

**Timeline 2 WAL segments appear after promotion** — the promoted node
(pg-ha-2) continues writing to the shared archive, confirming a PITR
chain would be reconstructable through the failover event using
`recovery_target_timeline = latest`.

### 4.4 Steady-State Write Probe — ✅ PASS

Probe ran at 1 write/second through HAProxy (`pg-ha-haproxy:5432`),
connecting to the Patroni primary. Sample steady-state output:

```
21:52:26 seq=000 db_seq=0001 OK   dt=0.088s
21:52:27 seq=001 db_seq=0002 OK   dt=0.024s
...
21:52:45 seq=018 db_seq=0019 OK   dt=0.027s
```

All writes at ≤90ms (network + sync replication overhead), typically
≤30ms.

### 4.5 Primary Failure — Automatic Detection and Promotion — ✅ PASS

**Kill:** `docker kill diep-pg-ha-val-3` at **21:52:46.356 UTC**  
(pg-ha-3 was the primary; pg-ha-2 was its sync standby; pg-ha-1 was the
async replica)

**Probe during failover window:**

```
21:52:45 seq=018 db_seq=0019 OK   dt=0.027s   ← last pre-failure write
21:52:53 seq=019 FAIL  timeout expired  dt=5.009s
21:52:59 seq=020 FAIL  timeout expired  dt=5.008s
21:53:00 seq=021 FAIL  server closed connection  dt=0.006s
21:53:01 seq=022 FAIL  server closed connection  dt=0.002s
...
21:53:13 seq=034 FAIL  server closed connection  dt=0.005s
21:53:14 seq=035 db_seq=0034 OK   dt=0.052s   ← first post-failover write
```

**Patroni promotion log:**
```
2026-06-16 21:53:10,484 INFO: promoted self to leader by acquiring session lock
2026-06-16 21:53:10.491 UTC [42] LOG:  received promote request
2026-06-16 21:53:10,584 INFO: updated leader lock during promote
```

**Timing:**
| Event | UTC | Elapsed from kill |
|---|---|---|
| Primary killed (`docker kill`) | 21:52:46.356 | 0s |
| Patroni acquired leader lock on pg-ha-2 | 21:53:10.484 | **24.1s** |
| HAProxy first routed write to new primary | 21:53:14 | **≈28s end-to-end** |

**Target was ≤35s end-to-end RTO — achieved: 28s.**

The 24s promotion time is governed by the etcd TTL (`ttl: 30s`). In
production with a lower TTL (`ttl: 15s`) the promotion time scales
proportionally (≈12-15s promotion → ≈17-20s end-to-end RTO). TTL tuning
is deferred to the production rollout; the current result demonstrates
the mechanism is correct.

### 4.6 Data Durability (RPO = 0) — ✅ PASS

**Pre-failure:** 19 committed rows (seq 1-19) on the primary (pg-ha-3).  
**Post-promotion on pg-ha-2:**

```sql
SELECT COUNT(*) AS total, MIN(seq) AS first, MAX(seq) AS last FROM k2_probe;
-- total=284, first=1, last=298

SELECT COUNT(*) FROM k2_probe WHERE seq <= 19;
-- count=19   ← all 19 pre-failure rows present
```

**Zero committed rows lost.** pg-ha-2 was the synchronous standby
(`synchronous_standby_names = "pg-ha-2"`, `synchronous_commit = on`):
every write acknowledged by the primary had been replicated and flushed
to pg-ha-2 before the primary returned `db_seq` to the client.

The 16 FAIL probe iterations (seq=019-034) represent connection-level
errors — `psycopg2.connect()` failed before the INSERT could execute
(or executed but the connection dropped before the transaction committed)
— not committed writes that were lost. The `db_seq` gap from 0019 → 0034
reflects PostgreSQL SERIAL advancing for partially-executed transactions
that were rolled back, which is expected behavior. There are **no
missing committed rows** in the `k2_probe` table.

Final probe totals:

| | Count |
|---|---|
| Writes OK (acknowledged) | 284 |
| Writes FAIL (all during failover window, no data committed) | 16 |
| Total iterations | 300 |
| Rows on promoted primary (pg-ha-2) | 284 |
| Rows on sync standby (pg-ha-1) | 284 |
| Pre-failure rows on new primary | 19/19 (all present) |

### 4.7 Application Reconnection via HAProxy — ✅ PASS

The probe script uses `psycopg2.connect(host=pg-ha-haproxy:5432, ...)` —
identical to how `fastapi/app.py` would connect after changing only
`DB_HOST=pg-ha-haproxy`. HAProxy re-evaluated its health checks every 2s;
after the new primary's `GET :8008/primary` returned HTTP 200, HAProxy
immediately routed connections to pg-ha-2. The probe reconnected on the
next `connect()` call with no code changes.

The probe script uses per-request `connect()` (mirroring
`fastapi/app.py:230`'s `psycopg2.connect(**DB_CONFIG)`): each request
opens a new connection, so reconnection is automatic on the next request
once HAProxy routes to the new primary. No connection-pool drain or
explicit reconnect logic is needed.

### 4.8 Original Primary Self-Heal — ✅ PASS

`docker start diep-pg-ha-val-3` at **21:58:30**.

pg-ha-3 rejoined the cluster as a standby replica at **21:58:51** — **21s
after restart** — via Patroni's pg_rewind mechanism (pg-ha-3's WAL
diverged on timeline 1; Patroni automatically ran `pg_rewind` to sync it
to pg-ha-2's timeline 2 checkpoint, then established streaming
replication).

```
pg-ha-1   role=sync_standby   state=streaming    lag=0
pg-ha-2   role=leader         state=running      lag=0   (promoted)
pg-ha-3   role=replica        state=streaming    lag=0   (rejoined)
```

Fully automatic — no manual intervention, no `pg_basebackup`, no etcd
key manipulation.

---

## 5. RTO / Failover — Before vs. After

| | Before (current, single `diep-timescaledb`) | After (K2, measured) |
|---|---|---|
| **Primary failure detection** | None (manual / external alert only) | Patroni etcd lease expiry: TTL=30s → detected in ≤30s |
| **Standby promotion** | N/A (no standby) | Patroni leader election: **24.1s** from kill |
| **HAProxy routing** | N/A | First write routed to new primary: **≈28s** end-to-end RTO |
| **RPO (data loss)** | ≈24h (last `pg_dump`); ≈65s with K1 PITR | **RPO = 0** — synchronous replication, all acknowledged writes on promoted standby |
| **Application reconnect** | Manual restart of `fastapi` + `diep-timescaledb` | Per-request `psycopg2.connect()` reconnects automatically through HAProxy on next request |
| **Former primary self-heal** | N/A | Automatic via `pg_rewind` in **21s** (no basebackup required) |
| **PITR chain continuity** | WAL archive from single instance | WAL archive continues on promoted node (timeline 2 segments), restorable with `recovery_target_timeline = 'latest'` |

**All targets from `K2_POSTGRES_HA_IMPLEMENTATION_PLAN.md` §9 met or exceeded.**

---

## 6. Issues Found and Resolved

### 6.1 Volume ownership for Patroni (startup wrapper required)

The `timescale/timescaledb-ha:pg16` image defaults to the `postgres`
user (uid=1000). Docker named volumes are mounted as root, preventing
Patroni from writing to the data directory.

**Fix:** `start-patroni.sh` wrapper (`user: root`) runs `chown -R 1000
/home/postgres/pgdata /wal-archive` then `exec gosu postgres
/usr/bin/patroni`. The `user: root` override applies only to this
startup script; Patroni and PostgreSQL run as uid=1000 for their entire
lifecycle.

**Production impact:** None — this is a docker-compose volume-creation
artifact. In production (Kubernetes CNPG), the StatefulSet spec sets
`fsGroup: 1000` at the pod level, so no wrapper is needed.

### 6.2 TimescaleDB 2.27.2 compression API change

`add_compression_policy()` requires `ALTER TABLE ... SET
(timescaledb.compress)` as a prerequisite in TimescaleDB 2.18+, whereas
older versions enabled compression implicitly. The error message
"columnstore not enabled" is specific to this version mismatch.

**Fix:** Added `ALTER TABLE k2_probe SET (timescaledb.compress)` before
`add_compression_policy()`. The underlying `policy_compression` job,
WAL-replicated catalog entry, and retention behavior are unchanged.

**Production impact:** None — this only affects DDL syntax for adding
compression to new tables. Existing `telemetry` table in production uses
the old `timescaledb.compress` option which remains supported.

### 6.3 pg_hba.conf: no local (Unix socket) entry

Patroni's bootstrap `pg_hba` only included `host` (TCP) entries. Local
socket `psql` commands failed with `no pg_hba.conf entry for host
"[local]"`.

**Fix:** Use `psql -h 127.0.0.1` (TCP) for all admin commands inside
the container. Documented as a non-issue for production: `fastapi` and
all clients connect via TCP (HAProxy or direct host:port), never via
Unix socket.

---

## 7. Recommendation

K2 design is **validated and ready for production scheduling**. Proceed with
`K2_POSTGRES_HA_IMPLEMENTATION_PLAN.md` Section 8 (Production Rollout):

1. Take a `pg_basebackup` of `diep-timescaledb` → MinIO `diep-pg-basebackups`.
2. Bootstrap `pg-ha-1` from that base backup; Patroni auto-clones `pg-ha-2`
   and `pg-ha-3`.
3. Add `pg-ha-haproxy` to `docker-compose.yml`; set `DB_HOST=pg-ha-haproxy`
   in `fastapi`'s env — **no code change**, only env-var update.
4. Enable K1 WAL archiving via `patronictl edit-config` (adds
   `archive_mode`/`archive_command` to all nodes simultaneously).
5. Soak 48h with `diep-timescaledb` still running read-only as fallback;
   monitor `pg_stat_replication` lag and Patroni REST `/cluster`.
6. For lower RTO in production: reduce `ttl` from 30s → 15s in Patroni DCS
   config (`patronictl edit-config`), which proportionally reduces promotion
   time to ≈12-15s.

---

## 8. Cleanup Performed

- Removed containers: `diep-pg-ha-val-1`, `diep-pg-ha-val-2`,
  `diep-pg-ha-val-3`, `diep-pg-ha-etcd`, `diep-pg-ha-haproxy`,
  `diep-pg-ha-probe`.
- Removed volumes: `diep-pg-ha-val_pg-ha-1-data`,
  `diep-pg-ha-val_pg-ha-2-data`, `diep-pg-ha-val_pg-ha-3-data`,
  `diep-pg-ha-val_pg-ha-etcd-data`, `diep-pg-ha-val_pg-ha-wal-archive`.
- Production volume `diep-lab_timescale-data` (created 2026-06-08) intact
  and unmodified throughout.
- `docker-compose-postgres-ha-validation.yml`,
  `postgres-ha-validation/patroni/patroni-base.yml`,
  `postgres-ha-validation/haproxy/haproxy.cfg`,
  `postgres-ha-validation/start-patroni.sh`, and
  `postgres-ha-validation/scripts/db_probe.py` are retained in the repo
  as the validated reference implementation for the production rollout.
