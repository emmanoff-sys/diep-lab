# R2-PLAT-003 Completion Report
### DAEP / RE-OS | Database Environment Contract Alignment | Revision 1.0 | 2026-07-06

## 1. Root Cause Confirmation

Release 2 database validation used multiple DB environment shapes:

- audit-service required `AUDIT_DB_DSN` because its settings class uses the `AUDIT_` prefix,
- identity-service tests used `IDENTITY_DATABASE_URL`,
- service integration used `DATABASE_URL`,
- legacy CIM/MDM/topology tests used `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`,
- migration tooling from R2-PLAT-002 used split DB variables.

This caused audit-service tests to fail during collection with a missing `DB_DSN` field even when
other DB variables were present.

## 2. Design

`DB_DSN` is now the canonical Release 2 database contract. The R2-PLAT-002 substrate helper derives
all compatibility aliases from it:

- `AUDIT_DB_DSN`
- `DATABASE_URL`
- `IDENTITY_DATABASE_URL`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

GitHub Actions exports the derived contract to `$GITHUB_ENV` before pytest profile execution. Docker
Compose records the same canonical contract. Local execution can generate a shell or JSON env file
from the helper.

## 3. Scope Control

This change is limited to R2-PLAT-003:

- no application functionality changed,
- no service settings classes changed,
- no EPIC-006 implementation changed,
- no WP-006-03B authorization,
- no R2-PLAT-004 work started.

## 4. Files Changed

| File | Purpose |
|------|---------|
| `scripts/release2/db_validation_substrate.py` | Parses canonical `DB_DSN` and emits compatibility aliases |
| `tests/test_release2_db_validation_substrate.py` | Tests `DB_DSN` parsing, alias derivation, and env-file output |
| `.github/workflows/release2-validation.yml` | Exports `DB_DSN`-derived environment before pytest profiles |
| `docker-compose.release2-db.yml` | Records canonical DB contract in local DB compose configuration |
| `engineering/governance/EECR/release-2/RELEASE-2-ENVIRONMENT-CONTRACT.md` | Updates official environment contract |
| `engineering/governance/EECR/release-2/RELEASE-2-DATABASE-VALIDATION-SUBSTRATE.md` | Updates substrate documentation |
| `engineering/governance/EECR/release-2/RELEASE-2-R2-PLAT-003-COMPLETION-REPORT.md` | Completion evidence |
| `engineering/governance/EECR/change-log.md` | EECR traceability |

## 5. Validation

Evidence directory:
`engineering/governance/EECR/release-2/evidence/r2-plat-003-2026-07-06/`

| Gate | Result |
|------|--------|
| Ruff | PASS |
| Black | PASS |
| isort | PASS |
| mypy | PASS |
| pytest affected scope | PASS, 6 substrate contract tests |
| Environment validation | PASS, `DB_DSN` derives all compatibility aliases with masked evidence |
| Audit-service collection symptom check | PASS for R2-PLAT-003: no missing `DB_DSN`; unrelated schema assertions remain non-green |
| Workflow YAML parse | PASS |
| Docker Compose config | PASS, canonical `DB_DSN` visible with password masked in evidence |
| DB connectivity evidence | Generated; local DB unavailable on `localhost:15432`, as expected without live DB substrate |
| git diff --check | PASS |

Evidence files:

| Artefact | Purpose |
|----------|---------|
| `quality-gates.log` | Ruff, Black, isort, mypy, pytest, classification, env validation, compose config, YAML, connectivity, diff check |
| `environment-validation.log` | Standalone environment contract and compose validation evidence |
| `db-env-contract-unit-results.xml` | JUnit for substrate contract tests |
| `audit-env-contract-collection.log` | Targeted audit-service collection symptom check |
| `audit-env-contract-collection.xml` | JUnit for targeted audit-service check |
| `db-dsn-connectivity-local.jsonl` | Masked local DB connectivity evidence |

## 6. Environment Contract

Canonical input:

```bash
DB_DSN=postgresql://diep:diep123@localhost:5432/diep
```

Derived aliases:

```bash
AUDIT_DB_DSN=postgresql+asyncpg://diep:diep123@localhost:5432/diep
DATABASE_URL=postgresql+asyncpg://diep:diep123@localhost:5432/diep
IDENTITY_DATABASE_URL=postgresql+asyncpg://diep:diep123@localhost:5432/diep
DB_HOST=localhost
DB_PORT=5432
DB_NAME=diep
DB_USER=diep
DB_PASSWORD=diep123
```

## 7. Remaining Risks

R2-PLAT-003 does not close:

- live DB availability,
- Docker daemon availability,
- legacy DB-host classification issues,
- Prometheus optional-dependency determinism,
- pip-audit dependency surface segmentation.

Additional non-R2-PLAT-003 observation: the targeted audit-service unit check executed after
environment alignment and no longer failed for missing `DB_DSN`, but two schema assertions remain
non-green because mocked `event_metadata` is not a dictionary. This is not an environment contract
failure and was not fixed under this work package.

## 8. EECR Recommendation

Record R2-PLAT-003 as implemented. Keep R2-RISK-017 mitigated until R2-PLAT-004 through
R2-PLAT-008 complete and the Release 2 validation gate is re-run.

## 9. ADR Impact

No ADR change is required. ADR-R2-07 already governs the Release 2 validation model; this change
aligns the database environment contract under that ADR.

## 10. Recommendation

Recommendation: **COMPLETE**.

Rationale: `DB_DSN` is now the canonical contract, compatibility aliases are generated
deterministically for all known consumers, and the original missing-`DB_DSN` collection failure is
removed. Remaining failures are outside R2-PLAT-003.
