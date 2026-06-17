# DIEP Production Deployment Tracker
## Mandatory Blocker Closure Dashboard

**Program:** Phase 18 — Production Rollout (HA cutover) + Phase 20/21 — Portal/Application Security
**Certification baseline:** 102/110 — CONDITIONAL GO (HA scope, `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`)
**Target score after closure:** 108/110 — UNCONDITIONAL GO
**Application/portal track:** NO-GO (Phase 20) → CONDITIONAL GO (Phase 21, `PRODUCTION_DEPLOYMENT_DECISION_v2.md`)
**Last updated:** 2026-06-17 (Phase 22 go-live readiness review)
**Review cadence:** Weekly (every Monday)
**Tracker owner:** Operations Lead

> **Legend:** 🔴 Open · 🟡 In Progress · 🟢 Closed · ⬜ Blocked

---

## Overall Progress

| Category | Total | Closed | Remaining |
|---|---|---|---|
| Security (SEC) | 6 | 0 | **6** |
| Infrastructure (INFRA) | 4 | 0 | **4** |
| EMQX Configuration (EMQX) | 2 | 0 | **2** |
| Monitoring (MON) | 4 | 0 | **4** |
| Application/Portal Security (APP) | 6 | 6 | **0** |
| Application/Portal — Minor (APP-MINOR) | 4 | 0 | **4** |
| **Total (MW1-relevant + application)** | **26** | **6** | **20** |

**Go-live gate (MW1 specifically):** SEC-1 through SEC-6, MON-1 through MON-4, and INFRA-2 must reach 🟢 Closed with sign-off before MW1 begins. **0 of these 11 MW1-gating items are closed as of this review (Phase 22, 2026-06-17).** The Application/Portal Security items (APP-1 through APP-6) were tracked and closed separately under Phase 20/21 and are not part of the MW1 gate (MW1 is K1 PITR + K4 Redis Sentinel — backend/infra scope only) — see "Phase 22 Go-Live Readiness Review" note below.
INFRA-4 gates MW3; INFRA-1, INFRA-3, EMQX-1, EMQX-2 gate their respective windows as shown in the Maintenance Window table.

> **Phase 22 note:** This tracker originally covered only the HA-cutover items below (SEC/INFRA/EMQX/MON). A parallel track — production *installation* and *web portal* validation — ran in Phases 20–21, found a separate NO-GO (no portal authentication/authorization, audit trail not attributable, Grafana default credentials, silently-failing backups), and closed it. Those items are folded into this tracker as the new "Application/Portal Security" sections below so one document reflects total go-live readiness. Closing APP-1→6 does **not** close any SEC/INFRA/EMQX/MON item and does **not** by itself authorize MW1.

---

## Security Blockers — SEC-1 through SEC-6

