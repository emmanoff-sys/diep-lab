# DIEP Web Portal Validation Report (Phase 20, Part B)

**Date:** 2026-06-17
**Environment:** Isolated clone `~/deploy-validation/phase20-fresh-install`,
Compose project `diep-phase20`, continuation of Part A's fresh installation.
**Methodology:** Real headless Chromium (Playwright) driven against the live
`diep-portal` container, plus direct `curl`/`psql`/OpenAPI-schema inspection.
No production system was touched. See `WEB_PORTAL_VALIDATION_PLAN.md` for full
methodology.

## Summary

| # | Area | Result | Notes |
|---|------|--------|-------|
| 1 | Authentication | **FAIL** | None exists. Every page and API call is reachable by an anonymous browser. |
| 2 | Authorization | **FAIL** | All portal traffic is forwarded under one shared admin-scoped token; backend RBAC is bypassed. |
| 3 | Dashboard | PARTIAL | Renders correctly with live data; fails silently (no error shown) when backend is down. |
| 4 | Device inventory | PASS | Fleet Management table accurately reflects all 5 registered devices. |
| 5 | Telemetry views | PARTIAL | "Latest telemetry" surfaces per-device timestamps, but most devices showed `—` (no recent data) during this test. |
| 6 | DERMS controls | PASS | Real dispatch request submitted through UI → backend → live status update, verified end-to-end. |
| 7 | Reports | PASS | Rollup counts (devices, commands, DERMS, alarms) matched independently observed backend state. |
| 8 | Audit logs | **FAIL** | No UI screen, no API endpoint. Table exists and is populated but is operationally invisible. |
| 9 | Error handling | PARTIAL | 404 and form validation handled correctly; backend-down behavior is inconsistent across screens (see PORTAL-5/6). |
| 10 | Session management | N/A (FAIL by design) | No cookies, no localStorage, no sessionStorage — there is no session of any kind to manage. |

**Overall: NOT READY.** Two of ten areas are hard failures (Authentication,
Authorization), with a third (Audit logs) absent entirely. The functional
DERMS/Dashboard/Reports/Device-inventory paths all work correctly against a
real backend.

## Screens tested

| Screen | Route | Method |
|---|---|---|
| Dashboard | `/` | Playwright, fresh context, screenshot |
| Fleet Management | `/fleet` | Playwright, screenshot |
| DERMS | `/derms` | Playwright, form fill + submit (invalid then valid), screenshot |
| Administration | `/administration` | Playwright, screenshot |
| Reports | `/reports` | Playwright, screenshot |
| Alarms | `/alarms` | Playwright, screenshot |
| 404 route | `/this-route-does-not-exist` | Playwright, screenshot |
| Dashboard (backend down) | `/` | Playwright, `diep-fastapi` stopped, screenshot |
| Fleet Management (backend down) | `/fleet` | Playwright, `diep-fastapi` stopped, screenshot |

Not exercised: Digital Twins, AI Operations (visible in nav, outside the
10-area scope of this plan; not tested).

## API interactions observed

All browser-originated calls were proxied through the portal's BFF route
(`/api/diep/[...path]` → `http://diep-fastapi:8000`, `Authorization: Bearer
<DIEP_PORTAL_TOKEN>` attached server-side). Observed during UI testing:

- `GET /assets` (Fleet Management table)
- `GET /derms/requests` (DERMS request log, polls every 5s)
- `POST /derms/battery_dispatch` — first with `target_soc=150` → **422**
  `{"detail":[{"type":"less_than_equal","loc":["body","target_soc"],"msg":"Input
  should be less than or equal to 100", ...}]}`; then `target_soc=80` →
  accepted, request `212e279a-...` → `SENT`, later observed as `EXECUTED` in
  the polling request log.
- `GET /devices`, `GET /commands` — confirmed directly via `curl` against
  FastAPI (200, 46–53ms).
- `GET /assets` while `diep-fastapi` was stopped → portal BFF returned
  **502** `{"detail":"proxy error: TypeError: fetch failed"}`, surfaced
  verbatim in the Fleet Management UI.

Zero client-visible `Authorization` headers were observed in the browser's
own network traffic — the token never leaves the server side, consistent
with the BFF design.

## Browser compatibility

Only Chromium (via Playwright) was tested, on the validation host. No
Firefox/WebKit/Safari/mobile testing was performed — this is a scope
limitation of this validation pass, not a statement that other browsers work
or fail.

## Performance observations

All measurements taken on the single validation host (not a production-scale
or multi-user environment); treat as a sanity check, not a load test.

| Page/endpoint | HTTP status | Time |
|---|---|---|
| `/` (Dashboard) | 200 | 188ms |
| `/fleet` | 200 | 107ms |
| `/derms` | 200 | 123ms |
| `/administration` | 200 | 142ms |
| `/reports` | 200 | 68ms |
| `/alarms` | 200 | 43ms |
| `GET /devices` (FastAPI direct) | 200 | 53ms |
| `GET /derms/requests` (FastAPI direct) | 200 | 75ms |
| `GET /commands` (FastAPI direct) | 200 | 46ms |

No slow pages or timeouts observed. No load/concurrency testing was performed
(single browser, single user, single request at a time).

## Security observations

This is the most consequential part of this report.

1. **No authentication boundary exists.** A fresh, anonymous Chromium context
   loaded every tested page — including `/administration`, which can
   register new devices into the platform — at HTTP 200 with zero
   redirects, zero login prompts, and zero cookies set at any point.

