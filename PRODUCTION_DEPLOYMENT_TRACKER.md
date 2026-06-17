# DIEP Production Deployment Tracker
## Mandatory Blocker Closure Dashboard

**Program:** Phase 18 — Production Rollout
**Certification baseline:** 102/110 — CONDITIONAL GO
**Target score after closure:** 108/110 — UNCONDITIONAL GO
**Last updated:** 2026-06-17
**Review cadence:** Weekly (every Monday)
**Tracker owner:** Operations Lead

> **Legend:** 🔴 Open · 🟡 In Progress · 🟢 Closed · ⬜ Blocked

---

## Overall Progress

| Category | Total | Closed | Remaining |
|---|---|---|---|
| Security (SEC) | 5 | 0 | **5** |
| Infrastructure (INFRA) | 4 | 0 | **4** |
| EMQX Configuration (EMQX) | 2 | 0 | **2** |
| Monitoring (MON) | 4 | 0 | **4** |
| **Total** | **15** | **0** | **15** |

**Go-live gate:** All 15 items must reach 🟢 Closed with sign-off before MW1 begins (security, monitoring, INFRA-4) or the relevant maintenance window (INFRA-1→3, EMQX-1→2).

---

## Security Blockers — SEC-1 through SEC-5

*Target: complete in Week 1, before any maintenance window is scheduled.*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| SEC-1 | Rotate 6 default passwords: `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, `DB_PASSWORD` in `.env` | Platform Eng / Ops | | 🔴 Open | `.env` diff confirming no `*_PASSWORD` value matches pilot defaults; `docker compose restart` confirming services healthy | |
| SEC-2 | Externalize Kafka SASL credential from 4 source locations (`docker-compose.yml`, `command_dispatcher.py`, `fastapi/app.py`, + 1 additional file) into `KAFKA_SASL_USERNAME` / `KAFKA_SASL_PASSWORD` in `.env`; confirm no hardcoded values remain (`grep -r "diep-kafka-pass" .`) | Platform Eng | | 🔴 Open | `grep` output showing zero matches for hardcoded credential in source; end-to-end Kafka produce/consume test PASS | |
| SEC-3 | Enable Caddy TLS reverse proxy for API (:8000), Portal (:3002), and Grafana (:3001); confirm all three endpoints respond on HTTPS and redirect HTTP | Platform Eng | | 🔴 Open | `curl -I https://<domain>:8000/readyz` returns 200; browser cert check screenshot or `openssl s_client` output | |
| SEC-4 | Restrict infrastructure port bindings from `0.0.0.0` to internal network: Postgres 5432, Redis 6379, Kafka 9092/9094, MinIO 9000/9002 | Platform Eng | | 🔴 Open | `docker inspect` showing port bindings to internal subnet; external connectivity test confirming ports not reachable from outside compose network | |
| SEC-5 | Replace EMQX admin credential (`diep-emqx-admin-2026`) with production-issued credential; confirm via `GET /api/v5/nodes` with new credential | Ops / Security | | 🔴 Open | EMQX HTTP API accessible with new credential; old credential returns 401; new credential stored in secrets manager or vault | |

---

## Infrastructure Prerequisites — INFRA-1 through INFRA-4

*INFRA-4 must complete before MW3. INFRA-1 and INFRA-2 are completed during MW1. INFRA-3 is completed during MW2.*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| INFRA-1 | Set WAL archive volume ownership to postgres uid=70 before enabling `archive_mode=on` on `diep-timescaledb`. Run during MW1 pre-flight: `docker run --rm -v diep-lab_wal-archive:/vol alpine chown -R 70:70 /vol` | Ops | MW1 | 🔴 Open | `docker exec diep-timescaledb ls -la /var/lib/postgresql/wal-archive` showing uid=70; first WAL segment visible in MinIO `diep-wal-archive` bucket within 65s of enable | |
| INFRA-2 | Add static IPAM entries to compose network config for `diep-redis` (primary) and `redis-replica` before Redis Sentinel cutover. Prevents DNS-resolution `+tilt` after container lifecycle events. Run during MW1 pre-flight. | Platform Eng | MW1 | 🔴 Open | `docker network inspect` confirming static IPs assigned; Sentinel `+reset-master` and `+slave` events in Sentinel logs (no `+tilt` entries); `sentinel masters` via `redis-cli` showing IP (not hostname) for master | |
| INFRA-3 | Mirror existing `diep-backups` and `diep-config-backups` buckets from single-node `diep-minio` to HA MinIO cluster before any client is re-pointed. `mc mirror minio-pilot/diep-backups minio-ha/diep-backups` | Ops | MW2 | 🔴 Open | `mc ls minio-ha/diep-backups` object count matches `mc ls minio-pilot/diep-backups`; `mc diff` showing zero divergence; WAL archive to HA MinIO confirmed in K1 PITR check after cutover | |
| INFRA-4 | Extract `CLUSTER_ID` from `diep-kafka`'s KRaft `meta.properties` file before adding new brokers. `docker exec diep-kafka cat /var/lib/kafka/data/__cluster_metadata-0/meta.properties \| grep cluster.id` — record value in runbook and compose env. | Ops | Pre-MW3 | 🔴 Open | `CLUSTER_ID` value recorded in `DIEP_PRODUCTION_CUTOVER_RUNBOOK.md` MW3 section; new brokers bring up with matching ID; `kafka-metadata-quorum.sh --describe` shows 3 voters | |

