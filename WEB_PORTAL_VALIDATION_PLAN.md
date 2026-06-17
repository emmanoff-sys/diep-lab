# DIEP Web Portal Validation Plan (Phase 20, Part B)

## Objective

Validate that the DIEP Operations Portal (Next.js, `diep-portal`) can be operated
exactly as it would be in production, against the fresh installation produced in
Part A of this phase. This is a validation-only exercise: no production system,
infrastructure, or codebase is modified as part of this plan.

## Scope

Continuation of the same isolated environment used in Part A
(`~/deploy-validation/phase20-fresh-install`, Compose project `diep-phase20`,
throwaway `.env` credentials). No new environment is created for Part B.

## Areas to validate

1. Authentication — is there a login boundary, and what protects it?
2. Authorization — are operator vs. admin actions enforced differently in the UI?
3. Dashboard — does the landing page render real platform state?
4. Device inventory — Fleet Management screen against the 5 registered devices.
5. Telemetry views — any live/near-live device data surfaced in the UI.
6. DERMS controls — submit a real dispatch request through the UI, both invalid
   and valid input, and confirm it reaches the backend and is reflected back.
7. Reports — rollup screen correctness against actual backend state.
8. Audit logs — is there a UI (or API) surface for the `audit_events` table.
9. Error handling — client-side validation, 404 routing, and backend-down
   behavior (simulated by stopping `diep-fastapi` in the isolated environment only).
10. Session management — cookies, `localStorage`, `sessionStorage` across page loads.

Browser compatibility and performance are recorded as secondary observations
(single browser engine, single host — see Report for caveats).

## Methodology

The validation host has no browser installed and the task requires genuine
hands-on UI testing rather than API-only inference. Playwright + Chromium is
installed live inside the running `diep-portal` container (`npm install
playwright --no-save` + `npx playwright install --with-deps chromium`), scoped
entirely to this throwaway container — not added to the DIEP image or repo.
Because `portal` bind-mounts `./portal:/app`, test scripts and screenshots
written to `/app` land on the host for inspection.

Concretely:
- Drive a real headless Chromium browser against `http://localhost:3000`
  (the portal's own internal port, reached from inside the container).
- Use a fresh, cookie-less browser context for each test to detect any
  session/identity artifacts honestly (no pre-seeded state).
- Capture full-page screenshots at each step and inspect them directly.
- Inspect network requests for client-visible `Authorization` headers.
- Cross-check UI behavior against the FastAPI OpenAPI schema and, where
  relevant, the underlying Postgres tables (e.g. `audit_events`) reached via
  `psql` directly — not just what the UI claims.
- For the backend-down scenario: `docker stop diep-fastapi` in the isolated
  environment only, observe the portal, then `docker start diep-fastapi` and
  confirm recovery before continuing.
- For performance: `curl -w` timing against portal pages and proxied API
  routes on the host-mapped port.

## Rules (carried forward from Part A)

No production modifications. No infrastructure changes beyond the already-isolated
validation environment. Validation only. Record every issue discovered.

## Deliverable

`WEB_PORTAL_VALIDATION_REPORT.md`, covering: screens tested, API interactions
observed, browser compatibility, performance observations, and security
observations — followed by `PRODUCTION_DEPLOYMENT_DECISION.md` synthesizing
this report with Part A's installation report.
