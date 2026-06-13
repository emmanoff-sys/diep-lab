# DIEP Phase 9J — Validation Report (Security Hardening)

> Date: 2026-06-05 · Scope: stages S0–S3. Result: API auth/RBAC + audit + rate limit +
> additive MQTT TLS enforced, **with zero stack breakage** — all five device verticals
> remain PRODUCTION_READY. Companion to `DIEP_PHASE9J_SECURITY_REPORT.md`.

---

## 1. Authentication & RBAC (S1)

| # | Test | Expected | Result |
|---|------|----------|--------|
| a | `GET /assets` no token | 200 (GETs open) | **200** ✓ |
| b | `POST /commands` no token | 401 | **401** ✓ |
| c | `POST /auth/token` (operator creds) | JWT issued | token (188 chars) ✓ |
| d | `POST /commands` with operator JWT | 202 | **202** ✓ |
| e | `POST /assets` (admin route) with operator JWT | 403 | **403** ✓ |
| f | `GET /auth/whoami` with operator JWT | identity | `{operator, role=operator, jwt}` ✓ |
| g | `GET /auth/whoami` with service API key | identity | `{svc-machine, role=service, apikey}` ✓ |

RBAC matrix holds: operator can issue commands/DERMS but not admin (assets/onboarding);
service can ingest but not command; admin is superuser.

---

## 2. No stack breakage (the critical constraint)

| Check | Evidence | Result |
|-------|----------|--------|
| Telemetry still flowing (ingestor authenticated) | all 5 devices, age 1–5 s in `telemetry` | ✓ |
| Command path intact (dispatcher ack authenticated) | operator JWT → `/commands` → driver → `Posted ack to FastAPI` → status **ACKED** | ✓ |
| DERMS intact via portal | portal BFF `POST /derms/battery_dispatch` → 202 → audited (`api-admin`) → `charge` **ACKED** | ✓ |
| Portal reads | `GET /api/diep/assets` via BFF → 200; fleet → 10 assets | ✓ |
| All five verticals | `5 of 5 PRODUCTION_READY` | ✓ |

---

## 3. Audit logging (S2)

`audit_events` rows written for state-changing actions, e.g.:
```
principal | role     | action                 | resource        | result
operator  | operator | issue_command          | BAT900:standby  | ok
api-admin | admin    | derms_battery_dispatch | BAT900          | ok
```
Telemetry/ack deliberately not audited (high-frequency; captured in the command lifecycle).

---

## 4. Rate limiting (S2)

130 rapid `POST /commands` (bogus device → no side effects) under one operator identity:
```
  120 × 404   (passed rate limit; rejected by handler as unknown device)
   10 × 429   (rate limit exceeded — 120/60s window enforced)
```
Limiter triggers exactly at the configured threshold; fail-open verified by design.

---

## 5. MQTT TLS (S3)

- Additive `listener 8883` (TLS) added beside `1883`; CA + server cert with SAN
  `diep-mqtt`/`localhost`/`127.0.0.1`.
- **TLS round-trip on 8883:** publish over TLS (`diep-device`) → subscribe over TLS
  (`diep-nodered`) received `"TLS-handshake-OK over 8883"`.
- **1883 unaffected:** after the broker restart all five edge devices reconnected and
  telemetry resumed (age 1–3 s) — the re-subscribe fix made the restart clean.

---

## 6. Secrets (S0)

- `app.py`/`auth.py` read DB + auth secrets from environment; `.env.example` documents all
  variables and flags the exposed defaults (`diep123`, `diep12345`, `*-2026`) for rotation.
- No new plaintext secret introduced in source beyond clearly-labelled lab defaults; the
  full secret-store (Vault) is S7.

---

## 7. Bonus fix — MQTT re-subscribe on reconnect

Discovered during verification: a 21 h-uptime edge driver still published telemetry but had
silently stopped receiving commands (paho doesn't re-SUBSCRIBE after auto-reconnect). Fixed
in the SDK (`on_connect` re-subscribe); all five edge containers now log
`MQTT (re)subscribed`. Verified by issuing a command post-fix → **ACKED**.

---

## 8. Result

Stages **S0–S3 complete and verified**. The headline Phase 9 risk — unauthenticated
actuation of physical assets — is closed: `/commands` and `/derms/*` now require an
authenticated operator, every actuation is audited and rate-limited, secrets are
env-driven, and MQTT TLS is available — all while the five certified verticals keep
running. Remaining stages **S4 (mTLS), S5 (Kafka SASL), S6 (TLS proxy), S7 (Vault)** are
cutover/new-infra work scoped in the security report §5.

**Recommended next action:** **S4 — per-device mTLS** (it gives every field device a unique,
revocable identity, retires the shared broker password, and is the security prerequisite the
9I certification `security` test checks — currently SKIPPED across all verticals), then **9K
(HA)** to address the also-SKIPPED `failover` test. The deferred **canonical schema
extension** (from 9C–9G) remains the cheapest high-leverage non-security improvement.
