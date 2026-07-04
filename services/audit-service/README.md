# RE-OS Audit Service — WP-005-04

Immutable Platform Audit Log for the DAEP / RE-OS platform.

**Port:** 8004 | **Python:** 3.11 | **Framework:** FastAPI + SQLAlchemy 2.x + AIOKafka

## Architecture

```
identity-service  ──iam.audit.events (Kafka)──►  audit-service ──► PostgreSQL (TimescaleDB)
future-services   ──POST /api/v1/audit/events ──►       │           audit.audit_events
admin client      ──GET  /api/v1/audit/events  ──────────┘           audit.chain_state
```

## Running Locally

```bash
cp .env.example .env
# Edit AUDIT_DB_DSN to point at your local PostgreSQL
pip install -e ".[dev]"
alembic upgrade head
uvicorn audit_service.main:app --reload --port 8004
```

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/audit/events` | Service JWT (`reos-internal`) | Write audit event |
| `GET`  | `/api/v1/audit/events` | User JWT + `admin:audit` | Query audit events |
| `GET`  | `/api/v1/audit/events/{event_id}` | User JWT + `admin:audit` | Get single event |
| `GET`  | `/api/v1/audit/verify-chain/{type}/{key}` | User JWT + `admin:audit` | Verify hash chain |
| `GET`  | `/api/v1/health/live` | None | Liveness |
| `GET`  | `/api/v1/health/ready` | None | Readiness (DB + Kafka + JWKS) |

## Running Tests

```bash
# Unit tests (no external deps)
pytest tests/unit/ -v

# Integration tests (require TimescaleDB + testcontainers)
pytest tests/integration/ -v
```

## Governance

- **Spec:** `engineering/specs/WP-005-04-audit-service-engineering-spec.md` v1.0
- **AR:** AR-051 (96/100 APPROVED, 2026-07-04)
- **EECR:** EECR-CHG-063..066
- **Branch:** `feature/iam-audit-service`
