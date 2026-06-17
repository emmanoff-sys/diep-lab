# DIEP Phase 18 — Production Gap Analysis
## Pre-Cutover Readiness Assessment

**Date:** 2026-06-17  
**Phase:** 18 — Production Rollout Program  
**Input documents:** `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`, `DIEP_PHASE17_EXECUTIVE_SUMMARY.md`  
**Certification status:** CONDITIONAL GO — all 6 Phase 17 HA stages complete  
**Purpose:** Enumerate every remaining gap between the Phase 17 CONDITIONAL GO and an unconditional production deployment

---

## 1. Certification Baseline

Phase 17 delivered a validated, documented HA design for all five stateful DIEP tiers. The `DIEP_PRODUCTION_READINESS_CERTIFICATION.md` scored the platform **102/110** and issued a **CONDITIONAL GO** for production deployment. The conditions are not engineering work — they are configuration, secret management, and operational readiness actions that were deferred from Phase 15A and identified during Phase 17 validation.

**No Phase 17 validation failures remain open.** All gaps below are pre-existing security debts, infrastructure setup steps, or operational improvements.

---

## 2. Mandatory Blockers — Must Close Before Go-Live

These items block promotion to production. A deployment that skips any of these will have either a security exposure or a missing operational prerequisite that makes a component unsafe to promote.

### 2.1 Security Blockers (SEC-1 through SEC-5)

| ID | Gap | Location | Risk if skipped |
|---|---|---|---|
| SEC-1 | 5 default `DIEP_*_PASSWORD` secrets not rotated: `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`. Also `DB_PASSWORD`. | `.env` | Credential brute-force trivial; attacker with network access can authenticate as any role |
| SEC-2 | Kafka SASL credential (`diep`/`diep-kafka-pass-2026`) hardcoded in 4 source locations: `docker-compose.yml`, `command_dispatcher.py`, `fastapi/app.py`, and one additional file | Source code | Credential visible to anyone with repo read access; rotation requires code changes |
| SEC-3 | Caddy TLS reverse proxy not enabled; API (:8000), Portal (:3002), and Grafana (:3001) served over HTTP | `docker-compose.yml`, Caddy config | All portal sessions, DERMS commands, and API tokens transmitted in plaintext |
| SEC-4 | Infrastructure ports bound to `0.0.0.0`: Postgres 5432, Redis 6379, Kafka 9092/9094, MinIO 9000/9002 | `docker-compose.yml` port bindings | Direct network access to all infra components without application-tier authentication |
| SEC-5 | EMQX admin password is the validation throwaway credential (`diep-emqx-admin-2026`) | EMQX dashboard / Mnesia config | Cluster management API accessible with a known credential from a public validation artifact |

**SEC-2 detail:** Centralizing the Kafka SASL credential into `.env` requires:
1. Add `KAFKA_SASL_USERNAME` and `KAFKA_SASL_PASSWORD` to `.env`
2. Replace hardcoded values in `docker-compose.yml` with `${KAFKA_SASL_USERNAME}` / `${KAFKA_SASL_PASSWORD}`
3. Replace hardcoded values in `command_dispatcher.py` and `fastapi/app.py` with `os.environ` reads
4. Repeat for the 4th location

### 2.2 Infrastructure Prerequisites (INFRA-1 through INFRA-4)

| ID | Gap | Dependency | What blocks if skipped |
|---|---|---|---|
| INFRA-1 | WAL archive volume ownership: `wal-archive` volume must be owned by postgres uid=70 before enabling `archive_mode=on` on `diep-timescaledb` | K1 PITR cutover | `archive_command` fails silently; WAL segments not shipped; RPO improvement never takes effect |
| INFRA-2 | Redis Sentinel IP seeding: `diep-redis` and `redis-replica` must have static IPs (via `ipam:` in compose network config) before configuring `sentinel monitor` | K4 Redis Sentinel cutover | Docker DNS resolution failures after container lifecycle events cause Sentinel to enter indefinite `+tilt` mode, blocking automatic failover |
| INFRA-3 | MinIO bucket migration: existing `diep-backups` and `diep-config-backups` buckets must be mirrored from `diep-minio` to the HA cluster before any client is re-pointed | K6 MinIO cutover | WAL archive and pg_dump references point to single-node MinIO until migration completes; HA MinIO starts empty, losing backup history |
| INFRA-4 | Kafka CLUSTER_ID extraction: the `CLUSTER_ID` from `diep-kafka`'s `meta.properties` must be extracted before adding new brokers — all 3 KRaft voters must share the same cluster ID | K3 Kafka cutover | New brokers with a mismatched cluster ID cannot join the quorum; existing topics are unreadable by the new voter set |

### 2.3 EMQX Configuration Prerequisites (EMQX-1 through EMQX-2)

