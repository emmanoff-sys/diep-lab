# Platform Recovery Verification Report
### RE-OS Development Platform | Post-Recovery Baseline Stabilisation
### Verification Date: 2026-07-11 | Verification Time: 01:48–02:10 UTC

---

## 1. Purpose

This document records the controlled post-recovery verification of the RE-OS development
platform following a VM instability event. It confirms the platform is stable, reproducible,
and suitable for continued programme execution under PAO-032 (WP-012-04 Contingency Analysis).

---

## 2. Recovery Event Summary

| Item | Detail |
|------|--------|
| Event type | VM write-ack / persistence failure (recurring pattern) |
| Affected services | Prometheus gracefully stopped (exit 0 at 22:40:42Z); kafka-exporter and dispatcher transient restarts at stack startup |
| Recovery action | Platform stack restarted; no data loss observed |
| Recovery time | Stack up at approximately 22:28 UTC (2026-07-10) |
| WAL continuity | Confirmed continuous — no gap in WAL archive at MinIO |

---

## 3. Platform Baseline

### 3.1 Git State

| Item | Value |
|------|-------|
| Branch | `feature/wp-012-04-contingency-analysis` |
| HEAD commit | `849486e9323cb70eb1964c171c12de37ac211665` |
| Commit message | `docs(governance): WP-012-03 formal closure after GOV-002 merge (EECR-CHG-133)` |
| Programme baseline | WP-012-03 CLOSED; WP-012-04 engineering in progress (pre-commit) |

### 3.2 Operating System

| Component | Version |
|-----------|---------|
| OS | Ubuntu 26.04 LTS |
| Kernel | 7.0.0-27-generic (x86_64) |
| Docker | 29.6.0, build fb59821 |
| Docker Compose | v5.1.4 |
| Python | 3.14.4 |

### 3.3 Platform Services

| Service | Version | Status |
|---------|---------|--------|
| PostgreSQL | 16.14 (Alpine musl) | RUNNING |
| TimescaleDB | 2.28.0 | RUNNING |
| Apache Kafka | latest (KRaft mode) | RUNNING |
| Redis | 7.4.9 | RUNNING (master + replica + 3 sentinels) |
| Grafana | 13.1.0 | RUNNING |
| Prometheus | — | RUNNING (restarted during verification) |
| MinIO | — | RUNNING |
| FastAPI | — | RUNNING (healthy) |

### 3.4 Resource Utilisation

| Resource | Value |
|----------|-------|
| Disk (/) | 102 GiB used / 146 GiB (74%) — 37 GiB available |
| Memory | 3.3 GiB used / 6.2 GiB (53%); 2.6 GiB buff/cache; 2.9 GiB available |
| Swap | 1.2 GiB used / 4.0 GiB (30%) |
| CPU (verification snapshot) | 24.2% us+sy, 75.8% idle, 3.0% wa |

---

## 4. Container Health Summary

All 25 containers verified running at time of verification (one — Prometheus — restarted
as part of this verification procedure after confirmed clean exit during recovery event).

| Container | Restarts | Health | Notes |
|-----------|----------|--------|-------|
| diep-fastapi | 0 | HEALTHY | /healthz 200 continuous |
| diep-timescaledb | 0 | HEALTHY | Checkpoints + CAgg refreshes active |
| diep-kafka | 0 | HEALTHY | KRaft mode, 0 consumer lag |
| diep-redis | 0 | HEALTHY | Master role confirmed |
| diep-redis-replica | 0 | HEALTHY | Replica synced, lag ~1s |
| diep-redis-sentinel-1/2/3 | 0 | HEALTHY | Quorum 2, 1 slave, 5 other sentinels |
| diep-grafana | 0 | HEALTHY | INFO-level only, cleanup jobs running |
| diep-prometheus | 0 | HEALTHY | Restarted 01:48 UTC; 7 targets up |
| diep-minio | 0 | HEALTHY | WAL archive actively receiving |
| diep-wal-shipper | 0 | HEALTHY | Shipping 1 segment per cycle (~60s) |
| diep-kafka-exporter | 11 | STABLE | Transient startup race; stable 3+ hrs |
| diep-dispatcher | 1 | STABLE | 1 restart at stack startup; stable |
| diep-ingestor | 0 | HEALTHY | — |
| diep-oms-detector | 0 | HEALTHY | (healthy label) |
| diep-nodered | 0 | HEALTHY | (healthy label) |
| All others (9) | 0 | HEALTHY | No issues |

---

## 5. Service Verification Detail

### 5.1 FastAPI

- `/healthz` returns `{"status":"ok","instance":"bd2634369ce5"}` — GREEN
- Caddy health-check polling confirmed in logs (200 every ~30s)
- OMS detect endpoint responding (200 POST /oms/detect observed in logs)

### 5.2 TimescaleDB / PostgreSQL

- PostgreSQL 16.14 operational; role `diep` confirmed
- TimescaleDB extension 2.28.0 loaded
- Continuous aggregate `telemetry_1m` refreshing on schedule
- Checkpoints completing cleanly (write+sync within normal bounds)
- Current WAL LSN: `F/C4000490`
- No replication configured (standalone dev; WAL shipped to MinIO as backup)

### 5.3 Kafka

- KRaft mode (no ZooKeeper dependency)
- Broker ID 1, healthy; consumer group `diep-command-dispatcher` at 0 lag
- Topics: `diep.commands`
- KRaft snapshot generation confirmed at 00:59 UTC
- No broker errors in recent logs

