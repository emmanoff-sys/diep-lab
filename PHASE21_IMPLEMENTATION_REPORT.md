# DIEP Phase 21 — Portal Security & Production Hardening: Implementation Report

**Date:** 2026-06-17
**Plan:** `PHASE21_REMEDIATION_PLAN.md`
**Scope:** PORTAL-1, PORTAL-2, PORTAL-3, PORTAL-4 (Phase 20 blockers), INSTALL-2,
INSTALL-3 (Phase 20 blockers). No DERMS redesign, no existing HTTP API contract
changes, no HA topology changes — all changes below are new endpoints/files or
additive fields.

All claims in this report were verified by deploying the changed code to a
fresh, isolated clone (`~/deploy-validation/phase21-fresh-install`, Compose
project `diep-phase21`, throwaway `.env`) and exercising it with real `curl`
requests, real `docker exec`/`docker logs`, and a real headless-Chromium
Playwright session against the live portal — the same methodology as Phase 20
Parts A/B. Nothing below is asserted from reading the code alone.

## A. Authentication

**Backend** (`fastapi/auth.py`, `fastapi/app.py`): added a DB-backed
`portal_users` table (`sql/012_users_rbac.sql`), PBKDF2-HMAC-SHA256 password
hashing (stdlib `hashlib.pbkdf2_hmac`, 200k iterations — no new dependency,
consistent with `auth.py`'s existing "dependency-free" design), and:
- `POST /auth/logout` — revokes the presented JWT's `jti` in Redis
  (`revoked:{jti}`), so a logged-out token is rejected on reuse, not just
  forgotten client-side.
- `POST /auth/password-reset/request` / `POST /auth/password-reset/confirm` —
  15-minute single-use reset tokens; confirming a reset bumps the user's
  `token_version`, which invalidates every other outstanding access/refresh
  token for that account (a real "log out everywhere" side effect).

**Verified:**
```
POST /auth/logout         -> {"status":"logged_out","revoked":true}
GET  /auth/whoami (old token) -> 401  (revocation confirmed)
POST /auth/password-reset/request {"username":"viewer"} -> 202 + reset_token
POST /auth/password-reset/confirm {reset_token, new_password} -> {"status":"password_updated"}
POST /auth/token (old password)  -> 401
POST /auth/token (new password)  -> 200, tv:1 in the issued JWT
POST /auth/password-reset/request x6 in <5min -> 4th request onward: 429
```
**Known, documented limitation:** this stack has no outbound email/SMS
integration, so the reset token is returned directly in the API response
rather than delivered out-of-band — exactly the same kind of placeholder the
codebase already has for ops alerting (Alertmanager's SMTP-template
receivers). This must be replaced with a real mailer before production;
flagged again under "Required before next Go" in the v2 decision doc.

**Portal**: new `portal/middleware.ts` (redirects any unauthenticated request
to `/login`), `portal/app/login/page.tsx`, `forgot-password/page.tsx`,
`reset-password/page.tsx`, and route handlers under `portal/app/api/auth/*`
that call FastAPI server-side and set the access/refresh JWTs as **HttpOnly**
cookies (`diep_at`, `diep_rt`) plus a non-HttpOnly `diep_role`/`diep_user` pair
used only for UI rendering.

**Verified (Playwright, fresh anonymous context):**
- Anonymous requests to `/`, `/fleet`, `/derms`, `/administration`, `/reports`,
  `/alarms` all redirect to `/login?next=...` — zero pages reachable without
  signing in (this is the direct fix for PORTAL-1).
- `document.cookie` after login as `viewer` returns only
  `"diep_role=viewer; diep_user=viewer"` — the session JWTs are confirmed
  `httpOnly: true` and never visible to page JavaScript.
- Clicking "Sign out" clears all four cookies and redirects to `/login`.
- Full self-service password-reset loop driven through the actual UI
  (forgot-password → reset-password → login with the new password) completed
  successfully end-to-end.

## B. Authorization (RBAC)

Roles are now `viewer < operator < engineer < admin` (`service` unchanged,
machine-only) in `auth.py`'s `_role_allowed()`. `POST /assets` and the
onboarding `enroll`/`validate` steps now also accept `engineer`
(certify/approve remain admin-only — the compliance gate is unchanged).

The portal's BFF (`portal/app/api/diep/[...path]/route.ts`) was rewritten:
it no longer attaches a fixed `DIEP_PORTAL_TOKEN` to every request. It now
forwards the logged-in caller's own access-token cookie, and on a 401
transparently exchanges the refresh-token cookie for a new access token once
before failing. This is the direct fix for PORTAL-2 — FastAPI's real
`require_role()` now actually executes per logged-in user.

**Verified:**
```
viewer  -> POST /assets (admin/engineer-only)  -> 403 "role 'viewer' not permitted..."
engineer -> POST /assets                       -> 201 (newly-granted permission works)
operator -> portal nav: Administration item absent (0 matches)
viewer  -> direct navigation to /administration -> redirected to /?denied=administration
admin   -> portal nav: Administration item present; page renders Users + Audit panels
```
Admin-only user management was added (`POST/GET /auth/users`,
`DELETE /auth/users/{username}`, with a guard against deleting the last
remaining admin) so the 4-role model is actually usable at runtime, not just
5 hardcoded demo accounts — exposed in the portal's Administration page as a
new "Users" panel (create/list/remove), visible only to `admin`.

## C. Audit logging

`audit_events` gained two additive, nullable columns (`site`, `request_id` —
`sql/012_users_rbac.sql`). A new ASGI middleware (`auth.RequestIDMiddleware`,
registered in `app.py`) stamps every request with `X-Request-ID` and makes it
available to `auth.audit()` via a contextvar automatically — no existing
`audit()` call site needed to change its signature for correlation. Call
sites that can cheaply supply `site=`/`device_id=` (asset registration,
onboarding, DERMS dispatch, command issuance) were updated to do so.

`GET /audit/events` (admin-only, paginated, filterable by principal/action/
since) closes PORTAL-4. The portal's Administration page gained an
admin-only "Audit log" panel rendering it.

**Verified** — a real query through the portal's own admin session showed
correctly attributed rows including `principal=admin, role=admin,
action=create_user, resource=jane.engineer`, `principal=viewer,
action=login`, and `principal=anonymous, action=login, result=denied` for a
bad-password attempt — each with its own `request_id`, fixing PORTAL-3 (no
human attribution) and PORTAL-4 (no read surface) together.

## D. Backup verification (INSTALL-3)

Root cause confirmed by reading `scripts/backup-db.sh`/`backup-config.sh`:
the upload step was one `docker run ... -c "A && B && C || true"` shell
chain; bash's left-associative `&&`/`||` meant the trailing `|| true`
(intended only to tolerate "nothing to prune") silently swallowed a failure
**anywhere** in the chain, including the upload itself, combined with a
hardcoded `DIEP_NET=diep-lab_diep-net` default that's wrong for any clone not
named exactly `diep-lab`.

Fixed in both scripts: network name is now autodetected from the running
`diep-minio` container (`scripts/lib-backup-alert.sh`'s `detect_diep_net()`);
the upload chain and the retention prune are now separate `docker run`
invocations so the prune's intentional `|| true` can't mask an upload
failure; a positive `mc stat` confirmation compares the uploaded object's
size to the local file; and on any failure the script now exits non-zero
**and** posts a `critical`-severity `BackupFailed` alert to the existing
Alertmanager instance (reusing its current routing tree, no new
notification path).

**Verified, both the success and failure path:**
```
$ bash scripts/backup-db.sh
[3/5] upload to MinIO ... on network diep-phase21_diep-net   <- correctly autodetected,
                                                                  NOT the old "diep-lab_..." default
[4/5] positive upload confirmation (size match)
      OK: s3://diep-backups/diep_20260617T102104Z.dump confirmed (63507 bytes)
Backup complete: diep_20260617T102104Z.dump

$ MINIO_ROOT_PASSWORD=wrong-password-on-purpose bash scripts/backup-db.sh
mc: <ERROR> Unable to initialize new alias from the provided credentials...
EXIT CODE: 1                                    <- old script would have exited 0 here

$ curl http://localhost:9093/api/v2/alerts
[... {"labels":{"alertname":"BackupFailed","job":"backup-db","severity":"critical"},
     "annotations":{"summary":"backup-db failed", ...}} ...]   <- alert live in Alertmanager
```

## E. Grafana hardening (INSTALL-2)

`docker-compose.yml`'s `grafana` service had no `environment:`/`env_file`
block at all, so the image's built-in `admin`/`admin` was always live. Fixed:
`GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD` now come from `.env`
(`GF_ADMIN_USER`/`GF_ADMIN_PASSWORD` in `.env.example`), and
`GF_ADMIN_PASSWORD` uses Compose's `${VAR:?error}` syntax — an unset value now
fails `docker compose up` loudly instead of silently defaulting.

**Verified:**
```
curl -u admin:admin ".../api/org"                    -> 401 (default rejected)
curl -u "admin:Phase21GrafanaPass!" ".../api/org"     -> 200 (configured credential works)
```
**Deployment note for any existing `.env`:** this is a breaking change for
deployments whose `.env` predates this phase — `GF_ADMIN_PASSWORD` must be
added before the next `docker compose up`, or Grafana (and only Grafana) will
fail to start. This project's own `.env` was deliberately **not** modified by
this change (it contains live-looking secrets including an SMTP app
password); whoever next runs `docker compose up` against it must add
`GF_ADMIN_USER`/`GF_ADMIN_PASSWORD` first.

## Files changed

`fastapi/auth.py`, `fastapi/app.py`, `sql/012_users_rbac.sql` (new),
`init-db.sh`, `scripts/backup-db.sh`, `scripts/backup-config.sh`,
`scripts/lib-backup-alert.sh` (new), `docker-compose.yml` (grafana service
only), `.env.example`, `portal/middleware.ts` (new),
`portal/lib/serverAuth.ts` (new), `portal/app/login/page.tsx` (new),
`portal/app/forgot-password/page.tsx` (new),
`portal/app/reset-password/page.tsx` (new), `portal/app/api/auth/*` (new),
`portal/app/api/diep/[...path]/route.ts`, `portal/components/AppShell.tsx`
(new), `portal/components/Sidebar.tsx`, `portal/components/Providers.tsx`,
`portal/app/layout.tsx`, `portal/app/administration/page.tsx`,
`portal/lib/api.ts`.

## What was deliberately not touched

DERMS endpoint logic, the `fastapi/auth.py` JWT format's existing claims
(`sub`/`role`/`tenant`/`use`/`iat`/`exp` — only `jti`/`tv` were added), every
pre-existing HTTP request/response shape, and the HA architecture (Postgres/
Redis/Alertmanager are reused, not replaced or duplicated).

## Next step

A full 10-area re-validation pass (mirroring Phase 20 Part B's structure) is
recorded separately in `WEB_PORTAL_VALIDATION_REPORT_v2.md`, followed by
`PRODUCTION_DEPLOYMENT_DECISION_v2.md`.
