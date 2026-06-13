# DIEP Group E — Scale & Commercial (Phases 12–14)

> **Status:** Phase 12 (multi-tenancy) implemented & verified; Phases 13 (analytics/ML
> productionization) and 14 (GA/commercial) designed with control mapping to what's built.
> Date: 2026-06-06. Stack intact (5/5 PRODUCTION_READY).

---

## 12 — Multi-tenancy (live & verified)

The platform had no tenant concept (all data global). Phase 12 adds tenant isolation:

- **Model** (`sql/011_tenancy.sql`): a `tenants` table (default / acme / globex, with `plan`)
  and an additive `devices.tenant_id` (existing devices → `default`).
- **Identity:** the JWT now carries a `tenant` claim; the `Principal` exposes `.tenant`
  (None = global superuser). Per-tenant operator logins (`acme-op`, `globex-op`).
- **Isolation enforced in the API:**
  - `GET /assets` is now **authenticated** and **scoped** to the caller's tenant.
  - `POST /assets` stamps the device's tenant.
  - `POST /commands` rejects cross-tenant actuation (`_assert_tenant_access`).
  - Global principals (admin + the `service` API keys used by the portal/ingestor/dispatcher)
    are unrestricted, so the platform plumbing is unaffected.

**Verified:** acme-op sees only `{INV900, MTR900}`; globex-op only `{BAT900, EVSE900}`; admin
sees all 5; acme-op commanding a globex device → **403**; own device → **202**; unauth read →
**401**. Portal (admin key) still sees all 10; ingestor/dispatcher unaffected; 5/5 PRODUCTION_READY.

**Remaining for full tenancy:** scope the rest of the read surface (`/state`, `/fleet`,
`/onboarding`, DERMS `_select_device`) by tenant; row-level tenant on telemetry queries (join
`devices`); per-tenant rate-limit tiers (the limiter already keys per principal); tenant
admin/CRUD APIs.

---

## 13 — Analytics / ML productionization (design)

The lab has forecast / anomaly / PdM analytics. Productionizing:

- **Model registry** (MLflow): versioned models, stage gates (staging→prod), lineage.
- **Training pipeline**: scheduled retraining (Argo Workflows/Airflow) on TimescaleDB +
  the continuous aggregates (9-Data) as the feature source; champion/challenger eval.
- **Feature store** (Feast or Timescale-backed): consistent features for train + serve;
  per-tenant feature isolation.
- **Serving**: model inference service behind the same API gateway; results to
  `analytics_events`; **drift/quality monitoring** wired to the 10C Prometheus/Alertmanager.
- **Scale**: per-tenant models where data volume warrants; batch + streaming inference.

---

## 14 — GA / commercial readiness (design + control mapping)

### SSO & identity
The auth is already **OIDC/JWT-shaped** (HS256 today). For GA: front it with **Keycloak or
Auth0** (OIDC), map IdP groups → DIEP roles + tenant claim, enterprise SSO/SAML, SCIM
provisioning. Mobile refresh-token flow (11B) already fits OAuth2.

### Billing & metering
Per-tenant usage is already attributable (devices carry `tenant_id`; audit + command/telemetry
counters per tenant). Add a metering rollup (devices, telemetry volume, commands, DERMS
actions per tenant/month) → billing (Stripe/usage-based); `plan` on `tenants` gates limits.

### SLAs
Backed by the 10C SLOs (availability 99.9%, command success ≥99%, dispatch p95 <1s, ack p95
<30s) + 10E DR (RPO≤5m/RTO≤30m). Publish tiered SLAs per `plan`; a **status page**
(Statuspage/Cachet) fed by the Prometheus probes.

### Compliance — control mapping (what's already built)
| Control area | Standard | DIEP today |
|--------------|----------|-----------|
| Access control / least privilege | SOC 2 CC6, ISO A.9, IEC 62443 | JWT/RBAC, per-device mTLS + ACL, tenant isolation |
| Encryption in transit | CC6.7, A.10 | TLS API (S6), mTLS MQTT (S4), SASL Kafka (S5) |
| Audit logging | CC7, A.12.4 | `audit_events` (who/what/when/ip/result) → SIEM |
| Secrets mgmt | CC6, A.10 | Vault KV/PKI (S7), env config (S0) |
| Vulnerability mgmt | CC7.1, A.12.6 | Trivy in CI + SBOM (10B) |
| Availability / DR | CC7/CC9, A.17 | HA manifests (9K), backups + verified restore (9-Data/10E) |
| Change management | CC8 | CI/CD signed images + atomic deploy/rollback (10B) |
| Monitoring | CC7.2 | Prometheus/Grafana/Alertmanager + SLO alerts (10C) |

**Gaps to GA:** formal SOC 2 Type II / ISO 27001 audit (evidence collection, policies,
pentest), 24×7 on-call + support tiers, customer docs/onboarding, data-residency per tenant,
contractual DPAs (GDPR/NDPR).

---

## Result — roadmap complete (lab scope)

Group E closes the production roadmap at the lab/artifact level: **multi-tenancy is live and
verified**, and the analytics-productionization + GA/commercial path is designed with most
security/availability/observability controls **already built** in Groups A–D.

**What genuinely remains is real-world, not code:** run the **9L hardware pilot**, stand up
the **k8s cluster** (apply `k8s/` + Helm), build the **native mobile app**, integrate a real
**IdP + billing**, and complete a formal **SOC 2/ISO 27001 audit** — each unblocked by the
platform now in place.
