# Secrets Scanning — DAEP / RE-OS

**Authority:** WP-004-09 | HLD v2.0 ADR-008 ("Vault for all secrets management. No secrets stored in environment variables or [...] without Vault integration") | Security Review Checklist ("no secret committed to git history")

## 1. Purpose

Automated secrets scanning enforces HLD ADR-008's "no unmanaged secrets"
principle as a preventive CI control — catching a committed credential before
it reaches `main` rather than relying on human code review vigilance alone.
Complements WP-003-11's infra-specific `tfsec`/`checkov` by covering
application code too.

## 2. Tool

**Gitleaks** (`gitleaks-action@v2`) — pattern-based detection against the PR
diff and full git history. Configured via `.gitleaks.toml` (extends all
default rules + RE-OS-specific Vault-path pattern).

Note: Gitleaks requires a `GITLEAKS_LICENSE` secret for private/org repos.
A free tier supports up to 1 committer (confirm the correct tier for this
org — Project Owner action).

## 3. Exception Process

Exceptions to the `.gitleaks.toml` allowlist require a justification comment.
The same no-blanket-suppression discipline as `.trivyignore` (WP-003-04) and
Bandit suppression policy (WP-001-07) applies here.

EPIC-003 `PLACEHOLDER-*` sentinel values are already allowlisted with path
scope — no additional entries needed for those.

## 4. Incident Response (True Positive)

A true positive (a real secret actually committed) must be treated as a
security incident:

1. **Rotate the credential immediately** — assume it is compromised from the
   moment it was pushed, even if the PR was never merged.
2. Rewrite git history (e.g., `git filter-repo`) or use GitHub's secret-
   scanning advisory for secret-scanning-supported token types.
3. File an incident report documenting what was committed, when, and the
   rotation action taken.
4. Review and close the gap that allowed the commit (pre-commit hook bypass?
   developer not running hooks? New secret type not covered by rules?).

The CI scan cannot retroactively prevent a secret that was already pushed —
it only blocks future merges.

## 5. One-Time Full-History Baseline Scan

```bash
# Run once before Release 1 closes (WP-004-09 §15, §33 AC):
gitleaks detect --source . -c .gitleaks.toml --log-level info
```

The result (clean/count-of-findings) belongs in the release exit criteria.

**Status in this repository:** not yet executed — requires Gitleaks binary
and a developer workstation. **Runtime PASS Deferred.**

## 6. Traceability

| Requirement | Source |
|-------------|--------|
| No unmanaged secrets principle | HLD v2.0 ADR-008 |
| Git history clean gate | Security Review Checklist |
| Vault as the sanctioned alternative | WP-003-13 |
