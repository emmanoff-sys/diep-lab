# DIEP Phase 22 — Production Go-Live Readiness Review

**Date:** 2026-06-17
**Objective:** Final readiness assessment before Maintenance Window 1 (MW1: K1 PITR + K4 Redis Sentinel).
**Method:** Document review of the five inputs below, cross-checked against the live repository state (`git status`, `grep`, `.env` inspection, `prometheus/alerts.yml`, `docker-compose.yml`) — assessment only, no code or configuration changes made.
**Inputs:** `PRODUCTION_DEPLOYMENT_DECISION_v2.md`, `PRODUCTION_DEPLOYMENT_TRACKER.md`, `PHASE21_IMPLEMENTATION_REPORT.md`, `WEB_PORTAL_VALIDATION_REPORT_v2.md`, `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`.

> **2026-06-17 update (same day):** this review's "0 of 11 closed" finding below was from static document/code review, by design (see Method above — no stack was running). Later the same day, a Docker-host issue was resolved (separately) and the stack came up, enabling actual live verification, documented in `MW1_VERIFICATION_REPORT.md`. That pass closed SEC-2, SEC-3, SEC-4, and MON-2; left SEC-1, SEC-5, MON-1, MON-3, MON-4 partial for documented reasons; and found 5 real bugs invisible to static review alone (Caddy not network-attached, a port collision with `diep-cadvisor`, a portal health-check hitting an auth-redirect path, a stale pre-rotation Grafana admin password, and a never-applied portal-auth DB migration that made Phase 21's login feature completely non-functional). **MW1 remains NO-GO** — read the open-blockers table below alongside that report, not as still fully untouched.

---

## Executive Summary

DIEP has two largely independent readiness tracks, and this review's main job is to stop them from being conflated:

1. **The HA-cutover track** (Phase 17/18, `DIEP_PRODUCTION_READINESS_CERTIFICATION.md` + `PRODUCTION_DEPLOYMENT_TRACKER.md`): six HA components (PITR, Patroni, Kafka KRaft, Redis Sentinel, MinIO EC:2, EMQX) are all individually **validated** (102/110, CONDITIONAL GO) but **none are yet live in the production-bound `docker-compose.yml`** — it still runs the single-instance pilot topology. Going live with HA requires 15 tracked prerequisite items (SEC-1→5, INFRA-1→4, EMQX-1→2, MON-1→4), of which **zero are closed**.
2. **The application/portal security track** (Phase 20/21): the portal had no authentication or authorization at all and backups were silently failing — a separate **NO-GO**. This has been fixed and **independently re-verified** against a fresh isolated deployment (real browser automation, not just code review): login is required everywhere, the backend's existing RBAC is finally reachable through the portal, the audit trail attributes actions to real users and is readable, and the backup scripts now fail loudly and alert instead of silently succeeding. New verdict: **CONDITIONAL GO**.

**Bottom line for MW1: NO-GO.** The application/portal fixes, while real and verified, do not touch any of the 11 items that the tracker's own gate requires before MW1 (SEC-1 through SEC-5, MON-1 through MON-4, INFRA-2) — all 11 remain open, confirmed by direct inspection of the current code and `.env`, not just by reading the tracker. MW1 should not be scheduled until those close.

Two additional findings surfaced by this review that weren't visible from any single input document:
- The entire Phase 20/21 fix set exists only as **uncommitted changes** in the working tree — nothing has been committed. A fresh checkout today would not include any of it.
- Phase 21's own code change (`docker-compose.yml` now requires `GF_ADMIN_PASSWORD` to start Grafana at all) is not yet reflected in this environment's actual `.env` — `docker compose up` would fail on the Grafana service today. This is folded into SEC-1 rather than tracked separately, since it's the same class of action (edit `.env`, restart).

---

## 1. Review of remaining open blockers

### From the HA-cutover tracker (unchanged status, re-confirmed by direct inspection)

