# DIEP Phase 21 — Portal Security & Production Hardening: Remediation Plan

**Date:** 2026-06-17
**Inputs:** `WEB_PORTAL_VALIDATION_REPORT.md`, `PRODUCTION_DEPLOYMENT_DECISION.md`,
`DIEP_PRODUCTION_READINESS_CERTIFICATION.md`, `PRODUCTION_INSTALLATION_VALIDATION_REPORT.md`.
**Objective:** resolve the findings that produced the Phase 20 **NO-GO**: PORTAL-1,
PORTAL-2, PORTAL-3, PORTAL-4, INSTALL-2, INSTALL-3. Per the governing rules: fix
only these findings, do not redesign DERMS, preserve existing HTTP APIs, preserve
the existing HA architecture (no new services/topologies).

## 1. Assessment — what already exists vs. what is missing

The backend (`fastapi/auth.py`, added in the Phase 9J security pass) already has a
real, mostly-complete RBAC/JWT layer: HS256 JWT issuance (`/auth/token`,
`/auth/refresh`), an `API_KEYS` map for machine clients, a `USERS` map for human
logins (admin/operator/viewer/+2 tenant demo accounts), `require_role()`,
`rate_limit()`, and an `audit()` writer into `audit_events`. **None of this is
exercised by the portal.** The portal's BFF (`portal/app/api/diep/[...path]/route.ts`)
ignores all of it and forwards every browser request under one fixed,
admin-scoped `DIEP_PORTAL_TOKEN` — this is PORTAL-1/PORTAL-2's root cause, and the
route's own comment already names the correct fix ("per-operator SSO/JWT via the
/auth/token login flow"). So Part A of this phase is primarily **portal-side**
wiring of an already-built backend capability, not inventing auth from scratch.

What genuinely needs to be built:
- A login UI, session cookie handling, and route protection in the portal (none
  exists today).
- A 4th role, `engineer`, in the backend's role hierarchy (today it's
  `viewer < operator < admin`, plus `service` for machines).
- Real logout (today JWTs are stateless with no revocation) and a password-reset
  flow (today passwords are fixed env-var values with no DB-backed, mutable
  credential store).
- Audit log read surface (PORTAL-4) and richer attribution: per-request
  correlation ID and site, neither of which `audit_events` captures today.
- The backup scripts' silent-failure bug (INSTALL-3) and Grafana's wide-open
  defaults (INSTALL-2).

## 2. Design decisions

### A. Authentication
- **Credential store:** add `portal_users` table (`sql/012_users_rbac.sql`),
  columns `username, password_hash, role, tenant, token_version,
  must_change_password, created_at, updated_at`. Passwords hashed with PBKDF2-HMAC-SHA256
  (stdlib `hashlib.pbkdf2_hmac` — `auth.py`'s docstring already commits to
  "dependency-free", no new pip package). On first use, the table is lazily
  seeded from the existing env-var-derived accounts (`DIEP_ADMIN_PASSWORD`, etc.)
  so the documented lab credentials keep working, but passwords become
  runtime-mutable (required for reset).
- **Login page:** `portal/app/login/page.tsx`. Posts to a new portal route
  `portal/app/api/auth/login/route.ts`, which calls FastAPI `/auth/token`
  server-side and, on success, sets the access + refresh JWTs as **HttpOnly**
  cookies (never readable by browser JS — avoids introducing an XSS token-theft
  surface) plus one small non-HttpOnly `diep_role` cookie purely for client-side
  nav rendering (the real enforcement stays server-side).
- **Session management:** `portal/middleware.ts` gates every route except
  `/login`, `/forgot-password`, `/reset-password`, static assets, and the new
  unauthenticated auth API routes — redirects to `/login` if no valid session
  cookie. The BFF (`route.ts`) is rewritten to forward the **caller's own**
  access-token cookie as the `Authorization` header instead of the fixed admin
  token; on a 401 (expired access token) it transparently refreshes once using
  the refresh cookie before failing.
- **Logout:** `POST /auth/logout` (new FastAPI endpoint) revokes the presented
  JWT's `jti` in Redis (`revoked:{jti}`, TTL = remaining token life) — real
  server-side revocation, not just "client forgets the cookie". Portal route
  `/api/auth/logout` calls it, then clears cookies.
- **Password reset:** `POST /auth/password-reset/request` (rate-limited, public)
  issues a 15-minute-TTL single-purpose JWT; `POST /auth/password-reset/confirm`
  verifies it, writes the new PBKDF2 hash, and bumps `token_version` (which
  invalidates every outstanding access/refresh token for that user — a real
  "log out everywhere" side effect, not just a changed password). **Known,
  documented limitation:** this stack has no outbound email/SMS service, so —
  exactly like the existing Alertmanager receivers, which point at
  `*.invalid` placeholder webhook URLs pending a real integration — the reset
  token is returned directly in the API response rather than emailed. This is
  flagged explicitly in the implementation report as a pre-production gap, not
  hidden.

### B. Authorization — RBAC
- Roles become `viewer < operator < engineer < admin` (`service` unchanged,
  machine-only). `engineer` is a superset of `operator`+`viewer` permissions,
  modeling "can do day-to-day ops AND device/config work, but not user
  management or final compliance sign-off."
