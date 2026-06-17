# DIEP Phase 18 — Go-Live Recommendation
## Production Deployment Authorization Document

**Date:** 2026-06-17  
**Version:** 1.0  
**Classification:** Internal — Engineering Leadership and Program Management  
**Inputs:** `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`, `PHASE18_PRODUCTION_GAP_ANALYSIS.md`, K1–K6 validation reports  
**Audience:** Engineering leadership, operations lead, program manager

---

## 1. Phase 18 Status

Phase 18 begins from a position of complete engineering validation. All six Phase 17 HA stages have been designed, validated, and certified. No HA validation failures remain open. The gap between the current CONDITIONAL GO and an unconditional production go-live consists entirely of configuration and operational actions — not engineering work.

| Stage | Validation status | Production cutover status |
|---|---|---|
| K1 — PostgreSQL PITR | ✅ PASS (4/4 checks) | Pending — MW1 |
| K4 — Redis Sentinel | ✅ PASS (8/8 checks) | Pending — MW1 |
| K6 — MinIO HA (EC:2) | ✅ PASS (14/14 checks) | Pending — MW2 |
| K3 — Kafka HA (KRaft RF=3) | ✅ PASS (10/10 checks) | Pending — MW3 |
| K2 — PostgreSQL Patroni HA | ✅ PASS (13/13 checks) | Pending — MW4 |
| K5 — MQTT HA (EMQX 5.8.6) | ✅ PASS (11/11 + 4 drills) | Pending — MW5 |

**Mandatory gap items outstanding as of 2026-06-17:** 15 (SEC-1→5, INFRA-1→4, EMQX-1→2, MON-1→4)  
**Estimated time to close mandatory gaps:** 12–16 person-hours  
**Estimated total time to full HA production:** 3–4 weeks (including all maintenance windows and soak periods)

---

## 2. Final Readiness Score

### 2.1 Current Score (Phase 17 Baseline, Pre-Cutover)

| Category | Score | Notes |
|---|---|---|
| Platform Resilience | 20/20 | All 5 SPOFs eliminated; RPO=0 (K2), RPO≤65s (K1); Kafka incidents structurally closed |
| Security | 16/20 | 5 default passwords unrotated (−2); no TLS on API/Portal (−1); Kafka SASL hardcoded (−1) |
| Operations | 19/20 | All failure runbooks present; PITR validated; −1 for monitoring gaps (MON-1→4) |
| Deployment | 17/20 | HA reference configs committed; clean-clone validated; −2 for floating image tags and pre-K8s state |
| Documentation | 10/10 | Full Phase 17 document set; K1–K6 implementation plans and reports; architecture doc |
| DERMS Functionality | 20/20 | End-to-end DERMS round-trip validated in K5; all 6 DERMS functions confirmed |
| **Total** | **102/110** | **CONDITIONAL GO** |

### 2.2 Projected Score After Phase 18 Mandatory Gap Closure

| Category | Projected score | Change from baseline | How closed |
|---|---|---|---|
| Platform Resilience | 20/20 | — | Already complete |
| Security | 20/20 | +4 | SEC-1→5 complete (rotate passwords +2, enable TLS +1, centralize SASL +1) |
| Operations | 20/20 | +1 | MON-1→4 close the remaining monitoring gap |
| Deployment | 18/20 | +1 | Image tag pinning (+1); Kubernetes migration still pending (−2) |
| Documentation | 10/10 | — | Already complete |
| DERMS Functionality | 20/20 | — | Already complete |
| **Projected total** | **108/110** | **+6** | **GO (unconditional for single-region deployment)** |

The remaining 2 points not recoverable pre-go-live: Kubernetes migration is a Q4 2026 item. The platform scores 18/20 on Deployment until multi-AZ Kubernetes is complete.

---

## 3. Remaining Risks

### 3.1 High Priority (Must Close — Mandatory Blockers)

These are the 15 mandatory gap items. None may remain open at production go-live.

| ID | Risk | Severity | Status |
|---|---|---|---|
| SEC-1 | 5 default `DIEP_*_PASSWORD` + `DB_PASSWORD` unrotated | High | Open |
| SEC-2 | Kafka SASL credential hardcoded in 4 source locations | High | Open |
| SEC-3 | No TLS on API, Portal, Grafana | High | Open |
| SEC-4 | Infra ports bound to 0.0.0.0 | High | Open |
| SEC-5 | EMQX admin password is validation throwaway | High | Open |
| INFRA-1 | WAL archive volume chown prerequisite | Medium | Open (done in MW1) |
| INFRA-2 | Redis Sentinel IP seeding prerequisite | Medium | Open (done in MW1) |
| INFRA-3 | MinIO bucket migration prerequisite | Medium | Open (done in MW2) |
| INFRA-4 | Kafka CLUSTER_ID extraction | Medium | Open (done before MW3) |
| EMQX-1 | SSL env var overrides for all EMQX nodes | Medium | Open (done in MW5) |
| EMQX-2 | EMQX node FQDN hostname requirement | Medium | Open (done in MW5) |
| MON-1 | EMQX cluster node count alert | Medium | Open |
| MON-2 | Kafka broker count alert | Medium | Open |
| MON-3 | MinIO disk count alert | Medium | Open |
| MON-4 | Patroni primary health alert | Medium | Open |