| ID | Status (confirmed) | How confirmed |
|---|---|---|
| SEC-1 (password rotation) | 🔴 Open | `.env` still has `DIEP_ADMIN_PASSWORD=change-me-admin-password`, `DIEP_OPERATOR_PASSWORD=change-me-operator-password`, `DIEP_VIEWER_PASSWORD=change-me-viewer-password`, `DB_PASSWORD=diep123` |
| SEC-2 (Kafka SASL hardcoded) | 🔴 Open | `grep -rn "diep-kafka-pass"` returns 4 hits: `docker-compose.yml` (×2), `dispatcher/command_dispatcher.py`, `fastapi/app.py` |
| SEC-3 (Caddy TLS) | 🔴 Open | `caddy/Caddyfile` exists but no `caddy:` service block in `docker-compose.yml` — not wired in |
| SEC-4 (port bindings) | 🔴 Open | `5432:5432`, `6379:6379`, `9092:9092`, `9000:9000` all present in unqualified (`0.0.0.0`-binding) short syntax |
| SEC-5 (EMQX admin credential) | 🔴 Open | Production EMQX isn't in `docker-compose.yml` yet; credential rotation is sequenced into the pre-MW1 security sprint per the certification |
| INFRA-1→4 | 🔴 Open | No `redis-replica`, `sentinel`, `patroni`, second/third Kafka broker, or MinIO HA pool present in `docker-compose.yml` — HA topology not yet cut over |
| EMQX-1, EMQX-2 | 🔴 Open | Gate MW5, not MW1; no production EMQX service exists yet to apply them to |
| MON-1→4 | 🔴 Open | `prometheus/alerts.yml` inspected directly — none of the four alerts (EMQX node count, Kafka broker count, MinIO disk count, Patroni health) exist; only generic `KafkaOutage`/`DatabaseOutage`/host alerts are present |

### From the application/portal track (Phase 20 → 21, now closed, re-verified)

| ID | Status | Evidence |
|---|---|---|
| PORTAL-1/2 (no auth/authz) | 🟢 Closed | Anonymous browser redirected to `/login` on every route; per-user JWT now forwarded to the backend; real 403s observed for under-privileged roles |
| PORTAL-3/4 (audit attribution/read surface) | 🟢 Closed | Audit rows attributed to real users; `GET /audit/events` + UI panel, admin-only |
| INSTALL-2 (Grafana default creds) | 🟢 Closed *(code)* | `admin:admin` confirmed rejected (401) against the fixed code in an isolated test deployment |
| INSTALL-3 (silent backup failure) | 🟢 Closed | Deliberately broken MinIO credentials → script now exits 1 and raises a live Alertmanager `BackupFailed` alert |

### New, discovered during this review (not previously tracked)

| Finding | Severity | Detail |
|---|---|---|
| This repo's `.env` lacks `GF_ADMIN_PASSWORD` | Blocking for *any* `docker compose up`, not just MW1 | Phase 21's `docker-compose.yml` change makes this a hard requirement (`${GF_ADMIN_PASSWORD:?...}`); the actual `.env` predates that change |
| This repo's `.env` lacks `DIEP_ENGINEER_PASSWORD` | Non-blocking (falls back to a documented lab default; only matters if the `engineer` role is to be used in this environment) | Same root cause as above |
| Phase 20/21 fix set is entirely uncommitted | Process risk, recommend treating as blocking before MW1 prep | `git status` shows 13 modified + 12 new files, 0 commits |
| Backup-at-rest encryption (MinIO) was identified in the certification (§6.3 item 6) but never given a tracked ID | Non-blocking for MW1, recommend closing before Day-30 | Added to tracker as **SEC-6** in this review |

---

## 2. Categorization

### Blocking (must close before MW1 is scheduled)

