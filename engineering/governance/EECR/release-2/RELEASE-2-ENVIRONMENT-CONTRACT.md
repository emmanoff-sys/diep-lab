# Release 2 Validation Environment Contract
### DAEP / RE-OS | R2-RISK-017 Execution Contract | Revision 1.4 | 2026-07-06

## 1. Mandatory Components by Profile

| Component | Unit | Service Integration | Database Integration | Docker | Security | Legacy Platform | Release Gate |
|-----------|------|---------------------|----------------------|--------|----------|-----------------|--------------|
| Python 3.12 | Mandatory | Mandatory | Mandatory | Mandatory for pre-build tooling | Mandatory | Mandatory | Mandatory |
| Docker daemon | Not required | Required if testcontainers used | Mandatory | Mandatory | Required for image scan | Not required | Mandatory |
| PostgreSQL | Not required | Mandatory where service tests require DB | Mandatory | Not required | Not required | Not required | Mandatory |
| TimescaleDB | Not required | Mandatory for audit-service DB tests | Mandatory for topology/audit DB paths | Not required | Not required | Not required | Mandatory if topology/audit DB paths run |
| Redis | Not required | Mandatory for identity integration tests | Optional unless selected tests require it | Not required | Not required | Not required | Mandatory if API stack requires it |
| Kafka | Not required | Optional unless broker profile enabled | Optional | Not required | Not required | Not required | Mandatory only for broker-enabled release gate |
| Prometheus client library | Optional, profile-controlled | Service-specific | Optional | Runtime image dependency as pinned | Scanned if present | Optional, must be deterministic | Mandatory only if metrics behavior is under test |

## 2. Dependency Versions

| Dependency | Version / Source |
|------------|------------------|
| Python | 3.12 for CI parity with legacy workflow; 3.11 remains service-ci Release 1 standard |
| PostgreSQL | `postgres:16` for RE-OS service integration |
| TimescaleDB | `timescale/timescaledb:latest-pg15` for audit-service testcontainers; `timescale/timescaledb:latest-pg16` acceptable for Release 2 topology validation if migrations pass |
| Redis | `redis:7-alpine` |
| Kafka | Broker disabled by default; enable only under explicit broker profile |
| Docker BuildKit | enabled through `docker/setup-buildx-action@v3` in CI |
| Trivy | `aquasecurity/trivy-action@master` until pinned by a later DevSecOps governance item |

## 3. Environment Variables

| Variable | Required For | Default / CI Value |
|----------|--------------|--------------------|
| `DB_DSN` | Canonical Release 2 DB contract | `postgresql://user:password@host:port/dbname`; required before profile execution |
| `AUDIT_DB_DSN` | audit-service settings compatibility alias | Derived from `DB_DSN` as `postgresql+asyncpg://...` |
| `DATABASE_URL` | RE-OS service integration compatibility alias | Derived from `DB_DSN` as `postgresql+asyncpg://...` |
| `IDENTITY_DATABASE_URL` | identity-service test/settings compatibility alias | Derived from `DB_DSN` as `postgresql+asyncpg://...` |
| `DB_HOST` | CIM, MDM, topology DB compatibility alias | Derived from `DB_DSN`; never implicit `diep-timescaledb` outside Docker network |
| `DB_PORT` | CIM, MDM, topology DB compatibility alias | Derived from `DB_DSN` |
| `DB_NAME` | CIM, MDM, topology DB compatibility alias | Derived from `DB_DSN` |
| `DB_USER` | CIM, MDM, topology DB compatibility alias | Derived from `DB_DSN` |
| `DB_PASSWORD` | CIM, MDM, topology DB compatibility alias | Derived from `DB_DSN`; masked in evidence |
| `REDIS_URL` | Identity/service integration | `redis://localhost:6379/0` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka-enabled profiles | `localhost:9092` only when broker profile enabled |
| `REOS_VALIDATION_PROFILE` | Release 2 profile selection | one of `unit`, `service-integration`, `database-integration`, `docker`, `security`, `legacy-platform`, `release-gate` |
| `PROMETHEUS_PROFILE` | Legacy optional dependency behavior | `absent`, `present`, or `isolated-registry` |
| `AUDIT_INTEGRATION_KAFKA` | Broker-specific audit tests | unset/`0` by default; `1` only when Kafka broker is provisioned |

## 4. Network Names

