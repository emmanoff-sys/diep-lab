# DIEP Phase 9J — Security Hardening

> **Status:** Implemented stages **S0–S3** (secrets→env, API auth/RBAC, audit+rate-limit,
> additive MQTT TLS). Date: 2026-06-05. The lab stays fully running — all five device
> verticals remain PRODUCTION_READY and live. Stages **S4–S7** (mTLS cutover, Kafka SASL,
> TLS reverse proxy, Vault) are documented as cutover/new-infra work (§5). Gated by
> `DIEP_SECURITY_HARDENING_PLAN.md`.

---

## 1. Summary

The #1 risk going into Phase 9 was that **the command/DERMS path actuated real assets with
no authentication** — anyone reaching `:8000` could drive batteries, inverters, chargers,
and breakers. Phase 9J closes that, additively, without breaking the running stack:

- **API authentication + RBAC** on every state-changing route (commands, DERMS, assets,
  onboarding, telemetry ingest, acks). Unauthenticated callers get 401; under-privileged
  get 403.
- **Audit logging** of every actuation (who/what/when/source/result).
- **Rate limiting** on the command/DERMS paths.
- **Secrets moved to environment** (DB password + all auth secrets) with a documented
  `.env.example`; lab defaults keep the stack running and are flagged for rotation.
- **Additive MQTT TLS** listener on `:8883` alongside the existing `:1883`.

A latent reliability bug surfaced and was fixed along the way (§6, MQTT re-subscribe).

---

## 2. What was built

### 2.1 API authentication & authorization (S1) — `fastapi/auth.py`
- **JWT (HS256, stdlib)** — no new dependency; `/auth/token` exchanges username/password
  for a short-lived role-bearing JWT; `/auth/whoami` echoes the caller identity.
- **API keys** — hashed/static keys for machine clients and the portal BFF, via
  `Authorization: Bearer <key>` or `X-API-Key`.
- **Roles:** `viewer` < `operator` < `admin`, plus `service` for machine ingest.
  `admin` is superuser. Enforced by `Depends(require_role(...))`.
- **Enforcement gate** `DIEP_AUTH_ENFORCED` (default on) for staged rollout.

| Route(s) | Required role |
|----------|---------------|
| `POST /commands` | operator |
| `POST /derms/*` (battery_dispatch, peak_shaving, demand_response, load_optimization) | operator |
| `POST /assets`, `POST /onboarding/*` (enroll/validate/certify/approve) | admin |
| `POST /telemetry`, `POST /commands/{id}/ack` | service (machine) |
| All `GET` routes (dashboards, state, fleet, health) | open (S1: GETs open initially) |

DERMS internally calls the command core `_dispatch_command()` (refactored out of the HTTP
handler), so DERMS actuation is authenticated **once** at the `/derms` boundary and not
double-checked on the internal hop.

### 2.2 Audit logging (S2) — `audit_events` table (`sql/008_security.sql`)
Every state-changing call appends `{ts, principal, role, action, resource, source_ip,
result, detail}`. Telemetry/ack are intentionally **not** audited (too high-frequency; the
command lifecycle already records them).

### 2.3 Rate limiting (S2)
Redis fixed-window limiter (`auth.rate_limit`) on `POST /commands` (120/60s) and `/derms/*`
(60/60s), keyed by principal/IP; **fail-open** if Redis is unavailable (never blocks
actuation on a limiter outage).

### 2.4 Secrets management (S0) — `.env.example`
`app.py` `DB_CONFIG` and `auth.py` read all credentials from environment with lab defaults.
DB password, JWT secret, service/operator/admin keys, user passwords, and the portal token
are now env-driven. `.env.example` documents every variable and flags the exposed defaults
(`diep123`, `diep12345`, `*-2026`) for rotation.

### 2.5 MQTT TLS (S3) — `mosquitto/config/`
A platform CA + server cert (SAN `diep-mqtt`/`localhost`/`127.0.0.1`) and an **additive**
`listener 8883` (TLS) beside `1883`. The driver SDK already honours `MQTT_TLS` /
`MQTT_CA_CERTS` / `MQTT_CLIENT_CERT` / `MQTT_CLIENT_KEY`, so a gateway moves to TLS by config
only. `require_certificate` (mTLS) is left commented as the S4 step.