| ID | Gap | Risk if skipped |
|---|---|---|
| EMQX-1 | `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__*` env vars not added to production EMQX nodes | EMQX 5.x persists SSL config to Mnesia on first boot; `fail_if_no_peer_cert=true` from `emqx.conf` alone is not reliably enforced after Mnesia init. Devices without client certs may connect. |
| EMQX-2 | EMQX node hostnames do not use `.local` (or other FQDN) suffix in production Docker Compose | Erlang long-name distribution rejects plain hyphenated hostnames; cluster will not form |

### 2.4 Monitoring Prerequisites (MON-1 through MON-4)

These are required before promotion because the components have no cluster-level alerts today. A cluster degradation will not page without them.

| ID | Alert to add | Threshold | Prometheus source |
|---|---|---|---|
| MON-1 | EMQX cluster node count | `emqx_cluster_nodes_running < 3` | `/api/v5/prometheus/stats` on any EMQX node |
| MON-2 | Kafka cluster node count | Broker count < 3 (or custom ISR check) | `kafka-exporter` |
| MON-3 | MinIO disk availability | `minio_cluster_disk_online_total < 4` | MinIO Prometheus endpoint |
| MON-4 | Patroni cluster health | Primary not healthy, or < 1 sync standby | Patroni REST API (`/cluster`) |

**Total mandatory blockers: 16 items** (5 SEC + 4 INFRA + 2 EMQX + 4 MON + 1 backup encryption review)

---

## 3. Recommended Before Go-Live — Medium Priority

These items do not block go-live but introduce known operational risks if deferred beyond the first 30 days of production operation.

| Item | Risk level | Detail | Estimated effort |
|---|---|---|---|
| Patroni TTL reduction (30s → 15s) | Medium | K2 validation used `ttl=30`; production target is `ttl=15` for tighter failover (~15s → 17–20s RTO). Apply via `patronictl edit-config` during or after K2 cutover. | 5 min (one `patronictl` command) |
| HAProxy inter-check tuning (MQTT) | Low-medium | Current `inter 5s fall 3 rise 2` = up to 15s before failed EMQX node is removed from L4 rotation. Reduce to `inter 2s fall 2` for tighter failover detection. | Config edit in HAProxy config |
| Docker image tag pinning | Medium | Several images use `latest` or `latest-pg16` floating tags. Pin to specific digests in the release compose file before production promotion. | Image digest lookup per service |
| Kafka SASL rotation runbook | Medium | No runbook exists for rotating the Kafka SASL credential after it is moved to `.env`. Document the rotation procedure (compose down → credential update → compose up) before the first scheduled rotation. | New runbook document |
| Redis exporter deployment | Medium | No dedicated Redis Prometheus exporter is currently deployed. Sentinel state, memory usage, and connected-client metrics are not visible to Grafana. | Add `redis-exporter` to compose |
| 3-node etcd for Patroni DCS | Medium | K2 validation used a single-node etcd container. Production Patroni should use a 3-node etcd cluster or the Kubernetes API as DCS (CNPG). Single-node etcd is itself a SPOF for DCS writes (though Patroni continues on last-known-good DCS state during outage). | Mitigated by Kubernetes migration (CNPG); for docker-compose production, add 3-node etcd |
| `clean_session` review for ingestor | Low | EMQX K5 validation confirmed that the ingestor with `clean_session=True` loses messages published during the ~5–15s reconnect window on a core node failure. Evaluate `clean_session=False` with a fixed client ID to allow EMQX to buffer QoS ≥ 1 messages for the ingestor during brief reconnect windows. | Code review + test |
| MinIO multi-host isolation | Medium | K6 validated the EC:2 code path correctly; however, 4 MinIO containers on a single Docker host share the same failure domain. True EC:2 node isolation requires separate physical hosts or separate Kubernetes nodes. Acceptable for initial production (EC:2 protects against individual drive/container failure); mitigated fully by Kubernetes deployment. | Kubernetes migration (Q4 2026) |

---

## 4. Post Go-Live Improvements

These items are not pre-conditions for production operation and are appropriate for the Q3–Q4 2026 roadmap.

| Item | Category | Phase 17 reference | Target quarter |
|---|---|---|---|
| Kubernetes migration | Infrastructure | Section 12 of certification | Q4 2026 |
| MinIO backup encryption (SSE-KMS or client-side) | Security | Section 6.3 item 6 | Q3 2026 |
| Kafka SASL_SSL upgrade (PLAINTEXT → SSL) | Security | Year-1 roadmap | Q3 2026 |
| Vault integration for all secrets | Security | Year-1 roadmap | Q3 2026 |
| Redis exporter + Sentinel state Grafana dashboard | Monitoring | MON gap | Q3 2026 |
| Patroni / EMQX / MinIO Grafana dashboards | Monitoring | MON gap | Q3 2026 |
| Scheduled chaos drills (Patroni kill, rolling restart, 2-node MinIO) | Resilience | Section 13 | Q4 2026 |
| IEC 62443 gap assessment | Compliance | Section 13 | Q1 2027 |
| SOC2 Type I preparation | Compliance | Section 13 | Q1–Q2 2027 |
| Multi-tenancy DERMS endpoint tenant-scoping | Feature | Section 13 | Q1–Q2 2027 |
| Dedicated `/derms/ev_charging` endpoint | Feature | Section 13 | Q1–Q2 2027 |
| OTA firmware update pipeline | Feature | Section 13 | Q1 2027 |
| Bulk cert issuance automation | Operations | Section 13 | Q1 2027 |
| SIEM integration for audit_events | Security | Phase 18 security checklist | Q3–Q4 2026 |

