# Versioning Policy — DAEP / RE-OS

## Authority
- LLD v2.0 §2.6 (`release/{version}` branch convention — "Release prep, bug fixes only", 2 approvals, full CI + security scan)
- Roadmap v1.0 Release Planning section (rollback procedures reference specific version identifiers)
- WP-001-10 Engineering Package

---

## 1. Versioning Scheme

DAEP / RE-OS adopts **Semantic Versioning 2.0.0** ([semver.org](https://semver.org)) for all services, shared libraries, and the platform release as a whole.

Format: `MAJOR.MINOR.PATCH`

| Segment | Triggers a Bump | DAEP / RE-OS Example |
|---------|----------------|----------------------|
| MAJOR | Breaking change — callers must change to remain compatible | Shared library API signature change; MQTT topic schema rename; IAM role contract break; REST API version deprecation |
| MINOR | New backward-compatible feature | New REST endpoint; new MQTT event type; new Grafana dashboard panel; new shared library function |
| PATCH | Backward-compatible bug fix | Null-pointer fix; error-message typo; dependency CVE patch (no API change) |

### 1.1 Pre-release Identifiers

Pre-release identifiers (e.g., `1.0.0-rc.1`, `1.1.0-beta.2`) may be applied on the `release/{version}` branch before the final merge to `main`. These identifiers are removed when the release is finalised.

### 1.2 Build Metadata

Build metadata suffixes (e.g., `+build.42`) are **not** included in git tags. Build provenance is tracked via CI run IDs and commit SHAs, not version strings.

---

## 2. Version Scope

| Artefact | Versioned? | Where the Version Lives |
|---------|-----------|------------------------|
| Platform release | Yes | `vMAJOR.MINOR.PATCH` git tag on `main`; `CHANGELOG.md` heading |
| Python service | Yes | `pyproject.toml [project].version` |
| Shared Python library (`libs/`) | Yes | `pyproject.toml [project].version`; published to artifact repository (WP-001-11) |
| Docker image | Yes | Tagged with the service version (EPIC-003 / WP-003-01) |
| React / Next.js app | Yes | `package.json "version"` |
| Flutter app | Yes | `pubspec.yaml version` |
| Database schema | Yes | Alembic revision ID (managed automatically; not bumped manually) |
| EECR governance document set | No | The EECR is versioned by WP sequence, not by semver |

---

## 3. Release Flow

The release flow follows LLD v2.0 §2.6:

```
develop/v1.1
    │
    │  (cut release branch when sprint scope is complete and all WPs are APPROVED)
    ▼
release/v1.0.0          ← bug fixes only; 2 approvals required; full CI + security scan
    │
    │  (squash merge to main after all checks pass)
    ▼
main ◄── git tag v1.0.0    (signed commit required — LLD v2.0 §2.6)
    │
    │  CHANGELOG.md updated; EECR Release Dashboard updated
    └── deploy to production
```

### 3.1 Step-by-Step Procedure

1. **Cut release branch.** `git checkout -b release/v1.0.0 develop/v1.1`
2. **Bump versions.** Update `version` in all relevant `pyproject.toml` and `package.json` files.
3. **Update CHANGELOG.md.** Promote `[Unreleased]` entries to a new version heading: `## [1.0.0] — YYYY-MM-DD`.
4. **Raise PR.** `release/v1.0.0` → `main`. Requires 2 approvals + full CI + security scan per LLD v2.0 §2.6.
5. **Squash merge.** After approval, squash-merge to `main`. Commit message: `release(v1.0.0): Release 1 — EPIC-001 through EPIC-00N complete`.
6. **Tag.** `git tag -s v1.0.0 -m "Release v1.0.0"` — signed commit required (GPG or SSH key, per WP-001-04 / LLD v2.0 §2.6).
7. **Push tag.** `git push origin v1.0.0`
8. **Record in EECR.** Update `engineering/governance/EECR/release-dashboard.md` and `release-history.md`.
9. **Deploy** from the tagged commit.

---

## 4. Git Tag Format

All release tags use the format: `vMAJOR.MINOR.PATCH`

| Example Tag | Meaning |
|-------------|---------|
| `v1.0.0` | Initial production release |
| `v1.1.0` | Minor feature release |
| `v1.0.1` | Patch / hotfix release |
| `v2.0.0` | Major breaking-change release |
| `v1.0.0-rc.1` | Release candidate (pre-release; not merged to `main` yet) |

Tags on `main` inherit the signed-commit requirement from WP-001-04 and LLD v2.0 §2.6. Unsigned tags on `main` are rejected by branch protection.

---

## 5. Changelog Maintenance

`CHANGELOG.md` at the repository root follows [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/).

### 5.1 Format

```markdown
## [Unreleased]
### Added
- Short description of the addition (WP reference in parentheses).
### Changed
- ...
### Fixed
- ...
### Removed
- ...
### Security
- ...

## [1.0.0] — 2026-MM-DD
### Added
- ...
```

### 5.2 Release 1 Process

For Release 1, changelog entries are maintained **manually**:
- One engineer maintains the `[Unreleased]` section, adding a line per completed Work Package.
- At release time, `[Unreleased]` is renamed to the release heading (e.g., `## [1.0.0] — 2026-MM-DD`) and a new empty `[Unreleased]` section is opened above it.

### 5.3 Future Automation

Automated changelog generation from Conventional Commits parsing (e.g., via `git-cliff` or `conventional-changelog`) is a Release 2 candidate. It is not scoped into Release 1 to avoid introducing a new commit-parsing dependency mid-foundation-build, which could retroactively impose constraints on commit message format across WPs already merged.

---

## 6. Rollback Procedure

If a production deployment must be rolled back:

1. **Identify** the last stable version from `CHANGELOG.md` (e.g., `v1.0.0`).
2. **Roll back** the deployment to the `v1.0.0` image/artifact tag (procedure specific to the deployment target — see WP-002 operational runbooks).
3. **Preserve the broken tag** in git — do not delete it. Add a note in `CHANGELOG.md` documenting the regression.
4. **Cut a hotfix branch** from the previous stable tag: `git checkout -b release/v1.0.1 v1.0.0`.
5. **Apply fix, release as PATCH** (`v1.0.1`) following §3.1.

---

## 7. Traceability

| Artefact | Reference |
|----------|-----------|
| LLD v2.0 §2.6 | `release/{version}` branch, 2-approval rule, squash merge to `main`, signed commits |
| Roadmap v1.0 §Release Planning | Rollback procedures reference specific version identifiers |
| WP-001-04 | Repository Governance (branch protection, commit signing requirement) |
| WP-001-08 | Dependency Policy (CVE patch → PATCH version bump) |
| WP-001-09 | Build Framework (wheel tagged with service version) |
| WP-001-10 | This document |
| WP-001-11 | Artifact Repository (version-tagged wheel publish) |
| WP-004-13 | CI release automation (future — EPIC-004) |
