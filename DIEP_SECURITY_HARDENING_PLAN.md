# DIEP Security Hardening Plan (Phase 9J)

> **Status:** Wave-1 design. No production code changed yet. This plan is the prerequisite
> for field-device integration: a real device cannot be certified (9I security test) or
> piloted (9L) on the current unsecured broker/API. Migration is staged to **keep the lab
> running** (per the "additive only" decision) until each cutover is ready.

## 1. Current posture (verified) and risk

| Layer | Current state | Risk |
|-------|---------------|------|
| MQTT | Auth (passwd) + ACL, `allow_anonymous false` ✅ — but **plaintext 1883/ws 9001, no TLS, shared `diep-device` password** | Credential sniffing; one shared identity for all devices; no per-device revocation |
| Kafka | `PLAINTEXT` listeners; no SASL/TLS | Anyone on the network can read/inject commands |
| FastAPI | **No auth, no TLS, no rate limit, no audit, no API keys** | Anyone who can reach :8000 can actuate physical assets via `/commands` and `/derms/*` |
| Secrets | Hardcoded: DB `diep123` (`app.py:28` + compose), MinIO `admin/diep12345`, MQTT `nodered-pass-2026` | Secrets in source control; no rotation |
| Portal | BFF proxy (no CORS exposure) ✅ | Inherits backend's lack of auth |

**Top risk:** the command/DERMS path actuates real batteries, inverters, chargers, and
breakers with **no authentication**. This is the single most important thing to fix before
any field device connects.

## 2. Target architecture

```
Operators ─JWT/OAuth2─▶ API GW (TLS, rate-limit, audit) ─▶ FastAPI cluster (RBAC)
Machines  ─API key────▶                                          │
Gateways/devices ─mTLS─▶ MQTT broker (TLS 8883, per-device certs+ACL)
Internal services ─SASL+TLS─▶ Kafka
Secrets ◀── env / Docker secrets → (Vault, fast-follow)
```

## 3. Workstreams

### 3.1 API authentication & authorization (JWT / OAuth2 / RBAC)
- Add `OAuth2PasswordBearer` + JWT (PyJWT) to FastAPI; verify on protected routes via a
  `Depends(require_role(...))` dependency.
- **Roles:** `viewer` (GET only), `operator` (commands/DERMS), `admin` (assets/onboarding).
- Machine clients (edge gateways, dispatcher, ingestor) use **API keys** (hashed, per-client)
  or client-credentials OAuth2 — not user JWTs.
- OAuth2 provider: start with a self-contained issuer (FastAPI + JWT) for the pilot; integrate
  Keycloak/Auth0 for production SSO.
- **Audit log:** every state-changing call (`POST /commands`, `/derms/*`, `/assets`,
  onboarding/cert) writes an `audit_events` row (who, what, when, source IP, result).
- **Rate limiting:** per-key/IP limits (e.g. `slowapi`/Redis token bucket) on actuation routes.

### 3.2 MQTT security (TLS + client certificates + ACL)
- Enable Mosquitto **TLS on :8883**; keep :1883 only on the internal network during migration,
  then disable.
- Issue **per-device / per-gateway X.509 client certs** from a platform CA (mutual TLS);
  use the certificate CN as the identity and bind ACLs to it (a gateway may only touch its
  site's topics). Retire the shared `diep-device` password.
- The driver SDK is **already TLS-ready** (`drivers/diep_driver/mqtt_client.py` honors
  `MQTT_TLS`/`MQTT_CA_CERTS`/`MQTT_CLIENT_CERT`/`MQTT_CLIENT_KEY`) — cutover is config, not code.
- Update `dispatcher`, `ingestor`, and simulators to TLS in lockstep (or run a transitional
  dual-listener broker so the lab keeps working during migration — the additive path).

### 3.3 Kafka security (SASL + TLS)
- Enable `SASL_SSL` listener; SCRAM credentials per service (FastAPI producer, dispatcher consumer).
- Keep an internal `PLAINTEXT` listener bound to the private network only during migration; remove after.

### 3.4 Secrets management
- **Phase 1 (now, non-breaking):** move all hardcoded secrets to environment variables /
  Docker secrets. `app.py` `DB_CONFIG` reads `os.getenv`; compose pulls from an untracked
  `.env`. Rotate the exposed defaults (`diep123`, `diep12345`, `nodered-pass-2026`).
- **Phase 2 (production):** HashiCorp Vault (or cloud secret manager) for dynamic DB creds,
  PKI issuance (the MQTT CA), and cert rotation. **Vault assessment:** recommended for
  utility/multi-tenant production; overkill for the pilot — env/Docker secrets suffice there.
- Add a secret-scanning pre-commit hook to prevent regressions.

### 3.5 Transport for the API & portal
- Terminate TLS at an API gateway / reverse proxy (Caddy/Traefik/Nginx) in front of FastAPI;
  HSTS; modern ciphers. Portal served over HTTPS.

## 4. Staged migration (keeps the lab running)

| Stage | Change | Lab impact |
|-------|--------|------------|
| S0 | Secrets → env/Docker secrets; rotate defaults | None (additive) |
| S1 | Add FastAPI JWT/RBAC + API keys, **enforced only on actuation routes**; GETs open initially | Portal keeps working (reads); add a service API key for dispatcher/ingestor |
| S2 | Add audit logging + rate limiting | None |
| S3 | Broker dual listener: add TLS :8883 alongside :1883; migrate gateways/drivers first | None (both work) |
| S4 | Issue per-device certs; migrate dispatcher/ingestor/sims to mTLS; disable :1883 | Cutover window |
| S5 | Kafka SASL_SSL; migrate producer/consumer; remove plaintext | Cutover window |
| S6 | TLS reverse proxy in front of API + portal; enforce auth on all routes | Cutover window |
| S7 | Vault for dynamic secrets + PKI (production only) | New infra |

## 5. Acceptance (feeds the 9I security test)
- No plaintext broker/API reachable from outside the private network.
- Every device authenticates with a unique, revocable credential (cert).
- `POST /commands` and `/derms/*` reject unauthenticated/under-privileged callers (401/403).
- No secret present in source control; all from env/secret store; defaults rotated.
- Audit row exists for every actuation; rate limits enforced.
- Kafka requires SASL+TLS; MQTT requires mTLS.

## 6. Out of scope here (tracked elsewhere)
- HA/clustering → `DIEP_HA_ARCHITECTURE.md` (9K).
- Device-identity lifecycle (enroll/renew/revoke) ties into onboarding (9H) and certification (9I).