---

## EMQX Configuration Prerequisites — EMQX-1 through EMQX-2

*Both items completed during MW5 pre-flight before any EMQX node is started.*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| EMQX-1 | Add SSL environment variable overrides to all 3 production EMQX node definitions in `docker-compose.yml`: `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__FAIL_IF_NO_PEER_CERT=true`, `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__VERIFY=verify_peer`, and `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__CACERTFILE`, `CERTFILE`, `KEYFILE` paths. Required because EMQX 5.x persists SSL config to Mnesia on first boot — `emqx.conf` alone is not reliably enforced after Mnesia init. | Platform Eng | MW5 | 🔴 Open | Connection attempt with no client cert rejected at TLS handshake (Paho `on_disconnect` callback fires before CONNACK); connection with valid client cert succeeds; `GET /api/v5/listeners` confirms `fail_if_no_peer_cert: true` | |
| EMQX-2 | Set EMQX node hostnames to `.local` FQDN format in production compose: `EMQX_NODE__NAME=emqx@emqx-1.local` (and `-2`, `-3`); set `hostname: emqx-1.local` in each service definition. Required because Erlang long-name distribution rejects plain hyphenated hostnames — cluster will not form without FQDN. | Platform Eng | MW5 | 🔴 Open | `GET /api/v5/nodes` returns 3 nodes all in `running` state; node names in response include `.local` suffix; `emqx@emqx-1.local` visible in cluster node list | |

---

## Monitoring Prerequisites — MON-1 through MON-4

*All 4 alerts must be active and routing to on-call before MW1 begins.*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| MON-1 | Add EMQX cluster node count alert to Alertmanager: `emqx_cluster_nodes_running < 3` from `/api/v5/prometheus/stats` scraped on any EMQX node. Route to `diep-oncall` receiver. | Ops | Pre-MW1 | 🔴 Open | Alertmanager rule file diff; `amtool alert add` test firing; on-call notification received (screenshot or delivery log); rule appears in `GET /api/v1/rules` with state `inactive` (no false fire) | |
| MON-2 | Add Kafka broker count alert: broker count < 3 sourced from `kafka-exporter` Prometheus metrics. Alert name: `KafkaBrokerCountLow`. Route to `diep-oncall`. | Ops | Pre-MW1 | 🔴 Open | Alertmanager rule file diff; `kafka-exporter` scrape confirmed in Prometheus targets; test alert fired and received by on-call; rule in `inactive` state under normal conditions | |
| MON-3 | Add MinIO disk availability alert: `minio_cluster_disk_online_total < 4` from MinIO Prometheus endpoint (`:9000/minio/v2/metrics/cluster`). Alert name: `MinioDiskOnlineLow`. Route to `diep-oncall`. | Ops | Pre-MW1 | 🔴 Open | Alertmanager rule file diff; MinIO Prometheus endpoint scraped in Prometheus targets; test alert fired and received; rule in `inactive` state with 4/4 disks online | |
| MON-4 | Add Patroni cluster health alert: primary not healthy or sync standby count < 1, sourced from Patroni REST API (`GET :8008/cluster`). Alert name: `PatroniClusterDegraded`. Route to `diep-oncall`. | Ops | Pre-MW1 | 🔴 Open | Alertmanager rule file diff; Patroni REST API scraped by Prometheus; test alert fired and received; rule in `inactive` state with healthy 3-node cluster | |

---

## Maintenance Window Gate Checklist

Before each maintenance window may begin, the corresponding gate items must be 🟢 Closed.

| Maintenance Window | Gate Items Required Closed | Ready? |
|---|---|---|
| MW1 — K1 PITR + K4 Redis Sentinel | SEC-1, SEC-2, SEC-3, SEC-4, SEC-5, MON-1, MON-2, MON-3, MON-4, INFRA-2 | 🔴 |
| MW2 — K6 MinIO HA | MW1 complete + 48hr soak passed | 🔴 |
| MW3 — K3 Kafka HA | MW2 complete + 24hr soak passed + INFRA-4 | 🔴 |
| MW4 — K2 PostgreSQL Patroni HA | MW3 complete + 24hr soak passed + INFRA-3 (MinIO migration confirmed) | 🔴 |
| MW5 — K5 EMQX HA | MW4 complete + 48hr soak passed + EMQX-1 + EMQX-2 | 🔴 |
| **Day-30 Sign-off** | MW5 complete + 7-day EMQX soak + all 10 checkpoint criteria PASS | 🔴 |

---

## Weekly Status Summary

*Complete this section at each Monday review.*

| Review Date | Items Closed This Week | Items Remaining | Blockers / Notes | Next Milestone |
|---|---|---|---|---|
| 2026-06-17 | 0 | 15 | Authorization pending | Board approval |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

---

**Tracker prepared by:** DIEP Platform Engineering
**Source documents:** `PHASE18_PRODUCTION_GAP_ANALYSIS.md`, `PHASE18_GO_LIVE_RECOMMENDATION.md`, `DIEP_PRODUCTION_SECURITY_CHECKLIST.md`
**Date created:** 2026-06-17
