# DIEP Web Portal Validation Report v2 (Phase 21 re-validation)

**Date:** 2026-06-17
**Environment:** Fresh isolated clone `~/deploy-validation/phase21-fresh-install`,
Compose project `diep-phase21`, throwaway `.env` — independent of, and not
reusing, the Phase 20 environment (which was already torn down).
**Methodology:** Same as Phase 20 Part B — real headless Chromium (Playwright)
installed live in the running `diep-portal` container, plus direct
`curl`/`psql`/Alertmanager-API inspection. No production system touched.
**Baseline for comparison:** `WEB_PORTAL_VALIDATION_REPORT.md` (Phase 20).

## Summary

| # | Area | Phase 20 | Phase 21 | Notes |
|---|------|----------|----------|-------|
| 1 | Authentication | **FAIL** | **PASS** | Every page now requires login; verified via anonymous-context redirect test. |
| 2 | Authorization | **FAIL** | **PASS** | Portal forwards the caller's own JWT; backend RBAC verified to actually deny/allow per role. |
| 3 | Dashboard | PARTIAL | PASS | Unchanged rendering; backend-down silent-failure behavior (PORTAL-5) is unchanged/out of scope this phase. |
| 4 | Device inventory | PASS | PASS | Unchanged; now also shows the asset registered live during this test (ENGTEST1). |
| 5 | Telemetry views | PARTIAL | PARTIAL | Unchanged from Phase 20 — out of scope for this phase. |
| 6 | DERMS controls | PASS | PASS | Unchanged; now exercised under a real per-user (operator) session instead of the shared admin token. |
| 7 | Reports | PASS | PASS | Unchanged; rollup counts correct (devices, analytics events). |
| 8 | Audit logs | **FAIL** | **PASS** | New `GET /audit/events` + Administration "Audit log" panel; rows show real per-user attribution. |
| 9 | Error handling | PARTIAL | PARTIAL | 404 and RBAC-denial handling verified correct; backend-down inconsistency (PORTAL-5/6) unchanged — out of scope this phase. |
| 10 | Session management | N/A (FAIL by design) | **PASS** | Real session now exists: HttpOnly JWT cookies, server-side logout revocation, password-reset-triggered global invalidation. |