- SEC-1 — rotate the 6 original secrets **and** set `GF_ADMIN_PASSWORD` (+ `DIEP_ENGINEER_PASSWORD` if the engineer role is in use); remove the now-dead `DIEP_PORTAL_TOKEN` line
- SEC-2 — centralize Kafka SASL credential
- SEC-3 — enable Caddy TLS for API/Portal/Grafana
- SEC-4 — restrict infra port bindings to internal-only
- SEC-5 — issue production EMQX admin credential
- MON-1, MON-2, MON-3, MON-4 — add the four missing Alertmanager rules
- INFRA-2 — static IP seeding for Redis Sentinel (MW1's own scope)
- **Process item:** commit the Phase 20/21 fix set before any MW1 preparation work begins, so it cannot be silently absent from whatever checkout MW1 is executed against

### Non-blocking (track, schedule, but does not gate MW1)

- INFRA-1 (WAL chown) — performed as the first pre-flight step *inside* MW1's own runbook, not a precondition to scheduling it
- INFRA-3 (MinIO bucket mirror) — gates MW2
- INFRA-4 (Kafka CLUSTER_ID) — gates MW3
- EMQX-1, EMQX-2 — gate MW5
- SEC-6 (backup-at-rest encryption) — target before Day-30, not MW1
- APP-MINOR-1/2/3 (PORTAL-5/6/7 — dashboard silent failure, raw 502, raw validation JSON) — UX polish, not access-control
- APP-MINOR-4 (password-reset has no real email delivery) — acceptable as an admin-assisted interim; must close before exposing self-service reset to untrusted/external users
- INSTALL-1, INSTALL-4, INSTALL-5 (documentation gaps: Alertmanager SMTP vars, hardcoded dev path, undocumented DERMS device-type defaults)

### Post-Go-Live (Year-1 roadmap, per the certification's Section 13)

- Kubernetes migration (CNPG, Strimzi, Bitnami Redis, MinIO Operator, EMQX Operator)
- Multi-AZ anti-affinity, PodDisruptionBudgets
- Chaos testing / scheduled fault-injection drills; re-injection of the Kafka checkpoint-corruption scenario against the production 3-broker cluster
- SLO definition and burn-rate alerting
- Kafka SASL_SSL transport upgrade (beyond SASL_PLAINTEXT)
- OTA firmware pipeline, bulk device-onboarding automation
- IEC 62443 gap assessment; SOC2 Type I preparation
- Multi-tenancy DERMS endpoint tenant-scoping; dedicated `/derms/ev_charging` endpoint
- Multi-site field pilot (30–60 days)

---

## 3. Verification by area

| Area | Verdict | Basis |
|---|---|---|
| **Security** | Partially ready | Application-layer access control (auth/authz/audit) is now solid (Phase 21, re-verified). Infrastructure-layer security is not: 5 of the original tracker's security items remain open (default secrets, hardcoded Kafka SASL credential, no TLS on API/Portal/Grafana, infra ports on `0.0.0.0`, EMQX credential), all independently re-confirmed in this review, not merely re-stated from prior docs. |
| **Operations** | Mostly ready, one new documentation gap | Runbook coverage is comprehensive per the certification (fresh deploy, PKI bootstrap, backup, PITR restore, all 6 HA components' failover/rollback procedures). New gap: the Phase 21 admin-assisted password-reset interim procedure and the `BackupFailed` Alertmanager alert are not yet written into `DIEP_OPERATIONS_MANUAL.md` — only into the Phase 21 report and the scripts' own comments. |
| **Monitoring** | Not ready for MW1 | Baseline alerting (host, API, generic Kafka/DB outage) is solid and pre-existing. MON-1 through MON-4 — the four alerts the tracker itself requires before MW1 — are confirmed absent from `prometheus/alerts.yml`. |
| **Backup/Restore** | Ready | K1 PITR validated; `verify-backup.sh` restore drill validated (Phase 20); `backup-db.sh`/`backup-config.sh` silent-failure bug fixed and the fix verified against both a successful run (correct dynamic network detection) and a deliberately-broken one (loud failure + live alert). INFRA-3 (mirroring backups to the future HA MinIO cluster) remains open but only matters once MW2 happens. |
| **HA Components** | Validated, not yet live | All six K1–K6 stages individually PASS in isolated test harnesses. None are present in the production-bound `docker-compose.yml` today — confirmed by grep (no `redis-replica`, `sentinel`, `patroni`, multi-broker Kafka, or MinIO HA pool). The platform is currently still running the original single-instance, all-SPOF pilot topology. |
| **Portal** | Ready | Authentication, authorization, session management, and the new 4-role model (viewer/operator/engineer/admin) all verified end-to-end against a real browser session in a fresh deployment. Minor UX issues (PORTAL-5/6/7) remain, explicitly non-blocking. |
| **DERMS** | Ready | Functionally unchanged by Phase 21 (explicitly out of scope, per rule). End-to-end dispatch flow re-verified under a real per-user `operator` session instead of the old shared admin token; EMQX round-trip separately validated in K5. |
| **Audit Logging** | Ready | Per-request correlation (`X-Request-ID`), site attribution, human-attributable principal, and an admin-only read UI/API all verified populated and correct in a live test session. |

---

## 4. Final Readiness Score

**102/110** — unchanged from the Phase 17 certification baseline.

This number deliberately does **not** move as a result of Phase 21. The certification's Security category (16/20) was capped specifically by SEC-1 through SEC-5, all of which remain open today — re-confirmed directly in this review, not assumed. The portal access-control gap that Phase 20 found and Phase 21 closed was never part of this scoring basis in the first place (it was discovered after the certification was written), so closing it is necessary but cannot, by itself, raise a score that was never measuring it. Put plainly: **fixing the portal does not unlock the HA score** — they are different gates.

**Target after closure:** 108/110 — unconditional GO — reached only once SEC-1→5 and MON-1→4 (and INFRA-1→4/EMQX-1→2 in their respective windows) are closed, per the existing tracker target.

---

## 5. Open Risks

| Risk | Category | Recommended disposition |
|---|---|---|
| 5 infrastructure security gaps open (SEC-1→5) | Blocking | Close before MW1; ~1–2 days per the certification's own Phase 1 estimate |
| 4 monitoring gaps open (MON-1→4) | Blocking | Close before MW1; alert-rule authoring + test-fire, no infra change required |
| HA components validated but not live | Blocking (for the HA program, not for today's pilot operation) | Proceed through MW1→MW5 per the existing, sound sequencing — no redesign needed |
| Phase 20/21 fix set uncommitted | Process | Commit/merge before MW1 prep; otherwise a fresh checkout silently reverts to the NO-GO portal state |
| This `.env` missing `GF_ADMIN_PASSWORD` | Blocking for any deploy, not just MW1 | One-line `.env` addition; fold into SEC-1 closure |
| Password reset has no real delivery channel | Accepted-risk candidate | Operate as admin-assisted only until a mailer is integrated; do not expose self-service reset externally before then |
| Backup-at-rest unencrypted (MinIO) | Accepted-risk candidate or scheduled work | No tracked owner/date today; now added as SEC-6, target pre-Day-30 |
| PORTAL-5/6/7 UX gaps | Low / accepted | Schedule as routine cleanup |

---

## 6. Maintenance Window Readiness

| Window | Scope | Readiness |
|---|---|---|
| **MW1** | K1 PITR + K4 Redis Sentinel | **NOT READY.** 0 of 11 gating items (SEC-1→5, MON-1→4, INFRA-2) closed. |
| MW2 | K6 MinIO HA | Not yet applicable — sequenced after MW1 + 48h soak. Plan and rollback procedure are sound; no changes needed to the plan itself. |
| MW3 | K3 Kafka HA | Not yet applicable — sequenced after MW2 + 24h soak + INFRA-4. |
| MW4 | K2 Patroni HA | Not yet applicable — sequenced after MW3 + 24h soak + INFRA-3. |
| MW5 | K5 EMQX HA | Not yet applicable — sequenced after MW4 + 48h soak + EMQX-1/2. |

The six-stage rollout sequencing (K1 → K4 → K6 → K3 → K2 → K5) and the per-window rollback procedures documented in the certification remain sound and require no rework as a result of this review.

---

## 7. Day-30 Readiness

Not yet assessable on the merits — D0 (MW1 execution) has not occurred, so the D0–D30 timeline in `PHASE18_GO_LIVE_RECOMMENDATION.md` has not started. The 10 Day-30 checkpoint criteria (all six HA components live; zero rollback incidents; weekly backup verification passing; PITR RPO ≤65s confirmed; zero Kafka message loss over 30 days; monthly Sentinel failover drill passed; MinIO 4/4 disks online; EMQX 3/3 nodes healthy; MON-1→4 alerts tested and routing; full security checklist signed off) are unchanged and require no redefinition. Two of the ten (MON-1→4 routing test, and indirectly the security checklist, which includes SEC-1→5) cannot even be attempted until MW1 closes the items in Section 2 above.

---

## 8. Recommendation feeding into the authorization package

MW1 should remain **NO-GO** until the 11 blocking items in Section 2 are closed. The application/portal security track is a genuine, separately-verified accomplishment and should be recorded as closed in its own right — it is a prerequisite for *exposing the portal* to real operators, independent of the HA cutover timeline, and should not be held hostage to MW1's schedule or vice versa. See `GO_LIVE_AUTHORIZATION_PACKAGE.md` for the formal Go/No-Go statement and required approvals.
