# R2-PLAT-007 Completion Report
### Security Dependency Audit Segmentation | 2026-07-06

## 1. Root Cause Confirmation

R2-PLAT-007 confirmed that Release 2 security validation previously treated independent dependency
surfaces as one resolver input. Template, audit-service, and legacy DIEP dependency locks are not a
single deployable dependency graph. Combining them in one `pip-audit` command creates scope
ambiguity and can fail before CVE evaluation.

Classification: Release Engineering / Validation Governance.

## 2. Design Approach

Implemented a governed dependency-audit helper that:

- classifies Release 2 application, shared library, legacy, development-only, and optional surfaces;
- materializes one public requirements file per mandatory pinned runtime surface;
- excludes first-party `reos-*` packages from public advisory-index audit input while recording the
  exclusion in evidence;
- runs `pip-audit --strict` independently per mandatory runtime surface;
- emits an aggregate summary plus per-surface artifacts for CI upload.

No dependency pins, business functionality, Release 1 artefacts, WP-006-03B scope, EPIC-007 scope,
or architecture implementation were modified.

## 3. Files Modified

| File | Change |
|------|--------|
| `.github/workflows/release2-validation.yml` | Security profile now invokes the segmented audit helper and uploads per-surface artifacts. |
| `scripts/release2/security_dependency_audit.py` | New governed R2-PLAT-007 dependency audit segmentation helper. |
| `tests/test_release2_security_dependency_audit.py` | New helper unit tests. |
| `engineering/governance/EECR/release-2/RELEASE-2-TEST-CLASSIFICATION.csv` | Classified the new helper test. |
| `engineering/governance/EECR/release-2/RELEASE-2-VALIDATION-FRAMEWORK.md` | Updated the Security Validation profile to require segmented dependency evidence. |
| `engineering/governance/EECR/release-2/RELEASE-2-SECURITY-DEPENDENCY-AUDIT-SEGMENTATION.md` | New governance control document. |
| `engineering/governance/EECR/change-log.md` | Added EECR-CHG-088. |

## 4. Validation Evidence

Evidence directory:

`engineering/governance/EECR/release-2/evidence/r2-plat-007-2026-07-06/`

Required evidence:

- `security-audit-helper-results.xml`
- `security-audit-dry-run-summary.json`
- `release2-pip-audit-summary.json`
- `release2-pip-audit/`
- `classification-validation.txt`
- `workflow-yaml-validation.txt`
- `quality-gates.log`

Validation result:

- Ruff PASS
- Black PASS
- isort PASS
- mypy PASS
- affected pytest PASS: 4 tests passed
- classification validator PASS: 102 files classified
- workflow YAML validation PASS
- segmented `pip-audit --strict` PASS for:
  - `release2-template-runtime`
  - `release2-audit-service-runtime`
  - `legacy-diep-runtime`
- `git diff --check` PASS

## 5. Remaining Risks

| Risk | Status | Treatment |
|------|--------|-----------|
| A mandatory surface may report a real CVE after segmentation | Open until CI confirms local evidence | Treat as a real security finding; do not weaken gate. |
| Shared libraries do not yet have standalone pinned runtime lock files | Controlled | Public transitives are audited through consuming pinned app/template locks; standalone locks require a future governed dependency-policy change. |
| Development-only tooling is classified but not runtime-gated | Accepted for R2-PLAT-007 scope | A tooling-lock audit can be authorized separately if the Programme Board wants development tooling in the release gate. |
| Identity-service dependency lock contains an invalid `mdurl==0.1.3` pin if audited as a standalone surface | Discovered outside R2-PLAT-007 security workflow scope | Do not change under R2-PLAT-007 because Release 1 is frozen and identity-service was not part of the current Release 2 security workflow input. Raise as a separate dependency-governance review if the Programme Board wants identity runtime audit added to Release 2. |

## 6. EECR Update Recommendation

Record EECR-CHG-088 as a RECOVERY / VALIDATION / CI/CD / SECURITY change for R2-PLAT-007.

## 7. ADR Impact

ADR-R2-07 remains valid. This work package implements ADR-R2-07 validation-governance controls for
security dependency evidence. No new ADR is required.

## 8. Recommendation

COMPLETE.

R2-PLAT-007 has implemented the governed segmented dependency audit model and produced local
evidence that mandatory runtime surfaces pass `pip-audit --strict` independently. CI validation is
still required before R2-RISK-017 can move from MITIGATED to RESOLVED.
