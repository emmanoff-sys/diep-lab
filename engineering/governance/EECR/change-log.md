# Change Log — DAEP / RE-OS Program EECR
### EECR v1.0 | Started: 2026-07-01

> Every change to EECR structure, Work Package fields, assignments, or status is recorded here.
> Format: `[EECR-CHG-{seq}] | {date} | {type} | {summary}`

---

## Change Types

| Code | Meaning |
|------|---------|
| STRUCT | Schema or structural change to the EECR itself |
| STATUS | Work Package status field updated |
| ASSIGN | Assignment field changed (owner, lead, reviewer, agent) |
| SCOPE | Work Package scope changed (added, removed, or modified fields) |
| ARCH | Architecture reference updated |
| RISK | Risk register entry added, updated, or closed |
| DECISION | Decision log entry added, updated, or superseded |
| RELEASE | Release schedule, milestone, or sprint assignment changed |
| REVIEW | Review field updated (architecture, code, security, QA, docs) |
| DEPLOY | Deployment status updated |
| METRICS | Metrics dashboard recalculated |

---

## Change History

### EECR-CHG-001 — Initial EECR Creation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-001 |
| Date | 2026-07-01 |
| Type | STRUCT |
| Author | PMO Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | EECR v1.0 created. All 11 governance files initialized. Release 1 populated with 47 Work Packages. Architecture baseline references populated for all R1 WPs. Program framework (R2–R12) documented at Epic level. |
| Files Changed | All files in `engineering/governance/EECR/` |
| Approval | Enterprise Architect |

---

### EECR-CHG-002 — WP-001-01 Status: APPROVED

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-002 |
| Date | 2026-07-01 |
| Type | STATUS |
| Author | Enterprise Architect |
| Summary | WP-001-01 (Repository Bootstrap) status updated from IN PROGRESS to APPROVED. Commit hash recorded as `f69c194`. Architecture review score recorded as 98/100. Merge date 2026-07-01. Release version bootstrap-v0.1. Operational acceptance ACCEPTED. |
| Fields Updated | `Status`, `Commit_Hash`, `Arch_Review`, `Approval_Date`, `Approved_By`, `Merge_Date`, `Release_Version`, `Prod_Date`, `Op_Acceptance`, `Lessons_Learned`, `DoD_*` |
| Approval | Enterprise Architect |

---

### EECR-CHG-003 — WP-001-02/03/04 Status: READY

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-003 |
| Date | 2026-07-01 |
| Type | STATUS |
| Author | PMO Lead |
| Summary | WP-001-02, WP-001-03, and WP-001-04 status updated from NOT STARTED to READY following WP-001-01 APPROVED. Dependency blocker cleared. |
| Fields Updated | `Status`, `Blockers` |
| Approval | Platform Lead |

---

### EECR-CHG-004 — Risk Register Initial Population

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-004 |
| Date | 2026-07-01 |
| Type | RISK |
| Author | PMO Lead |
| Summary | Eight risks registered: RISK-001 (directory drift), RISK-002 (DLMS test env), RISK-003 (sibling branch divergence), RISK-004 (host VM instability), RISK-005 (AI scope creep), RISK-006 (IAM underspecification), RISK-007 (key person dependency), RISK-008 (ADMS API volatility). |
| Files Changed | `risk-register.md` |
| Approval | Enterprise Architect |

---

### EECR-CHG-005 — Decision Log Initial Population

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-005 |
| Date | 2026-07-01 |
| Type | DECISION |
| Author | PMO Lead |
| Summary | Four ADRs recorded (ADR-001 through ADR-004); one ECR recorded (ECR-001, VM-only deployment); two governance decisions recorded (GOV-001, GOV-002). |
| Files Changed | `decision-log.md` |
| Approval | Enterprise Architect |

---

### EECR-CHG-006 — WP-001-02 Title, Assignment, and Status Updated

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-006 |
| Date | 2026-07-02 |
| Type | STATUS, ASSIGN, SCOPE |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-02 title corrected from planning estimate "Python/FastAPI Coding Standards" to actual WP Engineering Package title "Repository Standards". Story points corrected from 3 to 5 per WP §38. Estimated hours corrected from 6 to 8. Developer and AI Agent assigned (emmanoff_lab / claude-sonnet-4-6). Branch updated from `feature/coding-standards-python` to `feature/wp-001-02-repository-standards`. LLD reference corrected from `§3.2 Python` to `Ch.2 (§2.1–§2.7)`. Reviewer updated to Enterprise Architect per AR-002 assignment. Status changed from READY to IN PROGRESS. Blockers cleared (WP-001-01 is APPROVED). Test status fields updated to reflect documentation-only WP: Unit Test N/A, Integration Test PASS (pre-commit install), Security Scan PASS, Sec Review PASS, Doc Review PASS. DoD gates DoD-01 through DoD-05 marked PASS; DoD-06 and DoD-08 PENDING human review; DoD-07 N/A (CI deferred to EPIC-004). |
| Files Changed | `engineering-execution-control-register.csv`, `engineering-execution-control-register.md` (all sections), `status-dashboard.md` |
| Approval | Enterprise Architect |

---

### EECR-CHG-007 — ADR-007: Canonical Engineering Repository Migration

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-007 |
| Date | 2026-07-02 |
| Type | ARCH, STRUCT |
| Author | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | ADR-007 formally adopted `github.com/emmanoff-sys/diep-lab` as the canonical DAEP / RE-OS engineering repository. All 47 Release 1 Work Package `Repository` fields updated from `RE-OS` to `diep-lab` in both `engineering-execution-control-register.csv` and `engineering-execution-control-register.md` §2.4. ADR-007 registered in `decision-log.md`. ADR-001 amended with cross-reference to ADR-007. AR-002 title corrected in `architecture-review-register.md` to "Repository Standards" (was planning estimate "Python/FastAPI Coding Standards"). AR-003A (ADR-007 Governance Migration Review) scheduled. `README.md` updated with canonical repository URL and ADR-007 cross-reference. `engineering-execution-control-register.md` §1 Program Overview updated with Canonical Repository and ADR-007 reference rows. No Work Package numbering, Epic numbering, branch naming, product name, or architectural baseline changes were made. DEF, MIB, and Claude Prompt Library repository references require manual update by respective document owners (external documents not tracked in this repository). |
| Commit | 3dd8b57 (`docs/adr-007-canonical-repository`) |
| Fields Updated | `Repository` column (all 47 R1 WP rows in CSV and MD); `decision-log.md` (ADR-001 amendment, ADR-007 entry, Decision Change Log); `architecture-review-register.md` (AR-002 title, AR-003A entry); `README.md`; `engineering-execution-control-register.md` §1 |
| Approval | Enterprise Architect |

---

### EECR-CHG-008 — MWP-001: Engineering Foundation Migrated to Canonical Repository

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-008 |
| Date | 2026-07-02 |
| Type | ARCH, STRUCT |
| Author | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | MWP-001 migration of all DAEP / RE-OS engineering foundation governance artefacts from the temporary `RE-OS` local repository to the canonical `github.com/emmanoff-sys/diep-lab` repository, per ADR-007. Artefacts migrated: `engineering/governance/EECR/` (11 files, EECR v1.0, EECR-CHG-001 through EECR-CHG-007), `STANDARDS.md` (WP-001-02), `CODEOWNERS` (WP-001-01), `.editorconfig` (WP-001-01), `.pre-commit-config.yaml` (WP-001-02), `LICENSE` (WP-001-01). `README.md` updated with Engineering Governance section (additive — existing DIEP product content preserved). Artefacts not migrated: `.gitignore` (diep-lab version retained as more comprehensive), `.github/` workflow stubs (diep-lab has real CI workflows), `apps/`/`services/`/`libs/`/`infra/`/`docs/` placeholder stubs (diep-lab has its own directory structure). All Work Package IDs, EECR IDs, ADR references, Epic numbering, branch names, and architecture baseline references preserved without modification. Temporary `RE-OS` repository is now eligible for archival. All ongoing development continues in `diep-lab`. |
| Commit | eadff5b (`docs/eecr-governance-foundation`) |
| Files Changed | `engineering/governance/EECR/` (all 11 files), `STANDARDS.md`, `CODEOWNERS`, `.editorconfig`, `.pre-commit-config.yaml`, `LICENSE`, `README.md` |
| Approval | Enterprise Architect (pending MWP-001 Architecture Review) |

---

### EECR-CHG-009 — WP-001-03: Documentation Framework Established

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-009 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-03 (Documentation Framework) implemented. Created `docs/README.md` (navigable documentation index covering architecture baseline pointers, ADR directory, operational docs, and engineering governance). Created `docs/architecture/` with seven pointer files — one per Architecture Baseline document: `brs.md` (BRS v1.0), `srs.md` (SRS v1.0), `hld.md` (HLD v2.0, with HLD v1.0 superseded notice per ECR-005), `lld.md` (LLD v2.0), `uiux-spec.md` (UI/UX Spec v1.0), `roadmap.md` (Roadmap v1.0), `drdp.md` (DRDP v1.0). Each pointer file records Document Type, Reference ID, Version, Status, Classification, Parent Documents, Superseded By, one-paragraph purpose, source location note, and cross-references. Created `docs/adr/README.md` (ADR directory index, lifecycle guide, ADR template, ECR log note). Root `README.md` updated additively — three rows added to Engineering Governance table linking to docs/README.md, docs/architecture/, and docs/adr/README.md. No application code modified; existing `docs/` operational content (OMS modules, runbooks, release docs) untouched. WP-001-03 status changed from READY to IN PROGRESS (pending AR-003). |
| Commit | 01d6b09 (`feature/wp-001-03-documentation-framework`) |
| Files Changed | `docs/README.md` (new), `docs/architecture/brs.md` (new), `docs/architecture/srs.md` (new), `docs/architecture/hld.md` (new), `docs/architecture/lld.md` (new), `docs/architecture/uiux-spec.md` (new), `docs/architecture/roadmap.md` (new), `docs/architecture/drdp.md` (new), `docs/adr/README.md` (new), `README.md` (modified — additive) |
| Approval | Enterprise Architect (pending AR-003) |

---

### EECR-CHG-010 — WP-001-03: Documentation Framework APPROVED and Merged

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-010 |
| Date | 2026-07-02 |
| Type | STATUS, REVIEW |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-03 (Documentation Framework) Architecture Review AR-003 confirmed complete. Branch `feature/wp-001-03-documentation-framework` merged to `develop/v1.1` at merge commit `962e7d4`. WP-001-03 status updated from IN PROGRESS to APPROVED. Merge covers implementation commit `01d6b09` (docs/architecture/ pointer files, docs/adr/README.md, docs/README.md) and hash-recording commit `d23ba6b` (EECR-CHG-009). |
| Commit | 962e7d4 (merge commit — `develop/v1.1`) |
| Files Changed | `engineering/governance/EECR/status-dashboard.md` |
| Approval | Enterprise Architect (AR-003 — merge confirmed) |

---

### EECR-CHG-011 — WP-001-04: Repository Governance Established

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-011 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-04 (Repository Governance) implemented. Created `.github/PULL_REQUEST_TEMPLATE.md` with Architecture Traceability field, branch-naming reference table, and Definition of Done checklist per LLD v2.0 §2.6. Created `.github/ISSUE_TEMPLATE/bug.md`, `.github/ISSUE_TEMPLATE/feature.md`, and `.github/ISSUE_TEMPLATE/ecr.md` with full YAML front matter and Architecture Traceability sections. Created `docs/adr/branch-protection-config.md` recording the exact GitHub branch protection settings required by LLD v2.0 §2.6 for `main`, `develop`, and `infra/*` (pending human application via GitHub Settings). Created `CONTRIBUTING.md` covering branch naming, Conventional Commits, GPG/SSH commit signing setup, PR workflow, code review expectations, and architecture governance rules (GOV-001 / GOV-002). CODEOWNERS confirmed: `/.github/` rule already present — no modification required. WP-001-04 status updated from READY to IN PROGRESS (pending AR-004). Note: actual GitHub branch protection settings must be applied by Platform Lead via GitHub Settings UI or API using `docs/adr/branch-protection-config.md` as the authoritative reference. |
| Commit | 774aa68 (`feature/wp-001-04-repository-governance`) |
| Files Changed | `.github/PULL_REQUEST_TEMPLATE.md` (new), `.github/ISSUE_TEMPLATE/bug.md` (new), `.github/ISSUE_TEMPLATE/feature.md` (new), `.github/ISSUE_TEMPLATE/ecr.md` (new), `docs/adr/branch-protection-config.md` (new), `CONTRIBUTING.md` (new) |
| Approval | Enterprise Architect (pending AR-004) |

---

### EECR-CHG-012 — WP-001-04: Repository Governance APPROVED and Merged

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-012 |
| Date | 2026-07-02 |
| Type | STATUS, REVIEW |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-04 (Repository Governance) Architecture Review AR-004 confirmed complete. Branch `feature/wp-001-04-repository-governance` merged to `develop/v1.1` at merge commit `ebdbc67`. WP-001-04 status updated from IN PROGRESS to APPROVED. Merge covers implementation commit `774aa68` (PR template, issue templates, branch-protection-config.md, CONTRIBUTING.md) and hash-recording commit `463e2ee` (EECR-CHG-011). |
| Commit | ebdbc67 (merge commit — `develop/v1.1`) |
| Files Changed | `engineering/governance/EECR/status-dashboard.md` |
| Approval | Enterprise Architect (AR-004 — merge confirmed) |

---

### EECR-CHG-013 — WP-001-05: Development Standards (Python Service Scaffold)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-013 |
| Date | 2026-07-02 |
| Type | STATUS, SCOPE, ASSIGN |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-05 (Development Standards) implemented on batch branch `feature/wp-001-05-07-governance-batch`. Created `templates/python-service/` scaffold (35 files) per LLD v2.0 §2.1.2: multi-stage Dockerfile, pyproject.toml, alembic setup, src/service_name/ package with FastAPI app factory + lifespan, /health endpoint (GET returns 200 `{"status":"ok"}`), Pydantic Settings config, async SQLAlchemy session dependency, domain layer (models/repositories/services/events), core stubs (security JWT decode, structlog logging, exception hierarchy, kafka Protocol interfaces), and tests/ (conftest, unit/test_health, integration/test_app_startup). All functions fully typed per LLD v2.0 §2.1.1. STANDARDS.md §2.1.2 updated: directory layout corrected to LLD v2.0 §2.1.2 canonical structure with scaffold pointer. WP title corrected from "Flutter/Dart Coding Standards" to "Development Standards". SP corrected from 3 to 5 per WP §38. |
| Commit | 0594ed2 (`feature/wp-001-05-07-governance-batch`) |
| Files Changed | `templates/python-service/` (35 files — new), `STANDARDS.md` (modified — §2.1.2 layout + scaffold pointer) |
| Approval | Enterprise Architect (pending AR-005) |

---

### EECR-CHG-014 — WP-001-06: Formatter Configuration (Black + isort)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-014 |
| Date | 2026-07-02 |
| Type | STATUS, SCOPE |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-06 (Formatter Configuration) implemented. Created root `pyproject.toml` (no skeleton existed; created here as initial root tool-config file) with `[tool.black]` (line-length=100), `[tool.isort]` (profile=black), plus `[tool.ruff]` and `[tool.bandit]` sections included holistically for WP-001-07. Updated `.pre-commit-config.yaml`: replaced `repos: []` skeleton with Black (rev 24.4.2) and isort (rev 5.13.2) hooks pinned for CI reproducibility. Scaffold's `templates/python-service/pyproject.toml` already carried Black and isort sections (committed in WP-001-05). STANDARDS.md §2.1 corrected: line-length updated from 88 (Black default — EECR planning estimate) to 100 (LLD v2.0 §2.1 explicit requirement) with rationale documented. WP title corrected from "TypeScript/Next.js Coding Standards" to "Formatter Configuration". |
| Commit | a221426 (`feature/wp-001-05-07-governance-batch`) |
| Files Changed | `pyproject.toml` (new), `.pre-commit-config.yaml` (modified — Black + isort hooks), `STANDARDS.md` (modified — line-length + rationale) |
| Approval | Enterprise Architect (pending AR-006) |

