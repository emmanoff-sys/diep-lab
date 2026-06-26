# DIEP v1.0 — Administration Guide

Tenant, user, RBAC, and credential/cert rotation administration, current as
of this RC's qualification (2026-06-26). Verified against the live system,
not just the code.

## Roles & RBAC

FastAPI (`fastapi/auth.py`) defines a single role hierarchy: `viewer <
operator < engineer < admin`, plus a separate `service` role for machine/
device ingest (used by the ingestor's identity, not human operators). `admin`
is superuser. Roles are enforced per-route via `Depends(require_role(...))`.
**Known exception, not yet enforced:** `GET /telemetry/latest` has no role
requirement at all — see `SECURITY_GUIDE.md`.

`portal_users` table backs human accounts; the system refuses to remove the
last remaining `admin` (`fastapi/auth.py:216`, confirmed by reading the
constraint, not independently re-tested this session).

## Admin Credentials

`DIEP_ADMIN_KEY` / `DIEP_ADMIN_USER` / `DIEP_ADMIN_PASSWORD` env vars seed
the bootstrap admin identity, with weak literal fallbacks in code
(`diep-admin-dev-key-CHANGE-ME`, `admin`, `diep-admin-2026`) if unset.
**Checked live, 2026-06-26:** `DIEP_ADMIN_KEY` and `DIEP_ADMIN_PASSWORD` are
both rotated to strong (32-char) non-default values in this deployment's
`.env`, and confirmed actually loaded into the running `diep-fastapi`
container's environment. `DIEP_ADMIN_USER` is still the literal default
`"admin"` — a username, not a secret, so low severity, but rotate it too if
this deployment's threat model calls for not using a guessable admin
username.

## Tenant Administration

Tenants are identified by `tenant_id` (string), set on `devices`,
propagated into `telemetry.metadata->>'tenant_id'` via the AMI contract
envelope. CIM's tenant scoping (`services/cim/`, `CIM_API_KEYS` mapping
token→tenant_id) is independently verified to enforce isolation correctly —
a token scoped to one tenant gets a 404, not data, when requesting another
tenant's resources. FastAPI's tenant scoping is enforced on writes and most
asset/device reads but has known gaps on `/telemetry/latest` and (per prior,
not re-verified, SIT findings) some other telemetry read paths — see
`KNOWN_LIMITATIONS.md` before assuming every read endpoint is tenant-scoped.

## Certificate Administration

- Device mTLS certs: `certs/devices/*.crt`/`*.key`, CA at
  `certs/devices/ca.crt`. All device certs expire 2028-09-22/23; CA expires
  2036-06-17 (checked live via `openssl x509 -enddate`). No near-term action
  needed, but put rotation on a calendar — see `SECURITY_GUIDE.md`.
- Caddy/API TLS certs: `caddy/certs/api.crt`/`api.key`, same platform CA.
- To issue a new device cert: follow the existing device-onboarding
  procedure (not changed by this qualification) — this guide doesn't
  duplicate that, see the existing onboarding docs/scripts under `scripts/`
  and `drivers/<protocol>/README.md` for protocol-specific device setup.

## Secret Rotation

- `.env` is the single source for all service credentials (DB, Redis, Kafka
  SASL, MinIO, admin bootstrap) and is correctly gitignored.
- **Important, found live this session:** rotating a value in `.env` does
  **not** retroactively change a credential a stateful service (TimescaleDB,
  Redis) already initialized with on its data volume — Postgres in
  particular does not reapply `POSTGRES_PASSWORD` to an existing data
  directory. After rotating a DB/Redis password in `.env`, you must also
  apply it to the live service (`ALTER USER ... PASSWORD '...'` for
  Postgres; `CONFIG SET requirepass ...` plus updating Sentinel's
  `auth-pass` for Redis) and restart dependent services — confirmed this
  session that `.env` and the live TimescaleDB password had drifted apart
  for exactly this reason.
- Kafka SASL credentials are sourced from `.env` (`KAFKA_SASL_USERNAME`/
  `KAFKA_SASL_PASSWORD`) with no hardcoded fallback in the live compose file
  — confirmed by direct read.

## What This Guide Does Not Cover

General onboarding/offboarding workflows, device provisioning, and Day-2
operational procedures are unchanged by this qualification — see the
existing `DIEP_OPERATIONS_MANUAL.md` and protocol-specific driver
documentation under `drivers/`.
