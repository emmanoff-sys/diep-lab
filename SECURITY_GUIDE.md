# DIEP v1.0 — Security Guide

Current security posture as of this RC's qualification (2026-06-26), live-tested
against the running stack, not just read from prior design docs. Findings with
no fix applied are listed with the exact remediation needed — see
`GO_LIVE_CHECKLIST.md` for the prioritized action list.

## Authentication & Authorization

- **FastAPI**: JWT + API-key auth, RBAC (admin/operator/viewer/service),
  enforced per-route via `Depends(require_role(...))`. **Exception, confirmed
  open:** `GET /telemetry/latest` (`fastapi/app.py:1960`) has no auth
  dependency at all and returns a cross-tenant row to an anonymous request.
  **Fix needed:** add the same role/tenant-scoping dependency the `/telemetry`
  POST route already has, and filter by the caller's tenant.
- **MQTT**: mutual TLS, per-device certificates, CA-issued. Plaintext
  listeners retired. ACLs grant least-privilege per identity (`mosquitto/config/acl`).
- **Kafka**: SASL_PLAINTEXT with credentials sourced from `.env`
  (`KAFKA_SASL_USERNAME`/`KAFKA_SASL_PASSWORD`) — confirmed no hardcoded
  literal in the live compose file.
- **Redis**: `requirepass`/`masterauth` enforced, including across Sentinel
  failover (confirmed live in this qualification's failover drill).
- **CIM API**: its own lightweight Bearer-token auth (`CIM_API_KEYS`:
  token→tenant_id), independently verified to enforce tenant isolation
  (a scoped token cannot see another tenant's devices; cross-tenant detail
  request returns 404, not a leak).
- **Grafana**: requires login; `/api/datasources` correctly returns 401
  unauthenticated.

## Confirmed-open exposures (no fix applied yet — see Go-Live Checklist)

The following are reachable on this host's network interfaces with **zero
authentication**, live-confirmed 2026-06-26:

| Service | Port | What's exposed |
|---|---|---|
| Prometheus | 9090 | Full metric/query access |
| Alertmanager | 9093 | Can view **and silence** alerts |
| kafka-ui | 8081 | Live cluster/topic browsing |
| cAdvisor | 8080 | Per-container resource data |
| node-exporter | 9100 | Host metrics (lower severity) |
| Node-RED | 1880 | **Admin API** — `GET /flows` returns real flow definitions; the same API can deploy flows, meaning arbitrary JS execution, if `adminAuth` isn't enforced (a `nodered/.config.users.json` user DB exists but is not being enforced on the HTTP API as currently configured) |

Phase 22 SEC-4 bound the *data* ports (Postgres, Kafka, Redis, MinIO) to
`127.0.0.1`; this same treatment was never extended to the monitoring/admin
stack above. **Recommended fix:** bind all of these to `127.0.0.1` and put
them behind the same Caddy/auth boundary as Portal/Grafana, or put a
network-level ACL/firewall in front of this host restricting access to an
operator network — whichever this deployment's network model calls for.

## TLS

Caddy (Phase 22 SEC-3) terminates HTTPS for the API (`:8443`), Portal
(`:3443`), and Grafana, with HSTS and an HTTP→HTTPS redirect — confirmed
live and working. **This is additive, not enforced:** the original
plaintext container ports (FastAPI :8000, Portal :3002, Grafana :3001) are
still reachable directly, bypassing TLS entirely — confirmed live. To
actually enforce TLS, either firewall the plaintext ports to localhost-only
(matching the Phase 22 SEC-4 treatment already given to the data services)
or remove their host port-mappings once all clients are confirmed to be
using the Caddy front door.

## Secrets

- `.env` is correctly gitignored and not tracked.
- Kafka SASL credentials are sourced from `.env`, not hardcoded, in the live
  compose file.
- **Operational drift, found live:** the running `diep-timescaledb`
  container's actual database password no longer matches what's in
  `.env` — it was rotated in `.env` after the container/volume was created,
  and Postgres does not reapply `POSTGRES_PASSWORD` to an existing data
  directory. Anyone redeploying from current `.env` against a fresh volume
  would set a different password than the one in active use today.
  **Fix:** either reconcile `.env` to the live value, or rotate the live
  password to match `.env` via `ALTER USER ... PASSWORD` and restart
  dependent services.
- `docker-compose-timescale.yml` (confirmed not the file actually in use —
  check via `docker inspect <container> --format '{{index .Config.Labels
  "com.docker.compose.project.config_files"}}'` before trusting any
  standalone compose file) has a hardcoded weak password, as do the various
  `*-ha-validation.yml`/`*-pitr-validation.yml` files. None are live. Treat
  as dead reference material, or delete if they're no longer needed for
  re-running those validations.

## Certificates

All device certificates (`certs/devices/*.crt`) expire 2028-09-22/23; the CA
certificate expires 2036-06-17. No near-term expiry risk, but put device
cert rotation on a calendar well before 2028 rather than waiting for renewal
to become urgent.

## Tenant Isolation

CIM's tenant scoping is verified (see above). FastAPI's tenant scoping is
enforced on writes and most asset/device endpoints but **not** on
`GET /telemetry/latest` (see above) and has prior-session findings (not
re-verified this round) of inconsistent scoping elsewhere — see
`KNOWN_LIMITATIONS.md`.

## Network Exposure Summary

Loopback-only (good): TimescaleDB (5432), Kafka (9092), Redis (6379), MinIO
(9000/9002), Kafka SASL listener.
All-interfaces, authenticated: FastAPI (8000, JWT/API-key), Grafana (3001,
login), MQTT (8883, mTLS).
All-interfaces, **unauthenticated**: Prometheus (9090), Alertmanager (9093),
kafka-ui (8081), cAdvisor (8080), node-exporter (9100), Node-RED (1880).
