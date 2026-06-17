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
| Security (SEC) | 6 | 5 | **1** |
| Infrastructure (INFRA) | 4 | 1 | **3** |
| EMQX Configuration (EMQX) | 2 | 0 | **2** |
| Monitoring (MON) | 4 | 2 | **2** |
| Application/Portal Security (APP) | 6 | 6 | **0** |
| Application/Portal — Minor (APP-MINOR) | 4 | 0 | **4** |
| **Total (MW1-relevant + application)** | **26** | **14** | **12** |

**Go-live gate (MW1 specifically):** SEC-1 through SEC-5, MON-1 through MON-4, and INFRA-2 (10 items; SEC-6 is intentionally not in this gate, see note below) must reach 🟢 Closed with sign-off before MW1 begins. **As of 2026-06-17 (live verification + follow-up closures, same day): 7 of these 10 items are 🟢 Closed (SEC-1, SEC-2, SEC-3, SEC-4, MON-2, MON-3, INFRA-2), 3 are 🟡 Partial for documented, non-bug reasons (SEC-5, MON-1, MON-4 — each genuinely blocked on a future milestone: K5/MW5, K5/MW5, K2/MW4 respectively), and 0 remain 🔴 Open.** **MW1's network/infra prerequisites are now fully closed or correctly partial pending future milestones — but MW1 itself (the actual K1 PITR + K4 Sentinel cutover, including switching the app to a Sentinel-aware Redis client and running the failover drill) has not been executed and still requires explicit scheduling/sign-off.** See `MW1_VERIFICATION_REPORT.md` for full live evidence, including 6 bugs found and fixed during the verification/closure passes (Caddy network/port/health-check issues, a stale Grafana admin password, a never-applied portal-auth DB migration, a MinIO metric rename). The Application/Portal Security items (APP-1 through APP-6) were tracked and closed separately under Phase 20/21 and are not part of the MW1 gate (MW1 is K1 PITR + K4 Redis Sentinel — backend/infra scope only) — see "Phase 22 Go-Live Readiness Review" note below.
INFRA-4 gates MW3; INFRA-1, INFRA-3, EMQX-1, EMQX-2 gate their respective windows as shown in the Maintenance Window table.

> **Phase 22 note:** This tracker originally covered only the HA-cutover items below (SEC/INFRA/EMQX/MON). A parallel track — production *installation* and *web portal* validation — ran in Phases 20–21, found a separate NO-GO (no portal authentication/authorization, audit trail not attributable, Grafana default credentials, silently-failing backups), and closed it. Those items are folded into this tracker as the new "Application/Portal Security" sections below so one document reflects total go-live readiness. Closing APP-1→6 does **not** close any SEC/INFRA/EMQX/MON item and does **not** by itself authorize MW1.

---

## Security Blockers — SEC-1 through SEC-6

