# DIEP — Roadmap to Live Production + Mobile App

> Date: 2026-06-05. Status legend: ✅ done · 🟡 partial · ⬜ not started.
> This is the full phase list from "certified lab" to "deployed live system with a phone app."

---

## 0. Where we are today (baseline)

✅ Functional platform: MQTT/Kafka data+command plane, TimescaleDB/Redis, DERMS, AI analytics, Next.js portal.
✅ **Phase 9 device integration complete** — 5 real protocol verticals behind one Driver SDK, all PRODUCTION_READY: solar (SunSpec), meter (Modbus), battery (Modbus, DERMS-dispatchable), EV charger (OCPP 1.6), microgrid (IEC 60870-5-104).
🟡 **Phase 9J security S0–S3**: API auth/RBAC + audit + rate-limit, secrets→env, additive MQTT TLS. S4–S7 remain.
⬜ Still **single-node** (no HA). No CI/CD, no orchestration, no real field pilot, no mobile app.

**Maturity:** ~TRL 6 (validated in a representative lab). Production readiness ~45%.

---

## GROUP A — Finish hardening the core (security · reliability · data)

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **9J-S4** | Per-device **mTLS** (X.509 client certs), retire shared broker password, disable plaintext 1883 | ⬜ |
| **9J-S5** | **Kafka SASL_SSL** (per-service SCRAM creds) | ⬜ |
| **9J-S6** | **TLS reverse proxy** (Caddy/Traefik) in front of API + portal; enforce auth on all routes; HSTS | ⬜ |
| **9J-S7** | **Vault** (or cloud secret manager): dynamic DB creds, PKI for the MQTT CA, rotation | ⬜ |
| **9K** | **High Availability**: migrate to Kubernetes (or Swarm); stateful HA — Postgres/Timescale (Patroni/CloudNativePG), Redis Sentinel, Kafka (Strimzi), MinIO distributed; LB + FastAPI replicas | ⬜ |
| **9-Schema** | **Canonical telemetry extension** (the deferred fields: power_factor, energy counters, temperature, soh, state, vehicle_soc, connector_status, load_kw, setpoint_kw…) + ingestor/twin pass-through | ⬜ |
| **9-Data** | Data lifecycle: retention + Timescale continuous aggregates/downsampling, **backups + point-in-time recovery**, decide InfluxDB (wire or retire) | ⬜ |

---

## GROUP B — Production operations (the "live system" plumbing)

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **10A — IaC & orchestration** | Helm charts / Kustomize; Terraform for infra; dev/staging/prod environments; secrets via sealed-secrets/Vault | ⬜ |
| **10B — CI/CD** | Automated build/test, image registry, **signed images + SBOM**, automated deploy with rollback, DB migration automation | ⬜ |
| **10C — Observability/SRE** | Centralized logging (Loki/ELK), distributed tracing (OTel), **SLOs + alerting/on-call** (extend existing Prometheus/Grafana/Alertmanager), runbooks | 🟡 (metrics exist) |
| **10D — Security ops** | Secret rotation, dependency/vuln scanning, container hardening, **penetration test**, audit-log retention/SIEM, periodic RBAC review | ⬜ |
| **10E — Resilience/DR** | Multi-AZ, disaster-recovery plan + drills, chaos testing, backup restore tests | ⬜ |

---

## GROUP C — Field deployment & certification

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **9I-full** | Harden the certification harness so the **security + failover tests are real** (currently SKIPPED) — depends on 9J-S4 + 9K | 🟡 |
| **9A-build** | **Edge gateway productization**: hardened reference image (Pi5/IPC/Jetson), OTA updates, store-and-forward at the edge, fleet onboarding at scale (thousands of sites) | 🟡 (arch only) |
| **Remaining drivers** | IEC 61850 (9G-b), DLMS/COSEM meters, DNP3, BACnet — and OCPP 2.0.1 | ⬜ |
| **Compliance** | Grid-code conformance, cybersecurity standards (**IEC 62443**, NERC CIP if applicable), data protection (GDPR/NDPR), safety sign-off for breaker/islanding control | ⬜ |
| **9L — Pilot** | Field pilot: 1 of each device class, 30–60 days, 6 KPIs, runbook, support process | ⬜ |

---

## GROUP D — Mobile app (the phone-app track)

> Foundation already in place: JWT issuance (`/auth/token`), RBAC, the portal's BFF pattern, and existing web screens (fleet, twins, alarms, DERMS) to mirror.

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **11A — Public API readiness** | API gateway (TLS, per-tenant rate limits), **versioned public API (`/v1`)**, stable OpenAPI contract, CORS for the app, WebSocket/SSE for live telemetry, push backend (FCM/APNs) | 🟡 (auth/rate-limit exist) |
| **11B — Mobile auth** | OAuth2/OIDC + **refresh tokens**, biometric unlock, **MFA/step-up auth for actuation** (issuing commands from a phone must be re-authenticated), per-role mobile scopes | 🟡 (JWT base exists) |
| **11C — App build** | Choose path: **(fast) PWA** from the existing Next.js portal (installable, offline-capable) **or (full) native** via React Native / Flutter sharing the API. Screens: fleet overview, device twins, alarms, DERMS controls, onboarding approvals | ⬜ |
| **11D — Push notifications** | Alarms, command ACK/fail, certification/onboarding events → FCM (Android) / APNs (iOS) | ⬜ |
| **11E — Mobile hardening** | TLS **certificate pinning**, secure token storage (Keychain/Keystore), jailbreak/root detection, least-privilege per role, remote wipe via MDM | ⬜ |
| **11F — Distribution** | Apple App Store + Google Play release (or enterprise/MDM distribution for operators), staged rollout, crash/analytics (Sentry), accessibility, app-store review compliance | ⬜ |

**Fastest path to "app on a phone":** turn the existing portal into a **PWA** (add manifest + service worker + installable) — operators can "Add to Home Screen" and it behaves like an app, reusing the auth and screens we already have. A true native app (11C native + 11D/E/F) is the larger, app-store track.

---

## GROUP E — Scale & commercial

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **12 — Multi-tenancy** | Tenant isolation, per-tenant RBAC + data partitioning, SSO (Keycloak/Auth0), billing/metering, white-label | ⬜ |
| **13 — Analytics/ML productionization** | Forecasting/anomaly/PdM at scale, model registry + retraining, feature store | 🟡 (lab analytics exist) |
| **14 — GA / commercial launch** | SLAs, 24×7 support, customer docs/onboarding, status page, contractual security attestations (SOC 2 / ISO 27001) | ⬜ |

---

## Recommended critical path (dependency-ordered)

1. **9J-S4 (mTLS)** → unlocks the real 9I security cert and safe field actuation.
2. **9-Schema + 9-Data** → cheap, high-leverage; makes telemetry first-class and adds backups.
3. **9K (HA) + 10A/10B (orchestration + CI/CD)** → the single biggest lift; the "single-node lab → real system" jump.
4. **10C/10D/10E (observability, security-ops, DR)** → operability + auditability.
5. **9A-build + 9L (edge productization + pilot)** → prove it in the field.
6. **11A→11F (mobile)** → can start the **PWA (11C-fast)** in parallel now since the API + auth exist; the native app + push + store release follow API-gateway readiness (11A).
7. **12–14** → multi-tenant, scale, commercial GA.

**Two tracks can run in parallel today:** (a) the PWA wrapper of the existing portal for an immediate "phone app," and (b) the security/HA/ops hardening that gates real field deployment. The native mobile app and app-store release should wait until the public API gateway (11A) is firm so the contract is stable.
