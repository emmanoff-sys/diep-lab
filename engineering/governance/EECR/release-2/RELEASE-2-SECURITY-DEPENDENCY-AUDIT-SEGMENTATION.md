# Release 2 Security Dependency Audit Segmentation
### DAEP / RE-OS | R2-PLAT-007 | R2-RISK-017 | 2026-07-06

## 1. Purpose

R2-PLAT-007 establishes the governed Release 2 dependency-audit model. The control separates
independent dependency surfaces before security audit execution so `pip-audit` produces
scope-aware CVE evidence rather than failing on unrelated resolver conflicts.

This is a Release Engineering and DevSecOps control. It does not authorize dependency upgrades,
business-functionality changes, WP-006-03B, EPIC-007, or Release 1 modification.

## 2. Root Cause

The previous Release 2 security validation command combined multiple independent requirement
locks into one `pip-audit` invocation:

- `templates/python-service/requirements.txt`
- `services/audit-service/requirements.txt`
- `fastapi/requirements.txt`

Those files describe separate product/runtime surfaces and carry different FastAPI dependency
lines. A single resolver input makes security validation ambiguous because a dependency conflict can
fail the gate before CVE evaluation occurs. The issue is Release Engineering / validation governance,
not application behavior.

## 3. Governed Dependency Surfaces

| Surface ID | Category | Source | Audit Mode | Gate Impact |
|------------|----------|--------|------------|-------------|
| `release2-template-runtime` | Release 2 application dependencies | `templates/python-service/requirements.txt` | Mandatory `pip-audit --strict` | Required |
| `release2-audit-service-runtime` | Release 2 application dependencies | `services/audit-service/requirements.txt` | Mandatory `pip-audit --strict` | Required |
| `release2-shared-library-runtime` | Shared library dependencies | `libs/reos-*/pyproject.toml` | Classified; public transitives audited through pinned consuming locks | Required classification |
| `legacy-diep-runtime` | Legacy DIEP dependencies | `fastapi/requirements.txt` | Mandatory `pip-audit --strict` | Required |
| `development-tooling` | Development-only tooling | `pyproject.toml` and service/lib dev extras | Classified; outside runtime gate unless a tooling lock is approved | Non-runtime |
| `optional-dependencies` | Optional dependencies | service pyprojects and legacy runtime pins | Classified; audited when materialized in pinned runtime locks | Required classification |

## 4. Execution Model

The authoritative helper is:

```bash
python scripts/release2/security_dependency_audit.py \
  --output-dir release2-pip-audit \
  --summary release2-pip-audit-summary.json
```

For each mandatory runtime surface, the helper:

1. Reads the governed source manifest.
2. Removes first-party `reos-*` package lines from public `pip-audit` input.
3. Writes a surface-specific requirements artifact.
4. Runs `pip-audit --strict` against that one surface.
5. Writes a per-surface audit JSON and aggregate summary.

Metadata-only surfaces are recorded in the summary as `classified`, preventing silent leakage into
runtime audit scope.

## 5. Pass Criteria

The security dependency audit passes only when:

- every mandatory runtime surface materializes successfully;
- every mandatory runtime surface completes `pip-audit --strict`;
- no mandatory runtime surface reports an unaccepted vulnerability;
- shared library, optional dependency, legacy, and development-only scopes are explicitly classified;
- CI uploads the summary and all per-surface artifacts.

## 6. Traceability

| Control | Reference |
|---------|-----------|
| Risk | R2-RISK-017 |
| Work Package | R2-PLAT-007 |
| Architecture Decision | ADR-R2-07 |
| Validation Framework | `RELEASE-2-VALIDATION-FRAMEWORK.md` |
| Workflow | `.github/workflows/release2-validation.yml` |
| Helper | `scripts/release2/security_dependency_audit.py` |
