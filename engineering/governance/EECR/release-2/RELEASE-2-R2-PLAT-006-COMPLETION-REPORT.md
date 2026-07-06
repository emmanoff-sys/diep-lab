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
| `services/mdm/metrics.py` | Adds governed Prometheus profile handling and isolated registry support |
| `services/opcua/metrics.py` | Adds governed Prometheus profile handling and isolated registry support |
| `services/mdm/health.py` | Makes `/metrics` honor `PROMETHEUS_PROFILE=absent` |
| `services/opcua/health.py` | Makes `/metrics` honor `PROMETHEUS_PROFILE=absent` |
| `tests/test_mdm_pipeline.py` | Sets governed absent profile for MDM legacy validation |
| `tests/test_opcua_metrics.py` | Sets governed absent profile for OPC UA metrics validation |
| `tests/test_opcua_subscription.py` | Sets governed absent profile for OPC UA subscription validation |
| `tests/test_opcua_service.py` | Sets governed absent profile for OPC UA service validation |
| `tests/test_opcua_health.py` | Validates absent-profile metrics endpoint behavior |
| `tests/test_release2_observability_determinism.py` | Adds explicit absent and isolated-registry profile evidence |
| `engineering/governance/EECR/release-2/RELEASE-2-TEST-CLASSIFICATION.csv` | Classifies new observability determinism test |
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
| pytest affected scope | PASS |
| MDM/OPC UA legacy slice | PASS, 136 tests under `PROMETHEUS_PROFILE=absent` |
| Isolated registry validation | PASS |
| Classification validator | PASS, 101 files classified |
| Workflow YAML validation | PASS |
| git diff --check | PASS |

## 5. Tests Executed

```bash
PROMETHEUS_PROFILE=absent python -m pytest \
  tests/test_mdm_*.py tests/test_opcua_*.py tests/test_release2_observability_determinism.py -q
PROMETHEUS_PROFILE=isolated-registry python -m pytest \
  tests/test_release2_observability_determinism.py -q
python scripts/release2/validate_test_classification.py
```

## 6. Remaining Risks

| Risk | Status |
|------|--------|
| R2-PLAT-004 Docker operational validation pending | Not addressed by R2-PLAT-006 |
| R2-PLAT-007 security dependency audit segmentation | Not addressed by R2-PLAT-006 |
| R2-PLAT-008 final release gate evidence | Not authorized in this work package |

## 7. EECR Update Recommendation

Record EECR-CHG-087 as R2-PLAT-006 implemented. R2-RISK-017 remains mitigated until R2-PLAT-007
and R2-PLAT-008 are completed or residual risk is formally accepted.

## 8. ADR Impact

No new ADR is required. ADR-R2-07 remains valid; this work implements its governed validation
profile model for optional observability dependencies.

## 9. Recommendation

COMPLETE

Next recommended authorized work package: R2-PLAT-007, Security Dependency Audit Segmentation.
Do not implement R2-PLAT-007 until separately authorized.
