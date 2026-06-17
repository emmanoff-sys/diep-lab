# DIEP Phase 21 — Production Deployment Decision v2

**Date:** 2026-06-17
**Inputs:** `PRODUCTION_DEPLOYMENT_DECISION.md` (Phase 20, NO-GO),
`PHASE21_REMEDIATION_PLAN.md`, `PHASE21_IMPLEMENTATION_REPORT.md`,
`WEB_PORTAL_VALIDATION_REPORT_v2.md` — all produced from real, hands-on
execution against a second fresh, isolated clone, independent of the one
used in Phase 20 (which was torn down before this phase began).

## Recommendation: **CONDITIONAL GO**

The access-control gap that drove the Phase 20 **NO-GO** is closed and
independently re-verified: the portal now requires per-user login, the
backend's existing RBAC is actually enforced through it instead of bypassed,
the audit trail attributes actions to real principals and is readable, and
session lifecycle (logout, password reset) works end-to-end including
server-side token revocation. The two installation-time blockers (Grafana
default credentials, silently-failing backups) are also fixed and
independently re-verified. This is no longer a recommendation against
deploying — it is a recommendation to deploy **once the remaining items
below are completed**, none of which touch the access-control surface that
was the prior blocker.

## What changed since the Phase 20 NO-GO

| Phase 20 finding | Severity | Status now | Evidence |
|---|---|---|---|
| PORTAL-1: no authentication | Blocker/Security | **Fixed** | Anonymous context redirected to `/login` on every route (`WEB_PORTAL_VALIDATION_REPORT_v2.md`). |
| PORTAL-2: no authorization (shared admin token) | Blocker/Security | **Fixed** | BFF forwards per-user JWT; backend `require_role()` independently confirmed denying/allowing per role through the portal itself. |
| PORTAL-3: audit can't attribute to a human | Major/Security | **Fixed** | Audit rows now show real usernames/roles (`admin`, `viewer`, `operator`, ...), not the shared API-key identity. |
| PORTAL-4: no audit UI/API | Major | **Fixed** | `GET /audit/events` + Administration "Audit log" panel, admin-only. |
| INSTALL-2: Grafana default admin/admin | Blocker/Security | **Fixed** | `admin:admin` now returns 401; the configured credential is required to start the container at all. |
| INSTALL-3: backups silently fail | Blocker | **Fixed** | Reproduced the failure on purpose (bad MinIO credentials) — script now exits non-zero and raises a `BackupFailed` alert in Alertmanager, instead of reporting success. |

## Remaining items (not blockers, but required before declaring full Go)

These are pre-existing, lower-severity findings that this phase's rules
("fix only the NO-GO findings") deliberately left untouched:

1. **PORTAL-5/6/7 (Minor/UX):** Dashboard still fails silently when the
   backend is down; Fleet Management surfaces a raw 502; DERMS shows raw
   validation JSON. Cosmetic/UX, not access-control — schedule, don't block on.
2. **INSTALL-1/4/5 (documentation gaps):** Alertmanager's 5 SMTP env vars and
   the 4-of-5-disabled-by-default DERMS device types remain undocumented in
   the installation guide; `rebuild_flows.py` still has a hardcoded developer
   path. None of these affect the access-control surface.
3. **Password reset delivery is still lab-mode:** the reset token is returned
   directly in the API response because this stack has no outbound email/SMS
   integration. This must be replaced with a real mailer before exposing
   self-service password reset to real, untrusted users — until then, treat
   password reset as an **admin-assisted** flow only (an admin can also just
   use the new `POST /auth/users` + `DELETE /auth/users/{username}` to
   rotate an account directly).
4. **Existing deployments' `.env` files must add two new variables**
   (`GF_ADMIN_PASSWORD`, and `DIEP_ENGINEER_PASSWORD` if the engineer role is
   to be used) before their next `docker compose up` — `GF_ADMIN_PASSWORD`
   is now a hard requirement and Grafana will refuse to start without it.
   This was deliberately left for the operator to do (this phase did not
   modify any live `.env`).

## Why CONDITIONAL rather than unconditional GO

Two things keep this from being an unconditional Go:
- Item 3 above (password reset has no real delivery channel yet) is a
  genuine pre-production gap for any deployment with real, untrusted users
  self-resetting passwords — administrator-driven account management is the
  safe interim path.
- This phase's re-validation, like Phase 20's, was performed by one agent on
  one host, with Chromium as the only browser and no concurrent-user load
  testing. That scope limitation (already flagged as PORTAL-9 in Phase 20)
  still applies.

Neither of these is an access-control hole — they are operational maturity
items appropriate to close out before wide rollout, not before any
deployment at all.

## What does not need further change

mTLS enforcement, the DERMS command round-trip, TimescaleDB
initialization/retention, and `verify-backup.sh`'s restore drill were already
confirmed working in Phase 20 and were not touched by this phase. The portal's
BFF pattern (token never reaching the browser) continues to hold — Phase 21
strengthened it (per-user token instead of a shared one) without changing
that property.
