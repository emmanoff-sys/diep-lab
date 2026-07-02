# Branch Protection Configuration Record
### DAEP / RE-OS | `docs/adr/` | WP-001-04 | 2026-07-02

> This document is an audit record of the GitHub branch protection settings applied to
> `github.com/emmanoff-sys/diep-lab`. It exists because GitHub repository settings are
> not version-controlled files; this record makes the configuration auditable without
> GitHub UI access.
>
> **Authoritative source:** LLD v2.0 §2.6 Git Branching Strategy.
> **Applied by:** Platform Lead via GitHub Settings UI / API.
> **Apply-by date:** Before WP-001-05 commences (EPIC-001 completion gate).

---

## Configuration Status

| Branch Pattern | Protection Applied | Date Applied | Applied By |
|---------------|-------------------|--------------|------------|
| `main` | Pending — awaiting AR-004 approval + human application | — | — |
| `develop` | Pending — awaiting AR-004 approval + human application | — | — |
| `infra/*` | Pending — awaiting AR-004 approval + human application | — | — |

> Update this table when settings are applied. Record date and GitHub username of the person
> who applied the settings.

---

## Required Settings — Per LLD v2.0 §2.6

### `main` Branch

| Setting | Required Value |
|---------|---------------|
| Allow direct push | **Disabled** — no engineer may push directly to `main` |
| Merge strategy | **Squash merge only** — linear history maintained |
| Required approvals | **2** — both approvers must have write access |
| Dismiss stale reviews | **Enabled** — approval re-required after new commits |
| Require review from code owners | **Enabled** — CODEOWNERS file governs who must approve |
| Required status checks | **All CI checks must pass** — check names added as EPIC-004 creates them; this requirement stands before EPIC-004 lands, enforced with zero required checks initially |
| Require branches to be up-to-date | **Enabled** — branch must be current before merge |
| Require signed commits | **Enabled** — GPG or SSH commit signing mandatory (see [CONTRIBUTING.md](../../CONTRIBUTING.md#commit-signing)) |
| Allow force push | **Disabled** |
| Allow deletions | **Disabled** |
| Include administrators | **Enabled** — protection applies to all, including repo admins |

### `develop` Branch

| Setting | Required Value |
|---------|---------------|
| Allow direct push | **Disabled** |
| Merge strategy | **Squash merge only** |
| Required approvals | **1** |
| Dismiss stale reviews | **Enabled** |
| Require review from code owners | **Enabled** |
| Required status checks | **All CI checks must pass** (populated as EPIC-004 delivers check names) |
| Require branches to be up-to-date | **Enabled** |
| Require signed commits | **Disabled** (recommended but not mandatory for `develop`) |
| Allow force push | **Disabled** |
| Allow deletions | **Disabled** |
| Include administrators | **Enabled** |

### `infra/*` Branch Pattern

| Setting | Required Value |
|---------|---------------|
| Allow direct push | **Disabled** |
| Merge strategy | **Squash merge only** |
| Required approvals | **2** |
| Dismiss stale reviews | **Enabled** |
| Require review from code owners | **Enabled** (`/infra/` CODEOWNERS rule: `@RE-OS/infra-engineers`) |
| Required status checks | **Ansible lint + Terraform plan + security scan** (check names TBD when EPIC-004 creates the workflows; recorded here as intent) |
| Require branches to be up-to-date | **Enabled** |
| Require signed commits | **Disabled** |
| Allow force push | **Disabled** |
| Allow deletions | **Disabled** |
| Include administrators | **Enabled** |

---

## Branch Naming Conventions (Not GitHub-Enforced)

Per LLD v2.0 §2.6: the following branch types are convention, not platform-enforced,
because GitHub branch protection does not support wildcards on ephemeral branches
at the granularity required. Compliance is maintained via the PR template and CODEOWNERS review.

| Pattern | Purpose | Merge Target |
|---------|---------|-------------|
| `feature/{WP-ID}-{kebab-slug}` | Work Package implementation | `develop` |
| `fix/{WP-ID}-{kebab-slug}` | Bug fix | `develop` |
| `release/{version}` | Release preparation | `main` then back-merged to `develop` |
| `hotfix/{WP-ID}-{kebab-slug}` | Production emergency fix | `main` then back-merged to `develop` |
| `infra/{description}` | Infrastructure / platform config | `develop` |

---

## Verification Procedure

After settings are applied, verify via GitHub API:

```bash
# Verify main branch protection
gh api repos/emmanoff-sys/diep-lab/branches/main/protection

# Verify develop branch protection
gh api repos/emmanoff-sys/diep-lab/branches/develop/protection

# Verify direct-push rejection (should return HTTP 403)
git push origin HEAD:main
```

Expected outcomes per WP-001-04 §33 acceptance criteria:
- `git push origin HEAD:main` → rejected (403 / remote: Push rejected)
- PR to `main` with 1 approval → merge button disabled
- PR template renders with Architecture Traceability table

---

## Post-EPIC-004 Update Requirement

Per WP-001-04 §39: when EPIC-004 creates GitHub Actions workflows, the Platform Lead must
add each workflow check name to the "Required status checks" list for `main`, `develop`,
and `infra/*`. Update this document's Configuration Status table at that time.

---

## References

- LLD v2.0 §2.6 — Git Branching Strategy (authoritative source for all settings above)
- ADR-002 — Git Branch Strategy ([`../../engineering/governance/EECR/decision-log.md`](../../engineering/governance/EECR/decision-log.md))
- ADR-004 — CODEOWNERS and Branch Protection ([`../../engineering/governance/EECR/decision-log.md`](../../engineering/governance/EECR/decision-log.md))
- [`../../CODEOWNERS`](../../CODEOWNERS) — code owner assignments per branch/path pattern
- [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) — commit signing setup for engineers

---

*Configuration record — WP-001-04 | Settings to be applied by Platform Lead | Last updated: 2026-07-02*
