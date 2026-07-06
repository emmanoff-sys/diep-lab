# Release 2 Legacy DB Hostname and Classification Recovery
### DAEP / RE-OS | R2-PLAT-005 | Revision 1.0 | 2026-07-06

## 1. Purpose

R2-PLAT-005 removes ambiguity between legacy Docker-network database defaults and Release 2
host/CI validation execution. It is a validation-governance and test-fixture recovery item only. It
does not change application business logic, Release 1, EPIC-006 functionality, WP-006-03B, EPIC-007,
or R2-PLAT-006+ scope.

## 2. Root Cause

Legacy modules retain `diep-timescaledb` as a Docker-network default. That is valid inside the
legacy Docker Compose network, but invalid for host-based Release 2 validation where GitHub Actions
services and local DB substrate are reached through `localhost` or a governed `DB_DSN`-derived host.

The validation failure was amplified by one incorrectly isolated legacy unit test file:
`tests/test_cim_mapping_devices.py` claimed to use fake DB access, but direct row-conversion tests
did not install the fake topology lookup, so they reached `services.cim.db.query_one()` and attempted
to resolve `diep-timescaledb`.

## 3. Hostname Reference Classification

| Reference Type | Meaning | Release 2 Action |
|----------------|---------|------------------|
| Docker-only assumption | Compose service/container references | Valid only inside Docker network |
| Environment-derived legacy default | Legacy app defaults in `fastapi/common.py`, `fastapi/auth.py`, and `services/cim/config.py` | Override through `DB_DSN`-derived `DB_HOST` in Release 2 validation |
| Fixture container name | Unit tests that validate container inventory text only | Allowed if no DB connection is attempted |
| DB-dependent test | Test opens or reaches DB-backed code paths | Must be in `service-integration`, `database-integration`, or `release-gate`; never `legacy-platform` |

## 4. Enforcement

The governed audit helper is:

```bash
python scripts/release2/legacy_db_hostname_audit.py \
  --output release2-legacy-db-hostname-audit.jsonl
```

It emits a JSONL inventory of legacy hostname references and fails if a DB-dependent test is routed
through `legacy-platform` or lacks a governed DB-capable profile.

## 5. Test Fixture Recovery

`tests/test_cim_mapping_devices.py` now installs an autouse fake topology lookup. Pure row mapping
tests remain unit/legacy-platform tests and no longer fall through to live DB hostname resolution.

## 6. Exit Criteria

R2-PLAT-005 is complete when:

- legacy hostname inventory is recorded,
- classification audit passes,
- affected CIM mapping tests pass without resolving `diep-timescaledb`,
- database-dependent files remain classified into DB-capable profiles,
- Release 2 workflow runs the audit during classification.