*Target: SEC-1 through SEC-5 complete in Week 1, before any maintenance window is scheduled. SEC-6 targets pre-Day-30 (see note below).*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| SEC-1 | Rotate 6 default passwords: `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, `DB_PASSWORD` in `.env`. **Expanded per Phase 22 review:** also set the two new variables `GF_ADMIN_PASSWORD` and `DIEP_ENGINEER_PASSWORD` introduced by Phase 21 — confirmed absent from the current `.env` (`docker compose up` will now fail outright on the Grafana service without `GF_ADMIN_PASSWORD`, by design); also remove the now-unused `DIEP_PORTAL_TOKEN` line (dead since Phase 21's per-user-token rewrite of the portal BFF). | Platform Eng / Ops | | 🔴 Open | `.env` diff confirming no `*_PASSWORD` value matches pilot/lab defaults and both new vars are set; `docker compose up` confirming all services including Grafana start healthy | |
| SEC-2 | Externalize Kafka SASL credential from 4 source locations (`docker-compose.yml` ×2, `command_dispatcher.py`, `fastapi/app.py`) into `KAFKA_SASL_USERNAME` / `KAFKA_SASL_PASSWORD` in `.env`; confirm no hardcoded values remain (`grep -r "diep-kafka-pass" .`). **Re-confirmed open by direct grep during Phase 22 review** — all 4 locations still contain the literal credential. | Platform Eng | | 🔴 Open | `grep` output showing zero matches for hardcoded credential in source; end-to-end Kafka produce/consume test PASS | |
| SEC-3 | Enable Caddy TLS reverse proxy for API (:8000), Portal (:3002), and Grafana (:3001); confirm all three endpoints respond on HTTPS and redirect HTTP. **Re-confirmed open by Phase 22 review** — `caddy/Caddyfile` exists in the repo but no `caddy` service block exists in `docker-compose.yml`; the proxy is not wired in. | Platform Eng | | 🔴 Open | `curl -I https://<domain>:8000/readyz` returns 200; browser cert check screenshot or `openssl s_client` output | |
| SEC-4 | Restrict infrastructure port bindings from `0.0.0.0` to internal network: Postgres 5432, Redis 6379, Kafka 9092/9094, MinIO 9000/9002. **Re-confirmed open by Phase 22 review** — all listed ports found bound via the unqualified `"host:container"` short syntax, which binds `0.0.0.0` by default. | Platform Eng | | 🔴 Open | `docker inspect` showing port bindings to internal subnet; external connectivity test confirming ports not reachable from outside compose network | |
| SEC-5 | Replace EMQX admin credential (`diep-emqx-admin-2026`) with production-issued credential; confirm via `GET /api/v5/nodes` with new credential. Note: production EMQX (K5/MW5) is not yet present in the main `docker-compose.yml` — this item is gated into the pre-MW1 security sprint per the certification's Section 11 sequencing, ahead of when the credential is actually exercised at MW5. | Ops / Security | | 🔴 Open | EMQX HTTP API accessible with new credential; old credential returns 401; new credential stored in secrets manager or vault | |
| SEC-6 *(new, added Phase 22)* | Evaluate and, if adopted, implement backup-at-rest encryption for MinIO (SSE-KMS or client-side encryption of `pg_dump`/config archives). Identified in `DIEP_PRODUCTION_READINESS_CERTIFICATION.md` §6.3 item 6 but never given a tracked ID — added here so it isn't lost. Not required to unlock MW1 (PITR/backup correctness, not confidentiality, gates MW1), but should have an owner and target date before Day-30 sign-off. | Security / Platform Eng | Pre-Day-30 | 🔴 Open | Decision recorded (adopt SSE-KMS, client-side encryption, or formally accept the risk); if adopted, `mc stat` on a backup object shows server-side or client-side encryption metadata | |

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

