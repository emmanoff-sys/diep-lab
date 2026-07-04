# Audit Service — DAEP / RE-OS Platform

**WP-005-04 | EPIC-005 Platform Foundation | AR-051 APPROVED (96/100)**

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

## Security Review Conditions (from AR-051)

| Condition | Required Before |
|-----------|----------------|
| C-AR051-01: Clarify WP-005-06 scope boundary with §7.6 | WP-005-06 implementation start |
| C-AR051-02: Confirm port 8004 with Platform Lead | First staging deployment |

## References

- Spec: `engineering/specs/WP-005-04-audit-service-engineering-spec.md`
- AR: `engineering/governance/EECR/architecture-review-register.md` → AR-051
- EECR: EECR-CHG-063/064/065/066/067