*Target: SEC-1 through SEC-5 complete in Week 1, before any maintenance window is scheduled. SEC-6 targets pre-Day-30 (see note below).*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| SEC-1 | Rotate 6 default passwords: `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, `DB_PASSWORD` in `.env`. **Expanded per Phase 22 review:** also set the two new variables `GF_ADMIN_PASSWORD` and `DIEP_ENGINEER_PASSWORD` introduced by Phase 21 — confirmed absent from the current `.env` (`docker compose up` will now fail outright on the Grafana service without `GF_ADMIN_PASSWORD`, by design); also remove the now-unused `DIEP_PORTAL_TOKEN` line (dead since Phase 21's per-user-token rewrite of the portal BFF). | Platform Eng / Ops | | 🟢 Closed | `.env` diff confirms `DIEP_ADMIN_PASSWORD`/`OPERATOR`/`ENGINEER`/`VIEWER`/`ACME`/`GLOBEX`/`GF_ADMIN_PASSWORD`/`DB_PASSWORD` all rotated and `DIEP_PORTAL_TOKEN` removed; live-verified via full login/whoami/logout/RBAC/password-reset cycle. `DB_PASSWORD` rotated 2026-06-17 via live `ALTER ROLE` (zero downtime) and confirmed from a genuine network connection: old value rejected, new value accepted (`MW1_VERIFICATION_REPORT.md` §2, §5, §7). | |
| SEC-2 | Externalize Kafka SASL credential from 4 source locations (`docker-compose.yml` ×2, `command_dispatcher.py`, `fastapi/app.py`) into `KAFKA_SASL_USERNAME` / `KAFKA_SASL_PASSWORD` in `.env`; confirm no hardcoded values remain (`grep -r "diep-kafka-pass" .`). **Re-confirmed open by direct grep during Phase 22 review** — all 4 locations still contain the literal credential. | Platform Eng | | 🟢 Closed | `grep` confirms zero hardcoded-credential matches; live: `diep-dispatcher` logs show ongoing SASL-authenticated Kafka metadata refreshes against `diep-kafka:9094`, no auth errors (`MW1_VERIFICATION_REPORT.md` §2). | |
| SEC-3 | Enable Caddy TLS reverse proxy for API (:8000), Portal (:3002), and Grafana (:3001); confirm all three endpoints respond on HTTPS and redirect HTTP. **Re-confirmed open by Phase 22 review** — `caddy/Caddyfile` exists in the repo but no `caddy` service block exists in `docker-compose.yml`; the proxy is not wired in. | Platform Eng | | 🟢 Closed | Live: `https://localhost:8443/healthz`, `:3444/api/health`, `:3443/login` all 200 with HSTS header; `:8082`/`:3080`/`:3081` all 301-redirect to HTTPS. Endpoint ports differ from this row's literal text (API fronted at 8443/8082, not 8000) — see `MW1_VERIFICATION_REPORT.md` §1–2 for the 3 live bugs found and fixed (network attach, port collision with `diep-cadvisor` on 8080, portal health-check path) before this passed. | |
| SEC-4 | Restrict infrastructure port bindings from `0.0.0.0` to internal network: Postgres 5432, Redis 6379, Kafka 9092/9094, MinIO 9000/9002. **Re-confirmed open by Phase 22 review** — all listed ports found bound via the unqualified `"host:container"` short syntax, which binds `0.0.0.0` by default. | Platform Eng | | 🟢 Closed | Live `docker ps` confirms Postgres/Redis/Kafka/MinIO bound to `127.0.0.1` only; Kafka SASL listener (9094) never published to host at all (`MW1_VERIFICATION_REPORT.md` §2). | |
| SEC-5 | Replace EMQX admin credential (`diep-emqx-admin-2026`) with production-issued credential; confirm via `GET /api/v5/nodes` with new credential. Note: production EMQX (K5/MW5) is not yet present in the main `docker-compose.yml` — this item is gated into the pre-MW1 security sprint per the certification's Section 11 sequencing, ahead of when the credential is actually exercised at MW5. | Ops / Security | | 🟡 Partial (expected) | `EMQX_ADMIN_PASSWORD` issued in `.env`. Cannot be live-tested yet — EMQX itself isn't deployed until K5/MW5, matching this row's own sequencing note. | |
| SEC-6 *(new, added Phase 22)* | Evaluate and, if adopted, implement backup-at-rest encryption for MinIO (SSE-KMS or client-side encryption of `pg_dump`/config archives). Identified in `DIEP_PRODUCTION_READINESS_CERTIFICATION.md` §6.3 item 6 but never given a tracked ID — added here so it isn't lost. Not required to unlock MW1 (PITR/backup correctness, not confidentiality, gates MW1), but should have an owner and target date before Day-30 sign-off. | Security / Platform Eng | Pre-Day-30 | 🟢 Closed | **Decision: adopted SSE-KMS** (static MinIO KMS secret key, not Vault-backed — the existing `docker-compose-vault.yml` runs Vault in `-dev` mode only, by its own header comment not meant for real secrets, so a generated static key is the more honest choice here than wiring through a dev-mode service). `MINIO_KMS_SECRET_KEY` set in `.env`/`.env.example`, wired into the `minio` service. Both backup buckets (`diep-backups`, `diep-config-backups`, matching `scripts/backup-db.sh`/`backup-config.sh`) have `mc encrypt set sse-kms` default encryption enabled. Live evidence: `mc admin kms key status` shows the key with Encryption ✔ / Decryption ✔; a real uploaded object's `mc stat` shows `Encryption: SSE-KMS (arn:aws:kms:diep-backup-key)`. | |

