## Summary

<!-- Describe what this PR changes and why. One paragraph is sufficient for most PRs. -->

## Architecture Traceability

| Field | Value |
|-------|-------|
| Work Package | <!-- WP-XXX-XX (required) --> |
| Epic | <!-- EPIC-XXX --> |
| LLD Reference | <!-- §X.X — or "N/A: operational/docs change" --> |
| ADR Reference | <!-- ADR-XXX — or "N/A" --> |
| EECR Change Record | <!-- EECR-CHG-XXX (must exist before merge) --> |
| Branch Name | <!-- e.g. feature/WP-001-04-repository-governance --> |

## Changes

<!-- Bullet list of what changed and why each change was necessary. -->

-

## Testing

<!-- How was this tested? Reference WP §29 verification steps where applicable. -->

- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual verification performed against acceptance criteria in the WP

## Definition of Done

- [ ] Reviewed by at least 1 approver (`develop`); 2 approvers (`main`)
- [ ] Architecture Review complete if required — check EECR Architecture Review Register
- [ ] EECR updated with this commit hash before merge
- [ ] No placeholder text; no TODO items remain
- [ ] Documentation updated if observable behaviour changed
- [ ] Commits signed (mandatory for PRs targeting `main` — see [CONTRIBUTING.md](../CONTRIBUTING.md#commit-signing))
- [ ] Branch name follows LLD v2.0 §2.6 convention (table below)

## Branch Naming Reference

Per LLD v2.0 §2.6 and ADR-002:

| Pattern | Purpose |
|---------|---------|
| `feature/{WP-ID}-{kebab-slug}` | Feature or documentation work package |
| `fix/{WP-ID}-{kebab-slug}` | Bug fix |
| `release/{version}` | Release preparation |
| `hotfix/{WP-ID}-{kebab-slug}` | Production emergency fix |
| `infra/{description}` | Infrastructure / platform configuration change |

> `main`, `develop`, and `infra/*` branches have enforced branch protection rules.
> `feature/*`, `fix/*`, `release/*`, and `hotfix/*` are enforced by convention — see
> [docs/adr/branch-protection-config.md](docs/adr/branch-protection-config.md).
