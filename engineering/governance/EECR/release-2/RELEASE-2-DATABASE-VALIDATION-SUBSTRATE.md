# Release 2 Database Validation Substrate
### DAEP / RE-OS | R2-PLAT-002 / R2-PLAT-003 | Revision 1.1 | 2026-07-06

## 1. Purpose

This document defines the governed database substrate for Release 2 validation. It is platform
engineering support only. It does not implement EPIC-006, WP-006-03B, application functionality, or
R2-PLAT-003 environment-variable alignment.

## 2. Root Cause

R2-RISK-017 database validation failed because the validation run depended on host-installed
`pg_isready` and `psql`, while the local evidence environment had neither tool and had no reachable
PostgreSQL/TimescaleDB service. The previous workflow also split DB readiness and migration evidence
across shell commands rather than a reusable substrate.

## 3. Substrate Components

| Component | Purpose |
|-----------|---------|
| `docker-compose.release2-db.yml` | Local TimescaleDB service contract for developers with Docker available |
| `scripts/release2/db_validation_substrate.py` | Shared local/CI readiness and migration executor |
| `.github/workflows/release2-validation.yml` | CI database profile now uses the shared substrate instead of `pg_isready`/`psql` |
| `tests/test_release2_db_validation_substrate.py` | Unit evidence for configuration, migration ordering, and JSONL evidence output |

## 4. Environment Contract

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_DSN` | `postgresql://diep:diep123@localhost:5432/diep` | Canonical Release 2 DB contract |
| `AUDIT_DB_DSN` | derived | audit-service alias, asyncpg scheme |
| `DATABASE_URL` | derived | RE-OS service integration alias, asyncpg scheme |
| `IDENTITY_DATABASE_URL` | derived | identity-service alias, asyncpg scheme |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | derived | legacy CIM/MDM/topology compatibility aliases |

Passwords are masked in emitted substrate evidence.

## 5. Local Execution

When Docker is available:

```bash
docker compose -f docker-compose.release2-db.yml up -d
python scripts/release2/db_validation_substrate.py env \
  --format shell \
  --output .release2-db.env
python scripts/release2/db_validation_substrate.py migrate \
  --output release2-db-migrations.jsonl
```

When Docker is not available, local execution may still run static/unit substrate validation, but
connectivity and migration evidence must come from a governed CI runner or an approved database host.

## 6. CI Execution

The Release 2 database integration job provisions `timescale/timescaledb:latest-pg16` as a GitHub
Actions service, installs `psycopg2-binary`, and runs:

```bash
python scripts/release2/db_validation_substrate.py migrate \
  --output release2-db-migrations.jsonl
```

The workflow first writes `DB_DSN`-derived compatibility variables to `$GITHUB_ENV`. The JSONL
evidence is uploaded with the database integration JUnit artifacts.

## 7. Exit Criteria

R2-PLAT-002 is complete when:

| Criterion | Required Evidence |
|-----------|-------------------|
| DB connectivity substrate exists | `db_validation_substrate.py check` or `migrate` reaches `database_ready` |
| Migration execution substrate exists | `migration_set`, `migration_start`, and `migration_complete` JSONL records |
| TimescaleDB contract checked | `timescaledb_extension_present` after migrations |
| Local contract documented | `docker-compose.release2-db.yml` and this document |
| CI contract updated | Release 2 workflow uses the shared substrate |

## 8. Out of Scope

The following remain outside R2-PLAT-002:

- changing audit-service or identity-service configuration,
- reclassifying legacy DB tests,
- fixing Docker daemon availability,
- changing application schema or business behavior.