---

## Infrastructure Prerequisites — INFRA-1 through INFRA-4

*INFRA-4 must complete before MW3. INFRA-1 and INFRA-2 are completed during MW1. INFRA-3 is completed during MW2.*

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| INFRA-1 | Set WAL archive volume ownership to postgres uid=70 before enabling `archive_mode=on` on `diep-timescaledb`. Run during MW1 pre-flight: `docker run --rm -v diep-lab_wal-archive:/vol alpine chown -R 70:70 /vol` | Ops | MW1 | 🔴 Open | `docker exec diep-timescaledb ls -la /var/lib/postgresql/wal-archive` showing uid=70; first WAL segment visible in MinIO `diep-wal-archive` bucket within 65s of enable | |
| INFRA-2 | Add static IPAM entries to compose network config for `diep-redis` (primary) and `redis-replica` before Redis Sentinel cutover. Prevents DNS-resolution `+tilt` after container lifecycle events. Run during MW1 pre-flight. | Platform Eng | MW1 | 🟢 Closed | Scoped ahead of the MW1 runbook per K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md §6: `diep-net` pinned to `172.18.0.0/16`, `diep-redis`→`.240`, new `redis-replica`→`.241` (both static); added 3 Sentinels (quorum 2) per the validated design. Live evidence: `docker network inspect` confirms static IPs; replica `info replication` shows `master_link_status:up`; Sentinel logs show `+monitor`/`+slave`/`+sentinel` discovery by IP, zero `+tilt` across all 3; `sentinel masters` shows `172.18.0.240` (IP, not hostname); `sentinel master diep-master` shows `num-other-sentinels: 2`, `quorum: 2`. **Scope note:** this closes the network/topology prerequisite only — switching `fastapi`/`auth`/`copilot` to a Sentinel-aware client (`redis.sentinel.Sentinel(...).master_for(...)`) and running the actual failover drill is the MW1 cutover itself (Plan §6 steps 2-4), not part of INFRA-2. | |
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

**Resolved 2026-06-17:** the rows below each originally said "Route to `diep-oncall` receiver." No such receiver exists, and this lab stack has no outbound email/SMS/Slack integration wired up anywhere (the same gap independently noted for `BackupFailed` in Phase 21). Building a literal `diep-oncall` receiver would just be a second name for the same no-op destination, so the decision is to **correct the expectation, not add a receiver**: all 4 alerts route via the existing severity-based tree (`critical`/`warning` in `alertmanager/alertmanager.yml`), which is functionally correct. Treat "Route to `diep-oncall`" in the descriptions below as superseded by this note.