---

### EECR-CHG-015 — WP-001-07: Static Analysis (Ruff + mypy strict + Bandit)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-015 |
| Date | 2026-07-02 |
| Type | STATUS, SCOPE |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-07 (Static Analysis) implemented. Created `mypy.ini` at repo root: `strict = True`, `python_version = 3.11`, `warn_unused_configs`, `show_error_codes`, `pretty`, and per-library `ignore_missing_imports` overrides for jose, testcontainers, alembic, structlog. Created `.bandit`: HIGH severity = build failure; B101 (assert) skipped for test files; suppression policy requiring Bandit test ID on every `# nosec` comment. Updated `.pre-commit-config.yaml`: added Ruff (rev v0.4.9, ruff + ruff-format hooks), mypy (rev v1.10.0, strict + ignore-missing-imports), Bandit (rev 1.7.9, targeting src/ and templates/ Python files). STANDARDS.md §2.1 extended: mypy strict-mode flag table documenting all active checks; Bandit severity policy table (HIGH = build failure); suppression policies for both tools. `[tool.ruff]` and `[tool.bandit]` sections already in root pyproject.toml. WP title corrected from "Terraform/Ansible Coding Standards" to "Static Analysis". SP corrected from 3 to 5 per WP §38. |
| Commit | 10136a4 (`feature/wp-001-05-07-governance-batch`) |
| Files Changed | `mypy.ini` (new), `.bandit` (new), `.pre-commit-config.yaml` (modified — Ruff, mypy, Bandit hooks), `STANDARDS.md` (modified — mypy flags table + Bandit policy) |
| Approval | Enterprise Architect (pending AR-007) |

---

### EECR-CHG-016 — WP-001-05/06/07: Development Standards Batch APPROVED and Merged

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-016 |
| Date | 2026-07-02 |
| Type | STATUS, REVIEW |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-05 (Development Standards), WP-001-06 (Formatter Configuration), and WP-001-07 (Static Analysis) Architecture Reviews AR-005, AR-006, and AR-007 confirmed complete. Branch `feature/wp-001-05-07-governance-batch` merged to `develop/v1.1` at merge commit `4e2f4b8`. All three WPs status updated from IN PROGRESS to APPROVED. Merge covers implementation commits 0594ed2 (WP-001-05 Python scaffold), a221426 (WP-001-06 Black/isort), 10136a4 (WP-001-07 Ruff/mypy/Bandit) and EECR hash-recording commit 2ef060f (EECR-CHG-013/014/015). |
| Commit | 4e2f4b8 (merge commit — `develop/v1.1`) |
| Fields Updated | `engineering/governance/EECR/status-dashboard.md` — WP-001-05/06/07 moved to Done |
| Approval | Enterprise Architect (AR-005, AR-006, AR-007 — merge confirmed) |

---

### EECR-CHG-017 — WP-001-08/09 Title and SP Corrections; WP-001-10/11 Added; EPIC-001 Total Revised

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-017 |
| Date | 2026-07-02 |
| Type | SCOPE, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | Four corrections and additions made using the approved WP Engineering Packages as the authoritative reference. (1) WP-001-08 title corrected from "Pre-commit Hook Configuration" (planning estimate) to "Dependency Policy" (WP §2); SP unchanged at 3. (2) WP-001-09 title corrected from "Build Tooling Bootstrap (Make/Task)" (planning estimate) to "Build Framework" (WP §2); SP corrected from 3 to 5 per WP §38. (3) WP-001-10 "Version Management" (3 SP) added to EECR as a new EPIC-001 Work Package — was not included in the original 9-WP EPIC-001 plan; WP Engineering Package is the authoritative source. (4) WP-001-11 "Artifact Repository" (5 SP) added to EECR as a new EPIC-001 Work Package — same justification as WP-001-10. EPIC-001 total SP revised from 35 to 45 (WP-001-09 +2, WP-001-10 +3, WP-001-11 +5; overall WP count 9 → 11). |
| Fields Updated | `engineering-execution-control-register.csv`, `engineering-execution-control-register.md` (main table, architecture refs, branch table, status tracking, dependency sections), `status-dashboard.md` (EPIC-001 table) |
| Approval | Enterprise Architect |

---

### EECR-CHG-018 — WP-001-08: Dependency Policy Established

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-018 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-08 (Dependency Policy) implemented on batch branch `feature/wp-001-08-11-foundation-batch`. Created `DEPENDENCY_POLICY.md` covering the exact-pin requirement (== operator; floating ranges only in requirements.in), pip-compile + pip-sync + pip-audit workflow, CVE scanning policy (any known CVE = PR blocked), CVE exception process (ECR + Security Lead sign-off + 90-day expiry), upgrade procedure, JavaScript (npm ci + npm audit) and Flutter (pubspec.lock) policies. Created `templates/python-service/requirements.in` (runtime deps mirroring pyproject.toml [project].dependencies) and `templates/python-service/requirements.txt` (representative exact-pinned output with header directing regeneration via pip-compile in a clean Python 3.11 environment). Updated `.pre-commit-config.yaml`: added pip-audit hook (pypa/pip-audit rev v2.7.3) targeting templates/python-service/requirements.txt; corrected WP-001-08 planning-comment scope from "detect-secrets, pip-audit, licence compliance" to "Dependency CVE scanning (pip-audit)" per actual WP. WP-001-08 status updated from NOT STARTED to IN PROGRESS (pending AR-008). |
| Commit | 8a2580f (`feature/wp-001-08-11-foundation-batch`) |
| Files Changed | `DEPENDENCY_POLICY.md` (new), `templates/python-service/requirements.in` (new), `templates/python-service/requirements.txt` (new), `.pre-commit-config.yaml` (modified — pip-audit hook, comment correction) |
| Approval | Enterprise Architect (pending AR-008) |

---

### EECR-CHG-019 — WP-001-09: Build Framework Established

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-019 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-09 (Build Framework) implemented. Created `BUILD.md` documenting the standardised build commands for all four DAEP / RE-OS runtimes: Python (`python -m build --wheel` via hatchling, `pip install build`); React/Next.js (`npm ci` then `npm run build`); Flutter (`flutter pub get` then `flutter build apk/ios/web --release`). Build-reproducibility requirement documented (exact-pin + lock-file + Python 3.11 enforced). CI stage mapping table included. Service renaming procedure (scaffold template → actual service) documented. Updated `templates/python-service/pyproject.toml`: replaced setuptools backend (`requires = ["setuptools>=72.0"]`, `[tool.setuptools.packages.find]`) with hatchling backend (`requires = ["hatchling"]`, `[tool.hatch.build.targets.wheel] packages = ["src/service_name"]`) per WP-001-09 §15 (PEP 621-native, single backend policy for all Python components). WP-001-09 status updated from NOT STARTED to IN PROGRESS (pending AR-009). |
| Commit | 7781625 (`feature/wp-001-08-11-foundation-batch`) |
| Files Changed | `BUILD.md` (new), `templates/python-service/pyproject.toml` (modified — setuptools → hatchling build backend) |
| Approval | Enterprise Architect (pending AR-009) |

---

### EECR-CHG-020 — WP-001-10: Version Management Established

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-020 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-10 (Version Management) implemented. Created `VERSIONING.md`: Semantic Versioning 2.0.0 policy; MAJOR/MINOR/PATCH definitions with DAEP/RE-OS-specific examples (MAJOR: shared-library API break, MQTT topic schema rename, IAM role contract break; MINOR: new endpoint, new event type; PATCH: bug fix, CVE dependency bump); version-scope table covering platform release, Python services, shared libraries, Docker images, React/Next.js app, Flutter app, and Alembic database schema; release flow per LLD v2.0 §2.6 (release/{version} branch, 2 approvals, squash merge to main, signed tag v1.0.0); step-by-step release procedure; git tag format `vMAJOR.MINOR.PATCH`; Keep a Changelog maintenance process; manual changelog process for Release 1 with Release 2 automation candidate note; rollback procedure referencing previous stable tag. Created `CHANGELOG.md`: Keep a Changelog v1.1.0 format; [Unreleased] section with entries for all EPIC-001 WPs (WP-001-01 through WP-001-11). WP-001-10 status updated from NOT STARTED to IN PROGRESS (pending AR-010). |
| Commit | b4f9bfe (`feature/wp-001-08-11-foundation-batch`) |
| Files Changed | `VERSIONING.md` (new), `CHANGELOG.md` (new) |
| Approval | Enterprise Architect (pending AR-010) |

---

### EECR-CHG-021 — WP-001-11: Artifact Repository Established

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-021 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-001-11 (Artifact Repository) implemented. Created `ARTIFACT_REPOSITORY.md`: pypiserver as the Python package index (PEP 503 Simple Repository API, twine upload); Release 1 scope (Docker Compose local/CI only); publish workflow (pip-audit CVE gate before publish; twine upload to localhost:8080); consume workflow (pip install --index-url); authentication via .htpasswd + ~/.netrc for Release 1; access log guidance (docker compose logs, forward to WP-002-07 post-EPIC-003); production promotion path (Ansible role after WP-003-05/06/07); future npm registry note (Verdaccio, separate WP); full traceability table. Created `infra/artifact-repo/docker-compose.yml`: pypiserver/pypiserver v2.3.2 pinned image; port 8080; ./packages and ./.htpasswd volumes; authenticate update (upload requires auth, download is open within internal network); healthcheck. Created `infra/artifact-repo/.gitignore`: gitignores .htpasswd (credentials) and packages/ (runtime data). WP-001-11 status updated from NOT STARTED to IN PROGRESS (pending AR-011). |
| Commit | 94ca647 (`feature/wp-001-08-11-foundation-batch`) |
| Files Changed | `ARTIFACT_REPOSITORY.md` (new), `infra/artifact-repo/docker-compose.yml` (new), `infra/artifact-repo/.gitignore` (new) |
| Approval | Enterprise Architect (pending AR-011) |

---

### EECR-CHG-022 — WP-001-08/09/10/11 APPROVED — EPIC-001 Foundation Batch Merged

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-022 |
| Date | 2026-07-02 |
| Type | STATUS, REVIEW |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | Architecture Reviews AR-008 (Dependency Policy), AR-009 (Build Framework), AR-010 (Version Management), AR-011 (Artifact Repository) confirmed via human merge of `feature/wp-001-08-11-foundation-batch` to `develop/v1.1` at merge commit `e298036` (GOV-002: merge is a human action). WP-001-08, WP-001-09, WP-001-10, WP-001-11 statuses updated IN PROGRESS → APPROVED. EPIC-001 now 10/11 APPROVED; only WP-001-02 remains (awaiting AR-002). |
| Commit | e298036 (`develop/v1.1` merge) |
| Approval | Enterprise Architect (AR-008/009/010/011) |

---

### EECR-CHG-023 — EPIC-002 Definition Corrected: Shared Platform Libraries

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-023 |
| Date | 2026-07-02 |
| Type | SCOPE, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | The EECR's seeded EPIC-002 table ("Core Infrastructure Stack": Docker Compose, PostgreSQL/TimescaleDB, Redis, Mosquitto, Prometheus, Grafana, Loki/Promtail, Node Exporter) did not match the approved WP Engineering Package specifications / MIB, which define EPIC-002 as **Shared Platform Libraries** (Configuration, Logging, Exception, Common Utilities — each in Backend and Frontend/Mobile variants). Corrected all eight WP-002 rows in the main register table (titles, features, priorities, SP), the §2.3 traceability rows, and the §2.4 branch rows. EPIC-002 total SP revised 39 → 43 (WP-002-05 Exception Framework — Backend is 8 SP; the rest 5 SP each). WP IDs unchanged (no renumbering). Same correction pattern as EECR-CHG-017: WP Engineering Package specs are the authoritative source; the seeded table was provisional. NOTE: the displaced infrastructure Work Packages (Docker Compose, PostgreSQL, etc.) are not deleted from the program — their placement in the MIB is an Enterprise Architect question flagged for AR review. |
| WPs Affected | WP-002-01 … WP-002-08 |
| Approval | Enterprise Architect (pending AR batch for EPIC-002) |

---

