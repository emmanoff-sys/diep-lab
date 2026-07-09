# OA-072 — Integration Security Architecture

**Version:** 1.0.0
**Work Package:** WP-011-01
**Effective Date:** 2026-07-09

---

## 1. Security Principles

All Phase 2 integrations are governed by three security principles inherited
from the Phase 1 architecture freeze:

1. **No write-back.** The RE-OS platform never sends commands to external
   systems. Data flows inward only.
2. **Least privilege.** Connectors authenticate to Phase 1 ingestion services
   with the minimum credential scope required to submit events.
3. **Fail closed.** If a connector cannot authenticate or validate a message,
   it rejects the message and alerts — it does not fall back to an open state.

---

## 2. OT/IT Network Boundary

### 2.1 SCADA (OT) Boundary

SCADA systems operate on Operational Technology networks, which must be
air-gapped or one-way-isolated from the IT network hosting RE-OS.

**Required control:** a hardware data diode or a unidirectional security
gateway between the SCADA LAN and the connector host. The RE-OS platform
must have no routable path back to the SCADA LAN.

```
SCADA LAN (OT)
      │
  [Data Diode / Unidirectional Gateway]
      │  ── one way only, hardware-enforced ──►
      │
  [Connector Host] (DMZ / integration zone)
      │
  [RE-OS Ingestion Services] (IT / cloud)
```

### 2.2 GIS, OMS, AMI Boundary

These are IT systems. Connectors connect to them over the corporate network
or via dedicated APIs with mTLS.

No data diode is required, but the connector host must be network-segmented
from the SCADA LAN — the connector host must not bridge OT and IT.

---

## 3. Authentication

### 3.1 Connector → Phase 1 Ingestion Services

Connectors authenticate to Phase 1 services using **mTLS (mutual TLS)**
client certificates:

- Each connector instance holds a unique client certificate issued by the
  RE-OS internal CA.
- The Phase 1 ingestion service validates the client certificate against the
  CA trust bundle.
- The certificate's Common Name encodes the connector identity (used as the
  `actor` field in `OperationalEvent`).
- Certificates rotate on a 90-day schedule; rotation does not require connector
  restart (certificate hot-swap via filesystem mount).

### 3.2 External System → Connector

The connector authenticates to the external system using the authentication
mechanism native to that system's protocol:

| System | Recommended Authentication |
|--------|---------------------------|
| SCADA (IEC 61850) | IEC 62351-3 TLS profile |
| SCADA (DNP3) | DNP3 Secure Authentication v5 |
| SCADA (IEC 60870-5-104) | TLS with pre-shared keys (minimal) |
| GIS (OGC WFS REST) | OAuth 2.0 client credentials |
| OMS (REST API) | OAuth 2.0 client credentials |
| AMI headend (REST) | OAuth 2.0 client credentials or API key |

Specific authentication mechanism per work package is confirmed at the
WP-level PAO, not here.

### 3.3 External Consumers → Operator API v1

External consumers (SCADA displays, mobile apps, reporting tools) authenticate
with bearer tokens. The token is mapped to an `OperatorPrincipal` by the
`StaticTokenAuthenticator` (WP-013-02). Production deployment will replace
the static token map with an identity provider integration — this is a
deployment-time concern, not a WP-011-01 concern.

---

## 4. Authorisation

| Actor | Can access | Cannot access |
|-------|-----------|--------------|
| SCADA connector | `OperationalEventProcessor.process()` | Topology read, audit trail, Operator API write |
| GIS adapter | `topology/publish` endpoint (WP-006) | Operational state, analytics, Operator API write |
| OMS adapter | `OperationalIntelligenceService` constructor (history tuple) | Live state, topology write, Operator API |
| AMI connector | `OperationalEventProcessor.process()` | Same as SCADA connector |
| External read consumer | `GET /api/v1/...` (Operator API v1) | Any write path, ingestion services |

---

## 5. Secret Management

All connector secrets (client certificates, OAuth client credentials, API keys)
must:

1. Be injected at runtime via environment variables or a secrets manager (e.g.
   HashiCorp Vault, Kubernetes Secrets).
2. Never be embedded in source code, configuration files committed to the
   repository, or log output.
3. Be rotated on a schedule defined per secret type (certificates: 90 days;
   OAuth secrets: 180 days; API keys: on-demand).
4. Follow the RE-OS secret naming convention: `REOS_<CONNECTOR>_<PURPOSE>_<TYPE>`
   (e.g. `REOS_SCADA_IEC61850_CLIENT_CERT`).

---

## 6. Audit Requirements

Every connector must produce a structured audit log of its own activity,
separate from the RE-OS `OperationsAuditTrail`. The connector audit log must
record:

| Event | Required Fields |
|-------|----------------|
| Message received | `received_at`, `source`, `message_type`, `asset_id` |
| Contract submitted | `submitted_at`, `contract_type`, `result` (accepted/rejected), `reason` |
| Connection established / lost | `occurred_at`, `endpoint`, `event` |
| Authentication failure | `occurred_at`, `source`, `reason` |
| Degraded state entered / exited | `occurred_at`, `trigger`, `rejection_count` |

The connector audit log is append-only, structured JSON, and must be shipped
to the platform's logging infrastructure (out of scope for WP-011-01;
each connector PAO specifies the log destination).

---

## 7. Certificate Trust Architecture

```
RE-OS Internal CA
      │
      ├── Connector Client Cert (per instance)  ← issued to each connector
      ├── RE-OS Ingestion Server Cert            ← presented by Phase 1 services
      └── External System CA (trusted)           ← external CA imported at deployment
```

The RE-OS Internal CA is operated by the Platform team (outside WP-011-01
scope). Each connector work package must specify:
- the CN format for its client certificate;
- the CA rotation procedure;
- the certificate mount path on the connector host.

---

## 8. Security Requirements Checklist (Per Connector PAO)

Each future connector work package (WP-011-02 onwards) must address:

- [ ] OT/IT boundary control identified and approved
- [ ] Authentication mechanism to external system confirmed
- [ ] mTLS client certificate CN format specified
- [ ] Secret naming convention followed
- [ ] Audit log fields defined and shipping destination named
- [ ] No write-back path to external system
- [ ] No hardcoded credentials in repository
- [ ] Bandit scan clean on connector package
- [ ] CodeQL clean on connector package