### 3.2 Medium Priority (Address in First 30 Days)

| Risk | Detail | Mitigation |
|---|---|---|
| Single-node etcd for Patroni DCS | K2 validation used single-node etcd; production Patroni should use 3-node etcd or Kubernetes API DCS (CNPG) | Mitigated by Kubernetes migration (Q4 2026); for Docker Compose production, add 3-node etcd cluster |
| MinIO single-host deployment | 4 MinIO containers on 1 Docker host share same failure domain | EC:2 still protects individual drive/container failures; full isolation via Kubernetes migration |
| MQTT `clean_session=True` for ingestor | Messages published during ~5–15s reconnect window are lost on core EMQX node failure | `command_dispatcher.py` retries QoS 1 unacked commands; evaluate `clean_session=False` for ingestor |
| HAProxy EMQX health check timing | `inter 5s fall 3` = up to 15s before failed node removed from rotation | Reduce to `inter 2s fall 2` during or after MW5 |
| Floating Docker image tags | `latest`/`latest-pg16` tags can pull different images on next compose pull | Pin to digests before first compose pull in production |

### 3.3 Accepted by Design

These risks are understood, documented, and accepted:

| Risk | Acceptance basis |
|---|---|
| EMQX Mnesia requires `-v` teardown for SSL config changes | Env var overrides are reliable alternative; production starts from clean volumes |
| MinIO 2-node failure requires coordinated cluster restart to restore write quorum | Documented in runbook; reads continue throughout; estimated frequency: rare |
| Patroni promotion time bounded by etcd TTL (30s → 15s target) | Achievable via `patronictl edit-config`; 28s measured in validation |
| Kafka producer-perceived outage ≈12s on broker crash | Consumer uninterrupted; zero message loss; QoS 1 DERMS commands retry unacked |

---

## 4. Go / No-Go Recommendation

### 4.1 Current Recommendation

**CONDITIONAL GO**

All engineering work is complete. The HA validation is fully certified. The platform is ready for production deployment subject to the mandatory gap items in Section 3.1 being closed.

The go-live conditions are:

**Condition 1 — Security prerequisites complete (SEC-1 through SEC-5):**
- 5 default application passwords rotated
- Kafka SASL credential centralized into `.env` and removed from source code
- Caddy TLS enabled for API, Portal, Grafana
- Infra ports restricted to internal-only bindings
- EMQX admin credential replaced with vault-managed value

**Condition 2 — Monitoring prerequisites active (MON-1 through MON-4):**
- EMQX, Kafka, MinIO, and Patroni cluster-health alerts are registered in Alertmanager and verified to route to on-call

**Condition 3 — Infrastructure prerequisites complete (INFRA-1 through INFRA-4):**
- WAL archive volume ownership set
- Redis Sentinel IP seeding configured
- MinIO bucket migration completed
- Kafka CLUSTER_ID extracted and documented

**Condition 4 — EMQX deployment prerequisites complete (EMQX-1 through EMQX-2):**
- SSL env var overrides set on all 3 EMQX nodes
- EMQX node hostnames use `.local` FQDN suffix

When all four conditions are met, the recommendation becomes:

**UNCONDITIONAL GO for single-region Docker Compose production deployment.**

### 4.2 What This Recommendation Covers

The CONDITIONAL GO covers:
- Single-region Docker Compose production deployment on a single host
- 5-tier HA: WAL archiving (K1), Redis Sentinel (K4), MinIO EC:2 (K6), Kafka KRaft RF=3 (K3), PostgreSQL Patroni (K2), EMQX 3-node (K5)
- All measured resilience characteristics from Phase 17 validation (RPO=0 sync, RTO=28s failover, Kafka zero message loss, Redis ~6–7s failover, MinIO 0s single-node)
- All 5 SPOF elimination (all tiers HA)

The CONDITIONAL GO does not cover:
- Multi-region or multi-AZ deployment (requires Kubernetes anti-affinity — Q4 2026)
- Host-level failure domain isolation (containers share one physical host)
- SOC2 compliance (Q1–Q2 2027 roadmap)

