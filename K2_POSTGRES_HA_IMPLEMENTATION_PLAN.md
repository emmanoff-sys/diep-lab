# K2 — PostgreSQL/TimescaleDB HA Implementation Plan

**Phase:** 17, Stage 5 (K2)
**Date:** 2026-06-16
**Status:** Design + side-by-side validation (this stage). Production rollout
(Section 8) is deferred to a scheduled cutover after a soak period, per
`PHASE17_IMPLEMENTATION_PLAN.md` §4.
**Prerequisite:** K1 (PITR / WAL archiving — validated, production rollout
deferred but design confirmed compatible with this stage).

---

## 1. Objective

Eliminate `diep-timescaledb` as a single point of failure by promoting the
current single-instance PostgreSQL 16 / TimescaleDB deployment to a
**1-primary + 2-standby Patroni cluster** with automatic failover, while:

- Preserving all TimescaleDB features: the `telemetry` hypertable,
  compression policy (`compress_after: 7 days`), and retention policies
  (`drop_after: 90 days` on `telemetry`, `drop_after: 180 days` on
  `telemetry_1m`).
- Maintaining compatibility with the K1 PITR design (WAL archiving
  continues to work inside a Patroni-managed cluster — Patroni propagates
  `archive_command` / `archive_mode` / `archive_timeout` to all
  `postgresql.conf` instances it manages).
- Keeping the application-side change to a single environment-variable
  update (`DB_HOST` → HAProxy VIP) — no `fastapi/app.py` or
  `psycopg2` connection-code changes required.

---

## 2. Current State Assessment

| Item | Current value | Source |
|---|---|---|
| Image | `timescale/timescaledb:latest-pg16` (PG 16.14, Alpine) | `docker-compose.yml` |
| Container | `diep-timescaledb`, single node | `docker-compose.yml` |
| `wal_level` | `replica` (already sufficient for streaming replication) | live `SHOW wal_level` |
| `hot_standby` | `on` | live `SHOW hot_standby` |
| `max_wal_senders` | `10` | live `SHOW max_wal_senders` |
| `max_replication_slots` | `10` | live `SHOW max_replication_slots` |
| `archive_mode` | `off` (K1 production rollout deferred) | live `SHOW archive_mode` |
| Hypertables | `telemetry` (1 time dimension) | `timescaledb_information.hypertables` |
| Compression policy | `telemetry` — `compress_after: 7 days` | `timescaledb_information.jobs` |
| Retention policies | `telemetry` — `drop_after: 90 days`; `telemetry_1m` — `drop_after: 180 days` | `timescaledb_information.jobs` |
| Tables | 14 total: `alarms`, `analytics_events`, `audit_events`, `battery_assets`, `commands`, `derms_requests`, `device_certifications`, `device_onboarding`, `devices`, `ev_chargers`, `sites`, `solar_assets`, `telemetry`, `tenants` | live `\dt` |
| Storage | named volume `diep-lab_timescale-data` | `docker-compose.yml` |
| Application | `fastapi/app.py` — `psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)`, env-configurable, no connection pooling (per-request `connect()`) | `fastapi/app.py:48-51,230` |
| Failover today | None — operator-only restart; no replica to promote | n/a |
| RTO today | Manual: start container from existing volume; if volume is corrupt, restore from nightly `pg_dump` (~10-20 min) | `K1_PITR_IMPLEMENTATION_PLAN.md` §2 |
| RPO today | ≈ 24h (nightly `pg_dump`); ≈ 65s with K1 PITR (production rollout deferred) | `K1_PITR_VALIDATION_REPORT.md` §4 |

**Key finding:** `wal_level`, `hot_standby`, `max_wal_senders`, and
`max_replication_slots` are all already at values compatible with streaming
replication. Promoting to a Patroni HA cluster requires **zero changes to
these PostgreSQL parameters** — only adding new nodes and a DCS (Patroni
etcd) is needed.

---

## 3. HA Solution Evaluation

### 3.1 Candidates

