# DIEP Go-Live Authorization Package

**Date:** 2026-06-17
**Decision requested:** Authorization to schedule **Maintenance Window 1** (K1 PITR + K4 Redis Sentinel).
**Prepared from:** `PHASE22_GO_LIVE_READINESS_REPORT.md` (full detail), `PRODUCTION_DEPLOYMENT_TRACKER.md` (live tracking), `PRODUCTION_DEPLOYMENT_DECISION_v2.md`, `DIEP_PRODUCTION_READINESS_CERTIFICATION.md`.

> **2026-06-17 update (same day, live verification pass):** the recommendation below was written from document/code review only ("0 of 11 closed"). A Docker-host issue blocking the stack was separately resolved and the full stack came up, enabling live verification. Result: **4 of 11 items are now 🟢 Closed (SEC-2, SEC-3, SEC-4, MON-2), 5 are 🟡 Partial for documented reasons (SEC-1, SEC-5, MON-1, MON-3, MON-4), 2 remain 🔴 Open (SEC-6, INFRA-2)**. The verification also found and fixed 5 real bugs not visible to static review — notably, Phase 21's portal-auth migration (`sql/012_users_rbac.sql`) had never been applied, so login was completely non-functional until this pass, and Grafana's `admin/admin` default still worked because the password rotation never reached the already-initialized volume. **The MW1 recommendation below is still NO-GO** — the items below "Must close before MW1" should be re-read against `MW1_VERIFICATION_REPORT.md`, not as still-all-untouched. Full detail in `MW1_VERIFICATION_REPORT.md` and the corresponding rows in `PRODUCTION_DEPLOYMENT_TRACKER.md`.

---

## Current Status

| Track | Verdict | Detail |
|---|---|---|
| HA cutover (Phase 17/18) | CONDITIONAL GO, **102/110**, 0/15 prerequisite items closed | All six HA designs (PITR, Patroni, KRaft Kafka, Redis Sentinel, MinIO EC:2, EMQX) validated in isolated test harnesses; none yet live in production compose |
| Application/Portal security (Phase 20/21) | NO-GO → **CONDITIONAL GO**, re-verified | Portal authentication, authorization, audit attribution, and backup-failure alerting all fixed and independently re-tested against a fresh deployment |
| **MW1 (this request)** | **NO-GO** | 0 of 11 gating items (SEC-1→5, MON-1→4, INFRA-2) closed |

**One package, two tracks, one decision today:** this package asks for a No-Go on MW1 scheduling, while separately recording that the application/portal NO-GO from Phase 20 is now resolved and can be signed off independently of the HA timeline.

---

## Remaining Risks

### Must close before MW1 (blocking)

| # | Item | Owner | Estimated effort |
|---|---|---|---|
| 1 | SEC-1: rotate 6 default secrets in `.env`; add `GF_ADMIN_PASSWORD` (now hard-required) and `DIEP_ENGINEER_PASSWORD` | Platform Eng / Ops | Hours |
| 2 | SEC-2: centralize Kafka SASL credential out of 4 hardcoded source locations | Platform Eng | Hours |
| 3 | SEC-3: enable Caddy TLS for API/Portal/Grafana (seam already exists, unused) | Platform Eng | Hours–1 day |
| 4 | SEC-4: restrict infra ports (Postgres/Redis/Kafka/MinIO) off `0.0.0.0` | Platform Eng | Hours |
| 5 | SEC-5: issue production EMQX admin credential | Ops / Security | Hours |
| 6 | MON-1→4: add the four missing Alertmanager rules (EMQX/Kafka/MinIO/Patroni health) | Ops | Hours–1 day |
| 7 | INFRA-2: static IP seeding for Redis Sentinel | Platform Eng | Hours, during MW1 pre-flight |
| 8 | Commit the uncommitted Phase 20/21 fix set | Platform Eng | Minutes — process hygiene, not engineering work |

Certification's own estimate for items 1–6 collectively: **1–2 days** of pre-cutover hardening work, no downtime required.

### Accepted / scheduled, not blocking MW1

| Risk | Disposition requested |
|---|---|
| Password reset has no real email/SMS delivery (token returned directly in API response) | **Accept** as admin-assisted interim (`POST /auth/users` / `DELETE /auth/users/{username}`); do not expose self-service reset to untrusted/external users until a mailer is integrated |
| MinIO backups stored unencrypted at rest | **Decide:** adopt SSE-KMS/client-side encryption (new tracker item SEC-6, target pre-Day-30) or formally accept |
| Dashboard/Fleet/DERMS raw-error UX (PORTAL-5/6/7) | **Accept**, schedule as routine UX cleanup |
| INFRA-1, INFRA-3, INFRA-4, EMQX-1/2 | Not due yet — gate MW1's own pre-flight, MW2, MW3, and MW5 respectively; no action needed today |

---

## Required Approvals

| Approval | Approver role | What they are approving |
|---|---|---|
| 1 | **Security Lead** | SEC-1→6 closure plan and evidence; the two accepted-risk items (password-reset delivery, backup encryption) |
| 2 | **Operations Lead** | MON-1→4 closure plan; updated `PRODUCTION_DEPLOYMENT_TRACKER.md`; MW1 runbook readiness (INFRA-2 pre-flight) |
| 3 | **Engineering Lead** | That the application/portal fix set (Phase 20/21) is committed/merged and matches what was validated; that no DERMS or HA-architecture changes were introduced as a side effect (confirmed in this review) |
| 4 | **Platform Engineering** | Technical execution owner for SEC-1→4, MON-1→4 |
| 5 | **Board / Executive sponsor** | Final Go/No-Go for MW1 scheduling, per the existing tracker's "Next Milestone: Board approval" entry |

No approval in this package authorizes MW2 through MW5 or Day-30 sign-off — those remain gated on their own prerequisites and on MW1's successful soak, per the existing certification sequencing.

---

## Go / No-Go Recommendation

### MW1 (K1 PITR + K4 Redis Sentinel): **NO-GO**

Do not schedule MW1 until all 11 items in "Must close before MW1" above reach 🟢 Closed in `PRODUCTION_DEPLOYMENT_TRACKER.md` with sign-off recorded. This is not a new finding — the tracker has stated this gate since Phase 18 — but this review independently re-confirmed that **zero** of the 11 items have moved, by inspecting the live `.env`, `docker-compose.yml`, and `prometheus/alerts.yml` directly rather than re-stating prior status.

### Application/Portal security (Phase 20/21 scope): **CONDITIONAL GO — recommend sign-off**

The portal's authentication, authorization, and audit gaps that produced the Phase 20 NO-GO are fixed and independently re-verified. Recommend the Security Lead and Operations Lead sign off on this track now, conditioned on: (a) committing the fix set to version control, (b) operating password reset as admin-assisted only until a real delivery channel exists, and (c) tracking the remaining Minor/UX items (PORTAL-5/6/7) as routine cleanup, not as conditions of this sign-off.

### Overall

**No production go-live action should proceed today.** The path to MW1 is short and well-defined (an estimated 1–2 days of configuration work, no application code changes, no further validation cycles needed) — this is a scheduling and execution gap, not a design or validation gap. Re-run this authorization review once the 11 blocking items show 🟢 Closed in the tracker.