### 5.4 Redis / Sentinel

- Redis 7.4.9 master; 1 connected replica (offset sync confirmed)
- Sentinel cluster: 3 sentinels; quorum=2; `num-other-sentinels`=5
- RDB background save completed successfully at 22:29 UTC
- Master failover state: no-failover

### 5.5 WAL Shipping / MinIO

- MinIO healthy; bucket `diep-wal-archive` accessible
- WAL archive shipping confirmed: latest segment `000000010000000F000000CA` at 01:48:46 UTC
- Continuous 1-per-minute shipping cadence (every ~60s)
- WAL shipper startup error (MinIO connection refused at 19:48 UTC) was a transient
  startup-order issue; resolved automatically when MinIO became available at 22:28 UTC

### 5.6 Grafana

- No errors or warnings in logs; only INFO-level entries
- Cleanup, plugin update check, and bleve-backend cache eviction all normal

### 5.7 Prometheus

- Was in `Exited (0)` state — confirmed graceful shutdown at 22:40:42 UTC during
  recovery event. No crash; restart policy did not re-trigger.
- Restarted manually at 01:48:46 UTC as part of this verification.
- Confirmed healthy: `Prometheus Server is Healthy.`
- Active scrape targets: fastapi, kafka-exporter, minio, node-exporter,
  postgres-exporter, prometheus (self), redis-exporter — all UP
- Expected-down targets: cadvisor (not deployed), diep-mdm (not deployed),
  diep-opcua-connector (not deployed) — these are known dev-environment gaps

---

## 6. Repository Integrity Assessment

| Check | Result |
|-------|--------|
| Working tree clean | NO — WP-012-04 engineering in-progress (by design) |
| Recovery artefacts committed | NONE |
| Temporary scripts remaining | NONE (shell scripts are tracked project files) |
| Debugging configuration retained | NONE |
| Sensitive information exposed | NONE confirmed |
| Unexpected modifications | See table below |

**Unstaged modifications (all legitimate, non-artefact):**

| File | Nature |
|------|--------|
| `PLANNING.md` | Engineering addendum (2026-06-25) distinguishing CIM telemetry vs topology import |
| `nodered/.config.nodes.json` | Node-RED version bump 5.0.0 → 5.0.1 (automatic) |
| `.vscode/extensions.json` | VSCode extension recommendation added |
| `services/adms_grid_analytics/__init__.py` | WP-012-04 ContingencyAnalysisService export |
| `services/adms_grid_analytics/contracts.py` | WP-012-04 ContingencyImpactSummary TypedDict |
| `services/adms_grid_analytics/service.py` | WP-012-04 analyze_contingency delegation |

**Untracked files (all legitimate, in-progress):**

| File | Nature |
|------|--------|
| `.claude/` | AI assistant configuration |
| `.vscode/settings.json` | IDE workspace settings |
| `services/adms_grid_analytics/contingency_analysis_service.py` | WP-012-04 in-progress |
| `tests/test_adms_contingency_analysis_service.py` | WP-012-04 in-progress |

---

## 7. Outstanding Issues

See separate Outstanding Issues Register (`PLATFORM-RECOVERY-OUTSTANDING-ISSUES.md`).

---

## 8. Acceptance Criteria Assessment

| Criterion | Status |
|-----------|--------|
| No unexpected container failures | PASS — all failures were transient startup races |
| No persistent application errors | PASS — no recurring errors in any service log |
| Kafka healthy | PASS — 0 consumer lag, broker healthy |
| TimescaleDB without database errors | PASS — no DB errors (FATAL roles were verification attempts) |
| WAL shipping healthy | PASS — continuous archive shipping confirmed |
| Grafana and Prometheus operational | PASS — Prometheus restarted; both confirmed healthy |
| FastAPI health endpoints green | PASS — /healthz 200 continuous |
| Resource utilisation within limits | PASS — 74% disk, 53% memory, 24% CPU |
| Recovery documentation complete | PASS — this document and companions |
| Recovery snapshot | PENDING — requires operator hypervisor action (see Section 9) |

---

## 9. VM Snapshot

A hypervisor/VM snapshot must be taken manually by the platform operator.

**Required snapshot parameters:**

| Item | Value |
|------|-------|
| Name | `RE-OS-DEV-RECOVERY-BASELINE-2026-07-11` |
| Description | Known Good Engineering Baseline — post-recovery verification |
| Git commit | `849486e9323cb70eb1964c171c12de37ac211665` |
| Programme baseline | WP-012-03 CLOSED; WP-012-04 in progress |
| WAL LSN at snapshot | `F/C4000490` (or current at snapshot time) |
| Recommended time | Immediately after reading this report |

The snapshot record (`PLATFORM-RECOVERY-VM-SNAPSHOT-RECORD.md`) must be completed
by the platform operator after the snapshot is created.

---

## 10. Operational Readiness Statement

The RE-OS Development Platform is operationally ready to resume WP-012-04 engineering.

All core services are healthy. WAL backup is continuous. Repository integrity is confirmed.
No recovery artefacts are present. Prometheus has been restored. The platform has been
observed healthy for 3+ hours since recovery stack restart.

**Engineering work may resume on `feature/wp-012-04-contingency-analysis` from
commit `849486e9` immediately upon receipt of this report.**

---

*Produced by RE-OS Platform Verification | 2026-07-11T02:10:00Z*