| Criterion | **Patroni** | **repmgr** | **pg_auto_failover** |
|---|---|---|---|
| Image compatibility | `timescale/timescaledb-ha:pg16-latest` — official Timescale HA image with Patroni pre-installed, Debian-based, PG16 + all TimescaleDB extensions (hypertables, compression, retention policies) included; **zero custom image build** | Requires `repmgr` extension compiled into postgres. Not available in Alpine (`timescale/timescaledb:latest-pg16`); requires Debian-based custom image (compile from source or add apt repository) | Requires `pgautofailover` extension compiled into postgres. No Alpine packages; custom image build required for Alpine |
| External dependencies | Etcd (DCS, single or 3-node) or Patroni's built-in raft | None (uses postgres catalog for state) | Separate monitor node (plain postgres + pgautofailover extension) |
| Automatic failover | Yes — Patroni leader-election via DCS ensures a single primary; automatic standby promotion with no split-brain | Yes — with `repmgrd` daemon; manual intervention required if `repmgrd` is not running on all nodes | Yes — monitor node orchestrates failover automatically |
| Synchronous replication (RPO=0) | `synchronous_mode: true` — Patroni manages `synchronous_standby_names` automatically, resets it if a sync standby goes down to prevent writes from stalling | Manual `postgresql.conf` setting; no automatic management | Monitor handles sync replication config |
| TimescaleDB feature preservation | Full — `timescaledb-ha` image is official Timescale product; hypertables, compression jobs, and retention policies are standard Postgres extensions unaffected by Patroni | Full — if custom image is correctly built | Full — if custom image is correctly built |
| PITR / K1 compatibility | Full — `archive_command` and `archive_mode` are standard `postgresql.parameters` in Patroni config; shipper sidecar attaches to shared WAL volume same as K1 | Full — same config mechanism | Full — same config mechanism |
| Kubernetes / long-term path | CloudNativePG (CNPG) is Patroni-based; Timescale's `k8s/postgres-cnpg.yaml` draft uses CNPG; validated Patroni topology ports directly to CNPG | repmgr is not used by CNPG; K8s path would require rework | pg_auto_failover is not used by CNPG; K8s path would require rework |
| Operational tooling | `patronictl` (switchover, reinit, config reload), Patroni REST API (health checks, primary/replica routing for HAProxy) | `repmgr node status`, `repmgr cluster show` | `pg_autoctl` CLI |
| Complexity | Medium (etcd + 3 patroni nodes + HAProxy) | Low (no external DCS; repmgrd daemon per node) | Low-medium (monitor node + 2+ data nodes) |

### 3.2 Selection: Patroni

**Patroni** is selected on the following grounds:

1. **Zero custom image build.** `timescale/timescaledb-ha:pg16-latest` ships
   Patroni + pgBackRest + all TimescaleDB extensions out of the box, on the
   same PostgreSQL 16 version as production. repmgr and pg_auto_failover both
   require building a custom image from `timescale/timescaledb:latest-pg16`
   (Alpine base, no apt) — adding unbounded maintenance surface.

2. **Automatic RPO=0 synchronous replication.** `synchronous_mode: true` in
   Patroni config enables synchronous commit with at least one standby and
   dynamically adjusts `synchronous_standby_names` so writes never stall
   if a sync standby goes down — the critical property for zero data loss
   on primary failure.

3. **Direct path to the production Kubernetes target.** The
   `k8s/postgres-cnpg.yaml` draft already references CloudNativePG (CNPG),
   which is Patroni-based. The Patroni topology and `postgresql.parameters`
   validated here translate directly into the CNPG cluster spec (same
   `archive_command`, same sync replication settings, same TimescaleDB
   extension initialisation).

4. **HAProxy health routing.** Patroni's REST API (`GET :8008/primary`,
   `GET :8008/replica`) enables HAProxy to route port 5432 only to the
   current primary and port 5433 only to healthy replicas — a standard
   pattern that works with any libpq client (`fastapi/psycopg2`) via a
   single `DB_HOST` env-var update.

repmgr would have been simpler if the production image were Debian-based.
pg_auto_failover is well-suited for small clusters but lacks the
Kubernetes/CNPG integration path needed for Phase 17's end state.

---

## 4. Target Design

### 4.1 Topology