---

## 5. Recommended Rollout Sequence

The Phase 17 validated sequencing is the recommended production cutover order. Each step has a validated rollback path.

```
Phase 18 Pre-Cutover (1–2 days):
  ├─ SEC-1 through SEC-5: Security prerequisites
  ├─ MON-1 through MON-4: Monitoring prerequisites  
  ├─ INFRA-4: Kafka CLUSTER_ID extraction
  └─ Image tag pinning

MW1 — K1 PITR + K4 Redis Sentinel (2–4 hours):
  ├─ INFRA-1: WAL archive volume chown
  ├─ Enable archive_mode=on on diep-timescaledb
  ├─ INFRA-2: Redis IPAM configuration
  ├─ Start redis-replica + 3 sentinels
  └─ Switch REDIS_URL to Sentinel-aware client

  Soak: 48h monitoring
  ──────────────────────────────────────────

MW2 — K6 MinIO HA (2–3 hours):
  ├─ Start 4-node MinIO cluster
  ├─ INFRA-3: mc mirror bucket migration
  └─ Switch MINIO_ENDPOINT to HA cluster

  Soak: 24h; decommission single-node MinIO
  ──────────────────────────────────────────

MW3 — K3 Kafka HA (3–4 hours):
  ├─ Add kafka-2, kafka-3 brokers (same CLUSTER_ID)
  ├─ Update 3-voter KRaft quorum
  ├─ Recreate diep.commands as RF=3, min.isr=2
  └─ Update KAFKA_BOOTSTRAP to 3-broker list

  Soak: 24h
  ──────────────────────────────────────────

MW4 — K2 PostgreSQL Patroni HA (4–6 hours):
  ├─ pg_basebackup → MinIO
  ├─ Bootstrap Patroni 3-node cluster from base backup
  ├─ Start pg-ha-haproxy; switch DB_HOST
  └─ Enable WAL archiving via patronictl edit-config

  Soak: 48h with diep-timescaledb read-only fallback
  Decommission diep-timescaledb after soak
  ──────────────────────────────────────────

MW5 — K5 EMQX HA (4–6 hours):
  ├─ EMQX-1: SSL env vars on all 3 nodes
  ├─ EMQX-2: .local hostname suffixes
  ├─ Start 3-node EMQX + HAProxy
  ├─ Validate 11/11 functional checks
  └─ Switch MQTT endpoint from Mosquitto to EMQX

  Soak: 2–7 days with Mosquitto running as rollback
  Decommission Mosquitto after soak
  ──────────────────────────────────────────

Full HA production: ~3–4 weeks from MW1 start
```

**Total maintenance window time:** ~15–23 hours of active maintenance across 5 windows  
**Total elapsed calendar time:** 3–4 weeks (dominated by soak periods, not maintenance time)

---

## 6. First 30-Day Support Plan

### Week 1 — K1 + K4 Cutover and Stabilization

| Day | Activity |
|---|---|
| D0 | MW1 execution: PITR enabled; Redis Sentinel live |
| D1–D2 | Daily checks: WAL archive freshness; Sentinel quorum; `/readyz` |
| D3 | MW2 execution: MinIO HA live; bucket migration complete |
| D4–D5 | Daily checks: MinIO 4-disk status; WAL archive to HA MinIO confirmed |
| D7 | Soak checkpoint: MW1 and MW2 both stable; no alerts; backup verify passes |

### Week 2 — K3 + K4 Soak + K2 Preparation

| Day | Activity |
|---|---|
| D8 | MW3 execution: Kafka 3-broker cluster live |
| D9 | Kafka ISR check: all partitions at ISR=3 |
| D10 | Fault-injection verification: kill one Kafka broker; confirm consumer uninterrupted; restart |
| D11–D13 | Daily checks: Kafka ISR, consumer lag, Patroni state |
| D14 | Week 2 soak checkpoint: K1, K4, K6, K3 all stable |

### Week 3 — K2 Cutover and Patroni Stabilization

| Day | Activity |
|---|---|
| D14 | MW4 execution: Patroni 3-node cluster live; HAProxy routing active |
| D15 | Verify RPO=0: all rows present on new primary; WAL archiving on timeline 2 |
| D16 | Patroni switchover drill: graceful failover to pg-ha-2; confirm `/readyz` |
| D17–D18 | 48h soak with diep-timescaledb read-only fallback |
| D18 | Decommission diep-timescaledb (retain volume for 7 more days before removing) |
| D20–D21 | Daily checks: Patroni leader election health, replica lag, PITR freshness |

