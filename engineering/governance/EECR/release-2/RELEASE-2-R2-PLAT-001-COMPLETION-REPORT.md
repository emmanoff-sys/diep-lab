# R2-PLAT-001 Completion Report
### DAEP / RE-OS | Validation Profile Pytest Isolation | Revision 1.0 | 2026-07-06

## 1. Root Cause Confirmation

R2-PLAT-001 is confirmed as a validation orchestration failure. The Release 2 validation workflow
passed all files for a profile into one pytest process. That caused service-local
`tests/conftest.py` files to collide as `tests.conftest`, producing `ImportPathMismatchError`
before tests could execute.

The affected evidence was:

- unit validation: `EXIT_CODE=4`
- service integration validation: `EXIT_CODE=4`

## 2. Design Approach

The Release 2 classification helper now supports pytest isolation groups. Test files are grouped by
their owning package root:

- `services/<service>`
- `libs/<library>`
- repository-root `tests`

The Release 2 validation workflow runs pytest-based validation profiles one group at a time. Each
group produces its own JUnit XML artifact. This prevents unrelated service-local pytest
configuration from sharing one import namespace while preserving the approved test classification
manifest and validation profile model.

## 3. Scope Control

This change is limited to R2-PLAT-001:

- no application functionality changed
- no Release 1 artefacts changed
- no EPIC-006 implementation changed
- no WP-006-03B work started
- no R2-PLAT-002 or later recovery work implemented

## 4. Validation Evidence Required

R2-PLAT-001 is complete when:

| Criterion | Required Result |
|-----------|-----------------|
| Test classification manifest | PASS |
| Unit profile isolation groups | Listed deterministically |
| Service integration isolation groups | Listed deterministically |
| Unit profile execution | No `ImportPathMismatchError` |
| Service integration profile execution | No `ImportPathMismatchError` |
| Quality gates | Ruff, Black, isort, mypy, affected pytest, `git diff --check` complete |

## 5. Validation Evidence Produced

Evidence directory:
`engineering/governance/EECR/release-2/evidence/r2-plat-001-2026-07-06/`

| Gate | Command / Evidence | Result |
|------|--------------------|--------|
| Classification | `python3 scripts/release2/validate_test_classification.py` | PASS, 97 files classified |
| Unit groups | `--profile unit-tests --list-groups` | PASS, 7 isolation groups |
| Service integration groups | `--profile service-integration --list-groups` | PASS, 3 isolation groups |
| Unit pytest affected scope | grouped pytest execution | PASS for R2-PLAT-001 isolation: no `ImportPathMismatchError`; downstream test failures remain |
| Service integration pytest affected scope | grouped pytest execution | PASS for R2-PLAT-001 isolation: no `ImportPathMismatchError`; downstream test failures remain |
| Ruff | `python -m ruff check scripts/release2/validate_test_classification.py` | PASS |
| Black | `python -m black --check --diff scripts/release2/validate_test_classification.py` | PASS |
| isort | `python -m isort --check-only --diff scripts/release2/validate_test_classification.py` | PASS |
| mypy | `python -m mypy scripts/release2/validate_test_classification.py` | PASS |
| Workflow YAML parse | PyYAML parse of `.github/workflows/*.yml` | PASS |
| Diff hygiene | `git diff --check` | PASS |

JUnit evidence:

| Group | Summary |
|-------|---------|
| Unit group 1 | 29 passed |
| Unit group 2 | 20 passed |
| Unit group 3 | 14 passed |
| Unit group 4 | 14 passed |
| Unit group 5 | 4 collection errors caused by missing `DB_DSN`, assigned to R2-PLAT-003 |
| Unit group 6 | 66 passed, 2 failed from dependency behavior, not import collision |
| Unit group 7 | 103 passed, 3 failed, 2 skipped due `diep-timescaledb`, assigned to R2-PLAT-005 |
| Service integration group 1 | 9 passed |
| Service integration group 2 | 6 collection errors caused by missing `DB_DSN`, assigned to R2-PLAT-003 |
| Service integration group 3 | 11 passed, 11 failed, 2 skipped due unavailable DB/substrate behavior, assigned to R2-PLAT-002/R2-PLAT-003 |

Both affected profile logs were checked for `ImportPathMismatch`; none was present.

## 6. Files Modified

| File | Purpose |
|------|---------|
| `.github/workflows/release2-validation.yml` | Runs pytest-based validation profile groups in isolated pytest invocations |
| `scripts/release2/validate_test_classification.py` | Adds deterministic pytest isolation grouping by package/test root |
| `engineering/governance/EECR/release-2/RELEASE-2-R2-PLAT-001-COMPLETION-REPORT.md` | Records R2-PLAT-001 implementation and evidence |
| `engineering/governance/EECR/change-log.md` | Records EECR-CHG-082 |

## 7. Remaining Risks

R2-PLAT-001 does not address:

- database substrate readiness
- missing `DB_DSN`
- Docker daemon availability
- legacy DB hostname assumptions
- Prometheus optional-dependency determinism
- pip-audit dependency surface segmentation

Those remain assigned to R2-PLAT-002 through R2-PLAT-008.

## 8. EECR Recommendation

Record R2-PLAT-001 as implemented. Keep R2-RISK-017 MITIGATED, not RESOLVED, until the remaining
Platform Recovery work packages complete and the release gate is re-run.

## 9. ADR Impact

No ADR change is required. ADR-R2-07 already authorizes the validation governance model; this
change implements the approved isolation requirement inside that framework.

## 10. Recommendation

Recommendation: **COMPLETE** for R2-PLAT-001.

Rationale: the import-path collision is eliminated and the affected profiles now execute in
isolated package/test-root groups. The remaining non-green pytest results are downstream platform
items already assigned to R2-PLAT-002 through R2-PLAT-008.
