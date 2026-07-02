# Infrastructure Branch Checks Configuration Record
### DAEP / RE-OS | `docs/adr/` | WP-003-11 | 2026-07-02

> This document is an audit record of the GitHub required-status-checks
> configuration for `infra/*` branches on `github.com/emmanoff-sys/diep-lab`.
> It exists because GitHub repository settings are not version-controlled
> files; this record makes the configuration auditable without GitHub UI
> access. Companion record to [`branch-protection-config.md`](branch-protection-config.md)
> (WP-001-04), which established the `infra/*` branch protection *rule*
> itself — this document supplies the concrete required-checks *list* that
> rule could only reference as future work.
>
> **Authoritative source:** LLD v2.0 §2.6 `infra/{description}` branch row.
> **Applied by:** Platform Lead via GitHub Settings UI / API.
> **Apply-by date:** Before any real `infra/*` PR is merged.

---

## Configuration Status

| Check | Workflow Job | Registered as Required | Date Applied | Applied By |
|-------|-------------|------------------------|--------------|------------|
| `ansible-lint` | `.github/workflows/infra-checks.yml` → `ansible-lint` | **Pending** — awaiting Architecture Review + human application | — | — |
| `terraform-plan` | `.github/workflows/infra-checks.yml` → `terraform-plan` | **Pending** — awaiting Architecture Review + human application | — | — |
| `security-scan` | `.github/workflows/infra-checks.yml` → `security-scan` | **Pending** — awaiting Architecture Review + human application | — | — |

**This implementation did not call the GitHub API to register these checks
as required.** Modifying live branch-protection settings for a shared
repository is a hard-to-reverse, shared-system change requiring explicit
human authorization — consistent with WP-001-04's own precedent (its
branch-protection settings were likewise left "Pending" for the Platform
Lead to apply). `gh` CLI is authenticated with real write access to this
org in the implementation environment, which makes the omission a
deliberate choice, not a tooling limitation.

Update this table when settings are applied. Record date and GitHub
username of the person who applied them.

---

## Required Settings — Per LLD v2.0 §2.6

`infra/{description}` branch row: **2 approvals; Ansible lint; Terraform
plan; security scan.**

| Setting | Required Value |
|---------|-----------------|
| Required approvals | **2** (already configured structurally by WP-001-04's general `infra/*` rule) |
| Required status checks | `ansible-lint`, `terraform-plan`, `security-scan` (this record) |
| Require branches up to date | Enabled (inherited from WP-001-04's general rule) |

## Timeout Budgets (WP-003-11 §24 — this WP's own reasonable addition)

No LLD-specified timing budget exists for these checks (unlike the
application CI stages' explicit `<N minutes` budgets). A **<10 minute
total** default is proposed: 5 minutes per job, three jobs in parallel.
Revisit if real Terraform plans grow large enough to exceed it in later
releases (§35).

## Test Plan (to be executed once checks are live)

1. PR with a deliberately broken Ansible playbook → `ansible-lint` fails,
   blocks merge.
2. PR with an invalid Terraform config → `terraform-plan` fails, blocks
   merge.
3. PR with a deliberately insecure Terraform resource (e.g., unencrypted
   volume) → `security-scan` (tfsec) fails, blocks merge.
4. A clean, valid infra PR passes all three and is mergeable (subject to
   the 2-approval requirement).

**Not executed by this implementation** — requires the checks to first be
registered as required (see Configuration Status above), which is itself a
Platform Lead action.

## Cross-Reference

See [`branch-protection-config.md`](branch-protection-config.md) (WP-001-04)
for the general branch-protection rule structure this record completes —
both documents should be read together for the full branch-protection
story (§39).
