# Dependency Policy — DAEP / RE-OS

## Authority
- LLD v2.0 §2.1 (pip-audit row: "Dependency CVE scanning", config `requirements.txt`, enforcement "CI Stage 2; known CVE = PR blocked")
- Roadmap v1.0 §11.1 Stage 3 (dependency scanning: pip-audit / npm audit, <2 min, no known CVEs, PR blocked)
- WP-001-08 Engineering Package

---

## 1. Exact-Pin Requirement

All dependency versions **must** be exact-pinned using the `==` operator. Floating ranges (`>=`, `~=`, `^`) are permitted only in the human-authored source file (`requirements.in` for Python); the compiled, committed output (`requirements.txt`) **must** use exact pins throughout.

| Language | Source File | Pinned Output File | Pin Format |
|----------|------------|-------------------|------------|
| Python | `requirements.in` | `requirements.txt` | `package==x.y.z` |
| JavaScript / TypeScript | `package.json` | `package-lock.json` | lockfile exact pin |
| Flutter / Dart | `pubspec.yaml` | `pubspec.lock` | lockfile exact pin |

**Rationale:** Exact pins make the dependency tree fully reproducible across all environments (developer workstation, CI runner, production VM). A floating `>=` can silently pull a new version that introduces a CVE or a breaking change between a CI pass and a production deploy without any visible diff in source control.

---

## 2. Python Dependency Workflow

### 2.1 Toolchain

| Tool | Purpose | Install |
|------|---------|---------|
| `pip-compile` | Resolves `requirements.in` → exact-pinned `requirements.txt` | `pip install pip-tools` |
| `pip-sync` | Installs exactly the packages in `requirements.txt`; removes unlisted extras | included in `pip-tools` |
| `pip-audit` | Scans `requirements.txt` for known CVEs from the OSV database and PyPI Advisory DB | `pip install pip-audit` |

### 2.2 Workflow

```
requirements.in                  ← human-authored; floating ranges are OK here
        │
        │  pip-compile requirements.in -o requirements.txt
        ▼
requirements.txt                 ← machine-generated; exact pins; committed to git
        │
        │  pip-sync requirements.txt
        ▼
virtualenv                       ← exact environment installed
        │
        │  pip-audit -r requirements.txt --desc on
        ▼
CVE report                       ← zero known CVEs = proceed; any finding = PR blocked
```

### 2.3 Commands

```bash
# Install pip-tools and pip-audit.
pip install pip-tools pip-audit

# Compile the pinned requirements file from the source file.
# Run this after any change to requirements.in.
pip-compile requirements.in -o requirements.txt

# Install exactly the pinned environment.
# Removes packages not listed in requirements.txt.
pip-sync requirements.txt

# Scan for known CVEs. Zero findings required before committing.
pip-audit -r requirements.txt --desc on

# Install with dev dependencies (local development only).
pip install -e ".[dev]"
```

> **IMPORTANT:** Never install packages with `pip install <package>` directly into a managed
> environment. Always update `requirements.in`, regenerate `requirements.txt` with
> `pip-compile`, and re-install with `pip-sync`. Direct `pip install` bypasses both the
> exact-pin policy and the CVE gate.

### 2.4 Separate Files per Dependency Set

Each Python service or library maintains:

| File | Contents |
|------|----------|
| `requirements.in` | Runtime dependencies (mirrors `pyproject.toml [project].dependencies`) |
| `requirements.txt` | pip-compile output — exact-pinned runtime deps including transitive tree |

Optional dev-dependency pinning (`requirements-dev.in` / `requirements-dev.txt`) follows the same pattern and mirrors `pyproject.toml [project.optional-dependencies].dev`.

The canonical scaffold at `templates/python-service/` provides both files as the starting point for every new service.

---

## 3. CVE Scanning Policy

| Severity | pip-audit finding | Required Action |
|----------|------------------|-----------------|
| Any known CVE | Finding reported | **Block merge.** Update to a patched version or raise a documented exception per §3.1. |

pip-audit checks the [Open Source Vulnerabilities (OSV) database](https://osv.dev) and the PyPI Advisory Database. A finding against any pinned package blocks the PR **regardless of whether the vulnerable code path is reachable** — this conservative stance is consistent with LLD v2.0 §2.1 and Roadmap v1.0 §11.1 Stage 3.

### 3.1 CVE Exception Process

If no patched version is available and a finding must be accepted temporarily:

1. Raise an Engineering Clarification Request (ECR) citing the CVE ID, the affected package and version, and the business justification for accepting the risk.
2. Security Lead provides written sign-off.
3. The exception is recorded in the risk register with a 90-day expiry — a patched version must be available within 90 days or the service is re-evaluated for functional impact.
4. The `pip-audit` invocation for CI may add `--ignore-vuln <CVE-ID>` with the ECR reference in a comment on the same line; this comment must include the ECR ID and expiry date.

---

## 4. Upgrade Process

Bumping a pinned dependency follows this sequence:

```bash
# 1. Edit requirements.in to update the version constraint.
#    Example: change "fastapi>=0.111.0" to "fastapi>=0.115.0"

# 2. Recompile the pinned file.
pip-compile requirements.in -o requirements.txt

# 3. Install the updated environment.
pip-sync requirements.txt

# 4. Run the CVE scan on the new pins.
pip-audit -r requirements.txt --desc on

# 5. Run the full test suite.
pytest

# 6. Commit BOTH files in a single commit.
git add requirements.in requirements.txt
git commit -m "chore(deps): bump fastapi 0.111.1 → 0.115.0"
```

`requirements.in` and `requirements.txt` must always be committed together. A `requirements.txt` committed without its corresponding `requirements.in` source is an anti-pattern that breaks the reproducibility guarantee.

---

## 5. JavaScript / TypeScript Policy

- `package-lock.json` must be committed and must never be edited by hand.
- CI must use `npm ci` (not `npm install`) to enforce the lock file exactly.
- `npm audit --audit-level=moderate` blocks the PR on MODERATE or higher findings.
- Upgrade path: `npm install <package>@<new-version>`, then commit the updated `package-lock.json`.

---

## 6. Flutter / Dart Policy

- `pubspec.lock` must be committed for all applications.
- Upgrade path: `flutter pub upgrade <package>`, then commit the updated `pubspec.lock`.
- No direct equivalent to pip-audit exists in the Dart ecosystem at the time of this document's publication. Security scanning for Dart packages is delegated to GitHub Dependabot where configured (per WP-001-04 / repository governance). This policy will be updated when a suitable Dart CVE-scanning tool is adopted.

---

## 7. Known Scaffold Pins

The `templates/python-service/requirements.txt` contains representative pinned dependencies for the canonical Python service scaffold. Before deploying any service built from this scaffold:

1. Regenerate `requirements.txt` in a clean Python 3.11 environment: `pip-compile requirements.in -o requirements.txt`
2. Run `pip-audit -r requirements.txt --desc on` to confirm zero known CVEs against current databases.
3. Commit both `requirements.in` and the regenerated `requirements.txt` as part of the service setup commit.

---

## 8. Traceability

| Artefact | Reference |
|----------|-----------|
| LLD v2.0 §2.1 | pip-audit row (config: `requirements.txt`, enforcement: CI Stage 2, known CVE = PR blocked) |
| Roadmap v1.0 §11.1 Stage 3 | Dependency scanning (pip-audit / npm audit, <2 min, no known CVEs, PR blocked) |
| WP-001-08 | This policy document |
| WP-004-03 | CI Stage 3 — authoritative CI-gate implementation of this policy (EPIC-004) |