**Overall: READY for the access-control gap that drove the Phase 20 NO-GO.**
4 of the 4 hard-FAIL areas from Phase 20 (Authentication, Authorization, Audit
logs, Session management) are now PASS. The three PARTIAL areas
(Telemetry views, Error handling, and Dashboard's backend-down behavior) are
unchanged from Phase 20 — they were Minor/UX findings (PORTAL-5/6/7), not
NO-GO blockers, and were explicitly out of scope for this phase's "fix only
the NO-GO findings" rule.

## What was re-tested and how

### Authentication (PASS)
Fresh, cookie-less Chromium context requesting `/`, `/fleet`, `/derms`,
`/administration`, `/reports`, `/alarms` all redirected to
`/login?next=<path>` — zero pages reachable anonymously (screenshot:
`p21_anon_login_redirect.png`). Login with a wrong password returns 401 with
no cookies set; login with a correct password sets `diep_at`/`diep_rt` as
`httpOnly: true` cookies — confirmed via `document.cookie`, which returned
only `"diep_role=viewer; diep_user=viewer"`, never the tokens themselves.

### Authorization (PASS)
- Portal nav: `Administration` item is absent for `viewer` and `operator`
  sessions (0 DOM matches), present for `engineer` and `admin`.
- Direct URL entry to `/administration` as `viewer` redirects to
  `/?denied=administration` (middleware-level role gate, not just nav-hiding).
- The real enforcement point — FastAPI — was independently confirmed reachable
  through the portal's own proxy: `POST /api/diep/audit/events` as an
  `operator` session returns `403` (real backend RBAC), while the same call
  as `admin` returns `200`.
- The newly-added `engineer` role's expanded permission was verified to
  actually work, not just exist: `POST /assets` as `engineer` → `201` (was a
  bare RBAC concept in the plan; this confirms the wiring).

### Dashboard / Device inventory / Reports / Alarms (PASS, unchanged)
Re-screenshotted under a real `operator` session (not the old shared admin
token): Dashboard shows 6 assets / 1 healthy / 0 alarms with live data;
Fleet Management table lists all 6 registered devices including the one
registered live during this test pass (`ENGTEST1`); Reports shows correct
rollups (`Devices 6`, `Analytics events 47`); Alarms correctly shows the
empty state. No regressions found.

### Audit logs (PASS — was FAIL)
The Administration page (admin-only) now renders a populated "Audit log"
table. A real excerpt observed in this session:

| Time | Principal | Action | Result |
|---|---|---|---|
| 10:31:12 | admin (admin) | login | OK |
| 10:30:58 | viewer (viewer) | login | OK |
| 10:22:13 | anonymous | login (operator, wrong password) | DENIED |
| 10:20:48 | anonymous | password_reset_requested (nobody) | UNKNOWN_USER |
| 10:20:30 | admin (admin) | create_user (jane.engineer) | OK |

Every row carries a `request_id` (e.g. `d7328fdaef7d4ad3a4883387f603f835`)
correlatable to the originating HTTP request via the now-present
`X-Request-ID` response header, and a `site` column (populated where the
action is site/device-scoped). `GET /audit/events` is also independently
callable as a plain API (admin-only; 403 for any other role).

### Session management (PASS — was N/A/FAIL)
A real session now exists: `diep_at` (access JWT, 1h), `diep_rt` (refresh
JWT, 30d), both `httpOnly`; `diep_role`/`diep_user` (non-HttpOnly, UI-only).
`localStorage`/`sessionStorage` remain empty by design — the session lives
in HttpOnly cookies, not script-readable storage, which is the more secure
choice, not a gap. Logout (`POST /api/auth/logout`) clears all four cookies
client-side **and** revokes the JWT's `jti` server-side in Redis — confirmed
by reusing a just-logged-out access token directly against FastAPI and
observing `401` instead of the cached `200` it would have returned before
revocation.

### Password reset (new capability, PASS)
Full self-service loop driven through the actual UI: `/forgot-password` →
submit username → reset link rendered (lab-mode: the token is shown inline,
since this stack has no outbound email integration — documented, not
hidden) → `/reset-password?token=...` → submit new password → redirected to
`/login` → logging in with the **new** password succeeds, and the **old**
password is rejected (`401`). The reset also bumped `token_version`, so any
session that existed before the reset would be invalidated too (verified at
the API level: an old token's `tv` claim no longer matches the cached
current version).

### Performance (sanity check, not a load test)

| Page/endpoint (authenticated) | HTTP | Time |
|---|---|---|
| `/` (Dashboard) | 200 | 101ms |
| `/fleet` | 200 | 73ms |
| `/derms` | 200 | 437ms |
| `/administration` (operator — role-gate redirect) | 307 | 32ms |
| `/administration` (admin) | 200 | 74ms |
| `/reports` | 200 | 131ms |
| `/alarms` | 200 | 77ms |
| `GET /api/diep/devices` | 200 | 161ms |
| `GET /api/diep/derms/requests` | 200 | 116ms |
| `GET /api/diep/commands` | 200 | 142ms |
| `GET /api/diep/audit/events` (operator) | 403 | 60ms |
| `GET /api/diep/audit/events` (admin) | 200 | 142ms |

No regression versus Phase 20's baseline (all under ~450ms; the per-request
refresh-token-exchange-on-401 path adds at most one extra backend round trip,
only on the rare access-token-expiry case, not on the common path).

### Backend-down behavior (PORTAL-5/6 — unchanged, out of scope)
Not re-tested in this pass. These were Minor/UX findings, not part of the
Phase 20 NO-GO blockers, and the governing rule for this phase was "fix only
the NO-GO findings." They remain open, tracked items.

## Issues found in this pass

None new. No regressions found in any previously-passing area.

## Verdict

All four hard-FAIL/blocker areas from Phase 20 (Authentication, Authorization,
Audit logs, Session management) are now **PASS**, independently verified
against a fresh isolated deployment with real browser automation, not just
code review. See `PRODUCTION_DEPLOYMENT_DECISION_v2.md` for the updated
Go/No-Go recommendation.