```
                  ┌───────────────────────────────────────────────┐
                  │         diep-net (bridge)                      │
                  │                                                 │
  fastapi         │  ┌─────────────────────────────────────────┐   │
  (DB_HOST=       │  │  HAProxy (pg-ha-haproxy)                 │   │
  pg-ha-haproxy)─▶│  │  :5432 → current Patroni primary         │   │
                  │  │  :5433 → healthy replica(s)              │   │
                  │  │  health check: GET :8008/primary         │   │
                  │  └──────┬──────────────────────┬────────────┘   │
                  │         │                      │                │
                  │  ┌──────▼──────┐   ┌──────────▼───┐           │
                  │  │  pg-ha-1    │   │  pg-ha-2     │  pg-ha-3  │
                  │  │ (primary)   │──▶│  (sync std'by)│  (async)  │
                  │  │ Patroni     │   │  Patroni     │  Patroni  │
                  │  │ TimescaleDB │   │  TimescaleDB │ TimescaleDB│
                  │  │ :5432       │   │  :5432       │  :5432    │
                  │  │ :8008 REST  │   │  :8008 REST  │  :8008    │
                  │  └──────┬──────┘   └──────────────┘           │
                  │         │ streaming replication                 │
                  │         └─────────────────────────              │
                  │                                                 │
                  │  ┌──────────────────────────────────────────┐   │
                  │  │  pg-ha-etcd  (etcd v3, single node)      │   │
                  │  │  :2379 client / :2380 peer               │   │
                  │  │  DCS for Patroni leader election         │   │
                  │  └──────────────────────────────────────────┘   │
                  └───────────────────────────────────────────────┘

  Patroni cluster: scope=diep-pg-ha-val
  DCS: etcd3 @ pg-ha-etcd:2379
  Replication: pg-ha-1 primary → pg-ha-2 (sync), pg-ha-3 (async)
  Synchronous mode: synchronous_mode=true, synchronous_mode_strict=false
  (strict=false: if both standbys go down, primary degrades to async
   rather than blocking writes — correct for a 3-node cluster where
   min_synchronous_size=1 means 1 sync standby suffices)
```

### 4.2 Configuration Changes

| Setting | Current (`diep-timescaledb`) | Target (Patroni cluster) |
|---|---|---|
| Nodes | 1 primary, no replicas | 1 primary + 2 standbys |
| HA manager | None | Patroni (via `timescale/timescaledb-ha:pg16-latest`) |
| DCS | None | etcd v3 (single node for validation, 3-node for production) |
| `wal_level` | `replica` (unchanged) | `replica` (unchanged — Patroni default) |
| `hot_standby` | `on` (unchanged) | `on` (unchanged) |
| `max_wal_senders` | `10` (unchanged) | `10` (unchanged — sufficient for 2 standbys + base-backup slots) |
| Synchronous replication | Off | `synchronous_mode: true` — Patroni manages `synchronous_standby_names = 'ANY 1 (*)'` automatically |
| `archive_mode` | `off` (K1 deferred) | Passed via `postgresql.parameters.archive_mode: "on"` in Patroni config (K1 compatibility) |
| `archive_command` | `(disabled)` | Passed via `postgresql.parameters.archive_command` (K1 WAL-shipper path — same sidecar pattern as K1) |
| Client `DB_HOST` | `diep-timescaledb` (direct to single container) | `pg-ha-haproxy` (routes to Patroni primary via REST health check) — **env-var change only, no code change** |
| TimescaleDB hypertables / policies | Unchanged | Unchanged — TimescaleDB extension is present in `timescaledb-ha` image; all hypertable/compression/retention jobs replicate as part of streaming replication |

### 4.3 Patroni Configuration (per node)

Each node runs with a generated `patroni.yml` via environment variables
(standard Patroni convention, supported by `timescale/timescaledb-ha`):

```yaml
# effective patroni.yml — generated from env vars per node
scope: diep-pg-ha-val
name: pg-ha-1   # or pg-ha-2 / pg-ha-3

etcd3:
  hosts: pg-ha-etcd:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576   # 1 MB
    synchronous_mode: true
    synchronous_mode_strict: false
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        wal_level: replica
        hot_standby: "on"
        max_wal_senders: 10
        max_replication_slots: 10
        archive_mode: "on"
        archive_command: "test ! -f /wal-archive/%f && cp %p /wal-archive/%f"
        archive_timeout: 60
  initdb:
    - encoding: UTF8
    - data-checksums
  pg_hba:
    - host replication replicator 0.0.0.0/0 md5
    - host all all 0.0.0.0/0 md5

postgresql:
  listen: 0.0.0.0:5432
  connect_address: pg-ha-1:5432   # per-node
  data_dir: /home/postgres/pgdata/data
  authentication:
    replication:
      username: replicator
      password: ${PATRONI_REPLICATION_PASSWORD}
    superuser:
      username: postgres
      password: ${PATRONI_SUPERUSER_PASSWORD}
    admin:
      username: patroni_admin
      password: ${PATRONI_ADMIN_PASSWORD}

restapi:
  listen: 0.0.0.0:8008
  connect_address: pg-ha-1:8008   # per-node

tags:
  nofailover: false
  noloadbalance: false
  clonefrom: false
  nosync: false   # pg-ha-3 can be tagged nosync:true for async-only
```