2. **No authorization boundary exists.** The portal's BFF route handler
   (`portal/app/api/diep/[...path]/route.ts`) attaches one fixed,
   admin-scoped bearer token (`DIEP_PORTAL_TOKEN`, defaulting to the same
   value as `DIEP_ADMIN_KEY`) to every forwarded request, regardless of who
   is browsing. The route's own source comment acknowledges this directly:
   *"Production should replace this shared token with per-operator SSO/JWT
   via the /auth/token login flow."* The backend's RBAC model
   (`fastapi/auth.py`'s `API_KEYS` → `(principal, role)` and
   `require_role(*allowed)`) is real and functions correctly at the API
   layer — it is simply never exercised by the portal, since every portal
   action is performed as the same `api-admin`/`admin` identity.

3. **The audit trail cannot attribute actions to a human.** `audit_events`
   records `principal=api-operator` (or `api-admin`) for every action — the
   shared token identity, not a per-user identity — because there is no login
   step to capture one. A query against the live table during this test
   showed exactly the expected shape: one row, `principal=api-operator,
   role=operator, action=issue_command, resource=EV001:start_charging,
   result=ok`. Combined with finding #2, **any person with network access to
   the portal can issue DERMS commands or register devices, and the audit
   log will not distinguish them from any other anonymous user.**

4. **The audit trail itself is operationally invisible.** Despite the table
   being populated, there is no read API in the OpenAPI schema and no
   corresponding screen anywhere in the portal (`Reports`, `Administration`,
   and every other nav item were checked). An operator cannot answer "who did
   this?" through the product — only by querying Postgres directly, which is
   exactly what this validation had to do.

## Issues found

| ID | Severity | Issue | Evidence |
|---|---|---|---|
| PORTAL-1 | **Blocker / Security** | No authentication anywhere in the portal. | Fresh anonymous browser context reached every page (`/`, `/fleet`, `/derms`, `/administration`) at HTTP 200, zero cookies set. |
| PORTAL-2 | **Blocker / Security** | No authorization differentiation — all portal traffic is forwarded as one shared admin-scoped identity, bypassing the backend's real RBAC. | `portal/app/api/diep/[...path]/route.ts`: fixed `Authorization: Bearer ${TOKEN}` on every request, `TOKEN` defaults to the same value as `DIEP_ADMIN_KEY`. |
| PORTAL-3 | **Major / Security** | Audit log cannot attribute actions to an individual human; it only records the shared API-key identity. | Direct query of `audit_events`: `principal=api-operator` for a command issued through the (unauthenticated) portal/API. |
| PORTAL-4 | **Major** | No audit log UI or API — the `audit_events` table is operationally invisible to any portal user. | `grep -ril "audit"` across `app/`, `components/`, `lib/` → no hits; OpenAPI schema has zero audit-related paths. |
| PORTAL-5 | **Minor / UX** | Dashboard fails silently when the backend is unreachable — shows an all-zero, calm-looking state with infinite "Loading…" placeholders and no error indicator. | Screenshot with `diep-fastapi` stopped: Total assets/Healthy/Open alarms/Recommendations all show `0`, "Fleet map"/"Recent alarms"/"Top recommendations" stuck on "Loading…" with no banner. |
| PORTAL-6 | **Minor / UX** | Fleet Management surfaces a raw technical error (`GET /assets → 502`) with no retry action or operator guidance. | Screenshot with `diep-fastapi` stopped: red "Request failed / GET /assets → 502" box. |
| PORTAL-7 | **Minor / UX** | DERMS form surfaces the raw backend JSON validation error inline rather than a human-readable field-level message. | Screenshot: `POST /derms/battery_dispatch → 422: {"detail":[{"type":"less_than_equal",...}]}` rendered verbatim under the submit button. |
| PORTAL-8 | Informational | No session management exists in any form (no cookies, no localStorage, no sessionStorage) — consistent with, and a direct consequence of, PORTAL-1. | `ctx.cookies()`, `window.localStorage`, `window.sessionStorage` all empty across every tested page. |
| PORTAL-9 | Informational / scope | Only Chromium was tested; no cross-browser validation performed. | Methodology limitation, not a defect. |

## Positive findings

- The DERMS dispatch pathway works correctly end-to-end: UI → backend
  validation (rejects out-of-range input with a clear machine-readable 422)
  → accepted request → live status transition (`SENT` → `EXECUTED`) reflected
  in the UI's 5-second polling loop, with no manual refresh.
- Device inventory (Fleet Management) and Reports rollups both matched
  independently-observed backend state — no data-integrity or staleness
  issues found.
- 404 handling for unknown routes works correctly.
- All measured page/API response times were well under 200ms on this single
  host, with no errors or timeouts during normal operation.
- The BFF pattern correctly keeps the API token out of the browser — there is
  no *token leakage* problem, only a *token scoping/authentication* problem.

## Pass/Fail against plan criteria

| Area | Verdict |
|---|---|
| 1. Authentication | FAIL |
| 2. Authorization | FAIL |
| 3. Dashboard | PARTIAL |
| 4. Device inventory | PASS |
| 5. Telemetry views | PARTIAL |
| 6. DERMS controls | PASS |
| 7. Reports | PASS |
| 8. Audit logs | FAIL |
| 9. Error handling | PARTIAL |
| 10. Session management | FAIL (by design — none exists) |

**4 PASS/PARTIAL-functional areas, 3 outright FAIL areas, 3 PARTIAL areas
with real gaps.** Overall verdict for Part B: **NOT READY for production
exposure to untrusted or multi-tenant network access** in its current form.
The portal is functionally solid for the workflows it implements, but has no
access control whatsoever — a materially different (and more severe) risk
profile than anything found in Part A.
