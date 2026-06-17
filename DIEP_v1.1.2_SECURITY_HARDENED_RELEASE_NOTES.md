# DIEP Release Notes — v1.1.2-security-hardened

**Date:** 2026-06-17
**Tag:** `v1.1.2-security-hardened`
**Commit:** `267a7fe` — "Implement Phase 21 portal authentication, RBAC, audit logging and backup hardening"
**Status:** Conditional GO

---

## 1. Summary

This release incorporates the complete Phase 21 security remediation work
identified during Phase 20 production validation. Phase 20's production
installation and web-portal validation found that the Operations Portal had
no authentication or authorization of any kind, that the audit trail could
not attribute actions to a human operator, that backups could silently fail
while reporting success, and that Grafana shipped reachable on its default
credentials — a **NO-GO** for production deployment. Phase 21 designed and
implemented fixes for every one of those findings; this release packages
that work.

All claims below were independently re-verified against a fresh, isolated
deployment using real browser automation and real failure injection (not
code review alone) before this tag was cut — see Validation.

---

## 2. Major changes

- **Portal authentication** — login page, session cookies (HttpOnly JWTs),
  and a Next.js middleware gate that redirects every unauthenticated request
  to `/login`. No page is reachable anonymously.
- **JWT-backed session management** — access/refresh token pair issued at
  login; server-side logout revocation (Redis `jti` blacklist) so a
  logged-out token can't be replayed.
- **RBAC enforcement** — the portal's backend-for-frontend now forwards each
  signed-in user's own token to the API instead of one shared admin-scoped
  credential, so the backend's existing role checks (`require_role()`)
  finally apply per user.
- **Engineer role introduced** — new 4-tier role hierarchy
  `viewer < operator < engineer < admin`; `engineer` gains asset
  registration and onboarding enroll/validate permissions previously
  admin-only.
- **Password reset workflow** — self-service request/confirm flow; a
  successful reset invalidates all of that user's other outstanding
  sessions. (Known limitation: no real email/SMS delivery yet — see §5.)
- **Audit logging attribution** — every audited action now records the real
  signed-in principal and role, not a shared API-key identity; a new
  admin-only `GET /audit/events` endpoint and Administration-page panel
  make the trail readable for the first time.
- **Request correlation support** — every HTTP request is stamped with an
  `X-Request-ID`, automatically attached to any audit row it produces.
- **Backup verification and alerting improved** — `backup-db.sh` /
  `backup-config.sh` now autodetect the correct Docker network, positively
  confirm the uploaded object's size against the local file, and raise a
  live `critical`-severity Alertmanager alert on failure instead of
  silently exiting 0.
- **Grafana credential hardening** — the default `admin`/`admin` login is
  gone; `docker-compose.yml` now requires `GF_ADMIN_PASSWORD` to be set,
  failing the `up` command loudly if it isn't.

---

## 3. Issues closed

| Phase 20 NO-GO finding | Resolution |
|---|---|
| Missing portal authentication | Login required on every route (middleware + session cookies) |
| Missing authorization | Per-user token forwarding restores real backend RBAC enforcement |
| Unattributed audit events | Audit rows now show the real principal/role; readable via UI/API |
| Silent backup upload failure | Loud failure + live alert on any upload/verification error |
| Grafana default credentials | `GF_ADMIN_PASSWORD` required; default login rejected |

---

## 4. Validation

- `WEB_PORTAL_VALIDATION_REPORT_v2.md` — full 10-area portal re-validation
  against a fresh isolated deployment (real Chromium/Playwright sessions):
  anonymous redirect-to-login on every route, per-role nav/route gating,
  real backend 403s through the portal itself, logout token revocation,
  full password-reset self-service loop, populated and attributed audit
  log.
- `PRODUCTION_DEPLOYMENT_DECISION_v2.md` — synthesizes the above with the
  backup/Grafana fixes into the release's Go/No-Go determination.
- `PHASE21_IMPLEMENTATION_REPORT.md` — implementation detail and
  command-level evidence (curl transcripts, deliberate failure injection)
  for every change in §2.

---

## 5. Known limitations carried into this release

1. **Password reset has no real delivery channel** — the reset token is
   returned directly in the API response rather than emailed/texted, since
   this stack has no outbound mail integration yet. Operate password reset
   as **admin-assisted** (`POST /auth/users`, `DELETE /auth/users/{username}`)
   until a real mailer is wired in; do not expose self-service reset to
   untrusted/external users before then.
2. **Minor portal UX gaps unchanged from Phase 20** (tracked as
   APP-MINOR-1→3 / PORTAL-5/6/7): the Dashboard fails silently rather than
   showing an error banner when the backend is unreachable; Fleet
   Management surfaces a raw `502`; the DERMS form shows raw validation
   JSON inline. None are access-control issues.
3. **This release does not touch the HA-cutover or infrastructure-security
   track** (Kafka SASL credential centralization, Caddy TLS, infra port
   bindings, secret rotation, EMQX hardening, the four missing Alertmanager
   cluster-health rules). Those remain open and gate Maintenance Window 1
   independently of this release — see §6.

---

## 6. Status and next milestone

**Status: Conditional GO** — the application/portal security track is
closed and re-verified. This does **not** by itself authorize Maintenance
Window 1; MW1 (K1 PITR + K4 Redis Sentinel) is gated on a separate set of
infrastructure items.

**Next milestone: MW1 blocker closure** — `SEC-1` through `SEC-6`, `MON-1`
through `MON-4`, and `INFRA-2` must reach 🟢 Closed in
`PRODUCTION_DEPLOYMENT_TRACKER.md` before MW1 can be scheduled. See
`PHASE22_GO_LIVE_READINESS_REPORT.md` and `GO_LIVE_AUTHORIZATION_PACKAGE.md`
for the full readiness review and required approvals.

---

## 7. Related documents

| Document | Purpose |
|---|---|
| [`PHASE21_REMEDIATION_PLAN.md`](PHASE21_REMEDIATION_PLAN.md) | Design decisions and scoping for this release's fixes |
| [`PHASE21_IMPLEMENTATION_REPORT.md`](PHASE21_IMPLEMENTATION_REPORT.md) | Implementation detail and verification evidence |
| [`WEB_PORTAL_VALIDATION_REPORT_v2.md`](WEB_PORTAL_VALIDATION_REPORT_v2.md) | Post-fix portal re-validation |
| [`PRODUCTION_DEPLOYMENT_DECISION_v2.md`](PRODUCTION_DEPLOYMENT_DECISION_v2.md) | Go/No-Go determination for this release |
| [`PRODUCTION_DEPLOYMENT_TRACKER.md`](PRODUCTION_DEPLOYMENT_TRACKER.md) | Live blocker-closure dashboard, including this release's items (APP-1→6) |
| [`PHASE22_GO_LIVE_READINESS_REPORT.md`](PHASE22_GO_LIVE_READINESS_REPORT.md) | Combined HA + application readiness review ahead of MW1 |
| [`GO_LIVE_AUTHORIZATION_PACKAGE.md`](GO_LIVE_AUTHORIZATION_PACKAGE.md) | Sign-off package and required approvals for MW1 |