- Endpoint changes are **additive only** (no existing allowed-role is removed):
  `POST /assets` and onboarding `enroll`/`validate` now also accept `engineer`;
  onboarding `certify`/`approve` (compliance gate) stay `admin`-only by design.
- New admin-only user-management endpoints: `POST /auth/users` (create),
  `GET /auth/users` (list, no hashes returned), `DELETE /auth/users/{username}`
  (blocked from removing the last remaining admin, to prevent lockout). Needed
  because a 4-role model is only real if an Administrator can actually place
  people into the other 3 roles at runtime, not just via 5 hardcoded demo
  accounts.
- Portal: nav items and the Administration page's register-asset form/Users tab
  are hidden for `viewer`/`operator` (UX-level gating); the actual enforcement
  remains FastAPI's `require_role()`, which the portal now finally reaches
  per-user instead of bypassing.

### C. Audit logging
- `sql/012_users_rbac.sql` also adds two nullable columns to `audit_events`:
  `request_id` and `site` (additive migration, no existing column changes — old
  rows just have them NULL).
- A lightweight ASGI middleware in `app.py` generates/propagates `X-Request-ID`
  per inbound request via a `contextvars.ContextVar`; `auth.audit()` reads it
  automatically, so **no existing `audit()` call site needs to change its
  signature** to get correlation — only call sites that can cheaply supply
  `site=`/`device_id=` are touched, additively.
- New read endpoint `GET /audit/events` (admin-only; paginated; filters by
  `principal`, `action`, `since`) — closes PORTAL-4 (no UI/API surface). Portal
  gets a read-only "Audit log" panel on the Administration page, admin-only.

### D. Backup verification
Root cause of INSTALL-3 confirmed by reading `scripts/backup-db.sh` /
`backup-config.sh`: the upload step is one `docker run ... -c "A && B && C || true"`
shell chain. Bash's `&&`/`||` are equal-precedence, left-associative, so the
trailing `|| true` (meant only to tolerate "no objects matched the retention
prune") actually swallows a failure **anywhere** in the chain — including
`mc alias set` and the `mc cp` upload itself — making the whole `docker run`
always exit 0. Combined with a hardcoded `DIEP_NET` default
(`diep-lab_diep-net`) that's wrong for any clone whose directory/Compose-project
isn't named exactly `diep-lab`, this is the documented "looks healthy, isn't"
failure mode. Fix, in both scripts:
1. Derive the network name from the running `diep-minio` container
   (`docker inspect`) instead of guessing a fixed Compose-project name, falling
   back to the old default only if inspection fails.
2. Split the upload chain from the prune step into two separate `docker run`
   invocations, so the prune's intentional `|| true` can never mask an upload
   failure — the upload `docker run`'s own exit code now propagates to the
   script's `set -e`.
3. Add a **positive confirmation** step: after upload, `mc stat` the just-uploaded
   object in the bucket and compare its reported size to the local file's size;
   non-match or missing object is a hard failure.
4. On any failure, in addition to the script exiting non-zero (so cron's
   existing log-capture already shows it), POST a `critical`-severity alert to
   Alertmanager's own API (`/api/v2/alerts`) — reusing the routing tree that
   already exists in `alertmanager/alertmanager.yml` rather than adding a new
   notification path.

### E. Grafana hardening
`docker-compose.yml`'s `grafana` service today has no `environment:`/`env_file`
block at all, so the image's built-in `admin`/`admin` default is always live.
Fix: add `env_file: .env` + `GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD`
sourced from new `.env.example` variables (`GF_ADMIN_USER`, `GF_ADMIN_PASSWORD`,
required — Compose's `${VAR:?...}` syntax fails the `up` command loudly if
unset, rather than silently defaulting). Document the rotation process (change
`.env`, `docker compose up -d grafana` to recreate) in the installation guide.

## 3. Explicitly out of scope (per the governing rules)
DERMS endpoints/business logic are untouched beyond the additive `engineer` role
check on asset/onboarding endpoints already covered by existing tests. No new
services, databases, or message brokers are introduced — Postgres, Redis, and
Alertmanager are all already part of the architecture and are reused, not added.
No HA topology changes. Existing HTTP API contracts (request/response shapes)
for every pre-existing endpoint are unchanged; all changes are new endpoints or
additive optional fields.

## 4. Files expected to change
`fastapi/auth.py`, `fastapi/app.py`, `sql/012_users_rbac.sql` (new),
`scripts/backup-db.sh`, `scripts/backup-config.sh`, `docker-compose.yml`
(grafana service only), `.env.example`, `portal/middleware.ts` (new),
`portal/app/login/page.tsx` (new), `portal/app/forgot-password/page.tsx` (new),
`portal/app/reset-password/page.tsx` (new), `portal/app/api/auth/*` (new),
`portal/app/api/diep/[...path]/route.ts`, `portal/components/Sidebar.tsx`,
`portal/app/administration/page.tsx`, `DIEP_INSTALLATION_GUIDE.md` (Grafana var
documentation).

## 5. Re-validation plan
After implementation: fresh isolated clone (new throwaway directory + Compose
project, same methodology as Phase 20 Part A/B), real Playwright-driven retest
of all 10 Part B areas plus the new login/logout/reset/RBAC/audit-UI flows,
producing `WEB_PORTAL_VALIDATION_REPORT_v2.md`, then `PRODUCTION_DEPLOYMENT_DECISION_v2.md`.