### 2.6 Client updates (non-breaking rollout)
- **ingestor / dispatcher** — send the service token on `/telemetry` and `/commands/{id}/ack`.
- **portal BFF** — the transparent `next.config.js` rewrite is replaced by a server-side
  route handler (`portal/app/api/diep/[...path]/route.ts`) that injects an admin-scoped
  token; the token lives only in server env, never the browser. Production should swap this
  for per-operator SSO/JWT via `/auth/token`.

---

## 3. Architecture after S0–S3

```
Browser ─▶ Portal BFF (injects token) ─┐
Operators ─JWT (/auth/token)──────────▶ ├─▶ FastAPI: require_role + rate_limit + audit
Machines  ─API key (service)──────────▶ ┘        (GET open · POST role-gated)
                                                  └─ _dispatch_command ─▶ Kafka ─▶ dispatcher
Devices/gateways ─▶ MQTT 1883 (plaintext, migrating)  +  8883 (TLS, ready)
Secrets ◀── environment (.env) ; defaults flagged for rotation
```

---

## 4. Verification (see DIEP_PHASE9J_VALIDATION_REPORT.md)

401 (no token), 403 (wrong role), 202 (operator JWT), API-key auth, rate-limit 429,
audit rows, TLS round-trip on 8883, and **zero stack breakage** (telemetry + commands +
DERMS + all five verticals intact).

---

## 5. Remaining stages (S4–S7) — cutover / new infra, not executed here

| Stage | Work | Why deferred |
|-------|------|--------------|
| **S4** | Per-device X.509 client certs; `require_certificate true`; migrate dispatcher/ingestor/edge to mTLS on 8883; retire shared `diep-device` password and disable 1883 | Cutover window; needs a device-cert issuance/rotation lifecycle (ties to onboarding 9H) |
| **S5** | Kafka `SASL_SSL` + per-service SCRAM creds | Cutover window; breaks producer/consumer until migrated in lockstep |
| **S6** | TLS reverse proxy (Caddy/Traefik) in front of API + portal; enforce auth on **all** routes incl. GETs; HSTS | New infra; GETs currently open by design (S1) |
| **S7** | HashiCorp Vault for dynamic DB creds + PKI (the MQTT CA) + rotation | Production-only; env/Docker secrets suffice for the pilot |
| — | OCPP `wss://` + OCPP Security Profiles (9F); IEC-104 over TLS (9G) | Per-vertical hardening, fold into S4/S6 |

---

## 6. Discovered & fixed: MQTT re-subscribe on reconnect

While verifying the command path, a long-running edge driver (21 h uptime) was found to
have **stopped receiving commands** while still publishing telemetry: paho-mqtt does not
re-issue SUBSCRIBE after an auto-reconnect, so the `…/cmd` subscription was silently lost.
Fixed in the SDK (`drivers/diep_driver/mqtt_client.py`) by re-subscribing in an `on_connect`
handler. All five edge containers were refreshed and now log `MQTT (re)subscribed`. This
also made the broker restart for S3 safe (devices reconnected and re-subscribed cleanly).
Pre-existing bug, unrelated to auth — but it would have undermined command reliability for
the whole fleet.

---

## 7. Acceptance vs the plan (§5 of the hardening plan)

| Criterion | Status |
|-----------|--------|
| `POST /commands` & `/derms/*` reject unauthenticated/under-privileged callers (401/403) | ✅ done |
| Audit row for every actuation | ✅ done |
| Rate limits enforced | ✅ done |
| Secrets from env; defaults flagged for rotation | ✅ S0 done (rotation = deploy-time) |
| MQTT TLS available | ✅ S3 (server-auth TLS on 8883; mTLS = S4) |
| Every device authenticates with a unique revocable cert | ⏳ S4 (mTLS) |
| Kafka requires SASL+TLS | ⏳ S5 |
| No plaintext API/broker reachable externally | ⏳ S6 (TLS proxy; 1883 retire in S4) |
