# Engineering Specification — WP-005-04: Audit Service
## Immutable Platform Audit Log
### DAEP / RE-OS Programme | EPIC-005 — Platform Foundation

| Field | Value |
|-------|-------|
| Document ID | ENG-SPEC-005-04 |
| EECR Reference | EECR-R01-005-04 |
| WP ID | WP-005-04 |
| Version | 1.0 |
| Status | **APPROVED** — AR-051 (2026-07-04) |
| Prepared By | Enterprise Architect / PMO (AI-assisted: claude-sonnet-4-6) |
| Date | 2026-07-04 |
| Classification | Internal — Confidential |
| Supersedes | WP-005-04 v0.1 DRAFT (scratchpad, prior session) |
| Governance Note | EECR-CHG-063 re-titled WP-005-04 from "Login / Logout / Refresh Endpoints" to "Audit Service — Immutable Platform Audit Log". No WP renumbering. LLD ref updated from §7.4 to §7.6. |

---

> **STOP CONDITION:** This document is the implementation contract for WP-005-04. No source code may be committed to `feature/iam-audit-service` until this specification carries APPROVED status. Implementation begins only after EECR-CHG-066 records the implementation-ready gate.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Requirements](#2-business-requirements)
3. [Functional Requirements](#3-functional-requirements)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Security Requirements](#5-security-requirements)
6. [Compliance Requirements](#6-compliance-requirements)
7. [Architecture](#7-architecture)
8. [Data Model](#8-data-model)
9. [Database Schema](#9-database-schema)
10. [Kafka Event Model](#10-kafka-event-model)
11. [API Specification](#11-api-specification)
12. [Permission Model](#12-permission-model)
13. [Audit Event Taxonomy](#13-audit-event-taxonomy)
14. [Retention Policy](#14-retention-policy)
15. [Encryption Strategy](#15-encryption-strategy)
16. [Search and Query Requirements](#16-search-and-query-requirements)
17. [Reporting Requirements](#17-reporting-requirements)
18. [Metrics](#18-metrics)
19. [Logging](#19-logging)
20. [Tracing](#20-tracing)
21. [Health Checks](#21-health-checks)
22. [Performance Targets](#22-performance-targets)
23. [Capacity Targets](#23-capacity-targets)
24. [Configuration](#24-configuration)
25. [Deployment Requirements](#25-deployment-requirements)
26. [Testing Requirements](#26-testing-requirements)
27. [Deliverables](#27-deliverables)
28. [Acceptance Criteria](#28-acceptance-criteria)
29. [Definition of Done](#29-definition-of-done)
30. [Architecture Traceability](#30-architecture-traceability)
31. [Risks](#31-risks)
32. [Open Questions](#32-open-questions)

---

## 1. Executive Summary

### 1.1 Purpose

WP-005-04 delivers the RE-OS Audit Service — a standalone FastAPI microservice providing an immutable, tamper-evident, cryptographically-verified audit log for the DAEP / RE-OS platform. The service is the system of record for all security-relevant events: authentication, authorisation, identity lifecycle, RBAC mutations, and audit-log access itself.

### 1.2 Business Objective

The DAEP / RE-OS platform operates on critical energy infrastructure and handles privileged engineering operations, financial data, and PII. Regulatory requirements (BRS v1.0 Vol.3 §Audit, §Retention, §Privacy) mandate:
- A durable, append-only record of all security-relevant events
- Minimum 7-year retention with automated partition management
- Cryptographic tamper-detection to support forensic investigation
- Audit-log reads are themselves audited (chain of custody)

### 1.3 Scope

**In scope:**
- New `services/audit-service/` microservice (Python 3.11, FastAPI, port 8004)
- `audit` PostgreSQL schema with TimescaleDB hypertable on `timestamp_utc`
- Kafka consumer for `iam.audit.events` (new) and `user.registered` (existing)
- REST Write API (internal service-to-service, service JWT audience `reos-internal`)
- REST Query API (admin users, `admin:audit` permission, user JWT audience `reos`)
- Hash chain verify endpoint
- Prometheus metrics, structured logging, health endpoints, alertmanager rules
- Identity-service producer modifications (emit `iam.audit.events` from `auth.py`, `mfa.py`, `roles.py`, `users_admin.py`)
- Alembic migration including immutability trigger and TimescaleDB hypertable

**Out of scope:**
- Topology audit stamping (WP-006-06)
- Metering data access audit (R2)
- SIEM / external log forwarding (R3+)
- Audit UI / reporting dashboard (future WP)
- PII masking background job (future WP — schema supports nullable PII columns)
- Encryption at rest beyond host-level (R12 EPIC-047)

### 1.4 Dependencies

| Dependency | WP/Component | Status | Notes |
|-----------|------|--------|-------|
| Identity Service | WP-005-01 | **APPROVED** | JWT, JWKS, `admin:audit` seeded, user schema |
| MFA | WP-005-02 | **APPROVED** | MFA events to capture |
| RBAC | WP-005-03 | **APPROVED** | `RequirePermission("admin:audit")` pattern |
| Shared Platform Libraries | EPIC-002 | **APPROVED** | structlog, exceptions, BaseSettings |
| PostgreSQL + TimescaleDB | Infra | **OPERATIONAL** | `audit` schema; hypertable on `timestamp_utc` |
| Kafka | Infra | **OPERATIONAL** | New: `iam.audit.events`; existing: `user.registered` |
| HashiCorp Vault | Infra | **OPERATIONAL** | AppRole credentials for audit-service DB access |

---

## 2. Business Requirements

### 2.1 Regulatory Driver

BRS v1.0 Vol.3 §Audit mandates that the platform maintain a tamper-evident, append-only log of all security-relevant operations for minimum 7 years. Audit-log data must be available for forensic investigation, compliance reporting, and incident response within a reasonable access time.

### 2.2 Stakeholder Requirements

| Stakeholder | Requirement |
|-------------|------------|
| Compliance / Legal | 7-year retention; records must capture who, what, on what resource, outcome, when, from where |
| Security Operations | Hash chain verification; correlation-ID tracing across services; meta-audit of audit reads |
| Engineering / SRE | Prometheus metrics; Kafka consumer health; DLQ alerting |
| Platform Administrators | Query API with filtering; pagination; single-event lookup by ID |
| Privacy / Data Protection | PII fields (IP, UA, username) anonymised after 2 years; no PII in logs |

### 2.3 Governance Constraint

Per GOV-002 (ADR register): AI agents cannot self-approve or self-merge. This specification governs implementation by human engineers. No autonomous deployment to production.

---

## 3. Functional Requirements

| ID | Requirement | Source |
|----|------------|--------|
| AUD-FR-001 | Record every authentication event: login success/failure, account lockout, MFA challenge issued/passed/failed/lockout, token refresh, token revocation | BRS v1.0 Vol.3 §Audit |
| AUD-FR-002 | Record every user lifecycle event: registration, deactivation, reactivation, password change, password reset | BRS v1.0 Vol.3 §Audit |
| AUD-FR-003 | Record every RBAC event: role assigned/removed, role created/deleted, permission assigned/removed | BRS v1.0 Vol.3 §Audit |
| AUD-FR-004 | Record every access to the audit query API — audit-log reads are themselves audited (meta-audit, event type `audit.log.queried`) | SRS v1.0 §Audit Logging |
| AUD-FR-005 | Audit events SHALL be append-only — no UPDATE or DELETE permitted at any layer; enforced by PostgreSQL trigger `tg_audit_events_immutable` | SRS v1.0 §Audit Logging |
| AUD-FR-006 | Each event record SHALL carry: `event_id`, `event_type`, `actor_type`, `actor_id`, `action`, `resource_type`, `resource_id`, `outcome`, `timestamp_utc`, `correlation_id`, `service_name`, `prev_event_hash`, `event_hash`, `metadata` | SRS v1.0 §Audit Logging |
| AUD-FR-007 | Query API SHALL filter by: `actor_id`, `event_type`, `action`, `resource_type`, `resource_id`, `outcome`, `service_name`, `correlation_id`, date range | SRS v1.0 §Audit Logging |
| AUD-FR-008 | Query API accessible only to holders of the `admin:audit` permission (already seeded in WP-005-01 migration `0001_initial_schema.py`) | SRS v1.0 §RBAC; WP-005-03 |
| AUD-FR-009 | Query API SHALL support cursor-based pagination; maximum `page_size` = 200 events | SRS v1.0 §Audit Logging |
| AUD-FR-010 | Write API authenticated via service JWT with audience `reos-internal`; user JWTs rejected with 403 | SRS v1.0 §Audit Logging |
| AUD-FR-011 | Each event SHALL include SHA-256 hash of the previous event in the same actor partition; first event in partition uses sentinel `"GENESIS"` | SRS v1.0 §Audit Logging |
| AUD-FR-012 | Expose `GET /api/v1/audit/verify-chain/{partition_type}/{partition_key}` to verify hash chain integrity; returns broken-at event ID when tampered | SRS v1.0 §Audit Logging |
| AUD-FR-013 | Consume Kafka `iam.audit.events` and `user.registered`; persist as audit records | SRS v1.0 §Audit Logging |
| AUD-FR-014 | Kafka consumer uses at-least-once delivery; duplicate delivery handled via `event_id` unique constraint (idempotent INSERT OR IGNORE) | SRS v1.0 §Audit Logging |
| AUD-FR-015 | Identity-service MUST emit `iam.audit.events` Kafka messages for all auth/MFA/RBAC operations | SRS v1.0 §Audit Logging; LLD v2.0 §7.6 |
| AUD-FR-016 | Chain verify endpoint generates an `audit.chain.verified` audit event recording the verification itself | SRS v1.0 §Audit Logging |

---

## 4. Non-Functional Requirements

| ID | Requirement | Target | Verification |
|----|------------|--------|-------------|
| AUD-NFR-001 | REST write P95 latency | < 50 ms | Integration test + k6 |
| AUD-NFR-002 | REST query P95 (30-day single-actor window, no full-text) | < 200 ms | Integration test |
| AUD-NFR-003 | Kafka consumer steady-state lag | < 100 messages | Prometheus gauge |
| AUD-NFR-004 | Service startup (readiness probe passes) | < 10 s | CI smoke test |
| AUD-NFR-005 | Write throughput | 500 events/s @ P95 < 50 ms | k6 load test |
| AUD-NFR-006 | Audit event retention | 7 years minimum | TimescaleDB retention policy |
| AUD-NFR-007 | Write API availability | ≥ 99.9% | SRE monitoring |
| AUD-NFR-008 | Code coverage | ≥ 80% line/module | CI coverage gate |
| AUD-NFR-009 | Startup memory footprint | < 256 MB RSS | CI smoke test |
| AUD-NFR-010 | JWKS cache TTL | 300 s (configurable) | Unit test |

---

## 5. Security Requirements

| ID | Requirement | Source |
|----|------------|--------|
| AUD-SEC-001 | PostgreSQL trigger `tg_audit_events_immutable` fires BEFORE UPDATE OR DELETE on `audit.audit_events` and raises exception — no application code path can bypass | SRS v1.0 §Audit Logging |
| AUD-SEC-002 | DB role for audit-service holds INSERT + SELECT only on `audit.audit_events`; UPDATE and DELETE not granted at DB level | VAULT_STANDARDS.md |
| AUD-SEC-003 | Write API requires service JWT (RS256, aud=`reos-internal`); user JWTs rejected | SRS v1.0 §Audit Logging |
| AUD-SEC-004 | Query API requires user JWT (RS256, aud=`reos`) with `admin:audit` permission | WP-005-03 RBAC |
| AUD-SEC-005 | JWKS fetched from identity-service `/api/v1/jwks`; cached 300 s; RS256 only — HS256 rejected with clear error | WP-005-03 |
| AUD-SEC-006 | Hash chain computed server-side; `event_hash = SHA-256(canonical)` stored in non-nullable column | SRS v1.0 §Audit Logging |
| AUD-SEC-007 | DB credentials stored in Vault (AppRole); retrieved at startup from tmpfs; never in environment variables or application logs | VAULT_STANDARDS.md |
| AUD-SEC-008 | PII fields (`actor_ip_address`, `actor_user_agent`, `actor_username`) SHALL NOT appear in any structlog log line at any level | STANDARDS.md §4 |
| AUD-SEC-009 | `metadata` JSONB column MUST NOT contain credentials, secrets, tokens, or PII — enforced by code review and Bandit scanning | STANDARDS.md §4 |
| AUD-SEC-010 | All SQL queries MUST use SQLAlchemy parameterised queries — no raw string interpolation in repository layer | STANDARDS.md §5 |
| AUD-SEC-011 | Service-to-service JWT issued by identity-service using `create_service_jwt(aud="reos-internal", sub=<service-name>)` — audit-service validates aud claim only (no permission check for writes) | WP-005-01 |

---

## 6. Compliance Requirements

| ID | Requirement | Regulatory Source |
|----|------------|------------------|
| AUD-COMP-001 | Minimum 7-year retention; TimescaleDB retention policy `add_retention_policy(INTERVAL '84 months')` drops chunks older than 84 months | BRS v1.0 Vol.3 §Retention |
| AUD-COMP-002 | Records must capture: who (actor), what (action), on what resource (resource_type, resource_id), outcome, when (timestamp_utc), from where (actor_ip_address) | BRS v1.0 Vol.3 §Audit |
| AUD-COMP-003 | Hash chain integrity verifiable on demand by `admin:audit` holders — verify-chain endpoint | BRS v1.0 Vol.3 §Audit |
| AUD-COMP-004 | Audit log reads generate audit events (meta-audit — chain of custody for compliance reports) | SRS v1.0 §Audit Logging |
| AUD-COMP-005 | PII fields anonymised after 2 years from `timestamp_utc` — background job (future WP); schema supports nullable PII columns to accommodate post-anonymisation state | BRS v1.0 Vol.3 §Privacy |
| AUD-COMP-006 | `event_id` must be a producer-assigned UUID; enables idempotent replay in compliance investigations | SRS v1.0 §Audit Logging |

---

## 7. Architecture

### 7.1 Logical Architecture

```
identity-service  ──iam.audit.events (Kafka, keyed: actor_id)──►  audit-service ──► PostgreSQL
(WP-005-01/02/03)  ──user.registered  (Kafka, keyed: user_id)──►       │           audit.audit_events
                                                                          │           audit.chain_state
future-services   ──POST /api/v1/audit/events (REST, svc JWT)───────────►│
                                                                          │
admin/auditor     ──GET  /api/v1/audit/events (Bearer user JWT) ─────────►│
                   ──GET  /api/v1/audit/verify-chain/{type}/{key} ────────►│
                                                                           │
identity-service   ◄──GET /api/v1/jwks (cached 300s) ─────────────────── │
Vault              ◄──AppRole login/secret ──────────────────────────────  │
```

### 7.2 Component Inventory

| Component | Location | Responsibility |
|-----------|----------|---------------|
| `audit-service` | `services/audit-service/` | Main microservice (FastAPI, port 8004) |
| `AuditEventRepository` | `domain/repositories.py` | DB write and query; no update/delete methods |
| `AuditService` | `domain/services.py` | Business logic: write, query, verify chain, meta-audit |
| `HashChain` | `core/hash_chain.py` | SHA-256 chain computation and verification |
| `JWKSCache` | `core/security.py` | JWKS fetch, 300s cache, RS256 decode |
| `AuditConsumer` | `core/kafka.py` | AIOKafka consumer lifecycle, dispatch, retry, DLQ |
| Write API | `api/v1/endpoints/internal.py` | POST /audit/events |
| Query API | `api/v1/endpoints/audit_events.py` | GET /audit/events, GET /audit/events/{id}, GET /verify-chain |
| Health API | `api/v1/endpoints/health.py` | GET /health/live, GET /health/ready |

### 7.3 Sequence: Kafka Ingestion (Happy Path)

```
identity-service    Kafka broker        audit-service              PostgreSQL
      │                 │                     │                        │
      │──publish ──────►│ iam.audit.events     │                        │
      │                 │──deliver ───────────►│                        │
      │                 │                      │─ validate schema        │
      │                 │                      │─ compute event_hash     │
      │                 │                      │─ BEGIN TRANSACTION ────►│
      │                 │                      │─ INSERT audit_events ──►│
      │                 │                      │─ UPSERT chain_state ───►│
      │                 │                      │─ COMMIT ───────────────►│
      │                 │◄── commit offset ────│                        │
```

### 7.4 Sequence: REST Write (Synchronous)

```
internal-svc    audit-service          identity-service         PostgreSQL
      │               │  validate JWT (RS256)  │                    │
      │──POST /events─►│ ──GET /jwks ─────────►│                    │
      │  service JWT   │ ◄─JWKS ──────────────│                    │
      │                │  check aud=reos-int   │                    │
      │                │  compute event_hash   │                    │
      │                │──INSERT ──────────────────────────────────►│
      │                │──UPSERT chain_state ──────────────────────►│
      │◄── 201 ────────│                                            │
```

### 7.5 Sequence: REST Query + Meta-Audit

```
admin-client   audit-service         identity-service         PostgreSQL
      │               │  validate JWT (RS256)  │                    │
      │──GET /events──►│ ──GET /jwks ─────────►│                    │
      │  user JWT      │ ◄─JWKS ──────────────│                    │
      │                │  check admin:audit    │                    │
      │                │──SELECT events ──────────────────────────►│
      │◄── 200 ────────│◄──rows ──────────────────────────────────│
      │                │──INSERT audit.log.queried meta-event ─────►│
```

### 7.6 Service Interactions

| Interaction | Protocol | Auth | Direction |
|------------|---------|------|-----------|
| identity-service → `iam.audit.events` | Kafka / TLS | SASL/SCRAM | identity-service outbound |
| audit-service ← Kafka | Kafka / TLS | SASL/SCRAM | audit-service consumer |
| internal-service → audit REST write | HTTPS | Service JWT (aud: `reos-internal`) | inbound |
| admin client → audit REST query | HTTPS | User JWT (aud: `reos`) | inbound |
| audit-service → identity-service JWKS | HTTPS | None (public endpoint) | outbound |
| audit-service → PostgreSQL | TCP / TLS | Vault AppRole credentials | outbound |
| audit-service → Vault | HTTPS | AppRole role-id / secret-id (tmpfs) | outbound |

---

## 8. Data Model

### 8.1 `audit.audit_events` — Column Definitions

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | UUID | NOT NULL | PK; `gen_random_uuid()` default |
| `event_id` | UUID | NOT NULL | Producer-assigned; globally unique (UNIQUE constraint) |
| `event_type` | TEXT | NOT NULL | Dotted namespace: `auth.login.success` |
| `actor_type` | TEXT | NOT NULL | `user` \| `service` \| `system` |
| `actor_id` | UUID | NOT NULL | User UUID or service identifier UUID |
| `actor_username` | TEXT | NULL | Human-readable label; PII |
| `actor_ip_address` | INET | NULL | Client IP; PII |
| `actor_user_agent` | TEXT | NULL | HTTP User-Agent string; PII |
| `action` | TEXT | NOT NULL | Verb: `login`, `role.assigned`, `audit.query` |
| `resource_type` | TEXT | NOT NULL | `session` \| `user` \| `role` \| `audit_log` \| etc. |
| `resource_id` | TEXT | NULL | Resource identifier (string representation) |
| `outcome` | TEXT | NOT NULL | `success` \| `failure` \| `denied` |
| `outcome_reason` | TEXT | NULL | Detail for failures/denials |
| `correlation_id` | UUID | NOT NULL | X-Correlation-ID from originating request |
| `session_id` | TEXT | NULL | Opaque session reference |
| `service_name` | TEXT | NOT NULL | Originating service identifier |
| `service_version` | TEXT | NULL | Semver string of originating service |
| `prev_event_hash` | TEXT | NULL | NULL only for first event in partition (GENESIS) |
| `event_hash` | TEXT | NOT NULL | SHA-256 of canonical fields (§8.2) |
| `metadata` | JSONB | NULL | Additional context; no PII; max 4096 bytes serialised |
| `timestamp_utc` | TIMESTAMPTZ | NOT NULL | Event occurrence time (UTC-aware; producer-set) |
| `ingested_at_utc` | TIMESTAMPTZ | NOT NULL | DB insertion time (`DEFAULT NOW()`) |
| `schema_version` | SMALLINT | NOT NULL | Schema contract version; default 1 |

**Primary Key:** `(id, timestamp_utc)` — composite required by TimescaleDB hypertable.

### 8.2 Hash Chain Computation

```
canonical = "|".join([
    str(event_id),
    event_type,
    str(actor_id),
    action,
    outcome,
    timestamp_utc.isoformat(),          # ISO 8601 with UTC offset
    prev_event_hash or "GENESIS"
])
event_hash = sha256(canonical.encode("utf-8")).hexdigest()
```

**Rules:**
- All fields used in canonical string are immutable once written
- `timestamp_utc` must be UTC-aware (timezone offset +00:00 required in isoformat)
- Hash computed server-side at write time before INSERT
- First event in each actor partition has `prev_event_hash = NULL`; uses sentinel `"GENESIS"` in computation

### 8.3 `audit.chain_state` — Column Definitions

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `partition_type` | TEXT | NOT NULL | PK component: `actor` \| `date` |
| `partition_key` | TEXT | NOT NULL | PK component: actor UUID string or `YYYY-MM-DD` |
| `last_event_id` | UUID | NOT NULL | Most recent event in partition |
| `last_event_hash` | TEXT | NOT NULL | Hash of most recent event |
| `event_count` | BIGINT | NOT NULL | Running count of events in partition |
| `first_event_at` | TIMESTAMPTZ | NOT NULL | Timestamp of first event |
| `last_event_at` | TIMESTAMPTZ | NOT NULL | Timestamp of last event |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()`, updated on each INSERT |

**Primary Key:** `(partition_type, partition_key)` — supports both actor and date partitions.

---

## 9. Database Schema

### 9.1 Full DDL (Alembic migration `0001_create_audit_schema.py`)

```sql
-- Step 1: Schema
CREATE SCHEMA IF NOT EXISTS audit;

-- Step 2: Main events table
CREATE TABLE audit.audit_events (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
    event_id            UUID         NOT NULL,
    event_type          TEXT         NOT NULL,
    actor_type          TEXT         NOT NULL CHECK (actor_type IN ('user','service','system')),
    actor_id            UUID         NOT NULL,
    actor_username      TEXT,
    actor_ip_address    INET,
    actor_user_agent    TEXT,
    action              TEXT         NOT NULL,
    resource_type       TEXT         NOT NULL,
    resource_id         TEXT,
    outcome             TEXT         NOT NULL CHECK (outcome IN ('success','failure','denied')),
    outcome_reason      TEXT,
    correlation_id      UUID         NOT NULL,
    session_id          TEXT,
    service_name        TEXT         NOT NULL,
    service_version     TEXT,
    prev_event_hash     TEXT,
    event_hash          TEXT         NOT NULL,
    metadata            JSONB,
    timestamp_utc       TIMESTAMPTZ  NOT NULL,
    ingested_at_utc     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    schema_version      SMALLINT     NOT NULL DEFAULT 1,
    PRIMARY KEY (id, timestamp_utc)
);

-- Step 3: Unique constraint for idempotency
ALTER TABLE audit.audit_events
    ADD CONSTRAINT uq_audit_events_event_id UNIQUE (event_id);

-- Step 4: Indexes
CREATE INDEX ix_audit_events_actor_id
    ON audit.audit_events (actor_id, timestamp_utc DESC);
CREATE INDEX ix_audit_events_event_type
    ON audit.audit_events (event_type, timestamp_utc DESC);
CREATE INDEX ix_audit_events_resource
    ON audit.audit_events (resource_type, resource_id, timestamp_utc DESC);
CREATE INDEX ix_audit_events_correlation_id
    ON audit.audit_events (correlation_id);
CREATE INDEX ix_audit_events_outcome
    ON audit.audit_events (outcome, timestamp_utc DESC);
CREATE INDEX ix_audit_events_service_name
    ON audit.audit_events (service_name, timestamp_utc DESC);
CREATE INDEX ix_audit_events_metadata
    ON audit.audit_events USING GIN (metadata);

-- Step 5: TimescaleDB hypertable (1-month chunks)
SELECT create_hypertable(
    'audit.audit_events', 'timestamp_utc',
    chunk_time_interval => INTERVAL '1 month'
);

-- Step 6: Retention policy (7 years = 84 months)
SELECT add_retention_policy('audit.audit_events', INTERVAL '84 months');

-- Step 7: Compression (after 7 days; ~10x compression ratio expected)
ALTER TABLE audit.audit_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'actor_id',
    timescaledb.compress_orderby = 'timestamp_utc DESC'
);
SELECT add_compression_policy('audit.audit_events', INTERVAL '7 days');

-- Step 8: Immutability trigger function
CREATE OR REPLACE FUNCTION audit.prevent_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'audit_events is append-only: UPDATE and DELETE are permanently prohibited. '
        'Raise a programme ECR if PII anonymisation requires a controlled exception.';
END;
$$;

-- Step 9: Immutability trigger
CREATE TRIGGER tg_audit_events_immutable
    BEFORE UPDATE OR DELETE ON audit.audit_events
    FOR EACH ROW EXECUTE FUNCTION audit.prevent_mutation();

-- Step 10: Chain state table
CREATE TABLE audit.chain_state (
    partition_type  TEXT         NOT NULL,
    partition_key   TEXT         NOT NULL,
    last_event_id   UUID         NOT NULL,
    last_event_hash TEXT         NOT NULL,
    event_count     BIGINT       NOT NULL DEFAULT 0,
    first_event_at  TIMESTAMPTZ  NOT NULL,
    last_event_at   TIMESTAMPTZ  NOT NULL,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (partition_type, partition_key)
);
```

### 9.2 Downgrade Warning

The `downgrade()` function in the Alembic migration MUST include a prominent comment:

```python
# !! DESTRUCTIVE !! Drops audit.audit_events (ALL AUDIT RECORDS) and audit.chain_state.
# Downgrade is IRREVERSIBLE. Requires explicit Project Owner authorisation.
# Document authorisation in EECR change log before executing.
```

### 9.3 DB Role Permissions

The audit-service DB role (provisioned via Vault AppRole) receives:
- `CONNECT` on the `audit` database
- `USAGE` on schema `audit`
- `SELECT, INSERT` on `audit.audit_events`
- `SELECT, INSERT, UPDATE` on `audit.chain_state` (chain state requires UPSERT)
- `EXECUTE` on `audit.prevent_mutation` — NOT granted UPDATE/DELETE on the table

---

## 10. Kafka Event Model

### 10.1 Topics

| Topic | Type | Partitions | RF | Min ISR | Key | Value |
|-------|------|-----------|-----|---------|-----|-------|
| `iam.audit.events` | New | 6 | 3 | 2 | `actor_id` (UTF-8 string) | JSON — `AuditEventCreate` schema |
| `user.registered` | Existing | (existing) | (existing) | (existing) | `user_id` | Existing schema |
| `audit.dead.events` | New (DLQ) | 3 | 3 | 2 | same as source | Original message bytes + error metadata |

### 10.2 `iam.audit.events` Message Schema

```json
{
  "event_id":         "<UUID>",
  "event_type":       "auth.login.success",
  "actor_type":       "user",
  "actor_id":         "<UUID>",
  "actor_username":   "<string|null>",
  "actor_ip_address": "<string|null>",
  "actor_user_agent": "<string|null>",
  "action":           "login",
  "resource_type":    "session",
  "resource_id":      "<string|null>",
  "outcome":          "success",
  "outcome_reason":   "<string|null>",
  "correlation_id":   "<UUID>",
  "session_id":       "<string|null>",
  "service_name":     "identity-service",
  "service_version":  "<semver|null>",
  "metadata":         { "<key>": "<value>" },
  "timestamp_utc":    "2026-07-04T10:00:00.000Z",
  "schema_version":   1
}
```

**Producer rules:**
- `event_id` = fresh `uuid4()` per event — callers MUST use the same value on retry
- `timestamp_utc` = event occurrence time (NOT ingestion time); UTC-aware
- `correlation_id` = request `X-Correlation-ID` header; generate `uuid4()` if absent
- Producer failure is non-fatal — log ERROR and continue (audit loss is preferable to service outage)

### 10.3 Identity-Service Producer Modifications

| File | Required Change |
|------|----------------|
| `config.py` | Add `KAFKA_IAM_AUDIT_EVENTS_TOPIC: str = "iam.audit.events"` |
| `core/kafka.py` | Add `publish_iam_audit_event(event: dict[str, object]) -> None` (mirrors `publish_user_registered` pattern) |
| `api/v1/auth.py` | Emit after: login success, login failure, account lockout, token exchange, token refresh, token revocation |
| `api/v1/mfa.py` | Emit after: MFA challenge issued, MFA verified, MFA failed, MFA lockout, admin unlock |
| `api/v1/roles.py` | Emit after: role assigned to user, role removed from user, role created, role deleted |
| `api/v1/users_admin.py` | Emit after: user deactivated, user activated |

**Emission timing:** Publish AFTER the business action succeeds and DB transaction commits. For failure events, publish after recording the failure state. Producer call is fire-and-forget wrapped in `asyncio.create_task`.

### 10.4 Consumer Configuration

```python
consumer = AIOKafkaConsumer(
    settings.KAFKA_IAM_AUDIT_EVENTS_TOPIC,
    settings.KAFKA_USER_EVENTS_TOPIC,
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    group_id=settings.KAFKA_CONSUMER_GROUP_ID,     # "audit-service-consumer"
    auto_offset_reset="earliest",
    enable_auto_commit=False,                       # manual commit AFTER DB commit
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    max_poll_records=100,                           # batch for throughput
    session_timeout_ms=30_000,
    heartbeat_interval_ms=10_000,
)
```

### 10.5 Retry and Dead-Letter Behaviour

| Condition | Behaviour |
|-----------|-----------|
| DB write fails (transient) | Retry: 1 s → 2 s → 4 s (3 attempts total; exponential backoff) |
| Duplicate `event_id` | ON CONFLICT DO NOTHING — idempotent success; commit offset |
| 3 retries exhausted | Publish to `audit.dead.events` DLQ; commit source offset; increment `audit_dlq_events_total` counter |
| Schema validation failure | Log ERROR with schema diff; publish to DLQ; commit offset (consumer does not halt on bad messages) |
| DLQ publish fails | Log CRITICAL; skip offset commit; pause partition 30 s; retry DLQ publish |
| Consecutive DLQ publish failures > 5 | Fire `AuditDLQUnrecoverable` alert; manual intervention required |

---

## 11. API Specification

### 11.1 Endpoint Summary

| Method | Path | Auth | Permission | Response | Side Effect |
|--------|------|------|------------|----------|-------------|
| `POST` | `/api/v1/audit/events` | Service JWT (`reos-internal`) | aud claim | 201 / 409 | INSERT event + UPSERT chain |
| `GET` | `/api/v1/audit/events` | User JWT (`reos`) | `admin:audit` | 200 paginated | INSERT `audit.log.queried` meta-event |
| `GET` | `/api/v1/audit/events/{event_id}` | User JWT (`reos`) | `admin:audit` | 200 / 404 | No meta-event (single-record lookup) |
| `GET` | `/api/v1/audit/verify-chain/{type}/{key}` | User JWT (`reos`) | `admin:audit` | 200 | INSERT `audit.chain.verified` meta-event |
| `GET` | `/api/v1/health/live` | None | None | 200 | None |
| `GET` | `/api/v1/health/ready` | None | None | 200 / 503 | None |

### 11.2 POST /api/v1/audit/events

**Request body:** `AuditEventCreate` (see §11.5)

**Response codes:**

| Code | Condition |
|------|-----------|
| 201 | Event persisted; body: `AuditEventResponse` |
| 400 | Schema validation error; body: `ErrorResponse` with field-level detail |
| 401 | Missing or malformed JWT |
| 403 | JWT audience is not `reos-internal` |
| 409 | `event_id` already exists; body: existing `AuditEventResponse` (idempotent) |
| 500 | DB write failure after 3 retries |

### 11.3 GET /api/v1/audit/events

**Query parameters:**

| Parameter | Type | Default | Constraint |
|-----------|------|---------|-----------|
| `actor_id` | UUID | — | Optional filter |
| `event_type` | string | — | Exact match |
| `action` | string | — | Exact match |
| `resource_type` | string | — | Exact match |
| `resource_id` | string | — | Exact match |
| `outcome` | string | — | `success` \| `failure` \| `denied` |
| `service_name` | string | — | Exact match |
| `correlation_id` | UUID | — | Exact match |
| `date_from` | ISO 8601 UTC | 30 days ago | UTC-aware |
| `date_to` | ISO 8601 UTC | now | UTC-aware; ≥ `date_from` |
| `page` | int ≥ 1 | 1 | — |
| `page_size` | int 1–200 | 50 | Max 200 enforced server-side |
| `sort` | `asc` \| `desc` | `desc` | On `timestamp_utc` |

**Validation rules:**
- `date_to` ≥ `date_from`
- Maximum date range: 365 days (reject with `AUD_QUERY_DATE_RANGE_TOO_LARGE`)
- Naive datetimes rejected (must include UTC offset)

**Side effect:** Generates `audit.log.queried` event capturing querying actor, applied filters, result count, and query timestamp.

### 11.4 GET /api/v1/audit/verify-chain/{partition_type}/{partition_key}

**Path parameters:**
- `partition_type`: `actor` or `date`
- `partition_key`: actor UUID string (for `actor`) or `YYYY-MM-DD` (for `date`)

**Response body:**
```json
{
  "partition_type": "actor",
  "partition_key":  "550e8400-e29b-41d4-a716-446655440000",
  "chain_valid":    true,
  "events_checked": 1234,
  "broken_at_event_id": null,
  "broken_at_position": null,
  "verification_duration_ms": 245
}
```

When tampered: `chain_valid=false`, `broken_at_event_id=<UUID>`, `broken_at_position=<int>`.

### 11.5 AuditEventCreate Schema

```python
class AuditEventCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id:           UUID
    event_type:         Annotated[str, Field(max_length=100)]
    actor_type:         Literal["user", "service", "system"]
    actor_id:           UUID
    actor_username:     Annotated[str | None, Field(max_length=100)]  = None
    actor_ip_address:   Annotated[str | None, Field(max_length=45)]   = None
    actor_user_agent:   Annotated[str | None, Field(max_length=512)]  = None
    action:             Annotated[str, Field(max_length=100)]
    resource_type:      Annotated[str, Field(max_length=100)]
    resource_id:        Annotated[str | None, Field(max_length=255)]  = None
    outcome:            Literal["success", "failure", "denied"]
    outcome_reason:     Annotated[str | None, Field(max_length=500)]  = None
    correlation_id:     UUID
    session_id:         Annotated[str | None, Field(max_length=255)]  = None
    service_name:       Annotated[str, Field(max_length=100)]
    service_version:    Annotated[str | None, Field(max_length=50)]   = None
    metadata:           dict[str, object] | None = None
    timestamp_utc:      datetime           # UTC-aware; naive rejected by validator
    schema_version:     int = 1

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp_utc must be UTC-aware (naive datetimes rejected)")
        return v

    @field_validator("metadata")
    @classmethod
    def metadata_size_limit(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v)) > 4096:
            raise ValueError("metadata serialised size exceeds 4096 bytes")
        return v
```

### 11.6 Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `AUDIT_EVENT_DUPLICATE` | 409 | `event_id` already exists |
| `AUDIT_EVENT_NOT_FOUND` | 404 | Event ID not found |
| `AUDIT_QUERY_INVALID_DATE_RANGE` | 400 | `date_to` < `date_from` |
| `AUDIT_QUERY_DATE_RANGE_TOO_LARGE` | 400 | Range > 365 days |
| `AUDIT_QUERY_INVALID_DATETIME` | 400 | Naive datetime submitted |
| `AUDIT_CHAIN_NOT_FOUND` | 404 | No events in requested partition |
| `AUDIT_INVALID_PARTITION_TYPE` | 400 | `partition_type` not `actor` or `date` |
| `AUDIT_WRITE_UNAUTHORIZED` | 403 | JWT aud is not `reos-internal` |
| `AUDIT_READ_UNAUTHORIZED` | 403 | Missing `admin:audit` permission |

---

## 12. Permission Model

### 12.1 Permission Seeding

`admin:audit` permission is already seeded by WP-005-01 migration `0001_initial_schema.py`:
```python
("admin", "audit", "Access audit logs"),  # permission tuple: (namespace, action, description)
```
Assigned to system roles: `super_admin` (all permissions via wildcard) and `platform_admin` (explicit assignment).

The audit-service does NOT seed or manage permissions — it only validates the claim.

### 12.2 RBAC Matrix

| Operation | JWT Audience | Required Permission | Roles (WP-005-01 seeds) |
|-----------|-------------|--------------------|-----------------------|
| Write event (REST) | `reos-internal` | aud claim only | Internal services |
| Query events (list) | `reos` | `admin:audit` | `super_admin`, `platform_admin` |
| Get single event | `reos` | `admin:audit` | `super_admin`, `platform_admin` |
| Verify hash chain | `reos` | `admin:audit` | `super_admin`, `platform_admin` |
| Health endpoints | None | None | Unauthenticated |

### 12.3 JWT Validation Logic

**Write API (internal.py):**
```python
token = decode_rs256(raw_token, jwks_cache=jwks)
if token.audience != "reos-internal":
    raise AuditWriteUnauthorized
```

**Query/Verify API (audit_events.py, via RBAC dependency):**
```python
token = decode_rs256(raw_token, jwks_cache=jwks)
if token.audience != "reos":
    raise AuditReadUnauthorized
RequirePermission("admin:audit")(token)   # WP-005-03 pattern
```

---

## 13. Audit Event Taxonomy

### 13.1 Authentication Events

| Event Type | Action | Resource Type | Emitted By |
|-----------|--------|---------------|-----------|
| `auth.login.success` | `login` | `session` | auth.py (login success) |
| `auth.login.failure` | `login` | `session` | auth.py (wrong password) |
| `auth.login.locked` | `login` | `session` | auth.py (lockout threshold) |
| `auth.token.exchanged` | `token.exchange` | `session` | auth.py (code→token) |
| `auth.token.refreshed` | `token.refresh` | `session` | auth.py (refresh rotation) |
| `auth.token.revoked` | `token.revoke` | `session` | auth.py (explicit revoke) |

### 13.2 MFA Events

| Event Type | Action | Resource Type | Emitted By |
|-----------|--------|---------------|-----------|
| `auth.mfa.challenge_issued` | `mfa.challenge_issued` | `mfa` | mfa.py (TOTP setup, SMS OTP sent) |
| `auth.mfa.setup_required` | `mfa.setup_required` | `mfa` | auth.py (privileged role, no MFA) |
| `auth.mfa.verified` | `mfa.verified` | `mfa` | mfa.py (TOTP or FIDO2 verify) |
| `auth.mfa.failed` | `mfa.failed` | `mfa` | mfa.py (bad OTP) |
| `auth.mfa.locked` | `mfa.locked` | `mfa` | mfa.py (5-failure lockout) |
| `auth.mfa.admin_unlocked` | `mfa.admin_unlock` | `mfa` | mfa.py (admin unlock) |

### 13.3 User Lifecycle Events

| Event Type | Action | Resource Type | Emitted By |
|-----------|--------|---------------|-----------|
| `user.registered` | `user.register` | `user` | kafka consumer (existing `user.registered` topic) |
| `user.deactivated` | `user.deactivate` | `user` | users_admin.py |
| `user.activated` | `user.activate` | `user` | users_admin.py |
| `user.password.changed` | `password.change` | `user` | users_admin.py (when added) |

### 13.4 RBAC Events

| Event Type | Action | Resource Type | Emitted By |
|-----------|--------|---------------|-----------|
| `rbac.role.assigned` | `role.assign` | `user` | roles.py |
| `rbac.role.removed` | `role.remove` | `user` | roles.py |
| `rbac.role.created` | `role.create` | `role` | roles.py |
| `rbac.role.deleted` | `role.delete` | `role` | roles.py |

### 13.5 Audit Meta-Events

| Event Type | Action | Resource Type | Emitted By |
|-----------|--------|---------------|-----------|
| `audit.log.queried` | `audit.query` | `audit_log` | audit-service (GET /events) |
| `audit.chain.verified` | `audit.verify_chain` | `audit_log` | audit-service (GET /verify-chain) |

### 13.6 Event Type Naming Convention

Format: `{domain}.{entity}.{action}` (3 dotted levels). Domain examples: `auth`, `user`, `rbac`, `audit`. Reserved prefixes for future use: `meter`, `topology`, `billing`, `control`.

---

## 14. Retention Policy

### 14.1 PostgreSQL / TimescaleDB

| Layer | Policy | Mechanism |
|-------|--------|-----------|
| Full record retention | 7 years (84 months) | `add_retention_policy('audit.audit_events', INTERVAL '84 months')` — drops monthly chunks |
| Compression | After 7 days | `add_compression_policy` — segment by `actor_id`, order by `timestamp_utc DESC` |
| Estimated compression ratio | ~10× | Based on TimescaleDB columnar compression benchmarks for time-series data |
| `chain_state` retention | Indefinite | No retention policy — small table (one row per actor) |

### 14.2 PII Anonymisation

PII fields (`actor_ip_address`, `actor_user_agent`, `actor_username`) are retained as-is for 2 years from `timestamp_utc`. After 2 years, a future background job (separate WP) will:
1. Acquire a privileged DB session
2. Transiently disable `tg_audit_events_immutable` for the controlled update window
3. Set PII fields to `NULL` on eligible rows (timestamp_utc < NOW() - INTERVAL '2 years')
4. Re-enable trigger
5. Generate a `system.pii.masked` audit event recording the masking operation

This background job is explicitly out of scope for WP-005-04. Schema supports this by making all PII columns nullable.

### 14.3 Kafka Retention

`iam.audit.events`: 7-day message retention at Kafka level (broker-configured). This is not a compliance retention layer — PostgreSQL is the system of record.

---

## 15. Encryption Strategy

### 15.1 At Rest

| Layer | Strategy | Owner |
|-------|---------|-------|
| PostgreSQL data files | Host-level encryption (dm-crypt/LUKS) | EPIC-047 R12 scope |
| Kafka message contents | Not encrypted in transit between brokers (internal network) — TLS for client connections | Infra |
| Vault secrets | Vault's own encryption | Vault AppRole |
| Audit records in DB | No application-level encryption of columns in WP-005-04 scope | R12 scope |

No TOTP-style symmetric key encryption in the audit service (no secrets generated or stored). Contrast with WP-005-02 which encrypts MFA secrets with Fernet.

### 15.2 In Transit

| Connection | Protocol | Notes |
|-----------|---------|-------|
| Kafka consumer → broker | TLS + SASL/SCRAM | Configured via `ssl_context` in AIOKafkaConsumer |
| REST API → identity-service JWKS | HTTPS | TLS via standard Python httpx client |
| Audit-service → PostgreSQL | TLS | `sslmode=require` in DSN |
| Audit-service → Vault | HTTPS | TLS to Vault listener |

### 15.3 Secrets Management

DB credentials are NOT passed via environment variables. Pattern (identical to identity-service):
1. Vault AppRole `role_id` in tmpfs at `/run/reos/audit-service/vault-role-id`
2. Vault AppRole `secret_id` in tmpfs at `/run/reos/audit-service/vault-secret-id`
3. `config.py` reads `vault_role_id_path` and `vault_secret_id_path` settings
4. On startup, `core/vault.py` authenticates via AppRole and retrieves DB credentials
5. Credentials stored in memory; DB DSN constructed in-process; never logged

---

## 16. Search and Query Requirements

### 16.1 Supported Filters

All filters in `GET /api/v1/audit/events` are optional AND-combined. No OR semantics at query level.

| Filter | Operator | Index Used |
|--------|---------|-----------|
| `actor_id` | = | `ix_audit_events_actor_id` |
| `event_type` | = | `ix_audit_events_event_type` |
| `action` | = | No dedicated index; filtered post-index-seek |
| `resource_type` | = | `ix_audit_events_resource` |
| `resource_id` | = | `ix_audit_events_resource` (composite) |
| `outcome` | = | `ix_audit_events_outcome` |
| `service_name` | = | `ix_audit_events_service_name` |
| `correlation_id` | = | `ix_audit_events_correlation_id` |
| `date_from`, `date_to` | BETWEEN | TimescaleDB chunk exclusion |
| `metadata` fields | JSONB @> | `ix_audit_events_metadata` (GIN) |

### 16.2 Full-Text Search

Full-text search is not required in WP-005-04 scope. `actor_username` and `outcome_reason` are not indexed for ILIKE or to_tsvector. If required in future, raise a WP engineering package.

### 16.3 Pagination

Standard page-based pagination (`page` + `page_size`). Cursor-based pagination may be introduced as a future enhancement for large result sets (R2 scope). Maximum `page_size` = 200. Default = 50. Response body includes `total_count`, `page`, `page_size`, `total_pages`.

### 16.4 Sort Order

Sort on `timestamp_utc` only (ascending or descending). TimescaleDB chunk exclusion makes time-bounded queries highly efficient.

---

## 17. Reporting Requirements

### 17.1 In-Scope (WP-005-04)

| Report | Delivery | Trigger |
|--------|---------|---------|
| Hash chain verification result | JSON response body | `GET /verify-chain/{type}/{key}` |
| Per-query result set | JSON paginated response | `GET /audit/events` |
| Health / readiness | JSON | `GET /health/ready` |

### 17.2 Out-of-Scope (Future WPs)

| Report | Notes |
|--------|-------|
| Compliance export (PDF, CSV) | Future WP; query API is the foundation |
| Scheduled DORA-style audit summary | Future WP (R2) |
| Access frequency dashboard | Future WP — Grafana on top of Prometheus metrics |
| Actor-level activity timeline | Future WP — uses Query API as data source |

---

## 18. Metrics

All metrics exposed at `GET /metrics` (Prometheus scrape endpoint, port 8004).

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `audit_events_written_total` | Counter | `source` (kafka\|rest), `outcome` (success\|failure) | Audit events processed |
| `audit_events_write_duration_seconds` | Histogram | `source` | Write latency (buckets: 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s) |
| `audit_events_queried_total` | Counter | — | Query API calls |
| `audit_events_query_duration_seconds` | Histogram | — | Query latency |
| `audit_kafka_consumer_lag` | Gauge | `topic`, `partition` | Consumer lag per partition |
| `audit_kafka_events_consumed_total` | Counter | `topic`, `outcome` | Kafka messages consumed |
| `audit_dlq_events_total` | Counter | `topic` | Dead-letter queue messages sent |
| `audit_chain_broken_total` | Counter | `partition_type` | Chain integrity violations detected |
| `audit_jwks_cache_hits_total` | Counter | — | JWKS cache hits |
| `audit_jwks_cache_misses_total` | Counter | — | JWKS cache misses (refetches) |

---

## 19. Logging

### 19.1 Framework

structlog JSON processor chain, identical to identity-service (EPIC-002 `reos-logging`):
```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
```

### 19.2 Mandatory Log Events

| Event | Level | Excluded PII Fields |
|-------|-------|---------------------|
| Service startup | INFO | — |
| DB connection established | INFO | — |
| JWKS cache refreshed | INFO | — |
| Kafka consumer started | INFO | — |
| Event written (source, event_type, outcome) | DEBUG | actor_username, actor_ip_address, actor_user_agent |
| Kafka event consumed | DEBUG | All PII |
| DLQ event routed | WARNING | All PII |
| Chain integrity broken | CRITICAL | — |
| DB write retry | WARNING | — |
| Health check failure | ERROR | — |

### 19.3 PII Exclusion Rules

MUST NOT appear in any log line at any level:
- `actor_ip_address`
- `actor_user_agent`
- `actor_username`
- `metadata` field values (log the key names only if needed)
- Any token, credential, or secret

Enforced via: code review gate; unit test asserting log capture does not contain PII.

---

## 20. Tracing

### 20.1 Correlation ID Propagation

Every inbound HTTP request MUST carry `X-Correlation-ID` header. The audit-service:
1. Reads `X-Correlation-ID` from request headers; generates `uuid4()` if absent
2. Stores in structlog context via `structlog.contextvars.bind_contextvars(correlation_id=...)`
3. Propagates to all outbound calls (JWKS fetch headers)
4. Records in `audit_events.correlation_id` for every event (Kafka and REST)

### 20.2 OpenTelemetry (Future)

Full distributed tracing via OpenTelemetry (OTLP exporter) is deferred to R2. WP-005-04 MUST NOT add OpenTelemetry dependencies — the correlation-ID-in-structlog pattern is sufficient for R1 forensics.

### 20.3 Request ID in Responses

All error responses include `correlation_id` in response body for client-side incident correlation.

---

## 21. Health Checks

### 21.1 Liveness — GET /api/v1/health/live

- Returns 200 immediately
- No external dependency checks
- Kubernetes / systemd: SIGKILL if non-200 for > 30 s

Response: `{"status": "ok", "service": "audit-service", "version": "<semver>"}`

### 21.2 Readiness — GET /api/v1/health/ready

Checks:
1. PostgreSQL: `SELECT 1` against `audit.audit_events` — expect success
2. Kafka: consumer is in `RUNNING` state (not `STARTING`, `STOPPED`, or `ERROR`)
3. JWKS cache: last successful fetch < 600 s ago

Returns 200 only when all three pass. Returns 503 with failed component list if any check fails.

Response (ready):
```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "kafka_consumer": "ok",
    "jwks_cache": "ok"
  }
}
```

Response (not ready):
```json
{
  "status": "not_ready",
  "checks": {
    "database": "ok",
    "kafka_consumer": "error: consumer in STOPPED state",
    "jwks_cache": "ok"
  }
}
```

---

## 22. Performance Targets

| Operation | Target | Measurement | Verification |
|-----------|--------|------------|-------------|
| REST write P95 | < 50 ms | end-to-end (receive request → 201 response) | k6 load test + integration test |
| REST query P95 (30-day window, single actor, page_size=50) | < 200 ms | end-to-end | Integration test |
| Hash chain verify (10,000 events) | < 5 s | wall-clock | Performance test |
| Kafka consumer steady-state lag | < 100 messages | Prometheus gauge | Monitoring |
| Write throughput sustained | 500 events/s @ P95 < 50 ms | k6 ramping-arrival-rate | Load test (pre-AR-051) |
| Service startup to readiness | < 10 s | CI smoke test | Health check |
| JWKS cache refresh | < 1 s | Log timestamp | Unit test |

---

## 23. Capacity Targets

### 23.1 Event Volume Estimates (R1)

| Source | Events/Day (R1) | Events/Day (R5+) |
|--------|----------------|-----------------|
| IAM authentication (login, token ops) | ~5,000 | ~50,000 |
| MFA operations | ~2,000 | ~20,000 |
| RBAC mutations | ~500 | ~5,000 |
| User registration/deactivation | ~100 | ~1,000 |
| Audit log queries (meta-audit) | ~200 | ~2,000 |
| **Total** | **~8,000/day** | **~78,000/day** |

### 23.2 Storage Estimates

| Parameter | Value |
|-----------|-------|
| Average event size (compressed) | ~200 bytes |
| R1 daily volume | ~1.6 MB/day (compressed) |
| R1 annual volume | ~580 MB/year (compressed) |
| 7-year R1 total | ~4.1 GB (compressed) |
| R5+ daily volume | ~15.6 MB/day (compressed) |
| 7-year R5+ total | ~40 GB (compressed) |

TimescaleDB compression (~10×) applies after 7 days. Pre-compression peak: ~100 MB/day at R5+ scale.

### 23.3 Connection Pool

| Pool Parameter | Value | Notes |
|---------------|-------|-------|
| `pool_size` | 10 | Baseline; tune with `AUDIT_DB_POOL_SIZE` |
| `max_overflow` | 20 | Burst headroom |
| `pool_recycle` | 3600 s | Prevent stale connections |

---

## 24. Configuration

### 24.1 Settings Class

```python
class AuditServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_", env_file=".env")

    # Service identity
    SERVICE_NAME:                 str = "audit-service"
    SERVICE_VERSION:              str = "0.1.0"
    PORT:                         int = 8004
    ENVIRONMENT:                  Literal["local","shared_dev","ci","staging","production"] = "local"

    # Database
    DB_DSN:                       PostgresDsn           # AUDIT_DB_DSN (set by vault.py at runtime)
    DB_POOL_SIZE:                 int = 10
    DB_MAX_OVERFLOW:              int = 20
    DB_POOL_RECYCLE:              int = 3600
    DB_ECHO_SQL:                  bool = False

    # Vault
    VAULT_ADDR:                   str = "http://vault:8200"
    VAULT_ROLE_ID_PATH:           str = "/run/reos/audit-service/vault-role-id"
    VAULT_SECRET_ID_PATH:         str = "/run/reos/audit-service/vault-secret-id"
    VAULT_DB_SECRET_PATH:         str = "secret/data/audit-service/db"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS:      str = "kafka:9092"
    KAFKA_IAM_AUDIT_EVENTS_TOPIC: str = "iam.audit.events"
    KAFKA_USER_EVENTS_TOPIC:      str = "user.registered"
    KAFKA_DLQ_TOPIC:              str = "audit.dead.events"
    KAFKA_CONSUMER_GROUP_ID:      str = "audit-service-consumer"
    KAFKA_MAX_POLL_RECORDS:       int = 100
    KAFKA_SESSION_TIMEOUT_MS:     int = 30_000
    KAFKA_HEARTBEAT_INTERVAL_MS:  int = 10_000
    KAFKA_RETRY_MAX_ATTEMPTS:     int = 3
    KAFKA_RETRY_BASE_DELAY_S:     float = 1.0

    # JWT / JWKS
    JWKS_URL:                     str = "http://identity-service:8001/api/v1/jwks"
    JWKS_CACHE_TTL_SECONDS:       int = 300
    JWT_ALGORITHM:                Literal["RS256"] = "RS256"
    JWT_AUDIENCE_USER:            str = "reos"
    JWT_AUDIENCE_INTERNAL:        str = "reos-internal"

    # Query defaults
    QUERY_DEFAULT_DATE_RANGE_DAYS: int = 30
    QUERY_MAX_DATE_RANGE_DAYS:     int = 365
    QUERY_DEFAULT_PAGE_SIZE:       int = 50
    QUERY_MAX_PAGE_SIZE:           int = 200

    # Observability
    LOG_LEVEL:                    str = "INFO"
    METRICS_ENABLED:              bool = True
    HEALTH_CHECK_TIMEOUT_S:       int = 5
```

### 24.2 .env.example

```bash
# audit-service environment — NEVER commit real values
AUDIT_ENVIRONMENT=local
AUDIT_PORT=8004

# Database (set by vault.py at runtime; override for local dev only)
AUDIT_DB_DSN=postgresql+asyncpg://audit_user:changeme@localhost:5432/reos_audit

# Vault
AUDIT_VAULT_ADDR=http://localhost:8200
AUDIT_VAULT_ROLE_ID_PATH=/run/reos/audit-service/vault-role-id
AUDIT_VAULT_SECRET_ID_PATH=/run/reos/audit-service/vault-secret-id
AUDIT_VAULT_DB_SECRET_PATH=secret/data/audit-service/db

# Kafka
AUDIT_KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# JWT
AUDIT_JWKS_URL=http://localhost:8001/api/v1/jwks

# Logging
AUDIT_LOG_LEVEL=DEBUG
AUDIT_DB_ECHO_SQL=false
```

---

## 25. Deployment Requirements

### 25.1 Docker

Multi-stage Dockerfile (mirrors identity-service pattern):
```
Stage 1: builder — python:3.11-slim; pip-compile requirements; install deps
Stage 2: runtime — python:3.11-slim; non-root user reos (UID 1000); copy site-packages + src
         EXPOSE 8004
         HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
           CMD curl -f http://localhost:8004/api/v1/health/ready || exit 1
```

No `root` execution in runtime stage. No `COPY . .` in runtime stage (copy only required packages and `src/`).

### 25.2 systemd Unit

Pattern from WP-003-06 (`reos-service@.service`):
```ini
[Unit]
Description=RE-OS Audit Service
After=network.target postgresql.service kafka.service vault-agent.service

[Service]
Type=simple
User=reos
Group=reos
WorkingDirectory=/opt/reos/audit-service
ExecStart=/opt/reos/audit-service/.venv/bin/python -m uvicorn \
    audit_service.main:app --host 0.0.0.0 --port 8004 --workers 2
Restart=on-failure
RestartSec=5s
RuntimeDirectory=reos/audit-service
RuntimeDirectoryMode=0700

[Install]
WantedBy=multi-user.target
```

### 25.3 Ansible Deployment

Follows `infra/playbooks/deploy-rolling.yml` pattern (WP-004-11):
1. Drain upstream (Nginx health-check route)
2. Wait 30 s for in-flight requests to drain
3. Pull new Docker image
4. Run `alembic upgrade head` (first VM only)
5. Restart `reos-audit-service.service` via systemd
6. Health check: `GET /health/ready` — retries 24 × 5 s
7. Re-enable upstream

### 25.4 Port Allocation

| Service | Port |
|---------|------|
| identity-service | 8001 |
| (TBD WP-005-05) | 8002 |
| (TBD WP-005-06) | 8003 |
| **audit-service** | **8004** |

### 25.5 Docker Compose (Local Dev)

Add `audit-service` service to `docker-compose.yml` (or a new `docker-compose-audit.yml`):
```yaml
audit-service:
  build: ./services/audit-service
  ports: ["8004:8004"]
  environment:
    AUDIT_DB_DSN: "postgresql+asyncpg://audit_user:dev@timescaledb:5432/reos_audit"
    AUDIT_KAFKA_BOOTSTRAP_SERVERS: "kafka:9092"
    AUDIT_JWKS_URL: "http://identity-service:8001/api/v1/jwks"
    AUDIT_VAULT_ADDR: "http://vault:8200"
  depends_on: [timescaledb, kafka, identity-service, vault]
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8004/api/v1/health/ready"]
    interval: 30s
```

---

## 26. Testing Requirements

### 26.1 Unit Tests (tests/unit/)

| File | Coverage Required |
|------|-----------------|
| `test_hash_chain.py` | SHA-256 computation; GENESIS event; chain continuity (3+ events); broken chain detection on field mutation |
| `test_audit_service.py` | Write with valid schema; duplicate handling (returns 409); meta-audit emission on query |
| `test_schemas.py` | Required fields; max lengths; UTC enforcement on timestamp; metadata size limit (4096 bytes); naive datetime rejected |
| `test_security.py` | RS256 decode success; aud=`reos` accepted for query; aud=`reos-internal` accepted for write; aud=`reos` rejected for write; HS256 rejected; expired token rejected; `admin:audit` check passes/fails |
| `test_query.py` | Filter combinations; date range defaults; `page_size` cap at 200; max date range enforcement (365 days); naive datetime filter rejected |
| `test_kafka_handlers.py` | `iam.audit.events` message → AuditEventCreate; `user.registered` → AuditEventCreate; schema error → DLQ routing; retry backoff |

Coverage gate: ≥ 80% line coverage per module. CI fails below threshold.

### 26.2 Integration Tests (tests/integration/)

**Requirements:** Real PostgreSQL (TimescaleDB image), real Kafka — via testcontainers. No mocking of DB or Kafka (STANDARDS.md §7 — prior incident rule).

| File | Scenarios |
|------|-----------|
| `test_write_api.py` | POST /events → 201; duplicate event_id → 409; invalid schema → 400; no JWT → 401; user JWT (wrong aud) → 403 |
| `test_query_api.py` | Filter by actor_id; filter by event_type; date range; sort asc; pagination; no admin:audit → 403; meta-audit event generated; date range > 365 days → 400 |
| `test_chain_verify.py` | Valid chain → chain_valid=true; corrupt event_hash in DB → chain_valid=false, broken_at_event_id set; verify on empty partition → 404; verify generates meta-event |
| `test_kafka_consumer.py` | Consume `iam.audit.events` → persisted; consume `user.registered` → persisted; duplicate event_id → idempotent skip; schema invalid → DLQ published; 3 DB failures → DLQ |
| `test_immutability.py` | Direct UPDATE on audit_events via raw SQL → PostgreSQL exception raised; direct DELETE → exception |
| `test_health.py` | /health/live → 200; /health/ready → 200 (all checks ok); /health/ready → 503 (DB down); /health/ready → 503 (Kafka stopped) |

### 26.3 Security Tests

| Test | Assertion |
|------|-----------|
| PII absence in logs | Capture structlog output during write test; assert `actor_ip_address` not in any log message |
| Immutability trigger | `test_immutability.py` — see above |
| Hash chain tamper detection | Corrupt `event_hash` directly in DB via raw SQL; call verify-chain; assert `chain_valid=false` |
| Parameterised queries | Code review: grep `repositories.py` for raw string interpolation in SQL |
| `admin:audit` enforced | User without permission → 403 |
| HS256 token rejected | Craft HS256 token; POST /events → 401 |

### 26.4 Performance Tests

Run in pre-AR-051 environment (not CI):
- k6 ramping-arrival-rate: 10 RPS → 100 RPS → 500 RPS over 5 minutes
- Assert: P95 write < 50 ms at all load levels
- Assert: no 5xx at ≤ 500 RPS
- Record results in `LOAD_TESTING.md` section for WP-005-04

---

## 27. Deliverables

### 27.1 New Service — services/audit-service/

```
services/audit-service/
├── pyproject.toml               # hatchling backend; all deps pinned
├── requirements.in              # runtime deps
├── requirements.txt             # pip-compile output; exact pins
├── Dockerfile                   # multi-stage; non-root reos user; port 8004
├── .env.example
├── alembic.ini
├── alembic/
│   └── versions/
│       └── 0001_create_audit_schema.py
└── src/
    └── audit_service/
        ├── main.py              # FastAPI app factory + lifespan
        ├── config.py            # AuditServiceSettings (Pydantic BaseSettings)
        ├── dependencies.py      # DB session, get_current_user
        ├── api/
        │   └── v1/
        │       ├── router.py
        │       └── endpoints/
        │           ├── audit_events.py   # GET /events, GET /events/{id}, verify-chain
        │           ├── internal.py       # POST /events (write)
        │           └── health.py         # /health/live, /health/ready
        │       └── schemas/
        │           ├── audit_event.py    # AuditEventCreate, AuditEventResponse
        │           └── query.py          # AuditEventFilter, PaginatedResponse
        ├── domain/
        │   ├── models.py        # AuditEvent ORM, ChainState ORM
        │   ├── repositories.py  # write(), query(), get_by_id(), upsert_chain_state()
        │   ├── services.py      # AuditService: write, query, verify_chain
        │   └── events.py        # AuditEventCreated (frozen dataclass)
        └── core/
            ├── kafka.py         # AIOKafkaConsumer lifecycle + topic dispatch
            ├── security.py      # JWKS fetch+cache; JWT decode; permission check
            ├── hash_chain.py    # SHA-256 compute + verify_chain
            ├── exceptions.py    # AuditServiceError hierarchy
            └── logging.py       # structlog JSON setup
tests/
├── conftest.py                  # fixtures: db, kafka, http client
├── unit/
│   ├── test_hash_chain.py
│   ├── test_audit_service.py
│   ├── test_schemas.py
│   ├── test_security.py
│   ├── test_query.py
│   └── test_kafka_handlers.py
└── integration/
    ├── test_write_api.py
    ├── test_query_api.py
    ├── test_chain_verify.py
    ├── test_kafka_consumer.py
    ├── test_immutability.py
    └── test_health.py
```

### 27.2 Modified Files — services/identity-service/

See §10.3 for complete list. In scope for WP-005-04.

### 27.3 Documentation

| File | Content |
|------|---------|
| `services/audit-service/README.md` | Service overview; local dev setup; env vars; Kafka topic creation commands; Vault AppRole setup |
| `AUDIT_SERVICE.md` (repo root) | Architecture; event taxonomy; hash chain verification procedure; PII policy; operational runbook; alertmanager rules |

---

## 28. Acceptance Criteria

### 28.1 HTTP Behaviour

| ID | Criterion | Test |
|----|-----------|------|
| AC-01 | POST /events with valid service JWT + valid payload → 201 + event in DB | `test_write_api.py` |
| AC-02 | POST /events same event_id twice → first 201, second 409 (idempotent) | `test_write_api.py` |
| AC-03 | POST /events with user JWT → 403 | `test_write_api.py` |
| AC-04 | GET /events with valid admin:audit JWT → 200 + paginated events | `test_query_api.py` |
| AC-05 | GET /events without admin:audit → 403 | `test_query_api.py` |
| AC-06 | GET /events generates `audit.log.queried` meta-event | `test_query_api.py` |
| AC-07 | GET /verify-chain on valid chain → `chain_valid=true` | `test_chain_verify.py` |
| AC-08 | GET /verify-chain after corruption → `chain_valid=false` + `broken_at_event_id` | `test_chain_verify.py` |
| AC-09 | UPDATE on audit_events → PostgreSQL exception | `test_immutability.py` |
| AC-10 | DELETE on audit_events → PostgreSQL exception | `test_immutability.py` |

### 28.2 Kafka Behaviour

| ID | Criterion | Test |
|----|-----------|------|
| AC-11 | Kafka event consumed from `iam.audit.events` → persisted to DB | `test_kafka_consumer.py` |
| AC-12 | Duplicate Kafka event (same event_id) → idempotent skip, no error | `test_kafka_consumer.py` |
| AC-13 | Kafka event with invalid schema → routed to DLQ | `test_kafka_consumer.py` |
| AC-14 | DB failure on consume → 3 retries → DLQ | `test_kafka_consumer.py` |

### 28.3 Performance

| ID | Criterion | Method |
|----|-----------|--------|
| AC-15 | REST write P95 < 50 ms at 500 RPS | k6 load test |
| AC-16 | REST query P95 < 200 ms (30-day, single actor, page_size=50) | Integration test |
| AC-17 | Service startup to ready < 10 s | CI smoke test |

### 28.4 Security

| ID | Criterion | Method |
|----|-----------|--------|
| AC-18 | No PII in any structlog output | Log capture assertion test |
| AC-19 | HS256 token rejected at write endpoint | Unit test `test_security.py` |
| AC-20 | DB role has no UPDATE/DELETE grants | Vault policy review |

---

## 29. Definition of Done

| # | Criterion | Verification |
|---|-----------|-------------|
| DoD-01 | EARB Architecture Review AR-051: spec review APPROVED | AR-051 record |
| DoD-02 | All code passes: Black, isort (black profile), Ruff, mypy strict, Bandit (no HIGH) | CI pipeline |
| DoD-03 | Unit test coverage ≥ 80% line coverage per module | CI coverage gate |
| DoD-04 | All integration tests PASS against real PostgreSQL (TimescaleDB) + Kafka | CI pipeline |
| DoD-05 | Immutability trigger: UPDATE → exception; DELETE → exception | `test_immutability.py` |
| DoD-06 | Hash chain: corrupt `event_hash` → verify-chain returns `chain_valid=false` | `test_chain_verify.py` |
| DoD-07 | No PII in application logs — verified by log capture test | `test_write_api.py` |
| DoD-08 | `admin:audit` permission enforced: user without it → 403 | `test_query_api.py` |
| DoD-09 | Service JWT (aud=`reos-internal`) accepted for write; user JWT rejected | `test_write_api.py` |
| DoD-10 | Duplicate `event_id` → 409 (REST); idempotent skip (Kafka) | `test_write_api.py`, `test_kafka_consumer.py` |
| DoD-11 | Kafka DLQ: 3 DB write failures → message in `audit.dead.events` | `test_kafka_consumer.py` |
| DoD-12 | identity-service emits `iam.audit.events` for all auth/MFA/RBAC operations | Identity-service integration tests |
| DoD-13 | Meta-audit: GET /events generates `audit.log.queried` event | `test_query_api.py` |
| DoD-14 | Alembic migration runs cleanly; hypertable and retention policy applied | CI migration smoke test |
| DoD-15 | Health: /health/live → 200; /health/ready → 200 (all up); → 503 (DB down) | `test_health.py` |
| DoD-16 | Performance baseline recorded in `LOAD_TESTING.md`: P95 write < 50 ms; P95 query < 200 ms | Pre-AR load test |
| DoD-17 | PR approved by Security Lead + Tech Lead | GitHub PR reviews |
| DoD-18 | `AUDIT_SERVICE.md` and `services/audit-service/README.md` present and accurate | Doc review |
| DoD-19 | Alertmanager rules for `AuditChainBroken`, `AuditDLQEvent`, `AuditServiceDown` configured | Config review |
| DoD-20 | EECR-CHG-063 raised and recorded (WP-005-04 retitled to Audit Service) | EECR change log |
| DoD-21 | `audit_chain_broken_total` counter fires CRITICAL alert when > 0 | Alert rule test |
| DoD-22 | DB role verified: INSERT + SELECT only on `audit.audit_events`; no UPDATE/DELETE | Vault policy + DB test |

---

## 30. Architecture Traceability

| Requirement | BRS Ref | SRS Ref | HLD Ref | LLD Ref | EECR Ref | ADR Ref |
|-------------|---------|---------|---------|---------|---------|---------|
| Immutable audit log | Vol.3 §Audit | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |
| 7-year retention | Vol.3 §Retention | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |
| PII capture and retention | Vol.3 §Privacy | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |
| `admin:audit` RBAC | Vol.3 §Security | §RBAC | §Security Arch | §7.2, §7.6 | EECR-R01-005-02 | — |
| Hash chain integrity | Vol.3 §Audit | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |
| Kafka event-driven ingestion | Vol.2 §Platform | §Audit Logging | §Service Arch | §7.6 | EECR-R01-005-04 | ADR-006 |
| Service JWT (reos-internal) | Vol.3 §Security | §Auth | §Security Arch | §7.3 | EECR-R01-005-03 | — |
| TimescaleDB hypertable | Vol.2 §Data | §Audit Logging | §Data Layer | §7.6; STANDARDS §5.1 | EECR-R01-005-04 | — |
| P95 < 200ms query | — | §Performance | §Observability | §2.7; STANDARDS §7 | EECR-R01-005-04 | — |
| No PII in logs | Vol.3 §Privacy | §Dev Standards | §Observability | §2.3; STANDARDS §4 | All WPs | — |
| Python 3.11 / FastAPI / Pydantic v2 | Vol.1 §Quality | §Dev Standards | §Backend Arch | §2.1; STANDARDS §2 | All WPs | ADR-001 |
| Vault AppRole for DB credentials | Vol.3 §Security | §Auth | §Security Arch | §7.x | EECR-R01-005-01 | — |
| Meta-audit on query | Vol.3 §Audit | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |
| Append-only trigger | Vol.3 §Audit | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |
| RS256 / JWKS validation | Vol.3 §Security | §Auth | §Security Arch | §7.3 | EECR-R01-005-01 | — |
| service-iam-audit-service directory | Vol.1 §Governance | §SDLC | — | §3.1; STANDARDS §2.1.2 | EECR-R01-001-01 | ADR-007 |
| Prometheus metrics | — | §Performance | §Observability | §2.7 | All WPs | — |
| PII anonymisation (schema support) | Vol.3 §Privacy | §Audit Logging | §Security Arch | §7.6 | EECR-R01-005-04 | — |

---

## 31. Risks

| ID | Risk | Probability | Impact | Mitigation |
|----|------|------------|--------|-----------|
| R-AUD-001 | TimescaleDB `create_hypertable` fails on existing non-empty table | Low | High | Run migration before any application data enters the table; migration creates table + converts to hypertable atomically |
| R-AUD-002 | JWKS fetch failure at startup prevents write API from accepting events | Medium | High | Cache last-known JWKS in memory; retry with backoff; health/ready returns 503 only if cache > 600s stale, not on first miss |
| R-AUD-003 | Kafka backpressure causes consumer lag to grow; meta-audit events cascade | Medium | Medium | Batch consumer (max_poll_records=100); meta-audit events have lower priority; separate partition key from user events |
| R-AUD-004 | Hash chain verification over 84 months of data (7 years) exceeds P95 target | Low | Medium | Limit verify-chain to a single partition and a bounded time window; full audit via date partition-type is separate call |
| R-AUD-005 | Identity-service producer changes introduce latency to auth endpoints | Low | Medium | Producer calls are fire-and-forget (`asyncio.create_task`); failure is non-fatal and logged, not propagated |

---

## 32. Open Questions

| ID | Question | Owner | Target Resolution |
|----|---------|-------|-----------------|
| Q-AUD-001 | WP-005-06 "IAM Audit Event Logging" currently maps to LLD v2.0 §7.6 — same as WP-005-04 after EECR-CHG-063. Is WP-005-06 superseded by WP-005-04 scope, or should it be retitled to "IAM Audit Event Producer" covering only the identity-service producer modifications? | Enterprise Architect | Before WP-005-06 implementation |
| Q-AUD-002 | Port 8004 assignment: no canonical port registry in LLD v2.0 §7.6. Confirm 8004 is not already allocated to another EPIC-005 service. | Platform Lead | Before WP-005-04 implementation kick-off |
| Q-AUD-003 | `metadata` 4096-byte limit: is this sufficient for complex RBAC mutation events (e.g., bulk permission assignment)? If metadata needs to be larger, confirm schema change via ECR before implementation. | Tech Lead | Before implementation |
| Q-AUD-004 | DB user for audit-service `chain_state` requires UPDATE (UPSERT). DB role policy says INSERT + SELECT only on `audit_events`. Confirm that the separate `chain_state` table with INSERT + UPDATE permissions is acceptable under the Vault DB secrets policy. | Platform Lead / Security Lead | Before Vault AppRole provisioning |

---

*Engineering Specification v1.0 — APPROVED (AR-051 2026-07-04) | WP-005-04 | EPIC-005 | DAEP / RE-OS Programme*
*Prepared: Enterprise Architect / PMO | AI-assisted: claude-sonnet-4-6*
