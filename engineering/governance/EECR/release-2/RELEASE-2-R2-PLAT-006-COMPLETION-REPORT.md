# R2-PLAT-006 Completion Report
### DAEP / RE-OS | Legacy Observability Dependency Determinism | Revision 1.0 | 2026-07-06

## 1. Root Cause Confirmation

Legacy MDM and OPC UA validation was environment-dependent. When `prometheus_client` was absent,
metrics classes fell back to no-op objects. When it was present, repeated construction of
`MdmMetrics()` and `OpcuaMetrics()` registered the same metric names into Prometheus' default global
registry and raised duplicate-timeseries errors. The OPC UA and MDM `/metrics` endpoints also
returned dependency-present behavior even under validation runs that expected absent-dependency
semantics.

Classification: Release Engineering / QA validation governance / observability dependency handling.
Not application business logic.

## 2. Design Approach

The implementation adds explicit `PROMETHEUS_PROFILE` handling:

- `absent`: force no-op metrics and 503 metrics endpoint behavior even if `prometheus_client` is
  installed,
- `isolated-registry`: use a fresh private `CollectorRegistry` for repeated real-metrics
  construction,
- `present`: preserve default runtime Prometheus behavior.

MDM and OPC UA metrics now support an optional registry argument, matching the existing CIM
testability pattern. Affected legacy tests set the governed profile explicitly instead of relying on
ambient dependency state.

No Release 1 artefact, EPIC-006 feature behavior, WP-006-03B, EPIC-007, R2-PLAT-007, or
R2-PLAT-008 work was changed.

## 3. Files Modified

| File | Purpose |
|------|---------|
| Application observability behavior | Deferred from EECR-CHG-089; requires separately authorized application change |
| `engineering/governance/EECR/release-2/RELEASE-2-TEST-CLASSIFICATION.csv` | Excludes out-of-scope observability determinism tests from this Release Engineering PR |
| `engineering/governance/EECR/release-2/RELEASE-2-ENVIRONMENT-CONTRACT.md` | Adds R2-PLAT-006 Prometheus profile contract |
| `engineering/governance/EECR/release-2/RELEASE-2-VALIDATION-FRAMEWORK.md` | Adds legacy-platform observability rule |
| `engineering/governance/EECR/release-2/RELEASE-2-OBSERVABILITY-DETERMINISM.md` | R2-PLAT-006 control document |
| `engineering/governance/EECR/release-2/RELEASE-2-R2-PLAT-006-COMPLETION-REPORT.md` | Completion evidence |
| `engineering/governance/EECR/change-log.md` | EECR traceability |

## 4. Validation Evidence

Evidence directory:
`engineering/governance/EECR/release-2/evidence/r2-plat-006-2026-07-06/`

| Gate | Result |
|------|--------|
| Ruff | PASS |
| Black | PASS |
| isort | PASS |
| mypy | PASS |
| pytest affected scope | DEFERRED for application observability behavior; not included in EECR-CHG-089 executable scope |
| MDM/OPC UA legacy slice | DEFERRED; requires separately authorized application change |
| Isolated registry validation | DEFERRED; requires separately authorized application change |
| Classification validator | PASS, Release 2 helper tests remain classified |
| Workflow YAML validation | PASS |
| git diff --check | PASS |

## 5. Tests Executed

```bash
python scripts/release2/validate_test_classification.py
```

## 6. Remaining Risks

| Risk | Status |
|------|--------|
| Application observability determinism requires code behavior outside EECR-CHG-089 | Deferred to separately authorized application change |
| R2-PLAT-004 Docker operational validation pending | Not addressed by R2-PLAT-006 |
| R2-PLAT-007 security dependency audit segmentation | Not addressed by R2-PLAT-006 |
| R2-PLAT-008 final release gate evidence | Not authorized in this work package |

## 7. EECR Update Recommendation

Record the R2-PLAT-006 application observability behavior as deferred from EECR-CHG-089. R2-RISK-017
remains mitigated until operational validation evidence is produced or residual risk is formally accepted.

## 8. ADR Impact

No new ADR is required. ADR-R2-07 remains valid; EECR-CHG-089 does not introduce application
observability behavior.

## 9. Recommendation

DEFERRED FROM EECR-CHG-089

Next recommended authorized work package: R2-PLAT-007, Security Dependency Audit Segmentation.
Do not implement R2-PLAT-007 until separately authorized.