### 4.4 HAProxy Configuration

```
frontend pgsql_primary
    bind *:5432
    default_backend primary_backend

backend primary_backend
    option httpchk GET /primary
    http-check expect status 200
    server pg-ha-1 pg-ha-1:5432 check port 8008
    server pg-ha-2 pg-ha-2:5432 check port 8008
    server pg-ha-3 pg-ha-3:5432 check port 8008

frontend pgsql_replicas
    bind *:5433
    default_backend replica_backend

backend replica_backend
    balance leastconn
    option httpchk GET /replica
    http-check expect status 200
    server pg-ha-1 pg-ha-1:5432 check port 8008
    server pg-ha-2 pg-ha-2:5432 check port 8008
    server pg-ha-3 pg-ha-3:5432 check port 8008
```

Patroni's REST API returns HTTP 200 on `/primary` only for the current
primary and HTTP 200 on `/replica` only for healthy in-sync standbys —
HAProxy uses these checks to route traffic without any application change.

---

## 5. Implementation Steps (this stage)

1. ✅ Assess current deployment (Section 2).
2. ✅ Evaluate Patroni vs repmgr vs pg_auto_failover (Section 3).
3. ✅ Design 3-node Patroni topology, config, HAProxy (Section 4).
4. ✅ Produce this plan document.
5. Build `docker-compose-postgres-ha-validation.yml`: 1 etcd + 3 timescaledb-ha
   nodes + 1 HAProxy, all on `diep-lab_diep-net`, separate volumes,
   throwaway credentials.
6. Validate (Section 6): replication, lag, primary failure, standby promotion,
   HAProxy routing, app reconnection, PITR compatibility.
7. Simulate primary failure and measure RTO/data loss (Section 6).
8. Tear down; confirm `diep-timescaledb` (production) was never touched.
9. Produce `K2_POSTGRES_HA_VALIDATION_REPORT.md`.
10. (Deferred) Production rollout per Section 8.

---

## 6. Validation Plan

Isolated stack `docker-compose-postgres-ha-validation.yml`, project
`diep-pg-ha-val`, on `diep-lab_diep-net`.

| # | Step | Expected result |
|---|---|---|
| 1 | Bring up etcd + 3 patroni nodes | `patronictl -c patroni.yml list` shows 1 Leader + 2 Replica; all `State: running` |
| 2 | Create validation schema: table `k2_probe` + hypertable + compression policy | Table created on primary; `SELECT * FROM timescaledb_information.hypertables` shows `k2_probe` on primary and standbys |
| 3 | Streaming replication check | `SELECT * FROM pg_stat_replication` on primary shows 2 walsenders; replica lag ≈ 0 |
| 4 | Write probe: continuous `INSERT` into `k2_probe` via HAProxy:5432 (psycopg2) | All writes acknowledged (sync standby confirmed); consumer reads back same rows via HAProxy:5433 |
| 5 | **Primary failure**: `docker kill diep-pg-ha-val-1` (current primary) | Patroni detects via etcd lease expiry, promotes pg-ha-2 within TTL (≤30s); HAProxy routes to new primary within next health-check interval |
| 6 | **Standby promotion verification** | `patronictl list` shows pg-ha-2 as Leader; probe client reconnects via HAProxy (new primary); row count on promoted node matches pre-failure count with zero gaps |
| 7 | **Application reconnection** | psycopg2 probe script reconnects transparently through HAProxy; first write after failover succeeds (no code change, just reconnect via connection pool or retry) |
| 8 | **Original primary restart**: `docker start diep-pg-ha-val-1` | pg-ha-1 rejoins as standby under pg-ha-2's leadership; `pg_stat_replication` shows 2 walsenders again; `pg_rewind` handles any diverged WAL automatically |
| 9 | **PITR compatibility**: enable `archive_mode=on` + `archive_command` via `patronictl edit-config` | WAL segments appear in `/wal-archive` shared volume on all nodes (Patroni propagates config); archived segments correctly named by LSN |
| 10 | **TimescaleDB feature verification** | Compression policy fires (or is manually triggered with `compress_chunk()`); retention policy present; all 14 production-schema tables visible on both primary and promoted standby post-failover |
| 11 | **Data durability accounting** | Row count before kill = row count after promotion; last written sequence is present on promoted standby (synchronous replication guarantees RPO=0 for acknowledged writes) |
| 12 | Teardown | `docker compose -p diep-pg-ha-val down -v`; confirm `diep-timescaledb` volume (`diep-lab_timescale-data`) and production schema unchanged |