| Context | Hostname Rule |
|---------|---------------|
| GitHub Actions services | use `localhost`/published ports |
| Docker Compose / legacy internal network | service names such as `diep-timescaledb` are valid only inside that network |
| Local host execution | must not assume Docker-network hostnames resolve |

## 5. Optional vs Mandatory

Mandatory before R2-RISK-017 closure:

- Docker-enabled CI runner evidence,
- database integration profile with DB host resolution and migration output,
- deterministic Prometheus/observability dependency policy,
- test classification manifest passing.

Optional unless a profile explicitly enables them:

- Kafka broker execution,
- Prometheus runtime metrics endpoint behavior,
- deployment/staging environment validation.

## 6. Contract Violation Rule

Any test that requires an undeclared service or optional dependency must be reclassified or blocked
before it can be counted as Release 2 closure evidence.

## 7. R2-PLAT-003 DB_DSN Alignment

`DB_DSN` is the canonical Release 2 database contract. Compatibility variables are generated by:

```bash
python scripts/release2/db_validation_substrate.py env --format shell --output .release2-db.env
```

GitHub Actions writes the same contract to `$GITHUB_ENV` before pytest profile execution. Local and
CI validation must not hand-maintain divergent DB aliases.

## 8. R2-PLAT-002 Database Substrate

The governed database substrate is:

- local service contract: `docker-compose.release2-db.yml`
- shared readiness/migration helper: `scripts/release2/db_validation_substrate.py`
- CI evidence artifact: `release2-db-migrations.jsonl`

The substrate replaces host-specific `pg_isready` and `psql` assumptions for Release 2 validation.
Live database evidence is valid only when the helper emits `database_ready`, migration lifecycle
records, and `timescaledb_extension_present`.

## 9. R2-PLAT-004 Docker Runner Contract

The governed Docker validation substrate is:

- runner preflight: `python scripts/release2/docker_validation.py preflight`
- compose contract validation:
  `python scripts/release2/docker_validation.py compose-config --compose-file docker-compose.release2-db.yml`
- image build evidence:
  `python scripts/release2/docker_validation.py build --context fastapi --tag reos-r2-fastapi:<sha>`

Docker validation evidence is valid only when the helper emits:

- `docker_preflight_passed`,
- passing `docker_client`, `docker_compose`, `docker_buildx`, and `docker_daemon` events,
- passing `docker_compose_config`,
- `docker_build_passed`,
- `docker_image_metadata`.

Local machines with a Docker client but no reachable daemon may produce implementation evidence, but
they are not sufficient operational evidence for closing Docker validation.

## 10. R2-PLAT-005 Legacy DB Hostname Rule

`diep-timescaledb` is a legacy Docker-network hostname. It is valid only as:

- a Docker Compose service/container reference,
- a legacy application default when execution occurs inside the Docker network,
- a unit-test container-name fixture that does not open a database connection.

Release 2 host-based validation must not rely on `diep-timescaledb` resolving from the host. The
Release 2 validation framework must derive `DB_HOST` from `DB_DSN`; for CI service containers and
local host execution this value is `localhost` unless a governed environment explicitly supplies a
different reachable host.

DB-dependent tests must be classified into `service-integration`, `database-integration`, or
`release-gate`. They must not be routed through `legacy-platform`. Mixed files that contain pure
unit tests plus DB-backed tests must declare `Environment-dependent` classification and include a
DB-capable profile.

## 11. R2-PLAT-006 Prometheus Profile Rule

`PROMETHEUS_PROFILE` is the governed Release 2 observability dependency control.

| Value | Behavior | Valid Use |
|-------|----------|-----------|
| `absent` | Metrics objects and legacy `/metrics` endpoints behave as if `prometheus_client` is unavailable, even when the package is installed | Mandatory Release 2 unit, database, and legacy-platform validation default |
| `isolated-registry` | Metrics objects use a private `CollectorRegistry` when `prometheus_client` is available | Tests that must exercise real metric objects without polluting the global registry |
| `present` | Runtime default; metrics use the standard Prometheus client behavior and default registry unless an explicit registry is supplied | Application runtime and metrics endpoint behavior when observability dependency is intentionally present |

Legacy validation must not depend on ambient Python environment state to decide whether metrics are
real or no-op. Tests that require repeated metrics construction must use `absent` or
`isolated-registry`.
