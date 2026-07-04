# Audit Service — DAEP / RE-OS Platform

**WP-005-04 | EPIC-005 Platform Foundation | AR-051 APPROVED (96/100) | AR-052 APPROVED WITH CONDITIONS (90/100)**

## Purpose

The Audit Service is the system of record for all security-relevant events on the RE-OS platform. It provides:

- Immutable, append-only event storage (PostgreSQL trigger + DB role restrictions)
- SHA-256 hash chain for tamper detection
- 7-year retention via TimescaleDB monthly chunks
- REST write API for internal services (service JWT)
- REST query API for platform administrators (`admin:audit` permission)
- Kafka consumer for `iam.audit.events` and `user.registered`
- Meta-audit: query and chain-verify operations are themselves audited

## Immutability Guarantees

Three independent layers prevent mutation:

1. **PostgreSQL trigger** `tg_audit_events_immutable` — BEFORE UPDATE OR DELETE raises exception (cannot be bypassed by application code)
2. **DB role** — audit-service Vault AppRole has INSERT+SELECT only on `audit_events`; no UPDATE/DELETE granted
3. **Application layer** — `AuditEventRepository` has no update/delete methods

## Hash Chain

Each audit event contains `event_hash = SHA-256(event_id|event_type|actor_id|action|outcome|timestamp_utc|prev_event_hash_or_GENESIS)`.

Chain verification: `GET /api/v1/audit/verify-chain/actor/{actor_uuid}`

## Event Taxonomy

See `engineering/specs/WP-005-04-audit-service-engineering-spec.md` §13 for the full 22-event taxonomy.

Key events:
- `auth.login.success/failure/locked` — authentication outcomes
- `auth.mfa.verified/failed/locked/admin_unlocked` — MFA outcomes
- `auth.token.exchanged/refreshed/revoked` — token lifecycle
- `rbac.role.assigned/removed/created/deleted` — RBAC mutations
- `user.registered/deactivated/activated` — user lifecycle
- `audit.log.queried` / `audit.chain.verified` — meta-audit

## Deployment

Port: **8004** (provisional — confirm with Platform Lead per C-AR051-02)

```bash
alembic upgrade head
uvicorn audit_service.main:app --host 0.0.0.0 --port 8004 --workers 2
```

Readiness probe: `GET /api/v1/health/ready` — checks DB, Kafka consumer, JWKS cache freshness.

## PII Handling Policy

The audit service applies different PII controls at different layers (AUD-SEC-008 / BRS §4 / SRS §Audit Logging):

### Structured Log Output (Logging Layer)
`actor_ip_address`, `actor_username`, and `actor_user_agent` **MUST NOT appear in any structured log line** at any level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). This prevents PII from propagating into aggregated observability tooling (Grafana, Loki, alertmanager) where access controls may be weaker. Enforcement is at the call site — no logger in this service references these fields.

### Database Storage
All three PII fields are stored in full in `audit.audit_events`. Retention and anonymisation follow the platform Data Retention and Destruction Policy (DRDP). After 7 years (84 months), records are dropped by the TimescaleDB retention policy. PII anonymisation within the retention window (e.g., GDPR right-to-erasure) requires a controlled exception process per the immutability trigger comment and DRDP §3.

### API Responses (Query Layer)
`actor_ip_address`, `actor_username`, and `actor_user_agent` **ARE included in `AuditEventResponse`** for callers holding `admin:audit` permission. The entire purpose of storing these fields is to support forensic incident response — an administrator investigating a security incident must be able to determine originating IP and username. The PII exclusion requirement (AUD-SEC-008) applies to log output only, not to the authenticated query API.

This policy is consistent with BRS §4 (audit trail requirements), SRS §Audit Logging (event field requirements), and the principle that `admin:audit` is a privileged, purpose-limited permission granted only to platform security personnel.

## Architecture Review Conditions

### Resolved Pre-Merge (AR-052)

| Condition | Status | Resolution |
|-----------|--------|------------|
| C-AR052-01: Add `auth.login.success` event to identity-service login path | ✅ RESOLVED | Added in `services/identity-service/src/identity_service/api/v1/auth.py` |
| C-AR052-04: Document AuditEventResponse PII policy | ✅ RESOLVED | Documented above (Option B — accidental omission; fields added to response schema) |

### Open — Required Before First Staging Deployment

| Condition | Status | Owner |
|-----------|--------|-------|
| C-AR052-02: Populate `audit_kafka_consumer_lag` Gauge in consume loop | OPEN | Platform Lead |
| C-AR052-03: Hash chain write serialisation guard (SELECT FOR UPDATE on chain_state per actor) | OPEN | Platform Lead |
| C-AR052-05 (from C-AR051-02): Confirm port 8004 with Platform Lead | OPEN | Platform Lead |
| C-AR052-06 (from C-AR051-02): Confirm chain_state UPDATE permission with Security Lead | OPEN | Security Lead |

### Open — Required Before WP-005-06 Implementation

| Condition | Status | Owner |
|-----------|--------|-------|
| C-AR052-07 (from C-AR051-01): Resolve WP-005-04 / WP-005-06 scope boundary | OPEN | Enterprise Architect |

## References

- Spec: `engineering/specs/WP-005-04-audit-service-engineering-spec.md`
- AR: `engineering/governance/EECR/architecture-review-register.md` → AR-051 (96/100), AR-052 (90/100)
- EECR: EECR-CHG-063/064/065/066/067/068/069