### Week 4 — K5 Cutover, EMQX Stabilization, and 30-Day Review

| Day | Activity |
|---|---|
| D21 | MW5 execution: EMQX 3-node cluster live; Mosquitto traffic cutover |
| D22 | Validate F1 and F4 drills against production EMQX |
| D23 | All 11 V-checks against production EMQX with production device certs |
| D24–D28 | Daily checks: EMQX cluster nodes, connected devices, telemetry flow |
| D28 | Decommission Mosquitto (after 7-day soak from EMQX cutover) |
| D30 | **30-Day Checkpoint Review:** |

### Day 30 Checkpoint Criteria

| Criterion | Pass if |
|---|---|
| All Phase 17 HA components in production | K1 + K4 + K6 + K3 + K2 + K5 all live |
| Zero production incidents requiring rollback | No rollbacks executed |
| Backup verification passing | Weekly `verify-backup.sh` PASS |
| PITR RPO ≤ 65s confirmed | WAL shipping latency ≤ 65s measured daily |
| Kafka 0 message loss confirmed | 0 producer or consumer failures over 30 days |
| Redis Sentinel failover drill passed | Monthly drill (Section 3.4 of ops runbook) PASS |
| MinIO EC:2 health: 4 disks online | `mc admin info` shows 4/4 online |
| EMQX cluster: 3 nodes healthy | `/api/v5/nodes` shows 3 running |
| All MON-1→4 alerts tested and routing | Test alerts confirmed received by on-call |
| Security checklist complete | All 10 sections signed off |

**If all Day 30 criteria pass:** Issue unconditional production sign-off; proceed to Q4 2026 Kubernetes migration planning.

**If any Day 30 criterion fails:** Document failure, assign owner, set 7-day remediation target.

---

## 7. Year-1 Post-Go-Live Roadmap Commitments

| Quarter | Deliverable | Priority |
|---|---|---|
| Q3 2026 | HA production cutover complete (all 5 maintenance windows) | Critical |
| Q3 2026 | Caddy TLS live for API, Portal, Grafana | Critical (SEC-3) |
| Q3 2026 | Full secret rotation complete | Critical (SEC-1, SEC-2) |
| Q3 2026 | Redis exporter + Prometheus integration | High (operational visibility) |
| Q3 2026 | Patroni, EMQX, MinIO Grafana dashboards | High |
| Q3 2026 | Kafka SASL_SSL upgrade (PLAINTEXT → SSL transport) | High |
| Q4 2026 | Kubernetes migration (CNPG, Strimzi, EMQX Operator) | High |
| Q4 2026 | Multi-AZ anti-affinity for all replicated components | High |
| Q4 2026 | Scheduled chaos drills established (monthly) | Medium |
| Q4 2026 | 3-node etcd for Patroni DCS (Docker Compose production) | Medium (before K8s migration) |
| Q4 2026 | MinIO backup-at-rest encryption (SSE-KMS) | Medium |
| Q1 2027 | IEC 62443 gap assessment | Medium |
| Q1 2027 | OTA firmware update pipeline | Medium |
| Q1 2027 | Bulk cert issuance automation | Low |
| Q1–Q2 2027 | SOC2 Type I preparation | Medium |
| Q1–Q2 2027 | Multi-site field pilot (30–60 days) | High (commercial milestone) |

---

## 8. Final Recommendation Statement

DIEP has completed the most significant engineering milestone since v1.0 initial release: six HA validation stages eliminating every stateful single point of failure in the platform. The validation is rigorous — 60 functional checks, 4 failure drills, 16 technical issues discovered and resolved, zero validation failures remaining, all environments cleanly torn down.

**The recommendation is CONDITIONAL GO, becoming unconditional GO once the 15 mandatory gap items are closed.**

The conditions require approximately 12–16 hours of engineering and operations time. No new environments need to be built. No new validation needs to be performed. The work is configuration management, secret rotation, and adding four monitoring alerts.

Once those conditions are met, DIEP is ready to begin the 5-maintenance-window production cutover sequence — a ~3–4 week execution plan with documented rollback procedures at every step, validated reference configurations as the direct blueprint, and a measured 30-day stabilization checkpoint.

**Production go-live can begin as soon as the mandatory gap items are assigned, executed, and signed off per `DIEP_PRODUCTION_SECURITY_CHECKLIST.md`.**

---

**Recommended by:** Phase 17 and Phase 18 Platform Engineering  
**Date:** 2026-06-17  
**Document status:** Pending sign-off by Engineering Lead and Operations Lead  
**Next review:** Day 30 checkpoint (per Section 6)