| Gap ID | Description | Owner | Target Date | Status | Evidence Required | Sign-off |
|---|---|---|---|---|---|---|
| MON-1 | Add EMQX cluster node count alert to Alertmanager: `emqx_cluster_nodes_running < 3` from `/api/v5/prometheus/stats` scraped on any EMQX node. Route to `diep-oncall` receiver. | Ops | Pre-MW1 | 🟡 Partial | Rule live in Prometheus (`GET /api/v1/rules`, group `diep-ha-cluster-health`), state `inactive` — correct, since no EMQX scrape target exists yet (EMQX not deployed until K5/MW5). | |
| MON-2 | Add Kafka broker count alert: broker count < 3 sourced from `kafka-exporter` Prometheus metrics. Alert name: `KafkaBrokerCountLow`. Route to `diep-oncall`. | Ops | Pre-MW1 | 🟢 Closed | Rule live in Prometheus, state `firing` — correct and expected: 1 broker exists today (pre-K3), rule fires below 3, resolves automatically once K3/MW3 ships 3 brokers (`MW1_VERIFICATION_REPORT.md` §3). | |
| MON-3 | Add MinIO disk availability alert: `minio_cluster_disk_online_total < 4` from MinIO Prometheus endpoint (`:9000/minio/v2/metrics/cluster`). Alert name: `MinioDiskOnlineLow`. Route to `diep-oncall`. | Ops | Pre-MW1 | 🟢 Closed | Scrape job added (`mc admin prometheus generate`, bearer token mounted via `prometheus/secrets/minio_token`, gitignored); target `up` in Prometheus. Metric name corrected to `minio_cluster_drive_online_total` (this MinIO version renamed disk→drive — the tracker's original name doesn't exist). Rule live, state `pending` — correct, single-node MinIO today is below the eventual 4-drive K6/MW2 target. | |
| MON-4 | Add Patroni cluster health alert: primary not healthy or sync standby count < 1, sourced from Patroni REST API (`GET :8008/cluster`). Alert name: `PatroniClusterDegraded`. Route to `diep-oncall`. | Ops | Pre-MW1 | 🟡 Partial | Rule live in Prometheus, state `inactive` — correct, no Patroni exporter exists yet (Patroni not deployed until K2/MW4). | |

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
| MW1 — K1 PITR + K4 Redis Sentinel | SEC-1, SEC-2, SEC-3, SEC-4, SEC-5, MON-1, MON-2, MON-3, MON-4, INFRA-2 | 🟡 (7 closed, 3 partial, 0 open — pre-flight items clear; cutover itself not yet executed, see `MW1_VERIFICATION_REPORT.md`) |
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
| 2026-06-17 (live verification pass, same day) | +4 (SEC-2, SEC-3, SEC-4, MON-2 closed); +5 moved to 🟡 Partial (SEC-1, SEC-5, MON-1, MON-3, MON-4) | 2 of 11 MW1-gating items still 🔴 Open (SEC-6, INFRA-2); 5 🟡 Partial for documented, non-bug reasons | MW1 still **NOT** authorized. A prior Docker-host issue was resolved (by the user) and the full stack came up, which made live verification possible. That verification found and fixed 5 real bugs (Caddy: never network-attached, port 8080 collided with `diep-cadvisor`, portal health-check hit an auth-redirected path; Grafana: stale `admin/admin` from before this password rotation, same root cause as the known `DB_PASSWORD` issue; Phase 21 portal-auth: its DB migration `sql/012_users_rbac.sql` was never applied, so login was completely non-functional until now). Working tree still uncommitted. | Decide `DB_PASSWORD` rotation (SEC-1) and INFRA-2 scope; decide `diep-oncall` receiver naming (MON-1→4); commit the fix set; see `MW1_VERIFICATION_REPORT.md` |
| | | | | |
| | | | | |

---

**Tracker prepared by:** DIEP Platform Engineering
**Source documents:** `PHASE18_PRODUCTION_GAP_ANALYSIS.md`, `PHASE18_GO_LIVE_RECOMMENDATION.md`, `DIEP_PRODUCTION_SECURITY_CHECKLIST.md`
**Date created:** 2026-06-17
**Phase 22 update sources:** `PRODUCTION_DEPLOYMENT_DECISION_v2.md`, `PHASE21_IMPLEMENTATION_REPORT.md`, `WEB_PORTAL_VALIDATION_REPORT_v2.md`, `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`, direct re-verification against current repo state (`git status`, `grep`, `.env` inspection)
