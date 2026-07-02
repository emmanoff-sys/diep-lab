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
| Commit | *(recorded at closing commit of `feature/ecr-002-06-01-ui-message-specification`)* |
| Files Changed | `docs/architecture/UI_MESSAGE_SPEC.md` (new), `libs/reos-error-handling-ts/src/messages.ts` (modified — copy only), `libs/reos_error_handling/lib/map_error.dart` (modified — copy only), `libs/reos-error-handling-ts/tests/mapError.test.ts` (modified), `libs/reos_error_handling/test/map_error_test.dart` (modified), `libs/reos-error-handling-ts/README.md` (modified), `libs/reos_error_handling/README.md` (modified), `libs/README.md` (modified) |
| Approval | Enterprise Architect + UI/UX Design owner — Architecture Review for ECR closure pending; WP-002-06's own Architecture Review (from EECR-CHG-029) remains separately pending |

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
