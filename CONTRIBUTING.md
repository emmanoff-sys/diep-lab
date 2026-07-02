# Contributing to DAEP / RE-OS

**Repository:** `github.com/emmanoff-sys/diep-lab`
**Classification:** Internal — Confidential. Access restricted to authorised engineers within the DAEP / RE-OS programme.

---

## Before You Start

Every contribution must trace to an approved Work Package in the EECR. If you cannot identify a WP for your change, raise a Feature Request issue or contact the Platform Lead before starting work. Untracked changes will be rejected at review.

---

## Branch Naming

Follow LLD v2.0 §2.6 exactly. Branch names are checked during PR review.

| Pattern | Purpose | Example |
|---------|---------|---------|
| `feature/{WP-ID}-{kebab-slug}` | Work Package implementation | `feature/WP-001-04-repository-governance` |
| `fix/{WP-ID}-{kebab-slug}` | Bug fix | `fix/WP-003-01-null-pointer-auth` |
| `release/{version}` | Release preparation | `release/v1.1.0` |
| `hotfix/{WP-ID}-{kebab-slug}` | Production emergency fix | `hotfix/WP-005-03-jwt-expiry` |
| `infra/{description}` | Infrastructure / platform config | `infra/prometheus-alerting-rules` |

Never push directly to `main` or `develop`. Both branches are protected.

---

## Commit Message Convention

All commits follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/) (ADR-003):

```
<type>(<scope>): <short summary>

[optional body — wrap at 72 characters]

[optional footer — Co-Authored-By, Refs, Fixes]
```

| Type | When to use |
|------|------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation change only |
| `chore` | Tooling, config, governance (no production code change) |
| `refactor` | Code restructure with no behaviour change |
| `test` | Test additions or corrections |
| `ci` | CI/CD pipeline changes |
| `infra` | Infrastructure configuration |

**Scope** is the WP ID or affected area (e.g. `wp-001-04`, `fastapi`, `eecr`).

Examples:
```
feat(wp-003-01): add FastAPI service template with health endpoints
fix(wp-005-03): correct JWT expiry calculation for UTC midnight boundary
chore(eecr): record WP-001-04 commit hash in EECR-CHG-011
docs(wp-001-04): establish repository governance templates
```

---

## Commit Signing

### Why signing is required

LLD v2.0 §2.6 mandates signed commits on `main`. Signed commits provide cryptographic proof that a commit was created by the claimed author and has not been tampered with.

### Set up SSH signing (recommended)

SSH signing requires Git 2.34+ and a GitHub-registered SSH key.

```bash
# 1. Generate an SSH key if you don't have one
ssh-keygen -t ed25519 -C "your_email@example.com"

# 2. Add the public key to GitHub
#    GitHub → Settings → SSH and GPG keys → New SSH key → Key type: Signing Key

# 3. Configure Git to use SSH signing
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true

# 4. Verify
git log --show-signature -1
```

### Set up GPG signing (alternative)

```bash
# 1. Generate a GPG key (if you don't have one)
gpg --full-generate-key   # Choose RSA 4096, no expiry for long-lived keys

# 2. Export your public key and add it to GitHub
gpg --armor --export YOUR_KEY_ID
#    GitHub → Settings → SSH and GPG keys → New GPG key

# 3. Configure Git
git config --global user.signingkey YOUR_KEY_ID
git config --global commit.gpgsign true

# 4. Verify
git log --show-signature -1
```

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `error: gpg failed to sign the data` | Run `export GPG_TTY=$(tty)` and add to `.bashrc` / `.zshrc` |
| `signing key not available` | Confirm the key fingerprint matches `git config user.signingkey` |
| Push rejected: "unsigned commits" | Rebase and amend unsigned commits: `git rebase HEAD~N --exec 'git commit --amend --no-edit -S'` |

---

## Pull Request Workflow

1. **Branch** — create from `develop` (or `main` for hotfixes), following the naming table above.
2. **Implement** — follow the Work Package specification exactly. Raise an ECR issue if you encounter architectural ambiguity.
3. **Pre-commit** — run `pre-commit run --all-files` before pushing. The CI pipeline will run the same checks.
4. **Push** — push your branch and open a PR against `develop` (or `main` for releases/hotfixes).
5. **Fill the template** — complete every field in the PR template, especially Architecture Traceability.
6. **Review** — `develop` requires 1 approval; `main` requires 2. CODEOWNERS determines who must approve.
7. **EECR update** — add an EECR change record with your commit hash before requesting merge. The EECR is the audit trail; a PR without an EECR record will not be merged.
8. **Merge** — squash merge only. The Platform Lead or designated reviewer performs the merge.

---

## Code Review Expectations

**As an author:**
- Self-review your diff before requesting review.
- Respond to comments within one business day.
- Never force-push a branch under active review.

**As a reviewer:**
- Verify the PR traces to an approved WP.
- Check that the Architecture Traceability table is complete.
- Confirm the EECR change record exists before approving.
- Use GitHub's "Request changes" — do not merge with unresolved concerns.

---

## Architecture Governance

Per GOV-001 and GOV-002:

- No implementation may proceed without an approved Work Package.
- Architectural decisions may not be made or self-approved by AI agents.
- If an implementation gap requires an architectural decision, raise an [ECR issue](.github/ISSUE_TEMPLATE/ecr.md) and stop work until the Enterprise Architect resolves it.
- The EECR (`engineering/governance/EECR/`) is the single source of truth for all WP status, decisions, and change history.

---

## Pre-commit Hooks

Install the pre-commit hooks defined in `.pre-commit-config.yaml`:

```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

Hooks run automatically on `git commit`. To run manually across all files:

```bash
pre-commit run --all-files
```

---

## Questions and Support

- **Implementation questions:** Open a [Feature Request](.github/ISSUE_TEMPLATE/feature.md) or contact the Platform Lead.
- **Architectural ambiguity:** Open an [ECR](.github/ISSUE_TEMPLATE/ecr.md) — do not proceed without resolution.
- **Bug reports:** Open a [Bug Report](.github/ISSUE_TEMPLATE/bug.md).
- **Security issues:** See [SECURITY_GUIDE.md](SECURITY_GUIDE.md) for the responsible disclosure process.
