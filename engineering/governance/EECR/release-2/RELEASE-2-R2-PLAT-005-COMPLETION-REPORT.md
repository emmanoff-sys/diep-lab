# R2-PLAT-005 Completion Report
### DAEP / RE-OS | Legacy DB Hostname and Test Classification Recovery | Revision 1.0 | 2026-07-06

## 1. Root Cause Confirmation

`diep-timescaledb` and similar legacy database hostname assumptions are present as:

- Docker Compose service/container references,
- environment-derived legacy defaults in `fastapi/common.py`, `fastapi/auth.py`, and
  `services/cim/config.py`,
- unit-test fixture container-name values in `tests/test_deployment_unit.py`.

The Release 2 validation framework cannot resolve Docker-network hostnames from host-based
execution. R2-PLAT-003 already provides the governed `DB_DSN` contract and derives `DB_HOST`; the
remaining R2-PLAT-005 defect was that legacy profile routing and one CIM mapping fixture still
allowed host execution to fall back to the Docker-only hostname.

Classification: Release Engineering / QA validation governance / environment contract. Not
application business logic.

## 2. Design Approach

The implementation:

- adds a governed legacy DB hostname and classification audit helper,
- wires the audit into the Release 2 classification job,
- fixes `tests/test_cim_mapping_devices.py` so pure unit tests mock topology DB lookup consistently,
- updates test classification metadata for the new audit helper and CIM mapping fixture behavior,
- records the Release 2 hostname rule in the environment and validation framework documents.

No application business logic, Release 1 artefact, EPIC-006 feature behavior, WP-006-03B,
EPIC-007, R2-PLAT-006, R2-PLAT-007, or R2-PLAT-008 work was changed.

## 3. Files Modified

| File | Purpose |
|------|---------|
| `scripts/release2/legacy_db_hostname_audit.py` | Hostname inventory and DB-profile classification audit |
| `tests/test_release2_legacy_db_hostname_audit.py` | Unit tests for the audit helper |
| `tests/test_cim_mapping_devices.py` | Autouse fake topology lookup to prevent live DB fallback in pure mapping tests |
| `.github/workflows/release2-validation.yml` | Runs hostname/classification audit during Release 2 classification |
| `engineering/governance/EECR/release-2/RELEASE-2-TEST-CLASSIFICATION.csv` | Classifies the new audit helper test and clarifies CIM mapping device fixture behavior |
| `engineering/governance/EECR/release-2/RELEASE-2-ENVIRONMENT-CONTRACT.md` | Adds R2-PLAT-005 legacy hostname rule |
| `engineering/governance/EECR/release-2/RELEASE-2-VALIDATION-FRAMEWORK.md` | Adds legacy-platform DB hostname rule |
| `engineering/governance/EECR/release-2/RELEASE-2-LEGACY-DB-HOSTNAME-RECOVERY.md` | R2-PLAT-005 control document |
| `engineering/governance/EECR/release-2/RELEASE-2-R2-PLAT-005-COMPLETION-REPORT.md` | Completion evidence |
| `engineering/governance/EECR/change-log.md` | EECR traceability |

## 4. Validation Evidence

Evidence directory:
`engineering/governance/EECR/release-2/evidence/r2-plat-005-2026-07-06/`

| Gate | Result |
|------|--------|
| Ruff | PASS |
| Black | PASS |
| isort | PASS |
| mypy | PASS |
| pytest affected scope | PASS |
| Classification validator | PASS, 100 files classified |
| Legacy DB hostname audit | PASS, 16 references classified and zero profile-routing errors |
| Fixture validation | PASS, CIM mapping devices tests no longer resolve `diep-timescaledb` |
| Database profile validation | PASS for routing/classification evidence; live DB execution remains governed by R2-PLAT-002/003 substrate availability |
| Legacy compatibility validation | PASS for affected CIM mapping device scope |
| Workflow YAML validation | PASS |
| Docker Compose validation | Not modified by R2-PLAT-005 |
| git diff --check | PASS |

## 5. Tests Executed

```bash
python -m pytest tests/test_cim_mapping_devices.py tests/test_release2_legacy_db_hostname_audit.py -q
python scripts/release2/legacy_db_hostname_audit.py
python scripts/release2/validate_test_classification.py
python -m pytest tests/test_cim_mapping_devices.py -q
```

## 6. Remaining Risks

| Risk | Status |
|------|--------|
| Full legacy profile still contains R2-PLAT-006 observability dependency risk | Not addressed by R2-PLAT-005 |
| Docker operational validation remains pending from R2-PLAT-004 | Not addressed by R2-PLAT-005 |
| Live DB availability for database integration execution | Governed by R2-PLAT-002/003 and environment availability |

## 7. EECR Update Recommendation

Record EECR-CHG-086 as R2-PLAT-005 implemented. R2-RISK-017 remains mitigated until all remaining
platform recovery packages and the final release gate evidence are complete or accepted.

## 8. ADR Impact

No new ADR is required. ADR-R2-07 remains valid; this work implements the approved Release 2
validation governance model by enforcing DB hostname/profile routing rules.

## 9. Recommendation

COMPLETE

Next recommended authorized work package: R2-PLAT-006, Legacy Observability Dependency Determinism.
Do not implement R2-PLAT-006 until separately authorized.