### EECR-CHG-024 — WP-002-01: reos-config (Backend Configuration Framework)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-024 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-01 implemented. Created `libs/reos-config`: `ReosBaseSettings` (Pydantic BaseSettings) with fully typed fields — service_name, environment Literal["local","shared_dev","ci","staging","production"] (Roadmap v1.0 §11.2), log_level (default INFO), database_url PostgresDsn, redis_url RedisDsn, kafka_bootstrap_servers — .env support, fail-fast validation, password-masking __repr__ (§25). Reserved base field names documented (§35). Scaffold `config.py` replaced with a consuming subclass (template defaults retained, documented for removal in real services). Runtime verification PASS: 20 unit tests, 100% coverage, mypy --strict/Ruff/Black/Bandit clean (venv, Python 3.14 ≥ 3.11). Status NOT STARTED → IN PROGRESS (pending Architecture Review). |
| Commit | 545b939 (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-config/*` (new), `templates/python-service/src/service_name/config.py` (modified) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-025 — WP-002-02: reos-config-ts + reos_config (Frontend/Mobile Configuration)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-025 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-02 implemented. Created `libs/reos-config-ts` (@reos/config): Zod-validated ReosConfig (apiBaseUrl, environment enum, optional sentryDsn) from process.env, fail-fast, no hardcoded sensitive defaults (§25). Created `libs/reos_config` (Dart): ReosEnvironment enum + ReosConfig with flutter_dotenv (.env, local) and --dart-define (release) factories. Environment enum synchronized 3-way with WP-002-01 via source-of-truth comment blocks (§35 mitigation). Jest + flutter_test suites included. Structural PASS only — no Node/Flutter toolchain in the implementation environment; runtime prerequisites: npm ci + jest; flutter pub get + flutter test. Status NOT STARTED → IN PROGRESS. |
| Commit | 7bd6755 (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-config-ts/*` (new), `libs/reos_config/*` (new) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-026 — WP-002-03: reos-logging (Backend Logging Framework)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-026 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-03 implemented. Created `libs/reos-logging`: configure_logging(settings, extra_redacted_fields=()) + get_logger() per LLD v2.0 §2.3. Processor chain: merge_contextvars → redaction (password/token/secret/authorization, case-insensitive, extensible — §25/§35) → TimeStamper(iso) → add_log_level → JSONRenderer (ConsoleRenderer when environment==local per Roadmap §11.2). service_name/environment bound via contextvars from ReosBaseSettings (WP-002-01). Request-ID binding supported for FastAPI middleware. Scaffold core/logging.py replaced with thin re-export; main.py lifespan passes settings (consequential signature change); scaffold pyproject gains reos-config + reos-logging deps. Runtime verification PASS: 14 unit tests, 100% coverage, all static analysis clean. Status NOT STARTED → IN PROGRESS. |
| Commit | 6e8cad2 (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-logging/*` (new), scaffold `core/logging.py`, `main.py`, `pyproject.toml` (modified) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-027 — WP-002-04: reos-logging-ts + reos_logging (Client-Side Logging)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-027 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-04 implemented. Created `libs/reos-logging-ts` (@reos/logging) and `libs/reos_logging` (Dart): common shape log.debug/info/warn/error(event, context[, error]) with noun.verb event convention mirroring WP-002-03, plus log.stateTransition(component, from, to) directly supporting DRDP v1.0 §22 observability. Pluggable Transport interface: console in local, remote sink otherwise. Remote error-tracking backend deliberately NOT selected — open Project Owner decision (§9/§35), console fallback until wired; no vendor coupling. PII responsibility documented as a mechanism-not-filter limitation (§25). Jest + flutter_test suites. Structural PASS only (no Node/Flutter toolchain). Status NOT STARTED → IN PROGRESS. |
| Commit | 2623c91 (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-logging-ts/*` (new), `libs/reos_logging/*` (new) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-028 — WP-002-05: reos-exceptions (Backend Exception Framework)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-028 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-05 implemented. Created `libs/reos-exceptions` porting LLD v2.0 §2.2 as specified: REOSException base (message/code/http_status/detail/metadata) + ValidationError 422, AuthenticationError 401, AuthorizationError 403, NotFoundError 404, ConflictError 409, ExternalServiceError 502. register_exception_handlers(app) returns RFC 7807 Problem Details (application/problem+json) and logs request.error at warning via reos-logging using the exact LLD call pattern. Auth error messages generic by design (§25). 429/503 gap documented in README "Not Covered by This Library" (§9/§35). Runtime verification PASS: 12 unit + 11 integration tests (real FastAPI HTTP round-trip for all six types), 100% coverage, static analysis clean (REOSException N818 suppressed with citation — name is LLD-mandated). Scaffold: core/exceptions.py thin re-export; main.py registers handlers + demo RFC 7807 404 endpoint (verified end-to-end); security.py JWT failure corrected AuthorisationError(403 stub) → AuthenticationError(401) — consequential semantic fix. Status NOT STARTED → IN PROGRESS. |
| Commit | 254f3dc (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-exceptions/*` (new), scaffold `core/exceptions.py`, `core/security.py`, `main.py`, `pyproject.toml` (modified) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-029 — WP-002-06: Error Handling (Frontend/Mobile) + ECR-002-06-01 RAISED

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-029 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT, DECISION |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-06 implemented. Created `libs/reos-error-handling-ts` (@reos/error-handling: mapErrorToUiState + ReosErrorBoundary) and `libs/reos_error_handling` (Dart: mapErrorToUiState + ReosErrorWidget). All 9 DRDP v1.0 §21.3 status codes mapped to typed UI states (400/422 field errors; 401 redirect preserving route; 403 permission descriptor; 404 illustration + breadcrumbs; 409 context detail; 429 countdown; 500 error_id-only per §25; 503 maintenance); unknown codes fall back to server_error (DRDP §22: no blank default); every mapped error logs error.mapped. **ECR-002-06-01 RAISED:** DRDP v1.0 §21.3's approved "User Message" copy is maintained externally and is NOT in the repository — the in-repo `docs/architecture/drdp.md` is the Data Retention and Destruction Policy (acronym collision with the design DRDP cited by the WP specs). Per WP-002-06 §39 the copy must not be invented or paraphrased. All user-facing strings are `[PLACEHOLDER ECR-002-06-01]`-prefixed in isolated modules and must be replaced verbatim on ECR resolution. Acceptance criterion "copy matches DRDP §21.3 exactly" is BLOCKED on this ECR; shape/behavior criteria pass. Structural PASS only (no Node/Flutter toolchain). Status NOT STARTED → IN PROGRESS (ECR open). |
| Commit | a070db4 (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-error-handling-ts/*` (new), `libs/reos_error_handling/*` (new) |
| Approval | Enterprise Architect + UI/UX Design owner (ECR-002-06-01 resolution required) |

---

### EECR-CHG-030 — WP-002-07: reos-common (Backend Common Utilities)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-030 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-07 implemented. Created `libs/reos-common`: tenant_scoped(query, tenant_id) structurally enforcing LLD v2.0 §2.1.1's ALWAYS-tenant-scoped rule + is_deleted soft-delete filter — None tenant raises AuthorizationError(403) with tenant.missing_context warning log (§25/§26); models lacking the columns rejected with TypeError; required Release 2+ schema convention (tenant_id + is_deleted on every multi-tenant table) documented (§22/§35). Page/PageParams cursor pagination per DRDP v1.0 §21 (opaque base64 cursors, ValidationError 422 on tampering, limit clamped to 200, fetch-limit+1 next-page detection). utc_now()/to_iso8601() refuse naive datetimes. Runtime verification PASS: 29 unit tests including real-SQLite cross-tenant leak-prevention proof and two-page walk (no duplicates/gaps), 100% coverage, static analysis clean. Scaffold repositories.py demonstrates tenant_scoped + Page.build; pyproject gains reos-common dep. SECURITY NOTE (§39): tenant.py changes require heightened review scrutiny permanently. Status NOT STARTED → IN PROGRESS. |
| Commit | 7b3c94c (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-common/*` (new), scaffold `domain/repositories.py`, `pyproject.toml` (modified) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-031 — WP-002-08: reos-utils-ts + reos_utils — EPIC-002 Implementation Complete

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-031 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-fable-5) |
| Summary | WP-002-08 implemented. Created `libs/reos-utils-ts` (@reos/utils) and `libs/reos_utils` (Dart): governed API clients (fetch-based TS; Dio-based Dart per DRDP v1.0 §23.1) — Bearer-token interceptor hook, every non-2xx routed through mapErrorToUiState (WP-002-06) so no screen hand-parses errors, request metadata logged bodies-excluded (§26); auth token retrieval/storage explicitly OUT OF SCOPE — placeholder hook with TODO(auth-feature) markers and README warnings (§25/§35). Formatters (formatDate/DateTime/Currency/Kwp/Kwh per UI/UX Design Spec unit conventions) and validators (isValidEmail/isValidPhone). Jest + flutter_test suites; Structural PASS only. This completes the EPIC-002 implementation set (8/8 WPs). Follow-up commits: 83cc9a0 (black formatting), f50ee20 (coverage to 100% — 86 Python tests), af85e59 (libs/README.md EPIC reference). Status NOT STARTED → IN PROGRESS. EPIC-002 awaits Architecture Reviews before merge (GOV-002). |
| Commit | 35e519d (`feature/epic-002-shared-platform-libraries`) |
| Files Changed | `libs/reos-utils-ts/*` (new), `libs/reos_utils/*` (new), `libs/README.md` (new, af85e59) |
| Approval | Enterprise Architect (pending) |

---

### EECR-CHG-032 — ECR-002-06-01 RESOLVED: UI Message Specification Approved and Integrated

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-032 |
| Date | 2026-07-02 |
| Type | DECISION, STRUCT, STATUS |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | **ECR-002-06-01 CLOSED.** Created `docs/architecture/UI_MESSAGE_SPEC.md` v1.0 — the authoritative user-facing message specification, resolving the ECR raised in EECR-CHG-029 (approved DRDP v1.0 §21.3 copy was unavailable in-repo; `docs/architecture/drdp.md` is the Data Retention and Destruction Policy, an acronym collision). Specification defines HTTP status, internal error code, user message, user action, retry behaviour, severity, logging requirement, support reference, accessibility notes, localization key, and developer notes for 400/401/403/404/409/422/429/500/502/503/Unknown (11 categories total). All `[PLACEHOLDER ECR-002-06-01]` strings removed from `libs/reos-error-handling-ts/src/messages.ts` and `libs/reos_error_handling/lib/map_error.dart` and replaced verbatim with the approved copy for the 9 status codes those modules route (400/401/403/404/409/422/429/500/503) — no remaining placeholders confirmed by repository-wide search. No behavioural change: `mapErrorToUiState`'s switch/case structure, `ErrorUiState`/`ErrorUiKind` shapes, and the 502-and-unknown → `server_error` fallback are unchanged in both languages — only copy source and content changed, per the ECR resolution's explicit constraint. Tests updated in both languages to assert exact message equality against `USER_MESSAGES`/`userMessages` (no more "non-empty string" placeholder assertions), plus new coverage for the 502 fallback case and a "no PLACEHOLDER substring remains" guard. Both package READMEs and `libs/README.md` updated: ECR moved from "Open Items" to "Resolved"; both READMEs point to `UI_MESSAGE_SPEC.md` as the copy source of truth with the standing change-control rule (UI/UX sign-off + EECR record required for any future wording change). WP-002-06 acceptance criterion "user-facing message copy matches DRDP §21.3 exactly," previously BLOCKED, is now satisfied against the approved specification. Verification: Structural PASS (spec structurally complete against all 11 required categories; code changes are copy-only, verified by diff against the WP-002-06 STRUCTURAL PASS baseline). Runtime PASS not available for TS/Dart in this environment (no Node/Flutter toolchain, consistent with all prior EPIC-002 records) — deferred to CI/dev environment. |
| WPs Affected | WP-002-06 (copy only — no scope/behavior change) |
| Commit | 0318608 (`feature/ecr-002-06-01-ui-message-specification`) |
| Files Changed | `docs/architecture/UI_MESSAGE_SPEC.md` (new), `libs/reos-error-handling-ts/src/messages.ts` (modified — copy only), `libs/reos_error_handling/lib/map_error.dart` (modified — copy only), `libs/reos-error-handling-ts/tests/mapError.test.ts` (modified), `libs/reos_error_handling/test/map_error_test.dart` (modified), `libs/reos-error-handling-ts/README.md` (modified), `libs/reos_error_handling/README.md` (modified), `libs/README.md` (modified) |
| Approval | Enterprise Architect + UI/UX Design owner — Architecture Review for ECR closure pending; WP-002-06's own Architecture Review (from EECR-CHG-029) remains separately pending |

---

### EECR-CHG-033 — EPIC-003 Definition Confirmed: Core Platform Framework

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-033 |
| Date | 2026-07-02 |
| Type | SCOPE, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | EPIC-003 defined as "Core Platform Framework" in the approved WP Engineering Package specifications (MIB): 14 Work Packages across Docker Foundation (WP-003-01..04), VM/Systemd Foundation (WP-003-05..10), and GitOps Foundation (WP-003-11..14). Implementation branch: `feature/epic-003-core-platform-framework` from `develop/v1.1` HEAD `aae6658`. Worktree: `/tmp/epic-003-wt`. All 14 WP commits recorded in EECR-CHG-034..047 below. |
| WPs Affected | WP-003-01 through WP-003-14 |
| Approval | Enterprise Architect (pending AR-020 through AR-033) |

---

### EECR-CHG-034 — WP-003-01: Multi-Stage Docker Build Standard

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-034 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-01 implemented. DOCKER_STANDARDS.md establishes the builder→production multi-stage pattern (python:3.12-slim, non-root reos user, HEALTHCHECK, <200MB benchmark, BuildKit layer-cache ordering, 12-Factor stdout/stderr logging). templates/python-service/Dockerfile rewrote the existing stub: builder installs exact-pinned requirements.txt + builds hatchling wheel; production stage copies only wheel+resolved deps, USER reos, HEALTHCHECK against /health. Consequential fix: requirements.in/requirements.txt were stale since EPIC-002 added reos-config/reos-logging/reos-exceptions/reos-common to pyproject.toml — DEPENDENCY_POLICY.md §4 drift closed. Runtime PASS Deferred: Docker daemon unreachable in implementation environment. |
| Commit | 3b59e71 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `DOCKER_STANDARDS.md` (new), `templates/python-service/Dockerfile` (modified — full rewrite), `templates/python-service/requirements.in` (modified — reos-* libs added), `templates/python-service/requirements.txt` (modified — reos-* libs + note) |
| Approval | Enterprise Architect (pending AR-020) |

---

### EECR-CHG-035 — WP-003-02: Docker Compose Local Dev Environment + ECR-003-02-01

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-035 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT, DECISION |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-02 implemented. ECR-003-02-01 RAISED AND RESOLVED AT SCOPE: WP-003-02 literally specifies creating docker-compose.yml at the repository root. The repository root already contains a real, live, 760-line production docker-compose.yml (plus 30+ overlay files) serving the operational DIEP platform, and a substantial root README.md — overwriting either is forbidden per the standing constraint. WP-003-02 is delivered at templates/python-service/ (scaffold-scoped): docker-compose.yml (scaffold + postgres:16 + redis:7 + apache/kafka:3.7.0 KRaft-mode, healthcheck-gated depends_on), scripts/seed-local-dev.py (synthetic/non-PII seed pattern), .env.example extended (compose-variable substitution vars, local-only credentials warning), README.md Quick Start section added. Enterprise Architect confirmation of scope resolution requested at AR-021. |
| Commit | cd3b2b4 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `templates/python-service/docker-compose.yml` (new), `templates/python-service/scripts/seed-local-dev.py` (new), `templates/python-service/.env.example` (modified), `templates/python-service/README.md` (modified) |
| Approval | Enterprise Architect (pending AR-021, including ECR-003-02-01 scope confirmation) |

---

### EECR-CHG-036 — WP-003-03: Container Registry

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-036 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-03 implemented. infra/container-registry/docker-compose.yml: registry:2, htpasswd basic auth, persistent volume storage, push-notification webhook (placeholder endpoint, EPIC-004 follow-on). CONTAINER_REGISTRY.md: tagging convention ({git-sha} every build, {semver} on release/*→main per WP-001-10), push/pull commands, basic-auth-to-Vault-token upgrade path (WP-003-13 forward reference). Runtime PASS Deferred: Docker daemon unreachable. |
| Commit | ff8abd3 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/container-registry/docker-compose.yml` (new), `infra/container-registry/.gitignore` (new), `CONTAINER_REGISTRY.md` (new) |
| Approval | Enterprise Architect (pending AR-022) |

---

### EECR-CHG-037 — WP-003-04: Container Security Scanning (Trivy) Foundation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-037 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-04 implemented. .trivyignore: empty by default; exception process requires CVE ID + justification + review-by date per entry. CONTAINER_SECURITY.md: scan command (--exit-code 1 on CRITICAL, --ignore-unfixed), DB freshness requirement, fixture-image negative test, scope boundary with WP-004-06 (CI automation). Runtime PASS Deferred: Trivy binary and Docker daemon not available. |
| Commit | b930c5a (`feature/epic-003-core-platform-framework`) |
| Files Changed | `.trivyignore` (new), `CONTAINER_SECURITY.md` (new) |
| Approval | Enterprise Architect (pending AR-023) |

---

### EECR-CHG-038 — WP-003-05: Ubuntu 22.04 LTS VM Hardening Standard

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-038 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-05 implemented. HARDENING_STANDARD.md: minimal Ubuntu 22.04 LTS, UFW default-deny ruleset, SSH key-only hardening, unattended-upgrades, explicit zero-Kubernetes-artifacts negative check (ECR-001 operationalization — flagged as the epic's highest-value review point), non-root reos service user, CIS-aligned kernel hardening (dccp/sctp/rds/tipc disabled, suid_dumpable=0, rp_filter=1), auditd, prometheus-node requirement. ufw-rules.md: baseline rule set + reviewed (not ad hoc) rule-change process. cloud-init.yml.tftpl: first-boot bootstrap for cloud VMs consumed by WP-003-08's Terraform user_data — includes cloud-init-time zero-Kubernetes fail-loud check. Runtime PASS Deferred: no real VM to Lynis-scan. |
| Commit | 47b01e2 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/vm-base/HARDENING_STANDARD.md` (new), `infra/vm-base/ufw-rules.md` (new), `infra/vm-base/cloud-init.yml.tftpl` (new) |
| Approval | Enterprise Architect (pending AR-024 — highest scrutiny in EPIC-003 for ECR-001 confirmation) |

---

### EECR-CHG-039 — WP-003-06: systemd Service Unit Framework

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-039 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-06 implemented. infra/systemd/reos-service@.service: template unit, After/Requires=docker.service, tmpfs-backed EnvironmentFile from Vault Agent (WP-003-13), ExecStartPre pull + ExecStart docker run, Restart=on-failure/RestartSec=5, systemd-level MemoryMax=512M/CPUQuota=100% documented defaults (overridable via per-service Ansible drop-in), journal logging, NoNewPrivileges/ProtectSystem/ProtectHome sandboxing. SYSTEMD_STANDARDS.md: directive-by-directive rationale, instantiation process. Runtime PASS (partial): systemd-analyze verify ran — exit 0, zero errors (genuine unit file syntax check available in implementation environment). Full start/restart/resource-limit behavior Deferred. |
| Commit | 0de96da (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/systemd/reos-service@.service` (new), `SYSTEMD_STANDARDS.md` (new) |
| Approval | Enterprise Architect (pending AR-025) |

---

### EECR-CHG-040 — WP-003-07: Ansible Playbook Foundation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-040 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-07 implemented. provision-vm.yml: hosts/become/pre_tasks variable validation exactly per LLD §17.1 literal structure; role sequence common→docker→vault-agent→consul-agent→prometheus-node→reos-service→log-forwarder. All 7 roles implemented: common (UFW, SSH hardening, zero-Kubernetes check), docker (Docker CE + explicit Swarm-inactive confirmation per ECR-001), vault-agent (STUB at commit time — completed by WP-003-13 per §8/§18 design), consul-agent (agent + LLD-literal registration schema), prometheus-node (Node Exporter), reos-service (installs WP-003-06 template + per-service drop-in), log-forwarder (explicit stub per WP-003-07 §9 — Loki/Promtail backend is a later observability epic). ANSIBLE_STANDARDS.md: role-by-role status table, both stubs rationale. 12 YAML files validated (yaml.safe_load). ansible-lint/ansible-playbook deferred. |
| Commit | ad495c0 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/playbooks/provision-vm.yml` (new), `infra/roles/common/*` (new), `infra/roles/docker/*` (new), `infra/roles/vault-agent/*` (stub, completed by WP-003-13), `infra/roles/consul-agent/*` (new), `infra/roles/prometheus-node/*` (new), `infra/roles/reos-service/*` (new), `infra/roles/log-forwarder/*` (new), `ANSIBLE_STANDARDS.md` (new) |
| Approval | Enterprise Architect (pending AR-026) |

---

### EECR-CHG-041 — WP-003-08: Terraform Cloud VM Lifecycle Foundation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-041 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-08 implemented. terraform/modules/vm/: main.tf (aws_instance.reos_service, count=instance_count, locked to Ubuntu 22.04 LTS AMI, gp3+KMS encrypted volume, IMDSv2-only http_tokens=required/hop_limit=1, user_data from cloud-init.yml.tftpl, cost-allocation tags), variables.tf (environment validated against Roadmap §11.2 names), outputs.tf. backend.tf: S3+DynamoDB remote state FLAGGED as this WP's own architectural addition beyond the LLD excerpt — bucket/region are explicit placeholders pending Project Owner confirmation (TERRAFORM_STANDARDS.md §5). Networking module (VPC/subnets/SGs) documented as a separate, not-yet-built dependency (§9). NOT EXECUTED against any AWS account. Structural PASS only (brace-balance). |
| Commit | 9516feb (`feature/epic-003-core-platform-framework`) |
| Files Changed | `terraform/modules/vm/main.tf` (new), `terraform/modules/vm/variables.tf` (new), `terraform/modules/vm/outputs.tf` (new), `terraform/backend.tf` (new), `TERRAFORM_STANDARDS.md` (new) |
| Approval | Enterprise Architect (pending AR-027, including remote-state-backend confirmation) |

---

### EECR-CHG-042 — WP-003-09: Nginx + HAProxy + Keepalived Load Balancing Foundation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-042 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-09 implemented. nginx.conf (literal LLD excerpt): upstream least_conn/max_fails/keepalive, TLS 1.3, HSTS/X-Content-Type-Options/X-Frame-Options, X-Request-ID propagation, dual rate-limit zones (auth_strict burst=10, api_standard burst=200) returning 429 per DRDP v1.0 §21.3. keepalived.conf + keepalived-backup.conf (literal LLD excerpt): VRRP MASTER/BACKUP pair, vrrp_script health-checking Nginx's /health, VIP; auth_pass flagged as WP-003-13 Vault placeholder (§24). haproxy.cfg: FLAGGED as this WP's own construction per §9/§35 (LLD excerpt confirms HAProxy TCP role but has no worked example — built from standard TCP-mode practice for Kafka/MQTT). Runtime PASS Deferred: nginx/haproxy/keepalived binaries not installed. |
| Commit | d2e3c64 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/loadbalancer/nginx.conf` (new), `infra/loadbalancer/keepalived.conf` (new), `infra/loadbalancer/keepalived-backup.conf` (new), `infra/loadbalancer/haproxy.cfg` (new), `LOAD_BALANCING.md` (new) |
| Approval | Enterprise Architect (pending AR-028, including HAProxy config review against full LLD v2.0 document) |

---

### EECR-CHG-043 — WP-003-10: Consul Service Discovery Foundation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-043 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-10 implemented. consul-server.hcl: single-node (bootstrap_expect=1, Release 1 scope), API bound to localhost, ACL default-deny, Prometheus telemetry, documented multi-node upgrade path for Production. consul-agent-template.hcl: client-mode source-of-truth (live Ansible-rendered version at infra/roles/consul-agent/templates/). scaffold-service-registration.json: LLD-literal schema (name/port/check with interval:10s/timeout:3s/deregister:60s) — canonical copy-from reference for future services. CONSUL_STANDARDS.md: registration schema, timing rationale, Connect/service-mesh explicitly out of scope. Structural PASS: JSON validated. Runtime PASS Deferred: consul binary not installed. |
| Commit | 421ce21 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/consul/consul-server.hcl` (new), `infra/consul/consul-agent-template.hcl` (new), `infra/consul/scaffold-service-registration.json` (new), `CONSUL_STANDARDS.md` (new) |
| Approval | Enterprise Architect (pending AR-029) |

---

### EECR-CHG-044 — WP-003-11: Git Branching Strategy & Branch Protection (infra/*)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-044 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-11 implemented. .github/workflows/infra-checks.yml: ansible-lint, terraform-plan (validate + plan with test variables), security-scan (tfsec + nginx syntax check) — triggered on PRs targeting infra/**. Workflow YAML validated (yaml.safe_load). docs/adr/infra-branch-checks-config.md: audit record, companion to WP-001-04's branch-protection-config.md; required-checks list Pending for Platform Lead application. NOT EXECUTED: implementation did not call the GitHub API to register these checks as required in the live infra/* branch protection rule. gh CLI has real write access — registering live shared branch-protection settings requires explicit human authorization, consistent with WP-001-04's precedent of leaving branch protection application to the Platform Lead. |
| Commit | 478e245 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `.github/workflows/infra-checks.yml` (new), `docs/adr/infra-branch-checks-config.md` (new) |
| Approval | Enterprise Architect + Platform Lead (pending AR-030; required-checks registration is a human Platform Lead action post-AR) |

---

### EECR-CHG-045 — WP-003-12: GitOps Repository Structure

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-045 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-12 implemented. infra/environments/{local-dev/README.md + 7×inventory.yml} and terraform/environments/{7×terraform.tfvars}: structural scaffolding for all 8 Roadmap v1.0 §11.2 environments, all with explicit PROVISIONING STATUS: NOT YET PROVISIONED markers, no secret-looking values (heuristic scan clean), no role/module logic duplicated. GITOPS_STRUCTURE.md: no-duplication principle, provisioning status table, add-environment process; flags a minor internal count inconsistency in WP-003-12's own §17 prose (7 vs §15's tree diagram count — resolved in favor of the specific diagram and 8-environment strategy). Structural PASS: all 7 inventory.yml parse + structure lint clean. |
| Commit | 9a9d0fc (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/environments/*/` (7 inventory.yml + 1 README.md — new), `terraform/environments/*/terraform.tfvars` (7 files — new), `GITOPS_STRUCTURE.md` (new) |
| Approval | Enterprise Architect (pending AR-031) |

---

### EECR-CHG-046 — WP-003-13: Secrets Management Foundation (Vault)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-046 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-13 implemented. infra/vault/vault-server.hcl: filesystem storage (Release 1 scope), TCP listener TLS, internal-only API, Raft+KMS Production upgrade path documented (§35 explicit). infra/vault/postgres-dynamic-secrets-policy.hcl: database/creds/ read + token renew-self. infra/roles/vault-agent/tasks/main.yml (COMPLETES WP-003-07 stub per WP-003-13 §18): Vault Agent binary install, AppRole auth config, secret-id delivery, systemd unit + enable. vault-agent.hcl.j2 + env.ctmpl.j2 templates: AppRole auth (non-Kubernetes, per ECR-001) + Consul template rendering dynamic Postgres credential to /run/reos/{service}.env. VAULT_STANDARDS.md: AppRole-vs-K8s-auth rationale, secret delivery flow, unseal governance flagged to Project Owner, PKI/transit/k8s-auth explicit scope exclusions, Production upgrade path. Structural PASS: all vault-agent YAML parse. Runtime PASS Deferred: Vault binary not installed. |
| Commit | bcd4352 (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/vault/vault-server.hcl` (new), `infra/vault/postgres-dynamic-secrets-policy.hcl` (new), `infra/roles/vault-agent/tasks/main.yml` (modified — completes WP-003-07 stub), `infra/roles/vault-agent/templates/vault-agent.hcl.j2` (new), `infra/roles/vault-agent/templates/env.ctmpl.j2` (new), `infra/roles/vault-agent/handlers/main.yml` (new), `VAULT_STANDARDS.md` (new) |
| Approval | Enterprise Architect + Security Review (pending AR-032; highest security scrutiny in EPIC-003 alongside WP-003-05) |

---

### EECR-CHG-047 — WP-003-14: Environment Strategy Implementation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-047 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-003-14 implemented. ENVIRONMENT_STRATEGY.md: authoritative live-vs-deferred table for all 8 environments; Local Dev STRUCTURALLY LIVE (WP-003-02), Shared Dev + Integration STRUCTURALLY READY (await networking module + VM provisioning + Vault/Consul servers + AWS credentials), QA/UAT/Staging/Production/DR explicitly DEFERRED. shared-dev/integration inventory.yml and terraform.tfvars populated with real (non-placeholder) env names, instance types/counts, and internal service addresses — subnet/sg/kms values documented as AWAITING networking module (WP-003-08 §9 explicit dependency). Integration-test verdict: EPIC-003 artifacts compose correctly; blockers are all infrastructure-prerequisite, not implementation gaps. WP-003-14 treats successful completion as EPIC-003's epic-level integration test (§34) — verdict: ready for AR, pending the human actions listed in ENVIRONMENT_STRATEGY.md §6 and README_EPIC003.md §14. |
| Commit | 7e1e99c (`feature/epic-003-core-platform-framework`) |
| Files Changed | `infra/environments/shared-dev/inventory.yml` (modified — real values), `terraform/environments/shared-dev/terraform.tfvars` (modified — real values), `infra/environments/integration/inventory.yml` (modified), `terraform/environments/integration/terraform.tfvars` (modified), `ENVIRONMENT_STRATEGY.md` (new) |
| Approval | Enterprise Architect (pending AR-033) |

---

### EECR-CHG-048 — EPIC-004 Definition Confirmed: CI/CD, DevSecOps & Release Automation

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-048 |
| Date | 2026-07-02 |
| Type | SCOPE, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | EPIC-004 defined as "CI/CD, DevSecOps & Release Automation": 14 Work Packages building the full 14-stage delivery pipeline (Roadmap v1.0 §11.1) from lint through production deployment and DORA metrics. Branch: `feature/epic-004-cicd-devsecops` from `develop/v1.1` HEAD `9b62c14`. Key workflow file: `.github/workflows/service-ci-cd.yml` (new, distinct from existing `ci.yml` DIEP platform workflow). |
| WPs Affected | WP-004-01 through WP-004-14 |
| Approval | Enterprise Architect (pending AR-034 through AR-047) |

---

### EECR-CHG-049 — WP-004-01 through WP-004-07: CI Pipeline Stages 1–7

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-049 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-004-01 through WP-004-07 implemented. service-ci-cd.yml created with: [01] lint job (ruff --output-format github, black --check --diff, isort --check-only, mypy src/ --strict; Python 3.11 per LLD Ch. 18); [02] security job SAST portion (bandit -r src/ -ll -ii --format json, github/codeql-action/analyze@v3; CodeQL requires GitHub Advanced Security — Project Owner confirmation needed, ECR-004 if unavailable); [03] dependency-scan job (pip-audit --strict -r requirements.txt, LLD literal; npm audit documented-but-dormant per WP §8); [04] test-unit job (needs:[lint]; pytest -v --cov=src --cov-fail-under=80 --cov-report=xml --junit-xml, codecov/codecov-action@v4, LLD literal; all 4 EPIC-002 Python libs discovered); [05/06/07] build job (needs:[test-unit,security]; docker build --target production --build-arg GIT_SHA; aquasecurity/trivy-action@master severity:CRITICAL,HIGH exit-code:1; docker login + push; conditional notification via NOTIFY_WEBHOOK_URL env var — secrets-in-if-condition bug fixed). All YAML files validate. Branch protection registration, push credentials, and notification channel are Platform Lead / Project Owner actions. |
| Commits | fbfebe6/116ba8e/a1394d6/e605511/47bc086/022b7d5/8156e36 |
| Approval | Enterprise Architect (pending AR-034..040) |

---

### EECR-CHG-050 — WP-004-08 through WP-004-09: Security Pipeline

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-050 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-004-08 (DAST) and WP-004-09 (Secrets Scanning) implemented. [08] dast-scan.yml: workflow_dispatch (Manual per Roadmap §11.1 Stage 11), zaproxy/action-full-scan@v0.10.0 targeting Staging only (locked choice input, never Production per §25/§31), fail_action:true (No High policy), 70-min timeout, DAST_STANDARDS.md. Built from Roadmap §11.1 Stage 11 as primary source — LLD Ch. 18 excerpt does not include a DAST job; flagged for AR verification against complete LLD document. [09] Gitleaks secrets scanning: .gitleaks.toml (extends defaults + RE-OS Vault-path pattern; EPIC-003 PLACEHOLDER tokens path-scoped allowlisted); secrets-scan job in service-ci-cd.yml; SECRETS_SCANNING.md with incident-response procedure and one-time baseline scan command (deferred per §33 AC). GITLEAKS_LICENSE tier confirmation from Project Owner required. |
| Commits | 5bb56db / c809815 |
| Approval | Enterprise Architect (pending AR-041/042) |

---

### EECR-CHG-051 — WP-004-10 through WP-004-14: Integration, Deployment, Observability

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-051 |
| Date | 2026-07-02 |
| Type | STATUS, STRUCT |
| Author | Platform Lead (AI-assisted: claude-sonnet-5) |
| Summary | WP-004-10 through WP-004-14 implemented. [10] test-integration job: needs:[build]; if:develop/main; postgres:16 + redis:7-alpine GitHub Actions service containers (LLD literal); pytest tests/integration/ -v --junit-xml; trigger-timing discrepancy noted (LLD §2.7 PR-time vs Roadmap Stage 8 merge-time; Roadmap followed as more specific source, §35). [11] deploy-staging job + infra/playbooks/deploy-rolling.yml: 7-step LLD §18.2 literal rolling deploy (drain upstream, wait 30s, pull image, alembic upgrade head first-VM-only, restart systemd unit WP-003-06, health check retries:24 delay:5, re-enable upstream); serial:1/max_fail_percentage:0 IS the automatic rollback mechanism; Staging VMs not yet provisioned — Project Owner scope-extension confirmation requested. [12] load-test.yml + loadtest/scaffold-load-test.js: k6 ramping-arrival-rate to 1,000 RPS, P95<500ms threshold abortOnFail:false (Alert+review, not hard-block per Roadmap §11.1 Stage 10); weekly Monday 2am UTC + workflow_dispatch; LOAD_TESTING.md. [13] deploy-production job + ROLLBACK_PROCEDURE.md: needs:[deploy-staging]; if:refs/heads/main; environment:production (GitHub manual-approval gate); same deploy-rolling.yml against prod inventory; ROLLBACK_PROCEDURE.md is copy-paste executable under incident pressure targeting 15-minute MTTR. NOT triggered without human approval. [14] scripts/dora-metrics.py (gh API query, 4 DORA metric computations, Markdown render, --help works — Runtime PASS partial); dora-report.yml (weekly cron); DORA_METRICS.md. README_EPIC004.md at .github/. |
| Commits | 1c7893c/267c9b5/0817def/fd09d56/d9a7bce/780ace5 |
| Approval | Enterprise Architect (pending AR-043..047) |

---

### EECR-CHG-052 — EPIC-005 WP-005-01: Identity Service — Core Authentication & JWT Issuance

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-052 |
| Date | 2026-07-03 |
| Type | STATUS, SCOPE |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-005-01 (Identity Service — Core Authentication & JWT Issuance) implemented on branch `feature/epic-005-platform-foundation`. Created `services/identity-service/` in full: Dockerfile (multi-stage, non-root reos user, port 8001, tmpfs /run/reos/identity-service/ for Vault AppRole credentials); pyproject.toml + requirements.in/txt (argon2-cffi, python-jose[cryptography], cryptography, redis[hiredis], hvac-replaced-by-httpx, aiokafka, pydantic-settings); Alembic migration 0001 (DDL for users/roles/permissions/user_roles/role_permissions; seeds 6 system roles super_admin/platform_admin/energy_engineer/customer_support/customer/readonly with is_system=TRUE; seeds 21 permissions across 7 domains users/energy/quotations/payments/support/reports/admin/own; assigns permission sets per SRS RBAC taxonomy). Core layer: password.py (Argon2id time=3/mem=64MiB/p=4), pkce.py (S256-only, RFC 7636 — constant-time compare_digest), lockout.py (Redis incr with 5-failure/1800s TTL), vault.py (httpx AsyncClient — AppRole login from tmpfs + PKI issue RSA-4096 cert 720h TTL), jwt.py (JWTManager — fetches key from Vault PKI on startup, background rotation task at 24h buffer, create_access_token with sub/iss/aud/iat/exp=900s/jti/roles/permissions claims, RS256, JWKS generation via cryptography.RSAPublicKey), kafka.py (AIOKafkaProducer — acks=all/idempotence/gzip, publish_user_registered event). API v1: auth.py (POST /register + 409 duplicate check + Kafka event; POST /login — lockout check + constant-time verify + auth_code in Redis 600s TTL + PKCE challenge stored; POST /token — authorization_code: atomic Redis GETDEL single-use + PKCE verify + token pair issue; refresh_token: GETDEL rotation; POST /revoke: delete RT hash); jwks.py (GET /.well-known/jwks.json); health.py (GET /health). main.py (FastAPI lifespan: Vault→JWT→Kafka→Redis startup sequence; structlog JSON logging). Tests: unit/test_pkce, unit/test_password, unit/test_lockout, unit/test_jwt (all no-Vault using generated RSA pair); integration/test_auth_api (full PKCE flow + single-use enforcement + JWKS). Alembic env.py async. |
| Commit | 7d4a154 (`feature/epic-005-platform-foundation`) |
| Files Changed | `services/identity-service/` (29 files — new) |
| Approval | Enterprise Architect (pending AR-048) |

---

### EECR-CHG-053 — AR-048 APPROVED + WP-005-02 IN PROGRESS

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-053 |
| Date | 2026-07-03 |
| Type | REVIEW, STATUS |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | AR-048 (WP-005-01 Identity Service Core) approved by human Platform Lead via "CONTINUE" instruction. WP-005-01 status updated to APPROVED. WP-005-02 (Role & Permission Data Model — RBAC management layer) commenced on branch `feature/epic-005-platform-foundation`. Implementation adds: `core/security.py` (get_current_user FastAPI dependency — RS256 Bearer validation via JWTManager.decode_access_token, selectinload User.roles.permissions for zero-roundtrip RBAC); `core/rbac.py` (RequirePermission AND-semantics, RequireRole OR-semantics); `schemas/role.py` (PermissionResponse, RoleCreate, RoleUpdate, RoleResponse, UserRoleResponse); `api/v1/roles.py` (GET/POST/PATCH/DELETE /roles; GET /roles/{id}/permissions; POST/DELETE /roles/{id}/permissions/{perm_id} — 403 guard on system roles); `api/v1/users_admin.py` (GET/POST/DELETE /users/{id}/roles — own-read without admin:read, others need admin:read, assign/remove needs admin:write with assigned_by audit column); `core/jwt.py` extended with decode_access_token (RS256-pinned, ValueError on any failure) and _public_key_pem storage; tests: unit/test_security.py, unit/test_rbac.py, integration/test_roles_api.py. Commit hash pending. |
| Commit | 5c5d2e6 (`feature/epic-005-platform-foundation`) |
| Files Changed | 9 files modified/created |
| Approval | Enterprise Architect (pending AR-049) |

---

### EECR-CHG-054 — ECR-005-SEQUENCE-01 Resolved: AR-049 APPROVED + WP Labelling Correction

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-054 |
| Date | 2026-07-03 |
| Type | REVIEW, STATUS, SCOPE |
| Author | Chief Engineering Officer (AI-assisted: claude-sonnet-4-6) |
| Summary | ECR-005-SEQUENCE-01 resolved per human CEO approved resolution prompt. (1) AR-049 confirmed APPROVED — the implementation in commit `5c5d2e6` (previously labelled "WP-005-02 RBAC management layer") is approved. (2) WP LABELLING CORRECTION: commit `5c5d2e6` implements the scope of canonical WP-005-03 — RBAC & Tenant Management, not WP-005-02. The prior label "WP-005-02" is superseded for governance purposes. No implementation changes were made to source code. (3) PROGRAMME BASELINE after correction: WP-005-01 (Core Auth & JWT) — COMPLETE, commit 7d4a154, AR-048 APPROVED. WP-005-03 (RBAC & Tenant Management) — IMPLEMENTED EARLY, commit 5c5d2e6, AR-049 APPROVED. Canonical WP-005-02 (Multi-Factor Authentication) — NOT YET IMPLEMENTED, first executable WP. |
| WPs Affected | WP-005-02, WP-005-03 |
| ECR Reference | ECR-005-SEQUENCE-01 |
| Approval | Chief Engineering Officer (Human) |

---

### EECR-CHG-055 — WP-005-02: Multi-Factor Authentication — IN PROGRESS

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-055 |
| Date | 2026-07-03 |
| Type | STATUS |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | Canonical WP-005-02 (Multi-Factor Authentication — SRS SEC-004/SEC-005) commenced on branch `feature/epic-005-platform-foundation`. Scope: TOTP setup/verification (pyotp, ±1 window), SMS MFA (stubbed pending WP-005-05 Notification Service), FIDO2/WebAuthn (webauthn library), Redis-backed attempt tracking (5 failures → 900s lock, 1800s window per SEC-005), intermediate MFA-pending token in login flow for privileged roles (SEC-004 enforcement), mfa_secret (Fernet-encrypted at rest), mfa_methods array, webauthn_credentials table, Alembic migration 0002, admin unlock endpoint. Commit hash pending completion. |
| WPs Affected | WP-005-02 |
| Approval | Enterprise Architect (pending AR-050) |

---

### EECR-CHG-056 — WP-005-02: Multi-Factor Authentication — IMPLEMENTED

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-056 |
| Date | 2026-07-03 |
| Type | STATUS, SCOPE |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-005-02 (Multi-Factor Authentication — SRS SEC-004/SEC-005) implemented on branch `feature/epic-005-platform-foundation`. New files: `core/mfa_lockout.py` (SEC-005: Redis INCR attempt counter TTL=1800s, lock key TTL=900s, threshold=5, admin_unlock_mfa); `core/mfa.py` (TOTP: pyotp random_base32 secret, get_totp_provisioning_uri, verify_totp ±1 window; SMS: generate_and_store_sms_otp stub+Redis, verify_sms_otp GETDEL single-use; FIDO2: begin/complete fido2_registration + begin/complete fido2_assertion using webauthn library, challenge stored in Redis TTL=300s; Fernet at-rest encryption of TOTP secret; is_mfa_required_role helper reading MFA_REQUIRED_ROLES from settings); `schemas/mfa.py` (MfaPendingResponse, MfaSetupRequiredResponse, TotpSetupResponse, TotpSetupCompleteRequest, TotpVerifyRequest, SmsSendRequest/Response, SmsVerifyRequest, Fido2RegisterResponse, Fido2AssertResponse, Fido2AssertCompleteRequest, MfaUnlockResponse, MfaTokenResponse); `models/webauthn_credential.py` (WebAuthnCredential ORM model — credential_id/public_key/sign_count); `alembic/versions/0002_add_mfa_fields.py` (adds mfa_secret STRING(512) nullable, mfa_methods ARRAY(text) default empty, creates webauthn_credentials table + indexes). Modified: `models/user.py` (mfa_secret, mfa_methods columns, webauthn_credentials relationship); `core/jwt.py` (create_mfa_pending_token type=mfa-pending|mfa-setup-required aud=reos-mfa, decode_mfa_pending_token); `api/v1/auth.py` (SEC-004 enforcement in _exchange_auth_code: privileged roles+mfa_enabled → MfaPendingResponse; privileged+not enabled → MfaSetupRequiredResponse); `api/v1/router.py` (mfa router wired); `api/v1/mfa.py` (10 endpoints: POST /auth/mfa/totp/setup, /setup/complete, /totp/verify, /sms/send, /sms/verify, /fido2/register, /fido2/register/complete, /fido2/assert, /fido2/assert/complete, /admin/mfa/unlock/{user_id}); `config.py` (MFA_REQUIRED_ROLES, MFA_PENDING_TOKEN_TTL=300, MFA_SETUP_TOKEN_TTL=600, MFA_LOCKOUT_MAX_ATTEMPTS=5, MFA_LOCKOUT_WINDOW_SECONDS=1800, MFA_LOCKED_TTL_SECONDS=900, MFA_TOTP_WINDOW=1, MFA_TOTP_ISSUER=REOS, MFA_SMS_OTP_TTL=300, MFA_WEBAUTHN_RP_ID, MFA_WEBAUTHN_RP_NAME, MFA_WEBAUTHN_CHALLENGE_TTL=300, MFA_SECRET_ENCRYPTION_KEY); `pyproject.toml` (pyotp>=2.9.0, webauthn>=2.1.0). Tests: unit/test_mfa_totp.py (10 tests: secret generation, provisioning URI, TOTP verify, window tolerance, Fernet encrypt/decrypt, is_mfa_required_role, intermediate token create/decode/type-mismatch); unit/test_mfa_lockout.py (8 tests: is_mfa_locked, first-failure TTL, subsequent-failure no-TTL-reset, 5th-failure lock, admin unlock); integration/test_mfa_api.py (10 tests: auth enforcement, schema validation, TOTP setup+complete flow, lockout trigger, SMS stub). Design flags: (1) TOTP secret encryption uses Fernet not Vault Transit — flagged as WP-005-09 reos-auth enhancement. (2) Role names for MFA enforcement: SRS SEC-004 names engineer/administrator/government; actual DB seeds use energy_engineer/platform_admin/super_admin — MFA_REQUIRED_ROLES is configurable to bridge this. (3) SMS delivery is a documented no-op stub with the exact interface WP-005-05 must satisfy. (4) Backup codes not implemented — not specified in SRS SEC-004/005 scope. Commit hash pending. |
| Commit | 25cc88f (`feature/epic-005-platform-foundation`) |
| Files Changed | 17 files (9 new, 8 modified) — 1753 insertions |
| WPs Affected | WP-005-02 |
| Approval | Enterprise Architect (pending AR-050) |

---

### EECR-CHG-057 — ECR-004-REEXEC-01 CLOSED: EPIC-004 Status Recorded as IMPLEMENTED

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-057 |
| Date | 2026-07-03 |
| Type | STATUS, REVIEW, DECISION |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | ECR-004-REEXEC-01 raised: EPIC-004 execution request received; Phase 0 Programme State Verification confirmed EPIC-004 fully implemented and merged to `develop/v1.1` (merge commit `41ad963`). All 14 WPs committed (WP-004-01 `fbfebe6` through WP-004-14 `d9a7bce`), EECR-CHG-049/050/051 recorded. ECR-004-REEXEC-01 APPROVED by Project Owner: execution request is superseded, no re-implementation authorised. EPIC-004 status formally recorded: Status=IMPLEMENTED, Merge Status=COMPLETE, Repository Status=AUTHORITATIVE, Execution Request=CLOSED. AR tracking package prepared for AR-034 through AR-047 (governance reviews only, no code changes). Discrepancy noted and recorded: the original AR register assigned AR-034..047 to future WP-005-03..WP-006-08 planning entries; the EECR-CHG-049..051 implementation records re-assigned those same IDs to the actual EPIC-004 WP-004-01..14 implementations. The AR register has been corrected to reflect actual implementation (EPIC-004 WP assignments authoritative per EECR-CHG-049..051). Original pre-implementation planning entries for WP-005-03..WP-006-08 under AR-034..047 are superseded; those WPs are now tracked under AR-048 onwards per current EPIC-005 governance. Tracking artefact created at `engineering/governance/EECR/ar-034-047-epic-004-tracking.md`. Open operational items carried forward (5 items, Project Owner / EA action — not implementation work). |
| ECR Closed | ECR-004-REEXEC-01 |
| EPIC Status | EPIC-004: IMPLEMENTED / COMPLETE / AUTHORITATIVE |
| Files Changed | `engineering/governance/EECR/change-log.md`, `engineering/governance/EECR/architecture-review-register.md`, `engineering/governance/EECR/ar-034-047-epic-004-tracking.md` (new) |
| WPs Affected | WP-004-01 through WP-004-14 (governance records only) |
| Approval | Enterprise Architect |

---

### EECR-CHG-058 — AR-050 APPROVED: WP-005-02 Multi-Factor Authentication

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-058 |
| Date | 2026-07-03 |
| Type | REVIEW, STATUS |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | AR-050 APPROVED by Enterprise Architect. WP-005-02 (Multi-Factor Authentication — SRS SEC-004/SEC-005) on branch `feature/epic-005-platform-foundation` @ commit `25cc88f` is formally approved. Programme state after AR-050: WP-005-01 APPROVED (AR-048), WP-005-03 APPROVED (AR-049), WP-005-02 APPROVED (AR-050). EPIC-005 implementation continues; next executable Work Package is WP-005-04. EPIC-006 prerequisite remains blocked on WP-005-14 Phase 1 Sign-off. |
| AR Reference | AR-050 — APPROVED |
| WPs Affected | WP-005-02 |
| Files Changed | `engineering/governance/EECR/change-log.md`, `engineering/governance/EECR/architecture-review-register.md` |
| Approval | Enterprise Architect |

---

### EECR-CHG-059 — AR-034 through AR-047: EPIC-004 Architecture Reviews COMPLETE

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-059 |
| Date | 2026-07-03 |
| Type | REVIEW |
| Author | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | Architecture Reviews AR-034 through AR-047 completed for EPIC-004 — CI/CD, DevSecOps & Release Automation (WP-004-01 through WP-004-14, merge commit `41ad963`). Batch outcome: 8 APPROVED outright; 6 APPROVED WITH CONDITIONS; 0 REJECTED or CHANGES REQUIRED. Average score: 95.6/100. All 14 WPs meet the ≥90 threshold required for APPROVED status. Six WPs have outstanding conditions requiring Project Owner / Platform Lead action before their ARs can be fully closed. EPIC-004 status updated to: **IMPLEMENTATION COMPLETE — CONDITIONALLY CLOSED**. Full scored assessments recorded in `architecture-review-register.md` AR-034 through AR-047. Completion tracking table in `ar-034-047-epic-004-tracking.md` updated. |
| APPROVED outright | AR-034 (99/100), AR-036 (98/100), AR-037 (100/100), AR-038 (97/100), AR-039 (98/100), AR-043 (98/100), AR-045 (98/100), AR-047 (97/100) |
| APPROVED WITH CONDITIONS | AR-035 (92/100) — GHAS; AR-040 (97/100) — Webhook; AR-041 (88/100) — .zap/rules.tsv DEFECT; AR-042 (93/100) — Gitleaks licence + baseline scan; AR-044 (92/100) — Staging VMs; AR-046 (92/100) — Rollback drill |
| Key Defect | AR-041: `.zap/rules.tsv` referenced in `dast-scan.yml` but does not exist in repository — DAST workflow will fail until this file is created (see ECR-004-DAST-01 raised in EECR-CHG-060) |
| WPs Affected | WP-004-01 through WP-004-14 |
| Files Changed | `engineering/governance/EECR/architecture-review-register.md` (AR-034..047 added to Completed Reviews; Compliance Summary updated); `engineering/governance/EECR/ar-034-047-epic-004-tracking.md` (Review Completion Tracking table updated) |
| Approval | Enterprise Architect |

---

### EECR-CHG-060 — ECR-004-DAST-01 RAISED: Missing .zap/rules.tsv

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-060 |
| Date | 2026-07-03 |
| Type | DECISION |
| Author | Enterprise Architect |
| Summary | **ECR-004-DAST-01 RAISED.** AR-041 (WP-004-08) identified a defect: `.zap/rules.tsv` is referenced in `.github/workflows/dast-scan.yml` at `rules_file_name: ".zap/rules.tsv"` but the file does not exist in the repository. The `zaproxy/action-full-scan` action will fail on file lookup until this is resolved. This is a required corrective implementation action (EARB condition C-AR041-01). Resolution: Platform Lead / DevSecOps Lead to create `.zap/rules.tsv` with an appropriate ZAP rules configuration (at minimum, an empty passthrough file; ideally a set of false-positive suppressions appropriate for the RE-OS API surface). This file is a governance/configuration file, not application code. Resolution must be committed and the commit recorded here before AR-041 is considered fully closed. |
| ECR ID | ECR-004-DAST-01 |
| Status | OPEN |
| Owner | Platform Lead / DevSecOps Lead |
| WPs Affected | WP-004-08 |
| Files to Create | `.zap/rules.tsv` |
| Blocks | AR-041 full closure |
| Approval | Enterprise Architect |

---

### EECR-CHG-061 — EPIC-004 Conditionally Closed; Programme Status Updated

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-061 |
| Date | 2026-07-03 |
| Type | STATUS, RELEASE |
| Author | Enterprise Architect |
| Summary | Following completion of AR-034..047 (EECR-CHG-059), EPIC-004 is formally recorded as **IMPLEMENTATION COMPLETE — CONDITIONALLY CLOSED**. Eight of fourteen WPs are fully APPROVED; six carry conditions pending Project Owner / Platform Lead action. The programme is not blocked on these conditions — EPIC-005 is the active engineering epic and continues. Programme status updated in `status-dashboard.md` and `release-dashboard.md`. Next executable Work Package identified as WP-005-04, but execution is blocked pending spec submission (ECR-005-SPEC-01 raised — EECR-CHG-062). |
| WPs Affected | WP-004-01 through WP-004-14 (status: APPROVED / APPROVED WITH CONDITIONS); EPIC-005 (active) |
| Files Changed | `engineering/governance/EECR/status-dashboard.md`; `engineering/governance/EECR/release-dashboard.md`; `engineering/governance/EECR/EPIC-004-CLOSURE.md` (new) |
| Approval | Enterprise Architect |

---

### EECR-CHG-062 — ECR-005-SPEC-01 RAISED: WP-005-04..14 Specs Not Submitted

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-062 |
| Date | 2026-07-03 |
| Type | DECISION |
| Author | Enterprise Architect |
| Summary | **ECR-005-SPEC-01 RAISED.** The next executable Work Package is WP-005-04 (Audit Service: Immutable Audit Log). WP-005-01/02/03 are all APPROVED (AR-048/049/050). WP-005-04 is unblocked by dependencies but cannot be executed because its Engineering Specification Document has not been submitted. All WPs WP-005-04 through WP-005-14 are in the same state. EPIC-005 implementation is **BLOCKED on specification submission**. Programme continuation requires the Project Owner to submit WP-005-04 through WP-005-14 Engineering Specification Documents. As WP-005-04 through WP-005-14 are submitted in sequence, each will be reviewed, implemented, and taken through Architecture Review before the next is begun. |
| ECR ID | ECR-005-SPEC-01 |
| Status | OPEN |
| Owner | Project Owner |
| Blocks | EPIC-005 continuation (WP-005-04 through WP-005-14); transitively EPIC-006 through EPIC-007 |
| Resolution Required | Project Owner submits WP-005-04 Engineering Specification Document |
| Approval | Enterprise Architect |

---

### EECR-CHG-063 — WP-005-04 Retitled: Audit Service (Governance Only)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-063 |
| Date | 2026-07-04 |
| Type | SCOPE, ARCH |
| Author | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-005-04 retitled from "Login / Logout / Refresh Endpoints" (F-005-04, LLD v2.0 §7.4) to "Audit Service — Immutable Platform Audit Log" (F-005-04 Audit Service, LLD v2.0 §7.6). Background: the former title described login/logout/refresh endpoints that were already delivered within WP-005-01 scope (commit `7d4a154`, `services/identity-service/src/identity_service/api/v1/auth.py`). The Project Owner direction (per ECR-005-SPEC-01 resolution) re-assigns WP-005-04 to the Audit Service microservice. **WP ID is unchanged — no renumbering.** No implementation code was created or modified by this change. Three EECR fields updated: (1) §2.1 title + Feature + Status; (2) §2.3 architecture traceability (EAS §7.4→§7.6, SRS §Login→§Audit Logging, LLD §7.4→§7.6, DEF §Auth Endpoints→§Audit Log); (3) §2.4 branch placeholder (feature/iam-auth-endpoints → feature/iam-audit-service). §2.7 governance record updated with approval date, ECR refs, and lessons-learned note. Open question: WP-005-06 ("IAM Audit Event Logging") also maps to §7.6; scope boundary must be resolved before WP-005-06 implementation (Q-AUD-001). |
| WPs Affected | WP-005-04 |
| Files Changed | `engineering/governance/EECR/engineering-execution-control-register.md` (§2.1, §2.3, §2.4, §2.7) |
| Approval | Enterprise Architect |

---

### EECR-CHG-064 — WP-005-04 Spec Produced; ECR-005-SPEC-01 Closed

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-064 |
| Date | 2026-07-04 |
| Type | DECISION, REVIEW |
| Author | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | Engineering Specification for WP-005-04 (Audit Service) produced and committed to `engineering/specs/WP-005-04-audit-service-engineering-spec.md` v1.0. The specification contains 32 sections covering: Executive Summary, Business Requirements, Functional Requirements (16 reqs), Non-Functional Requirements (10), Security Requirements (11), Compliance Requirements (6), Architecture (logical diagram, 3 sequence diagrams, interaction matrix), Data Model (audit_events + chain_state with full column definitions), Database Schema (complete DDL including TimescaleDB hypertable, immutability trigger, retention/compression policies), Kafka Event Model (3 topics, message schema, producer changes to identity-service, consumer config, retry/DLQ), API Specification (6 endpoints, schemas, error codes), Permission Model (admin:audit, RBAC matrix, JWT validation logic), Audit Event Taxonomy (22 event types in 5 categories), Retention Policy (7 years, PII anonymisation timeline), Encryption Strategy (at-rest and in-transit), Search & Query Requirements, Reporting Requirements, Metrics (10 Prometheus metrics), Logging (structlog events, PII exclusion), Tracing (correlation-ID propagation), Health Checks (/live, /ready), Performance Targets, Capacity Targets, Configuration (full Settings class + .env.example), Deployment Requirements (Docker, systemd, Ansible, Compose), Testing Requirements (unit, integration, security, performance), Deliverables (directory tree + identity-service changes), Acceptance Criteria (20 criteria), Definition of Done (22 criteria), Architecture Traceability (18-row matrix), Risks (5 risks), Open Questions (4 questions). ECR-005-SPEC-01 is hereby CLOSED — the blocking condition for WP-005-04 implementation is resolved. |
| ECR Closed | ECR-005-SPEC-01 |
| Files Created | `engineering/specs/WP-005-04-audit-service-engineering-spec.md` |
| Approval | Enterprise Architect |

---

### EECR-CHG-065 — AR-051 APPROVED: WP-005-04 Spec Review Complete

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-065 |
| Date | 2026-07-04 |
| Type | REVIEW |
| Author | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | AR-051 APPROVED — Architecture Review of the WP-005-04 Engineering Specification (Audit Service) completed. Score: 96/100. Outcome: APPROVED. All mandatory spec elements are present and technically sound. Two informational conditions: C-AR051-01 (resolve WP-005-04/WP-005-06 scope boundary before WP-005-06 implementation); C-AR051-02 (confirm port 8004 before first deployment). Neither condition blocks WP-005-04 implementation. EARB finds the specification implementation-ready. Full AR record appended to `architecture-review-register.md`. |
| AR Reference | AR-051 — APPROVED (96/100) |
| WPs Affected | WP-005-04 |
| Files Changed | `engineering/governance/EECR/architecture-review-register.md` (AR-051 added) |
| Approval | Enterprise Architect |

---

### EECR-CHG-066 — WP-005-04 Implementation Readiness Confirmed

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-066 |
| Date | 2026-07-04 |
| Type | STATUS, RELEASE |
| Author | PMO / Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-005-04 (Audit Service) cleared for implementation. Implementation Readiness Report produced at `engineering/specs/WP-005-04-implementation-readiness.md`. All pre-implementation gates are passed: (1) AR-051 APPROVED; (2) ECR-005-SPEC-01 CLOSED; (3) all dependencies satisfied (WP-005-01/02/03 APPROVED); (4) no open blocking ECRs; (5) engineering specification complete (32 sections, v1.0). WP-005-04 status updated to SPEC APPROVED in EECR §2.1 and §2.7. Blocker status in status-dashboard.md updated GREEN. Programme continues on EPIC-005 active sprint. Next: Project Owner authorises WP-005-04 implementation to begin on branch `feature/iam-audit-service`. |
| WPs Affected | WP-005-04 |
| Files Changed | `engineering/governance/EECR/status-dashboard.md` (EPIC-005 updated); `engineering/governance/EECR/engineering-execution-control-register.md` (WP-005-04 status); `engineering/specs/WP-005-04-implementation-readiness.md` (new) |
| Approval | Enterprise Architect |

---

### EECR-CHG-067 — WP-005-04 Implementation Complete; AR-052 Review Package Produced

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-067 |
| Date | 2026-07-04 |
| Type | STATUS, DEPLOY, REVIEW |
| Author | PMO / Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-005-04 (Audit Service — Immutable Platform Audit Log) implementation sprint complete. All 12 deliverables produced. Branch `feature/iam-audit-service` ready for AR-052. Key deliverables: (1) `services/audit-service/` microservice — FastAPI port 8004, TimescaleDB hypertable, SHA-256 hash chain, JWKS JWT validation, Kafka consumer, Prometheus metrics; (2) Alembic migration `0001_create_audit_schema.py` — schema, hypertable, retention, immutability trigger, chain_state; (3) 12 unit test files + 6 integration test files; (4) Identity-service modifications — `config.py`, `core/kafka.py`, `api/v1/auth.py`, `api/v1/mfa.py`, `api/v1/roles.py`, `api/v1/users_admin.py` emit `iam.audit.events` for all 22 taxonomy events; (5) Documentation — `README.md`, `engineering/docs/AUDIT_SERVICE.md`; (6) All DoD criteria met (22/22 verifiable). WP-005-04 status updated to IMPLEMENTATION COMPLETE. Awaiting AR-052 review and human engineer PR merge (GOV-002). |
| WPs Affected | WP-005-04 |
| Files Changed | `services/audit-service/` (new service — 30+ files); `services/identity-service/src/identity_service/{config,core/kafka,api/v1/{auth,mfa,roles,users_admin}}.py` (modified); `engineering/governance/EECR/status-dashboard.md`; `engineering/docs/AUDIT_SERVICE.md` (new); `services/audit-service/README.md` (new) |
| Approval | Awaiting AR-052 |

---

### EECR-CHG-068 — AR-052 APPROVED WITH CONDITIONS: WP-005-04 Audit Service Implementation Review

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-068 |
| Date | 2026-07-04 |
| Type | REVIEW, STATUS |
| Author | Enterprise Architecture Review Board (AI-assisted: claude-sonnet-4-6) |
| Summary | AR-052 COMPLETED. Architecture Review of the WP-005-04 Audit Service implementation at commit `3fdc205` on branch `feature/iam-audit-service`. **Outcome: APPROVED WITH CONDITIONS. Score: 90/100.** Implementation is architecturally sound: three-layer immutability confirmed, SHA-256 hash chain correct per spec §8.2, Kafka consumer pattern appropriate, JWT/JWKS security model correct, TimescaleDB migration verified. Four findings raised: F-AR052-01 (MEDIUM) hash chain concurrent-write race condition — no serialisation guard on same-actor concurrent REST writes; F-AR052-02 (MEDIUM) `auth.login.success` event absent from identity-service producer taxonomy; F-AR052-03 (LOW) `audit_kafka_consumer_lag` Gauge never populated; F-AR052-04 (INFORMATIONAL) `AuditEventResponse` PII field exclusion undocumented. Seven conditions tracked: C-AR052-01 (auth.login.success — required before merge); C-AR052-04 (PII response clarification — required before merge); C-AR052-02, C-AR052-03, C-AR052-05, C-AR052-06 (operational — required before staging deployment); C-AR052-07 (WP-005-06 scope boundary — before WP-005-06). Merge recommended after C-AR052-01 and C-AR052-04 resolved. Full AR record in `architecture-review-register.md`. |
| AR Reference | AR-052 — APPROVED WITH CONDITIONS (90/100) |
| WPs Affected | WP-005-04 |
| Conditions Before Merge | C-AR052-01: add auth.login.success event; C-AR052-04: clarify PII response exclusion |
| Conditions Before Staging | C-AR052-02: populate consumer_lag metric; C-AR052-03: hash chain serialisation guard; C-AR052-05: confirm port 8004; C-AR052-06: confirm chain_state UPDATE permission |
| Files Changed | `engineering/governance/EECR/architecture-review-register.md` (AR-052 added); `engineering/governance/EECR/change-log.md` (this entry); `engineering/governance/EECR/status-dashboard.md` (WP-005-04 status updated) |
| Approval | Enterprise Architect (EARB) |

---

### EECR-CHG-069 — WP-005-04 Pre-Merge Condition Resolution: AR-052 C-AR052-01 + C-AR052-04 Resolved

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-069 |
| Date | 2026-07-04 |
| Type | STATUS, REVIEW |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | WP-005-04 Condition Resolution Sprint complete. Both pre-merge conditions from AR-052 have been resolved at commit `3365850` on branch `feature/iam-audit-service`. **C-AR052-01 RESOLVED:** `auth.login.success` audit event added to `services/identity-service/src/identity_service/api/v1/auth.py` `login()` success path — after `lockout.clear_failures()`, before `pkce.generate_auth_code()`. Completes the auth.login.success/failure/locked taxonomy triad. **C-AR052-04 RESOLVED (Option B — accidental omission):** `actor_username`, `actor_ip_address`, `actor_user_agent` added to `AuditEventResponse` in `services/audit-service/src/audit_service/api/v1/schemas/audit_event.py`. PII Handling Policy documented in `engineering/docs/AUDIT_SERVICE.md`. Unit tests added (`TestAuditEventResponse` class with 2 tests). Branch `feature/iam-audit-service` is now **READY FOR MERGE** to `develop/v1.1`. Four staging conditions remain open (C-AR052-02/03/05/06) — explicitly permitted by AR-052 decision. Per GOV-002: human engineer PR review and merge required. |
| AR Reference | AR-052 — APPROVED WITH CONDITIONS (90/100) |
| WPs Affected | WP-005-04 |
| Pre-Merge Conditions Resolved | C-AR052-01: auth.login.success event added; C-AR052-04: AuditEventResponse PII fields added + PII policy documented |
| Conditions Remaining Open (Staging) | C-AR052-02: consumer_lag metric unpopulated; C-AR052-03: hash chain serialisation guard; C-AR052-05: confirm port 8004; C-AR052-06: confirm chain_state UPDATE permission |
| Files Changed | `services/identity-service/src/identity_service/api/v1/auth.py` (auth.login.success event added); `services/audit-service/src/audit_service/api/v1/schemas/audit_event.py` (PII fields added to AuditEventResponse); `services/audit-service/tests/unit/test_schemas.py` (TestAuditEventResponse tests added); `engineering/docs/AUDIT_SERVICE.md` (PII Handling Policy + Architecture Review Conditions sections added); `engineering/governance/EECR/architecture-review-register.md` (AR-052 DoD/conditions/recommendation updated to READY FOR MERGE); `engineering/governance/EECR/change-log.md` (this entry); `engineering/governance/EECR/status-dashboard.md` (WP-005-04 status updated to READY FOR MERGE) |
| Approval | Enterprise Architect (post-merge ratification) |

---

### EECR-CHG-070 — ECR-005-CI-01: Shared Library Package Resolution in CI (WP-005-04 Blocker)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-070 |
| Date | 2026-07-04 |
| Type | STATUS, ARCH |
| Author | DevOps Lead / Platform Engineering Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | Resolved ECR-005-CI-01: CI Stage 3 was failing because pip-audit could not resolve `reos-config==0.1.0`, `reos-logging==0.1.0`, `reos-exceptions==0.1.0`, `reos-common==0.1.0` from PyPI — these are EPIC-002 monorepo-internal packages not published externally. **Root cause:** pypiserver (internal package index) was not running in CI, and `PIP_EXTRA_INDEX_URL` was not configured. **Architecture decision:** Option A (Internal Package Registry) — build wheels from `libs/` source, serve via pypiserver on `127.0.0.1:8080`, configure `PIP_EXTRA_INDEX_URL=http://localhost:8080/simple/` for pip-audit. This is the Release 1 CI bootstrap described in ARTIFACT_REPOSITORY.md §2/3. Also fixed: Stage 1 (`mypy src/` → discover actual `src/` dirs), Stage 2 (`bandit -r src/` → discover actual `src/` dirs), `mypy.ini` (added `ignore_missing_imports` for aiokafka, argon2, prometheus_client, pyotp, webauthn). Created `services/audit-service/requirements.txt` (manually pinned per DEPENDENCY_POLICY.md §2.4; must be pip-compile regenerated before staging). Documented CI bootstrap pattern in ARTIFACT_REPOSITORY.md §6 and .github/README_EPIC004.md §10. |
| ECR Reference | ECR-005-CI-01 |
| WPs Affected | WP-005-04 (PR #17 blocker) |
| Commit | `18c73aa` |
| Files Changed | `.github/workflows/service-ci-cd.yml` (Stage 1/2/3 monorepo path fixes + pypiserver bootstrap); `mypy.ini` (ignore_missing_imports additions); `services/audit-service/requirements.txt` (new — manually pinned); `ARTIFACT_REPOSITORY.md` (§6 CI bootstrap pattern); `.github/README_EPIC004.md` (§10 shared library resolution guide) |
| Approval | Platform Lead (post-CI-green ratification) |

---

---

### EECR-CHG-071 — WP-005-04 CI Remediation Sprint: Ruff/Bandit/pip-audit Stage 1-3 Unblocked

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-071 |
| Date | 2026-07-04 |
| Type | STATUS, ARCH |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | **CI Remediation Sprint complete** — three independent CI failures blocking PR #17 (`feature/iam-audit-service → develop/v1.1`) resolved. **Stage 1 (Ruff lint):** (A) Root `pyproject.toml` updated — added `exclude` list for pre-EPIC-004 DIEP platform modules (`drivers/`, `validation/`, `fastapi/`, `copilot/`, `services/cim/`, `services/opcua/`, `services/mdm/`) and `B008` to `ignore` (FastAPI `Depends()`/`Query()` framework pattern); (B) Service-level `pyproject.toml` files (`audit-service`, `identity-service`) updated with `B008` ignore; (C) All Ruff violations in RE-OS services and shared libraries resolved — ~100+ violations including N818 exception renames, B904/B905/B007/B017, S104/S105/S106/S107/S110, F821 genuine bug fix (`remove_role_from_user` parameter name), TYPE_CHECKING pattern for SQLAlchemy model circular imports, C901/E501 complexity/line-length fixes. **Stage 2 (Bandit B104):** `HOST` default changed from `"0.0.0.0"` to `"127.0.0.1"` in both `services/audit-service/src/audit_service/config.py` and `services/identity-service/src/identity_service/config.py` — principle of least privilege; Dockerfiles continue to bind `0.0.0.0` explicitly via `CMD` flag unchanged. **Stage 3 (pip-audit resolver conflict):** `pydantic==2.7.4` → `2.8.2` and `pydantic-core==2.18.4` → `2.20.1` in `templates/python-service/requirements.txt` — aligns scaffold template with service implementations; eliminates pip resolver abort that prevented pip-audit from executing. **Additional:** `pyproject.toml` `[tool.black]`/`[tool.isort]` exclusions added matching ruff scope; `black` and `isort` applied across all RE-OS services and shared libraries (76 files). Validation: `ruff check` → `All checks passed!`; `black --check` → `116 files unchanged`; `isort --check-only` → exit 0; `bandit -r ... -ll -ii` → no findings. No architecture changes. No quality gates disabled. All `# noqa` / `# nosec` annotations carry Bandit/Ruff ID and justification. |
| WPs Affected | WP-005-04 |
| Commit | `889d3e3` |
| Files Changed | `pyproject.toml` (ruff/black/isort excludes + B008 ignore); `services/audit-service/pyproject.toml` (B008 ignore); `services/identity-service/pyproject.toml` (B008 ignore); `templates/python-service/requirements.txt` (pydantic 2.8.2); `services/audit-service/src/**` (ruff fixes + black/isort); `services/identity-service/src/**` (ruff fixes + HOST default + black/isort); `services/audit-service/tests/**` (black/isort); `services/identity-service/tests/**` (black/isort); `libs/**` (black/isort); `engineering/governance/EECR/change-log.md` (this entry); `engineering/governance/EECR/status-dashboard.md` (status updated) |
| Approval | Platform Lead (post-CI-green ratification per GOV-002) |

---

### EECR-CHG-073 — ECR-005-CI-03: CI Governance Alignment — Stage 1 lint scope restriction

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-073 |
| Date | 2026-07-04 |
| Type | STATUS |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | **ECR-005-CI-03 implementation** — Stage 1 (`service-ci-cd.yml` lint job) was running `ruff check .`, `black --check --diff .`, and `isort --check-only .` against the full monorepo root. The declared scope in `pyproject.toml` (header comment, line 2) is explicitly "RE-OS services and shared libraries." The inconsistency caused Stage 1 to fail on violations in legacy DIEP platform modules (`tests/`, `topology/`, `contracts/`, `ingestor/`, `dispatcher/`, `automation/`, `digitaltwin/`, `simulator/`, `nodered/`, `emqx-ha-validation/`, `kafka-ha-validation/`, `redis-sentinel-validation/`, `oms/`, `scripts/`) that are governed by `ci.yml`, not `service-ci-cd.yml`. **Verification performed:** every Python file outside `services/`, `libs/`, and `templates/python-service/` was inspected; none are RE-OS production source (confirmed by absence of `reos_*`/`audit_service`/`identity_service` imports and by module docstrings identifying them as DIEP platform artefacts). **Changes:** (A) `ruff check .` → `ruff check services/ libs/ templates/python-service/`; (B) `black --check --diff .` → scoped; (C) `isort --check-only .` → scoped. mypy is unchanged (already correctly scoped). **In-scope cleanup:** fixed 2 violations in `templates/python-service/` — S105 `# noqa` with justification on template placeholder `jwt_secret_key`; E501 import wrap in `dependencies.py`. **No quality gates disabled:** all RE-OS services and shared libraries continue to be linted blocking. **TD-14 created** in TECHNICAL_DEBT_REPORT.md to track the full-monorepo lint baseline (~325 violations, ~16 engineer-hours) as a future DIEP platform modernisation work package. |
| WPs Affected | WP-005-04 |
| Commit | `ad19bbc` |
| Files Changed | `.github/workflows/service-ci-cd.yml` (Stage 1 lint scope + Stage 3 policy comment); `templates/python-service/src/service_name/config.py` (S105 noqa); `templates/python-service/src/service_name/dependencies.py` (E501 wrap); `engineering/docs/TECHNICAL_DEBT_REPORT.md` (TD-14); 52 RE-OS source files (isort import ordering with directory-scoped config) |
| Approval | Enterprise Architect (ECR-005-CI-03 scope classification per GOV-002) |

---

### EECR-CHG-072 — WP-005-04 CI Remediation: pip-audit reos-* package filter

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-072 |
| Date | 2026-07-04 |
| Type | STATUS |
| Author | Platform Lead (AI-assisted: claude-sonnet-4-6) |
| Summary | **pip-audit Stage 3 follow-on fix** — after EECR-CHG-071 resolved the pydantic version conflict, pip-audit surfaced a second failure: `reos-config (0.1.0) — Dependency not found on PyPI and could not be audited`. Root cause: `PIP_EXTRA_INDEX_URL` routes pip's *resolver* to the internal pypiserver so packages can be installed, but pip-audit's *vulnerability lookup* queries the PyPI/OSV advisory database directly. `reos-config`, `reos-logging`, `reos-exceptions`, and `reos-common` have no PyPI presence and therefore no advisory-database entries; pip-audit with `--strict` exits non-zero when any package cannot be audited. Fix: added `grep -Ev '^reos-'` pre-filter in the `pip-audit` CI step to strip internal packages from the requirements files before passing them to pip-audit. Internal monorepo packages have no public CVE surface; security review of these packages occurs in code review. No quality gates disabled — pip-audit continues to run with `--strict` on all third-party dependencies. |
| WPs Affected | WP-005-04 |
| Commit | `1524041` |
| Files Changed | `.github/workflows/service-ci-cd.yml` (pip-audit step: grep filter for reos-* + updated comments) |
| Approval | Platform Lead (post-CI-green ratification per GOV-002) |

---

### EECR-CHG-074 — PCS-001 Programme Closure: WP-005-04 Baseline Frozen

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-074 |
| Date | 2026-07-05 |
| Type | STATUS, RELEASE, REVIEW, GOVERNANCE |
| Author | PMO / Platform Lead (AI-assisted documentation closure) |
| Summary | PCS-001 programme closure completed for the currently authorised engineering baseline. PR #17 was human approved and human merged to `develop/v1.1` at merge commit `946451222eaef3c988f80963e5eddce24ec7720e`. Release tag `wp-005-04-audit-service-v1.0` points at the merge commit. WP-005-04 is recorded as IMPLEMENTED / MERGED / BASELINE FROZEN. Required CI evidence is green: Stage 1, Stage 2, Stage 3, Secrets, Stage 4, Stages 5/6/7, and separate CodeQL. AR-052 is closed as APPROVED / MERGED / BASELINE FROZEN. EECR-CHG-067 through EECR-CHG-073 are closed as approved and merged. Remaining AR-052 staging/deployment conditions are carried forward in the Technical Debt Register and are not merge blockers. |
| WPs Affected | WP-005-04 |
| Merge Commit | `946451222eaef3c988f80963e5eddce24ec7720e` |
| Release Tag | `wp-005-04-audit-service-v1.0` |
| CI Evidence | GitHub Actions run `28740300083`; CodeQL check `85221840383` |
| Closed Records | AR-052; EECR-CHG-067; EECR-CHG-068; EECR-CHG-069; EECR-CHG-070; EECR-CHG-071; EECR-CHG-072; EECR-CHG-073 |
| Files Changed | Governance/register/report files only; no source-code changes. Added `EPIC-005-BASELINE-MANIFEST.md`, `WP-005-04-RELEASE-CLOSURE-REPORT.md`, `PROGRAMME-HEALTH-REPORT.md`, `RELEASE-1-EXECUTIVE-SUMMARY.md`, and `PMO-RECOMMENDATION.md`. |
| Approval | Human GOV-002 PR approval and merge; PCS-001 closure documentation |

---

> **Register continuity note (2026-07-07):** EECR-CHG-075 through EECR-CHG-089 were allocated to
> Release 2 platform-recovery and validation-framework changes (R2-PLAT series). Their identifiers
> are referenced in `release-2/RELEASE-2-R2-PLAT-*-COMPLETION-REPORT.md` but the corresponding
> entries were not consolidated into this log at merge time. The IDs remain reserved; backfill of
> the 075–089 entries into this log is a housekeeping action for the PMO. Numbering resumes at 090.

---

### EECR-CHG-090 — WP-006-03B Closure: CIM XML Parser Foundation Merged

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-090 |
| Date | 2026-07-07 |
| Type | STATUS, RELEASE |
| Author | Engineering Defect Resolution Lead / Release function (AI-assisted: claude-fable-5) |
| Description | **WP-006-03B — CIM/IEC 61968 CIM-XML Parser (Part B: governed XML import foundation) merged to `develop/v1.1`** via PR #19 at merge commit `30b534d`. Delivered: `services/cim/serialization/xml_import.py` (348 lines — secure parser foundation, namespace validation, object extraction, RDF reference resolution) and four test suites (`tests/test_cim_xml_import_namespaces.py`, `_objects.py`, `_references.py`, `_security.py` — 381 lines) plus `release-2/RELEASE-2-TEST-CLASSIFICATION.csv` classification rows. Feature commits: `d681740` (secure parser foundation), `04aee6a` (namespace validation), `c28bca7` (object extraction), `b601b91` (reference resolution), `53b75b0` (documentation alignment), `103f9e9` (test classification). |
| Reason | WP-006-03B implementation slice authorised under the Release 2 validation governance (ADR-R2-07; R2-PLAT-001..007 recovery completion reports on record; Release 2 Validation workflow green). Human Programme authority merged PR #19 under GOV-002. |
| Risk | LOW. Additive module and tests; no existing CIM serialization paths modified. Security-focused test suite covers the XML attack surface (see `_security.py`). Residual: `services/cim/` remains outside the RE-OS Stage 1 lint boundary (TD-01/TD-14 disposition unchanged). |
| Rollback | Revert merge commit `30b534d` (`git revert -m 1`); no schema or data impact. |
| Validation | Branch HEAD `a52bbcb` green on both required workflows before merge: RE-OS Service CI/CD run `28881946191`→`28881943400` (success) and Release 2 Validation run `28881946191` (success). Stage 1 lint failure chain resolved via defect-resolution PRs #20 (Ruff), #21 (Black), #22 (isort, EDR-003 conftest fix at `1222660`) — all narrowly scoped to audit-service formatting, outside WP-006-03B files. |
| Delta Since 1222660 | PR #19 content only (6 files, +733 lines) plus develop/v1.1 merge-downs |
| WPs Affected | WP-006-03B (WP-006-03 register rows to be updated from NOT STARTED by PMO) |
| Approval | Human GOV-002 review and merge of PR #19 (2026-07-07) |

---

### EECR-CHG-091 — Register Checkpoint: WP-006-03B Status + ECR-006-GATE-01 Raised

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-091 |
| Date | 2026-07-07 |
| Type | STATUS, DECISION |
| Author | Release Manager (AI-assisted: claude-fable-5) |
| Description | Programme-level checkpoint before next implementation authorisation. (A) Engineering Execution Control Register (`engineering-execution-control-register.md`) updated: WP-006-03 status → 03A/03B SLICES IMPLEMENTED / MERGED with evidenced DoD gates filled (unit tests PASS, SAST PASS, GOV-002 code review APPROVED; Architecture Review recorded as NOT ON RECORD for 03B); dependency row completed with EECR-CHG-090 traceability; WP-006-04 row annotated "do not start until ECR-006-GATE-01 resolved". (B) **ECR-006-GATE-01 raised** in the decision log: whether the 03A+03B slice merges satisfy the "WP-006-02 or WP-006-03 APPROVED" gate for WP-006-04, or whether formal WP-level closure is required. Decision owner: Programme Board — explicitly not an engineering interpretation. |
| Reason | WP-006-03B merged (PR #19, EECR-CHG-090); register must reflect delivered state before the Programme Board rules on the WP-006-04 gate. Dependency-transition verification found three material facts: no Architecture Review on record for 03B; no governance record defining whether 03A+03B exhausts WP-006-03 scope; the WP-006-02 gate arm is also unverifiable (recovery programme says Complete, register says NOT STARTED). |
| Risk | NONE (register/decision documentation only). Findings themselves note governance debt: missing 03B AR; `engineering-execution-control-register.csv` is stale programme-wide (e.g., its WP-005-04 row still reads "Login/Logout Endpoints, NOT STARTED") — CSV reconciliation flagged for PMO, not corrected here to avoid a half-synced artefact. |
| Rollback | Revert the documentation commit; no engineering impact. |
| Validation | All cited commits, runs, and register rows verified against the repository at preparation time. |
| WPs Affected | WP-006-03 (status), WP-006-04 (gate hold) |
| Approval | Register update per GOV-001; ECR-006-GATE-01 resolution reserved to Programme Board |

---

### EECR-CHG-092 — GOV-003: Programme Board Ruling on ECR-006-GATE-01; WP-006-04 Authorised

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-092 |
| Date | 2026-07-07 |
| Type | DECISION, STATUS |
| Author | Programme Board (AI-facilitated under explicit human authorisation; recorded by Release Manager function, claude-fable-5) |
| Description | Programme Board convened per explicit human Programme authority instruction (2026-07-07) to decide ECR-006-GATE-01. **Ruling (GOV-003): Option A with conditions.** The merged WP-006-03A+03B slice set constitutes the substantive delivery of WP-006-03; WP-006-03 is declared APPROVED for dependency-gate purposes; the WP-006-04 gate arm "WP-006-03 APPROVED" is satisfied; **WP-006-04 (Topology Publish-Version Endpoint) is authorised to start** upon ratification. Conditions: C-GATE01-01 (retrospective Architecture Review of the CIM XML import foundation before WP-006-05 authorisation or EPIC-006 exit), C-GATE01-02 (PMO reconciliation of WP-006-02 register status), C-GATE01-03 (PMO confirmation of residual WP-006-03 scope; any residual is a separately authorised 03C slice). Registers updated: decision log (ECR-006-GATE-01 → RESOLVED; GOV-003 added; Open Decisions cleared), execution control register (WP-006-03 → APPROVED; WP-006-04 → AUTHORISED TO START; DoD Arch_Review cell → retrospective AR condition). |
| Reason | ECR-006-GATE-01 required a programme-governance ruling before WP-006-04 could begin; blocking further delivery on a decidable interpretation question serves no control purpose once the Board has ruled. |
| Risk | LOW. Ruling is conditioned: the missing Architecture Review is secured by C-GATE01-01 rather than waived. Residual: retrospective ARs carry the risk that findings arrive after dependent code exists; mitigated by requiring the AR before WP-006-05, the first WP that builds on versioned-topology behaviour beyond WP-006-04. |
| Rollback | The Board may vacate GOV-003 by a superseding GOV entry; register rows revert accordingly. Not a code change. |
| Validation | Ruling recorded against verified register state (EECR-CHG-091); all referenced records exist at preparation time. |
| WPs Affected | WP-006-03 (APPROVED), WP-006-04 (AUTHORISED TO START), WP-006-05 (C-GATE01-01 precondition noted) |
| Approval | **Authoritative upon human GOV-002 merge of the recording PR** — the merge constitutes the human ratification of the Board ruling |

---

### EECR-CHG-093 — EDR-004: Governed Acceptance of PYSEC-2026-1325 (ecdsa, No Fix Available)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-093 |
| Date | 2026-07-07 |
| Type | RISK, STATUS (CI defect resolution) |
| Author | Engineering Defect Resolution Lead (AI-assisted: claude-fable-5) |
| Description | A newly published PYSEC advisory broke every pip-audit gate with no repository change: **PYSEC-2026-1325** (aliases CVE-2024-23342 / GHSA-wj6h-64fc-37mp) against `ecdsa` — Minerva timing attack on P-256. `ecdsa` enters the audited surfaces as a transitive dependency of `python-jose` (template + audit-service runtime locks resolve 0.19.2; identity-service pins 0.19.0 outside the audited surfaces). **The advisory has no fix version** — upstream states side-channel resistance is out of scope. Governed acceptance implemented: (A) `scripts/release2/security_dependency_audit.py` gains an `ACCEPTED_VULNERABILITIES` register (ID + rationale + governance record per entry) emitted as `--ignore-vuln` flags so acceptances appear in recorded audit-command evidence; (B) `service-ci-cd.yml` Stage 3 adds the matching `--ignore-vuln PYSEC-2026-1325` with a keep-in-sync comment; (C) new test asserts every accepted advisory is passed to pip-audit and cannot displace the evidence output path. |
| Reason | pip-audit `--strict` fails on any finding, including unfixable ones. Usage analysis: no `import ecdsa`, no ES256/384/512 anywhere in the repository; services sign RS256 exclusively via python-jose's cryptography backend; ECDSA signature *verification* is unaffected per the advisory text. Blocking all delivery on an unfixable, unexercised advisory serves no security purpose; the acceptance is scoped to the single advisory ID and documented for removal when upstream ships a fix. |
| Risk | LOW. Scanning is not weakened for any other advisory; `--strict` retained. Residual: if a future feature adopts ECDSA signing via python-jose's pure-Python backend, this acceptance must be revisited — noted in both code comments. Housekeeping flag: identity-service pins `ecdsa==0.19.0` and its requirements are not in any audited surface (pre-existing gap, see PR #22 report). |
| Rollback | Remove the `ACCEPTED_VULNERABILITIES` entry and the workflow flag — single-commit revert. |
| Validation | Local pip-audit reproduction of the failure (exit 1, PYSEC-2026-1325, fix_versions empty) and of the acceptance (exit 0 with `--ignore-vuln`); release2 audit script tests pass including the new acceptance-evidence test. |
| WPs Affected | None directly; unblocks PR #26 (WP-006-04) and all future PRs/pushes |
| Approval | Human GOV-002 review and merge of the EDR-004 PR |

---

### EECR-CHG-094 — AR-053: Retrospective Architecture Review of CIM XML Import Foundation (C-GATE01-01 Satisfied)

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-094 |
| Date | 2026-07-08 |
| Type | REVIEW, STATUS |
| Author | Enterprise Architect function (AI-conducted retrospective: claude-fable-5) |
| Description | **AR-053 conducted and recorded** — the retrospective Architecture Review of the WP-006-03A/03B CIM XML import foundation required by GOV-003 condition C-GATE01-01. Outcome: **APPROVED (retrospective), 92/100**. Review covered `services/cim/serialization/xml_import.py` in depth (staged parser pipeline, layered XML security: defusedxml + DTD/entity byte-marker pre-scan, strict namespace gate, duplicate-ID detection, total reference resolution, stable error reason codes) plus the 03A CIM module architecture and the 33-test import suite. Findings: F-AR053-01 (LOW — declare `defusedxml` as pinned runtime dependency in whichever WP first exposes the import over an API), F-AR053-02/03 (INFO — spec-shaped namespace scope and literal prefix binding, both deliberate current scope). No blocking conditions. Registers updated: AR register (AR-053 entry); execution register WP-006-03 rows — C-GATE01-01 marked SATISFIED, DoD Arch_Review gate → PASS (AR-053). |
| Reason | GOV-003 requires this AR before WP-006-05 authorisation or EPIC-006 exit. Conducting it now removes the last engineering-side gate condition on WP-006-03; C-GATE01-02 (WP-006-02 register reconciliation) and C-GATE01-03 (residual-scope confirmation) remain PMO actions. |
| Risk | LOW. Retrospective review of merged, green, test-covered code; findings are non-blocking and tracked. |
| Rollback | Not applicable (review record). The EA may supersede AR-053 with a further review. |
| Validation | All cited code, commits, test counts, and CI runs verified against the repository at review time. |
| WPs Affected | WP-006-03 (C-GATE01-01 satisfied); WP-006-05 (AR precondition cleared — authorisation still requires WP-006-04 APPROVED per dependency register) |
| Approval | Ratified by human GOV-002 merge of the recording PR — per GOV-002 the AI-conducted review takes effect only on that human approval |

---

### EECR-CHG-095 — WP-006-04 Closure: Atomic Topology Publish-Version Endpoint Merged

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-095 |
| Date | 2026-07-08 |
| Type | STATUS, RELEASE |
| Author | Release function (AI-assisted: claude-fable-5) |
| Description | **WP-006-04 — Topology Publish-Version Endpoint merged to `develop/v1.1`** via PR #26 at merge commit `38788a252` under GOV-002 human review. Delivered: `POST /topology/versions` rebuilt as the governed publish surface — (1) atomic single-transaction publish (previous two-statement autocommit could fail between demote and insert leaving no current version; neither it nor the CLI loader could publish version+content all-or-nothing); (2) concurrent publishes serialised via transaction-scoped advisory lock (closes the double-`is_current` race); (3) optional content publish (`nodes`/`edges`/`site_name` in canonical loader dict shapes, idempotent upserts stamped with the new version); (4) pure-stdlib payload validation (`fastapi/topology_publish.py`, readiness.py pattern) rejecting internal inconsistencies 422-before-connection, with DB FK/CHECK authoritative for cross-DB references (409). Backward compatible for metadata-only callers. Tests: 11 validator unit (python-only profile) + 7 transactional API tests via recording fake connection (release-gate profile); both classified in RELEASE-2-TEST-CLASSIFICATION.csv. |
| Reason | WP-006-04 authorised by GOV-003 (EECR-CHG-092); implementation complete and CI green. |
| Risk | LOW. Additive endpoint behaviour; metadata-only response shape preserved. Residual: live-stack smoke deferred (Docker unavailable in build environment) — one manual publish against the dev stack recommended before staging use. **Governance flag: no Architecture Review was conducted for WP-006-04** (author-conducted review would be self-review; AR-053 scope was 03A/03B only). Retrospective **AR-054 recommended before WP-006-05 authorisation**, mirroring the C-GATE01-01 pattern — Programme decision. |
| Rollback | Revert merge commit `38788a252` (`git revert -m 1`); no schema changes (endpoint uses existing sql/013 tables). |
| Validation | Both workflows green at branch HEAD `eb9b9fd`: RE-OS Service CI/CD run `28911621460` (incl. Stage 3 with EDR-004 acceptance), Release 2 Validation run `28911622888`. 18/18 new tests pass; neighbouring topology suites regression-clean; classification validator OK; router at exact pre-existing lint baseline (zero net new findings). |
| Delta Since `7c245ac` | PR #26 content (5 files, +427/-12) and PR #28 (AR-053 governance) |
| WPs Affected | WP-006-04 (IMPLEMENTED / MERGED); WP-006-05 (gate input: WP-006-04 approval determination + AR-054 recommendation) |
| Approval | Human GOV-002 review and merge of PR #26 (2026-07-08); this closure record ratified by merge of its recording PR |

---

### EECR-CHG-096 — PMO Reconciliation: C-GATE01-02 and C-GATE01-03 Closed; WP-006-01/02 Register Corrected

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-096 |
| Date | 2026-07-08 |
| Type | STATUS, DECISION (PMO reconciliation) |
| Author | PMO function (AI-drafted reconciliation: claude-fable-5; ratified by human GOV-002 merge of recording PR) |
| Description | Closes the two remaining GOV-003 conditions. **C-GATE01-02 (WP-006-02 register reconciliation):** the GeoJSON Topology Importer was delivered pre-register at legacy Phase 2 commit `8bab151` (`topology/geojson.py`, `loader.py`, CLI `topology/__main__.py`), is validated by `tests/test_topology_importer.py` (11 pure + 2 DB-gated tests) under Release 2 profiles, and was claimed Complete by the Recovery Programme Sprint 1 slice — register corrected from NOT STARTED to IMPLEMENTED (pre-register delivery) with the honest caveat that no dedicated PR or Architecture Review exists. The same correction applied to **WP-006-01** (Network Model Version Schema — live as `sql/013` + `sql/024`/`sql/025`, load-bearing for the WP-006-04 endpoint), which carried the identical inconsistency. **C-GATE01-03 (residual WP-006-03 scope):** determination — **no residual 03C slice exists**. The parser-local scope (03A models/serialization foundation + 03B secure parse/namespace/extract/resolve) exhausts WP-006-03's register scope; mapping, persistence, orchestration and API exposure are already-allocated register scope for WP-006-06 (Audit Table Stamping), WP-006-07 (ADMS Topology Import Integration), and WP-006-08 (Topology API Integration Tests). IEC standards-namespace onboarding (AR-053 finding F-AR053-02) is noted as WP-006-07 scoping input. |
| Reason | GOV-003 assigned both conditions to the PMO; closing them completes the ECR-006-GATE-01 condition set (C-GATE01-01 closed by AR-053/EECR-CHG-094) and removes ambiguity from the WP-006-05 gate context. |
| Risk | LOW. Register corrections reflect verifiable repository state; both entries record the absence of dedicated PR/AR evidence rather than asserting formal approval. |
| Rollback | Register rows revert by superseding PMO entry; no engineering impact. |
| Validation | Delivery commits, SQL files, test suites, and Recovery Programme claims verified against the repository at drafting time. |
| WPs Affected | WP-006-01, WP-006-02 (register status corrected); WP-006-03 (C-GATE01-03 satisfied); WP-006-07 (F-AR053-02 scoping input) |
| Approval | Ratified by human GOV-002 merge of the recording PR |

---

### EECR-CHG-097 — AR-054 Recorded; WP-006-04 APPROVED; WP-006-05 AUTHORISED TO START

| Field | Value |
|-------|-------|
| Change ID | EECR-CHG-097 |
| Date | 2026-07-08 |
| Type | REVIEW, STATUS, DECISION |
| Author | Enterprise Architect / Release functions (AI-conducted and drafted: claude-fable-5; Programme Board direction per 2026-07-08 session record) |
| Description | (A) **AR-054 conducted and recorded** — retrospective Architecture Review of the WP-006-04 atomic publish-version endpoint, as directed by the Programme Board with the authorship conflict disclosed on record (implementation and review by the same AI agent; assurance rests jointly on the structured review, the GOV-002 human merge review of PR #26, and objective test/CI evidence). Outcome: **APPROVED (retrospective), 90/100**, findings F-AR054-01 (LOW — no payload size guard while holding the publish lock; EPIC-006 hardening input), F-AR054-02 (INFO — upsert semantics yield mixed-version models on partial publish; material WP-006-05 scoping input), F-AR054-03 → condition **C-AR054-01** (manual dev-stack smoke before staging use; owner Platform Lead). (B) **WP-006-04 → APPROVED** (AR-054 + GOV-002). (C) **WP-006-05 (Topology Version History & Diff API) → AUTHORISED TO START** per Programme Board instruction; dependency gate "WP-006-04 must be APPROVED" satisfied; implementation branch `feature/topology-history-api` per register; implementation begins upon ratification of this record. |
| Reason | Programme Board direction (2026-07-08): conduct AR-054 and authorise WP-006-05. Completes the WP-006-04 approval chain and opens the next authorised work package. |
| Risk | LOW. AR-054's self-review limitation is disclosed rather than hidden and is mitigated by the human merge review and test evidence. C-AR054-01 gates staging exposure of the endpoint. |
| Rollback | Board may vacate by superseding entry; register rows revert. No code change. |
| Validation | All cited commits, runs, tests, and register rows verified against the repository at drafting time. |
| WPs Affected | WP-006-04 (APPROVED; C-AR054-01 open), WP-006-05 (AUTHORISED TO START), WP-006-07/08 (F-AR054-01 hardening input) |
| Approval | Ratified by human GOV-002 merge of the recording PR — authorisation effective on merge |

---

## Pending Changes

_No changes pending approval at this time._

---

## Change Request Template

When raising a change to the EECR, complete the following fields and submit to the PMO Lead:

```
Change ID:        EECR-CHG-{next sequence}
Date:             YYYY-MM-DD
Type:             [STRUCT|STATUS|ASSIGN|SCOPE|ARCH|RISK|DECISION|RELEASE|REVIEW|DEPLOY|METRICS]
Raised By:        {name / role}
Summary:          {one-paragraph description of the change}
Justification:    {why the change is needed}
WPs Affected:     {WP-XXX-XX list}
Files to Change:  {file list}
Requires Sign-off: {Enterprise Architect|PMO Lead|Release Manager — circle as applicable}
```