*Re-confirmed open by direct inspection of `prometheus/alerts.yml` during the Phase 22 review — none of MON-1 through MON-4 exist in the rules file yet (it has `KafkaOutage`/`DatabaseOutage`/host-level alerts only). Phase 21 separately added a one-off, push-based `BackupFailed` alert (posted directly to Alertmanager's API by `scripts/backup-db.sh`/`backup-config.sh` on failure) — that is unrelated to MON-1→4 and does not close any of them.*

---

## Application/Portal Security — APP-1 through APP-6 *(added Phase 22, closed via Phase 20/21)*

*Found via the independent Production Installation + Web Portal Validation track (Phase 20), closed via Phase 21 remediation, and re-verified against a fresh isolated deployment in this same track. Folded into this tracker for a single source of truth. None of these gate MW1 (K1 PITR + K4 Redis Sentinel is backend/infra-only) — listed here for completeness and because some (APP-5/6) materially affect the SEC-1 evidence above.*

| Gap ID | Description | Status | Evidence |
|---|---|---|---|
| APP-1 | Portal had no authentication — every page reachable anonymously | 🟢 Closed | `WEB_PORTAL_VALIDATION_REPORT_v2.md` — anonymous context redirected to `/login` on all 6 tested routes |
| APP-2 | Portal had no authorization — one shared admin-scoped token bypassed backend RBAC | 🟢 Closed | Per-user JWT now forwarded by `route.ts`; `viewer`/`operator` confirmed to get real 403s from admin-only/`engineer`-only endpoints |
| APP-3 | Audit trail could not attribute actions to a human | 🟢 Closed | Audit rows now show real usernames/roles, not the shared API-key identity |
| APP-4 | Audit trail had no UI or API read surface | 🟢 Closed | `GET /audit/events` (admin-only) + Administration "Audit log" panel |
| APP-5 | Grafana reachable on default `admin`/`admin` | 🟢 Closed (code) / 🔴 **Open (this environment's `.env`)** | `docker-compose.yml` now requires `GF_ADMIN_PASSWORD`; this repo's own `.env` does not yet set it — see expanded SEC-1 above |
| APP-6 | Backup scripts reported success while silently failing the off-site upload | 🟢 Closed | Reproduced the failure on purpose (bad MinIO credential) — script now exits non-zero and raises a live `BackupFailed` Alertmanager alert |

## Application/Portal Security — Minor, non-blocking *(added Phase 22)*

| Gap ID | Description | Status | Notes |
|---|---|---|---|
| APP-MINOR-1 | Dashboard fails silently with no error banner when backend is unreachable (PORTAL-5) | 🔴 Open | UX polish; schedule, doesn't block any MW |
| APP-MINOR-2 | Fleet Management surfaces a raw `502` with no retry guidance (PORTAL-6) | 🔴 Open | UX polish |
| APP-MINOR-3 | DERMS form shows raw backend validation JSON inline (PORTAL-7) | 🔴 Open | UX polish |
| APP-MINOR-4 | Password-reset has no real email/SMS delivery — reset token is returned directly in the API response (lab-mode) | 🔴 Open (risk accepted as admin-assisted interim — see `GO_LIVE_AUTHORIZATION_PACKAGE.md`) | Treat reset as admin-assisted (`POST /auth/users` / `DELETE /auth/users/{username}`) until a real mailer is wired in; do not expose self-service reset to untrusted users before this is closed |

*Also noted, not separately tracked: all Phase 20/21 code (the entire APP-1→6 fix set) currently exists only as uncommitted changes in the working tree (`git status` confirms 13 modified + 12 new files, nothing committed). Recommend committing/merging before any MW1 preparation begins, so the fix set can't be lost or accidentally absent from a fresh deployment checkout.*

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

*SEC-6 and the Application/Portal (APP-1→6, APP-MINOR-1→4) items above are intentionally not in this gate — SEC-6 targets pre-Day-30, and the application track was validated/closed independently of the HA cutover. APP-5's `.env` gap is carried inside SEC-1 above, since both require the same `.env` edit + restart action.*

---

## Weekly Status Summary

*Complete this section at each Monday review.*

| Review Date | Items Closed This Week | Items Remaining | Blockers / Notes | Next Milestone |
|---|---|---|---|---|
| 2026-06-17 | 0 | 15 | Authorization pending | Board approval |
| 2026-06-17 (Phase 22 review, same day) | +6 (APP-1→6, application/portal track) | 15 MW1-gating SEC/INFRA/EMQX/MON items unchanged at 0 closed; +4 APP-MINOR items added (non-blocking); +1 new item (SEC-6) added | MW1 still **NOT** authorized — 0 of 11 MW1-gating items (SEC-1→6 minus SEC-6, MON-1→4, INFRA-2) closed. APP-5 reopened the `.env` question for SEC-1 (Grafana + engineer-role vars missing). Phase 20/21 code fixing APP-1→6 is uncommitted — recommend committing before MW1 prep. | Close SEC-1→5, MON-1→4, INFRA-2; see `PHASE22_GO_LIVE_READINESS_REPORT.md` |
| | | | | |
| | | | | |
| | | | | |

---

**Tracker prepared by:** DIEP Platform Engineering
**Source documents:** `PHASE18_PRODUCTION_GAP_ANALYSIS.md`, `PHASE18_GO_LIVE_RECOMMENDATION.md`, `DIEP_PRODUCTION_SECURITY_CHECKLIST.md`
**Date created:** 2026-06-17
**Phase 22 update sources:** `PRODUCTION_DEPLOYMENT_DECISION_v2.md`, `PHASE21_IMPLEMENTATION_REPORT.md`, `WEB_PORTAL_VALIDATION_REPORT_v2.md`, `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`, direct re-verification against current repo state (`git status`, `grep`, `.env` inspection)