---

## 5. Gap Closure Ownership Matrix

| Gap ID | Action required | Owner | Dependency | Estimated effort |
|---|---|---|---|---|
| SEC-1 | Rotate 6 default passwords in `.env` | Ops / Platform Eng | None | 30 min |
| SEC-2 | Externalize Kafka SASL credential to `.env` | Platform Eng | SEC-1 complete first | 1–2 hours (code change + test) |
| SEC-3 | Enable Caddy TLS reverse proxy | Platform Eng | TLS cert provisioned for domain | 1–2 hours |
| SEC-4 | Restrict infra port bindings to internal network | Platform Eng | Compose network topology reviewed | 1–2 hours |
| SEC-5 | Issue EMQX production admin credential | Ops / Sec | Vault or secrets manager available | 30 min |
| INFRA-1 | chown wal-archive volume (uid=70) | Ops | Maintenance window for Postgres restart | 15 min during MW |
| INFRA-2 | Add static IPAM to compose network for Redis tier | Platform Eng | Redis Sentinel compose additions | 30 min |
| INFRA-3 | mc mirror diep-backups → MinIO HA cluster | Ops | MinIO HA cluster running | 30–60 min + mirror time |
| INFRA-4 | Extract CLUSTER_ID from diep-kafka meta.properties | Ops | Prior to K3 MW | 10 min |
| EMQX-1 | Add SSL env var overrides to all 3 EMQX nodes | Platform Eng | EMQX production compose file | 30 min |
| EMQX-2 | Set EMQX node hostnames to .local FQDN | Platform Eng | EMQX production compose file | 15 min |
| MON-1 | Add EMQX node count alert to Alertmanager | Ops | EMQX Prometheus endpoint scraped | 30 min |
| MON-2 | Add Kafka broker count alert | Ops | kafka-exporter running | 30 min |
| MON-3 | Add MinIO disk online alert | Ops | MinIO Prometheus endpoint scraped | 30 min |
| MON-4 | Add Patroni health alert | Ops | Patroni REST API accessible | 30 min |

**Total estimated effort for mandatory blockers:** ~12–16 hours of engineering and operations time, none of which requires new validation environments or service restarts beyond the planned maintenance windows.

---

## 6. Recommended Gap Closure Sequence

```
Week 1 (Pre-Cutover):
  Day 1-2:  SEC-1, SEC-2, SEC-3, SEC-4, SEC-5  ← Security prerequisites
  Day 3:    MON-1, MON-2, MON-3, MON-4         ← Monitoring prerequisites
  Day 4:    INFRA-4 (CLUSTER_ID extraction)     ← Kafka prep
  Day 5:    Image tag pinning, Kafka SASL rotation runbook

Week 2 (Maintenance Window 1):
  MW1:  INFRA-1 (chown) + INFRA-2 (Redis IPAM) → K1 PITR + K4 Redis Sentinel cutover

Week 2-3 (Maintenance Window 2):
  MW2:  INFRA-3 (MinIO mirror) → K6 MinIO HA cutover; 24h soak

Week 3 (Maintenance Window 3):
  MW3:  K3 Kafka HA cutover; 24h soak

Week 4 (Maintenance Window 4):
  MW4:  K2 Postgres HA cutover; 48h soak begins

Week 6 (After K2 soak, Maintenance Window 5):
  MW5:  EMQX-1 + EMQX-2 → K5 EMQX HA cutover
```

---

## 7. Phase 18 Gap Analysis Summary

| Category | Mandatory blockers | Recommended | Post go-live |
|---|---|---|---|
| Security | 5 (SEC-1→5) | 1 (Kafka rotation runbook) | 3 (encryption, SASL_SSL, Vault) |
| Infrastructure | 4 (INFRA-1→4) | 3 (Patroni TTL, etcd HA, image pins) | 1 (Kubernetes migration) |
| EMQX configuration | 2 (EMQX-1→2) | 1 (clean_session review) | — |
| Monitoring | 4 (MON-1→4) | 2 (Redis exporter, dashboards) | 2 (chaos drills, SLO alerts) |
| Operations | — | 1 (HAProxy tuning) | 4 (drills, SIEM, bulk cert) |
| Compliance | — | — | 3 (IEC 62443, SOC2, multi-tenancy) |
| **Total** | **15** | **8** | **13** |

**Platform status:** CONDITIONAL GO. Once the 15 mandatory blockers are closed in sequence (Security → Monitoring → Infrastructure → Component cutovers), the platform is recommended for unconditional GO for single-region production deployment.
