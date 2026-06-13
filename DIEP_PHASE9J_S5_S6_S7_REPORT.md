# DIEP Phase 9J — S5 (Kafka SASL) · S6 (TLS proxy) · S7 (Vault) + mTLS Fleet Migration

> **Status:** All implemented and verified. Date: 2026-06-06. The security backlog
> (S5–S7) is closed and the **mTLS migration is complete** — the entire platform now runs
> on mutual TLS with no plaintext MQTT and no shared device password. Stack intact: 5/5
> verticals PRODUCTION_READY. Builds on S0–S4.

---

## 1. S5 — Kafka authentication (SASL)

**Gap:** the command bus (FastAPI → Kafka `diep.commands` → dispatcher) was `PLAINTEXT` —
anyone on the network could inject commands.

**Done (additive, KRaft single broker):**
- Added a **SASL_PLAINTEXT listener on 9094** (`KAFKA_LISTENER...SASL_JAAS_CONFIG`, mechanism
  PLAIN, user `diep`); 9092 PLAINTEXT kept internal for inter-broker + kafka-ui.
- Migrated the **FastAPI producer** and **dispatcher consumer** to 9094 with SASL creds
  (env-driven, code default).

**Verified:**
- Dispatcher log: `Authenticated as diep via SASL / Plain` on `diep-kafka:9094`.
- Command end-to-end over SASL: `set_setpoint`→MGC900 → **ACKED**.
- **Unauthenticated produce rejected**: a PLAINTEXT client to 9094 times out (broker refuses
  to serve un-authenticated requests); an authed client succeeds.

Production form = **SASL_SSL + per-service SCRAM** in `k8s/kafka-strimzi.yaml`.

---

## 2. S6 — TLS reverse proxy (HTTPS)

**Done:** the Caddy API gateway (from 9K) now terminates **HTTPS on :8443** in front of the
load-balanced FastAPI replicas, with a cert issued from the platform CA (CN=`diep-api`, SAN
`localhost`) and **HSTS**. HTTP :8080 / :8090 kept for internal/lab.

**Verified:**
- `https://diep-api:8443/healthz` validates against the platform CA → served by a replica.
- `strict-transport-security: max-age=31536000; includeSubDomains` present; HTTP/2.
- Authenticated call over HTTPS: `GET /assets` → 200.

Production form = the k8s **Ingress + cert-manager** (Let's Encrypt) in `k8s/api.yaml`.

---

## 3. S7 — Vault (secrets + PKI)

**Done:** stood up **HashiCorp Vault** (`docker-compose-vault.yml`, dev mode) demonstrating
the two production roles:
- **KV secrets engine** — stored the DIEP app secrets (`db_password`, `jwt_secret`,
  `service_token`, `admin_key`) and read them back (served from Vault, not source).
- **PKI engine** — generated a DIEP root CA, created a `diep-device` role, and **issued a
  per-device cert for INV901** (cert + private key) — the production replacement for the
  openssl CA used in S4 and the code-default lab secrets from S0.

**Runtime integration (documented):** a Vault Agent sidecar injects secrets as env / fetches
short-lived certs per service; Vault runs HA (not -dev) with auto-unseal. Out of lab scope.

---

## 4. mTLS fleet migration — COMPLETE

S4 migrated one vertical (INV900). This completes the rest and **retires plaintext MQTT**.

**Done:**
- **All 5 device verticals on per-device mTLS**: INV900, MTR900, BAT900, MGC900, and the OCPP
  CSMS (identity `csms`, charger-domain scope). Each has a CA-signed cert (CN = id) + a
  scoped ACL block; no shared password.
- **Infra clients on mTLS**: the **ingestor** (`u'ingestor'`, reads all telemetry) and
  **dispatcher** (`u'dispatcher'`, reads acks / issues commands) — added TLS to their paho
  clients; these replace the shared `diep-nodered` identity.
- **Decommissioned** the redundant legacy simulators (INV001/BAT001/MG001/EV001/METER001) and
  nodered (the old command router) — superseded by the edge verticals + dispatcher.
- **Retired the plaintext listeners**: `listener 1883` and `9001` removed — the broker now
  serves **8883 mutual-TLS only**.

**Verified:**
- Broker clients are exactly: `INV900, MTR900, BAT900, MGC900, csms, ingestor, dispatcher` —
  **all mTLS, zero shared-password clients**.
- **1883 is closed** (connection attempt fails: "Bad file descriptor").
- Full secured path end-to-end: operator JWT → HTTPS-capable API → **Kafka SASL** → dispatcher
  (mTLS) → **MQTT mTLS** cmd → driver (mTLS) → ack → `charge`→BAT900 **ACKED**.
- Telemetry flowing for all 5 verticals over mTLS; ingestor (mTLS) persisting it.
- 5/5 PRODUCTION_READY; portal (200) and HTTPS gateway (200) healthy.

---

## 5. Security posture — before Phase 9 → now

| Layer | Before | Now |
|-------|--------|-----|
| API auth | none | JWT/RBAC + API keys, audit, rate-limit (S1/S2) |
| API transport | http | **HTTPS** at the gateway, HSTS (S6) |
| MQTT | plaintext 1883, shared password | **mTLS-only 8883**, per-device certs, ACL isolation (S3/S4) |
| Kafka | PLAINTEXT, anyone injects | **SASL auth** on the command bus (S5) |
| Secrets | hardcoded in source | env (S0) + **Vault** KV/PKI (S7) |
| HA | single-node | LB'd API replicas + Redis replica + k8s manifests (9K) |

---

## 6. Remaining (production / cluster)

- **SASL_SSL** for Kafka (TLS, not just SASL) + remove the internal 9092 PLAINTEXT — Strimzi.
- **Vault in HA** (not dev) + Vault Agent wiring into every service; **cert rotation + CRL/OCSP**.
- **Lock down 9092** (network policy) until Kafka is fully TLS.
- Move the API behind a real **Ingress + cert-manager** (public CA) rather than the lab Caddy.
- **OCPP `wss://`** (9F) and **IEC-104 over TLS** (9G) — per-vertical transport TLS.
- Auto-issue device certs at **onboarding (9H)** via Vault PKI.

These are tracked for **Group B (10A/10B — orchestration + CI/CD)**, where the `k8s/` manifests
deploy the production forms of all of the above.

---

## 7. Result

Phase 9J is **complete (S0–S7)**. DIEP now has authenticated, authorized, audited,
rate-limited, TLS-terminated APIs; a SASL-authenticated command bus; and a **fully
mutual-TLS device fleet with per-device identities and no plaintext MQTT** — the security
baseline required before any real field deployment. Group A of the production roadmap (9K,
Schema, Data, and the full 9J security stack) is done; next is **Group B — orchestration
(10A) + CI/CD (10B)** to deploy the cluster.
