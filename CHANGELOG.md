# Changelog — DAEP / RE-OS

All notable changes to DAEP / RE-OS are documented in this file.

Format follows [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) — see [VERSIONING.md](VERSIONING.md).

---

## [Unreleased]

### Added

- **WP-001-01 — Repository Bootstrap:** `CODEOWNERS`, `.editorconfig`, `LICENSE` (Apache 2.0), `README.md` engineering governance section, `.gitignore`, `apps/`, `services/`, `libs/`, `infra/`, `docs/` directory scaffold.
- **WP-001-02 — Repository Standards:** `STANDARDS.md` (coding and toolchain standards), `.pre-commit-config.yaml` skeleton.
- **WP-001-03 — Documentation Framework:** `docs/README.md` navigable index; `docs/architecture/` pointer files for BRS, SRS, HLD, LLD, UI/UX Spec, Roadmap, and DRDP; `docs/adr/README.md` ADR directory and lifecycle guide.
- **WP-001-04 — Repository Governance:** `.github/PULL_REQUEST_TEMPLATE.md`; `.github/ISSUE_TEMPLATE/` (bug, feature, ECR templates); `docs/adr/branch-protection-config.md`; `CONTRIBUTING.md` with branch naming, Conventional Commits, commit signing, and GOV-001/GOV-002 governance rules.
- **WP-001-05 — Development Standards:** `templates/python-service/` Python / FastAPI service scaffold (35 files); `STANDARDS.md` §2.1.2 directory-layout update per LLD v2.0 §2.1.2.
- **WP-001-06 — Formatter Configuration:** Root `pyproject.toml` with Black (100-char) and isort (profile=black) tool configuration; Black and isort pre-commit hooks; `STANDARDS.md` line-length corrected from 88 to 100 per LLD v2.0 §2.1.
- **WP-001-07 — Static Analysis:** `mypy.ini` (strict mode, Python 3.11, per-library import overrides); `.bandit` (HIGH severity = build failure, suppression policy); Ruff, mypy, and Bandit pre-commit hooks; `STANDARDS.md` mypy flag table and Bandit severity-policy table.
- **WP-001-08 — Dependency Policy:** `DEPENDENCY_POLICY.md` (exact-pin rationale, pip-compile workflow, CVE scanning policy, upgrade procedure, JavaScript/Flutter policies); `templates/python-service/requirements.in` and `requirements.txt`; pip-audit pre-commit hook.
- **WP-001-09 — Build Framework:** `BUILD.md` (build commands for Python, React/Next.js, and Flutter; reproducibility requirement; CI stage mapping); `templates/python-service/pyproject.toml` migrated from setuptools to hatchling build backend.
- **WP-001-10 — Version Management:** `VERSIONING.md` (Semantic Versioning policy, release flow, rollback procedure); `CHANGELOG.md` (this file).
- **WP-001-11 — Artifact Repository:** `ARTIFACT_REPOSITORY.md` (pypiserver publish/consume workflow, authentication, production promotion path); `infra/artifact-repo/docker-compose.yml` (local pypiserver instance).

---

<!-- Releases are appended below in descending order as branches are cut and merged to main. -->