---

## 7. Rollback Procedure

| Stage | Rollback action |
|---|---|
| **Validation stack (this stage)** | `docker compose -f docker-compose-postgres-ha-validation.yml -p diep-pg-ha-val down -v` — removes all validation containers and volumes. Production `diep-timescaledb` and `diep-lab_timescale-data` are never referenced. |
| **Production rollout (Section 8, future)** | The Patroni cluster is bootstrapped from a pg_basebackup of the current `diep-timescaledb` volume; the original container keeps running during the soak period. Rollback = re-point `DB_HOST` back to `diep-timescaledb` (env-var change + `fastapi` restart, no data migration to reverse). The Patroni cluster can be decommissioned after the soak period; `diep-timescaledb` is never stopped/removed until after a successful PITR restore drill against the new cluster. |
| **TimescaleDB extension** | TimescaleDB is included in `timescaledb-ha:pg16-latest`; extension exists in data directory and replicates as a catalog entry — no risk of extension mismatch on promotion. |
| **K1 PITR compatibility** | Patroni's `archive_command` management is strictly additive to existing postgresql parameters — disabling it requires only a `patronictl edit-config` to remove the parameter, with no effect on existing WAL archives. |

---

## 8. Production Rollout (deferred — NOT executed in this stage)

Only after `K2_POSTGRES_HA_VALIDATION_REPORT.md` shows PASS for all checks:

1. Create a `pg_basebackup` of `diep-timescaledb` → upload to MinIO
   `diep-pg-basebackups` bucket (using K1 WAL-shipper to MinIO).
2. Bootstrap `pg-ha-1` (new Patroni primary) from that base backup:
   `PATRONI_BOOTSTRAP_FROM: pg_basebackup` or manual `pg_basebackup -D`
   into the new node's volume, then start Patroni — it detects an existing
   data directory and skips initdb.
3. Start `pg-ha-2` and `pg-ha-3`; Patroni automatically clones from
   `pg-ha-1` via `pg_basebackup` + streaming replication.
4. Add `pg-ha-haproxy` to `docker-compose.yml`. Test HAProxy routing
   against the new cluster.
5. Update `DB_HOST` in `fastapi`'s env from `diep-timescaledb` to
   `pg-ha-haproxy`; rolling restart `fastapi` — **no code change**.
6. Run the K1 WAL-archive enable step (add `archive_mode=on` via
   `patronictl edit-config`) and verify WAL-shipper sidecar picks up
   segments from all 3 nodes' shared `wal-archive` volume.
7. Soak period (recommend 48h): `diep-timescaledb` remains running
   read-only as fallback; monitor `pg_stat_replication` lag, Prometheus
   `pg_replication_lag` alert, and `patronictl list` for health.
8. After soak: `docker compose stop timescaledb`; decommission
   `diep-timescaledb` and its volume only after a successful PITR restore
   drill against the new cluster's WAL archive.
9. Port topology into `k8s/postgres-cnpg.yaml` (CloudNativePG operator,
   already drafted) for the eventual Kubernetes cutover — CNPG uses the
   same Patroni-based mechanisms.

---

## 9. RTO / Failover Targets

| | Before (current, single `diep-timescaledb`) | Target (K2, measured in validation) |
|---|---|---|
| **Primary failure detection** | None (manual / external alert) | Patroni etcd lease expiry: `ttl=30s` → detection in ≤30s |
| **Standby promotion** | N/A (no standby) | Patroni leader election + promotion: target **≤30s** from detection |
| **Application reconnection** | N/A (manual restart of whole stack) | HAProxy re-routes next health-check cycle (every 2s); psycopg2 `connect()` on next request to HAProxy succeeds → target **≤35s** end-to-end RTO |
| **Data loss (RPO)** | ≈ 24h (last `pg_dump`); ≈ 65s with K1 PITR | **RPO = 0** for writes acknowledged by primary with `synchronous_mode=true` (at least 1 sync standby confirmed write before ack) |
| **PITR compatibility** | RPO ≈ 65s (K1 validation, deferred prod) | Unchanged — WAL archiving works identically in Patroni cluster (Patroni propagates `archive_command` to all nodes' `postgresql.conf`) |
| **TimescaleDB feature continuity** | Hypertables/policies on single primary | Identical on promoted standby — streaming replication copies all catalog entries including TimescaleDB metadata; compression/retention jobs re-fire on schedule |
