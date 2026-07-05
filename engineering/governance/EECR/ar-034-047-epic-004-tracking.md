# Architecture Review Tracking Package — AR-034 through AR-047
### EPIC-004 — CI/CD, DevSecOps & Release Automation
### Prepared: 2026-07-03 | Status: PENDING ENTERPRISE ARCHITECT REVIEW

> **Purpose:** This package briefs the Enterprise Architect for each of the 14 outstanding
> Architecture Reviews covering EPIC-004's Work Packages WP-004-01 through WP-004-14.
> All implementation is complete and merged to `develop/v1.1` (merge commit `41ad963`).
> No implementation changes may result from these reviews — they are governance gates only.
>
> **Review authority:** Enterprise Architect (with DevSecOps Lead co-review on security items).
>
> **Outcome required per WP:** APPROVED / APPROVED WITH CONDITIONS / CHANGES REQUIRED / REJECTED
> using the rubric in `architecture-review-register.md` (threshold: ≥90/100 for APPROVED).

---

## Numbering Discrepancy — Noted for EA

The original `architecture-review-register.md` pre-assigned AR-034..047 to WP-005-03..WP-006-08
as planning placeholders. EECR-CHG-049..051 (written at EPIC-004 implementation time) re-assigned
those same IDs to WP-004-01..14. This tracking package follows the EECR implementation records
as authoritative. The AR register has been corrected accordingly (EECR-CHG-057). The displaced
WP-005/006 pre-planned entries are superseded by the current EPIC-005 AR sequence (AR-048+).

---

## Review Matrix

| AR ID | WP | Title | Commit | CI/CD Feature | EA Priority |
|-------|----|-------|--------|---------------|-------------|
| AR-034 | WP-004-01 | Stage 1 Lint & Type Check | `fbfebe6` | CI Pipeline | Standard |
| AR-035 | WP-004-02 | Stage 2 SAST Security | `116ba8e` | CI Pipeline | **Security** |
| AR-036 | WP-004-03 | Stage 3 Dependency Scanning | `a1394d6` | CI Pipeline | **Security** |
| AR-037 | WP-004-04 | Stage 4 Unit & Component Tests | `e605511` | CI Pipeline | Standard |
| AR-038 | WP-004-05 | Stage 5 Container Build | `47bc086` | CI Pipeline | Standard |
| AR-039 | WP-004-06 | Stage 6 Container Image Scanning | `022b7d5` | Security Pipeline | **Security** |
| AR-040 | WP-004-07 | Stage 7 Registry Push | `8156e36` | CI Pipeline | Standard |
| AR-041 | WP-004-08 | Stage 11 DAST | `5bb56db` | Security Pipeline | **Security** |
| AR-042 | WP-004-09 | Policy as Code / Secrets Scanning | `c809815` | Security Pipeline | **Security** |
| AR-043 | WP-004-10 | Stage 8 Integration Tests | `1c7893c` | CI Pipeline | Standard |
| AR-044 | WP-004-11 | Stage 9 Staging Deployment | `267c9b5` | Release Automation | **High** |
| AR-045 | WP-004-12 | Stage 10 Load Testing | `0817def` | Release Automation | Standard |
| AR-046 | WP-004-13 | Stage 12 Production Deploy & Rollback | `fd09d56` | Release Automation | **Highest** |
| AR-047 | WP-004-14 | DORA Metrics & Pipeline Observability | `d9a7bce` | Release Automation | Standard |

---

## AR-034 — WP-004-01: Stage 1 Lint & Type Check

| Field | Value |
|-------|-------|
| Review ID | AR-034 |
| Work Package | WP-004-01 |
| WP Title | CI Pipeline — Stage 1 Lint & Type Check |
| Implementation Commit | `fbfebe6` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (lint job) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 1; LLD v2.0 Ch. 18 `lint` job |

**Scope implemented:**
- `lint` job on `ubuntu-22.04`; trigger: PR to `main`/`develop` + push to `main`/`develop`/`feature/**`/`fix/**`/`release/**`
- Tools: `ruff check . --output-format github`, `black --check --diff .`, `isort --check-only .`, `mypy src/ --strict`
- Python 3.11 pinned (LLD Ch. 18 exact)
- Registered as required status check

**EA focus areas:**
- Confirm trigger branch pattern matches LLD v2.0 Ch. 18 exactly
- Confirm mypy `--strict` flag present (not a weaker `--check`)
- Confirm Python 3.11 pin is compatible with WP-001-05's Python 3.10+ minimum

**Open items requiring EA decision:** None — standard implementation.

---

## AR-035 — WP-004-02: Stage 2 SAST Security

| Field | Value |
|-------|-------|
| Review ID | AR-035 |
| Work Package | WP-004-02 |
| WP Title | CI Pipeline — Stage 2 SAST Security |
| Implementation Commit | `116ba8e` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (security/SAST job) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 2; LLD v2.0 Ch. 18 `security` job (Bandit + CodeQL steps) |
| DevSecOps Co-Review | Required |

**Scope implemented:**
- `security` job (SAST portion): Bandit `bandit -r src/ -ll -ii --format json -o bandit.json`
- CodeQL: `github/codeql-action/analyze@v3` with `languages: python`
- HIGH-severity findings block the job

**Open flag requiring Project Owner / EA decision:**
> **FLAG:** CodeQL requires **GitHub Advanced Security** (GHAS) which may not be available on
> the repository's current GitHub tier. If GHAS is unavailable, CodeQL steps will silently
> fail or skip. EA must confirm GHAS availability before approving AR-035.
> If unavailable: raise a new ECR to fall back to Bandit-only; do **not** silently mark
> AR-035 APPROVED with a hidden inactive CodeQL step.

**EA focus areas:**
- Confirm GHAS availability with Project Owner (item above)
- Confirm Bandit flags `-ll -ii` match LLD exactly (medium+ severity, medium+ confidence)
- Confirm HIGH+ blocking policy is enforced (exit code from Bandit check)

---

## AR-036 — WP-004-03: Stage 3 Dependency Scanning

| Field | Value |
|-------|-------|
| Review ID | AR-036 |
| Work Package | WP-004-03 |
| WP Title | CI Pipeline — Stage 3 Dependency Scanning |
| Implementation Commit | `a1394d6` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (dependency scan); `npm-audit-config.md` |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 3; LLD v2.0 Ch. 18 `security` job (`pip-audit` step); WP-001-08 `DEPENDENCY_POLICY.md` |
| DevSecOps Co-Review | Required |

**Scope implemented:**
- `pip-audit --strict -r requirements.txt` (LLD literal; `--strict` = zero-tolerance CVE policy)
- npm audit: documented-but-dormant (no frontend app scaffold exists yet); activation plan in `npm-audit-config.md`
- Zero-CVE policy hard-blocks PR merge

**Open flag requiring EA awareness:**
> **FLAG:** npm audit is documented but not yet active (no real frontend scaffold in Release 1).
> EA should confirm this documented-but-dormant approach satisfies the Roadmap's Stage 3
> "No known CVEs; PR blocked" policy for the current release scope, and that activation
> is tracked in `npm-audit-config.md` with an explicit TODO.

**EA focus areas:**
- Confirm `--strict` flag present and aligned with `DEPENDENCY_POLICY.md`
- Confirm npm-audit activation plan is documented and not just omitted

---

## AR-037 — WP-004-04: Stage 4 Unit & Component Tests

| Field | Value |
|-------|-------|
| Review ID | AR-037 |
| Work Package | WP-004-04 |
| WP Title | CI Pipeline — Stage 4 Unit & Component Tests |
| Implementation Commit | `e605511` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (test-unit job) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 4; LLD v2.0 Ch. 18 `test-unit` job; LLD v2.0 §2.7 (80% coverage) |

**Scope implemented:**
- `test-unit` job: `needs: [lint]`; pytest `--cov=src --cov-fail-under=80 --cov-report=xml --junit-xml=results.xml`
- `codecov/codecov-action@v4` for coverage reporting
- Codecov token stored as GitHub Actions secret (not hardcoded)

**EA focus areas:**
- Confirm `needs: [lint]` dependency ordering matches LLD Ch. 18 (tests only run after lint passes)
- Confirm `--cov-fail-under=80` present (LLD §2.7 target)
- Confirm Codecov token is in secrets (Security posture)

**Open items requiring EA decision:** None.

---

## AR-038 — WP-004-05: Stage 5 Container Build

| Field | Value |
|-------|-------|
| Review ID | AR-038 |
| Work Package | WP-004-05 |
| WP Title | CI Pipeline — Stage 5 Container Build |
| Implementation Commit | `47bc086` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (build job — build step) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 5; LLD v2.0 Ch. 18 `build` job (Docker build step) |

**Scope implemented:**
- `build` job: `needs: [test-unit, security]`
- `docker build --target production --build-arg GIT_SHA=${{ github.sha }} -t $REGISTRY/$SERVICE:${{ github.sha }} .`
- `--target production` selects multi-stage production layer (WP-003-01 Dockerfile)
- `GIT_SHA` baked in for image provenance

**EA focus areas:**
- Confirm `needs: [test-unit, security]` ordering is correct (both gates must pass before build)
- Confirm `--target production` flag and tag format match LLD Ch. 18 exactly
- Confirm `$REGISTRY` resolves to WP-003-03's internal registry

**Open items requiring EA decision:** None.

---

## AR-039 — WP-004-06: Stage 6 Container Image Scanning

| Field | Value |
|-------|-------|
| Review ID | AR-039 |
| Work Package | WP-004-06 |
| WP Title | Security Pipeline — Stage 6 Container Image Scanning |
| Implementation Commit | `022b7d5` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (Trivy step within build job); `.trivyignore` (WP-003-04) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 6; LLD v2.0 Ch. 18 `build` job (Trivy step); WP-003-04 `CONTAINER_SECURITY.md` |
| DevSecOps Co-Review | Required |

**Scope implemented:**
- `aquasecurity/trivy-action@master`; `severity: 'CRITICAL,HIGH'`; `exit-code: '1'`
- Positioned between Docker build and registry push (sequential steps, push only reached if scan passes)
- `.trivyignore` from WP-003-04 respected

**Design decision requiring EA awareness:**
> **FLAG:** The Roadmap's Stage 6 policy text says "No CRITICAL; Image not pushed."
> The LLD's actual `trivy-action` config uses `severity: 'CRITICAL,HIGH'` — blocking on
> HIGH as well. Implementation follows the LLD (stricter superset). EA should confirm
> that blocking on HIGH+CRITICAL (not CRITICAL alone) is the intended policy. If
> Roadmap-literal-only is desired, raise an ECR to relax to CRITICAL-only.

**EA focus areas:**
- Confirm CRITICAL+HIGH policy is intentional (not an inadvertent scope expansion)
- Confirm step sequencing (scan before push — push never reached on scan failure)
- Confirm `.trivyignore` exception process is documented and entries are justified

---

## AR-040 — WP-004-07: Stage 7 Registry Push

| Field | Value |
|-------|-------|
| Review ID | AR-040 |
| Work Package | WP-004-07 |
| WP Title | CI Pipeline — Stage 7 Registry Push |
| Implementation Commit | `8156e36` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (push step + notification step, within build job) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 7; LLD v2.0 Ch. 18 `build` job (final push step) |

**Scope implemented:**
- `docker login` step (credentials from GitHub Actions secret)
- `docker push $REGISTRY/$SERVICE:${{ github.sha }}` (only reached after scan passes)
- Conditional notification step via `NOTIFY_WEBHOOK_URL` env var (secrets-in-if-condition bug fixed)

**Open flag requiring Project Owner decision:**
> **FLAG:** Notification channel/webhook is not confirmed. The workflow reads from
> `NOTIFY_WEBHOOK_URL` secret — if the secret is empty/unset, the notification step
> is a no-op. Project Owner must confirm the notification target (Slack, email, etc.)
> and provision the `NOTIFY_WEBHOOK_URL` secret. Until confirmed, the Roadmap's
> "Notification" policy item is partially unmet.

**EA focus areas:**
- Confirm push credentials use GitHub Actions secrets (not hardcoded)
- Confirm notification mechanism and flag outstanding Project Owner action if not yet confirmed

---

## AR-041 — WP-004-08: Stage 11 DAST

| Field | Value |
|-------|-------|
| Review ID | AR-041 |
| Work Package | WP-004-08 |
| WP Title | Security Pipeline — Stage 11 DAST |
| Implementation Commit | `5bb56db` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/dast-scan.yml` (separate, manually-triggered workflow); `DAST_STANDARDS.md` |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 11 |
| DevSecOps Co-Review | Required |

**Scope implemented:**
- Separate `dast-scan.yml` workflow (`workflow_dispatch`, not part of main pipeline)
- `zaproxy/action-full-scan@v0.10.0` — active scan, not baseline/passive
- Target locked to Staging only (locked choice input — Production not selectable)
- `fail_action: true` (No High policy)
- 70-minute job timeout (Roadmap budget: <60 min; timeout is the guard, not the expected runtime)

**Design note:**
> The LLD's captured Ch. 18 excerpt does not include a DAST job. This WP is built
> primarily from Roadmap §11.1 Stage 11. EA should verify against the full LLD document
> (beyond the captured excerpt) whether any additional DAST configuration constraints apply.

**EA focus areas:**
- Confirm `workflow_dispatch` manual trigger (Roadmap: "Manual")
- Confirm Staging-only safeguard (Production never targeted)
- Confirm `fail_action: true` enforces "No High; Release blocked" policy
- Confirm `zaproxy/action-full-scan` constitutes "full site scan" per Roadmap §11.1

---

## AR-042 — WP-004-09: Policy as Code / Secrets Scanning

| Field | Value |
|-------|-------|
| Review ID | AR-042 |
| Work Package | WP-004-09 |
| WP Title | Security Pipeline — Policy as Code / Secrets Scanning |
| Implementation Commit | `c809815` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.gitleaks.toml`; `.github/workflows/service-ci-cd.yml` (secrets-scan job); `SECRETS_SCANNING.md` |
| Architecture Sources | HLD v2.0 ADR-008; `review-checklists.md` Security Review Checklist |
| DevSecOps Co-Review | Required |

**Scope implemented:**
- Gitleaks pattern-based secrets scanning on every PR diff
- Custom rule: RE-OS Vault-path pattern (`secret/reos/` namespace — should never appear as literal in code)
- `EPIC-003 PLACEHOLDER` tokens path-scoped allowlisted (not a blanket suppression)
- `SECRETS_SCANNING.md` with incident-response procedure and one-time baseline scan command

**Open flag requiring Project Owner decision:**
> **FLAG:** Gitleaks licence tier must be confirmed by Project Owner. Gitleaks has
> a commercial licence for certain use cases. Confirm that the chosen tier is compatible
> with this repository's usage before marking AR-042 APPROVED.

**Open action (Platform Lead, before Release 1 close-out):**
> The one-time full-history baseline scan (`gitleaks detect --source=. --log-opts="HEAD"`)
> has been documented but not yet executed. This is a Release 1 exit criterion per
> `release-exit-criteria.md`. Result must be recorded in `SECRETS_SCANNING.md` before
> AR-042 can be fully closed.

**EA focus areas:**
- Confirm Gitleaks licence tier (Project Owner action)
- Confirm Vault-path pattern covers ADR-008's "no unmanaged secrets" principle
- Confirm baseline scan has been executed and result is clean before approving

---

## AR-043 — WP-004-10: Stage 8 Integration Tests

| Field | Value |
|-------|-------|
| Review ID | AR-043 |
| Work Package | WP-004-10 |
| WP Title | CI Pipeline — Stage 8 Integration Tests |
| Implementation Commit | `1c7893c` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (test-integration job) |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 8; LLD v2.0 Ch. 18 `test-integration` job |

**Scope implemented:**
- `test-integration` job: `needs: [build]`; trigger: `develop`/`main` only
- GitHub Actions service containers: `postgres:16` + `redis:7-alpine`
- `pytest tests/integration/ -v --junit-xml=int-results.xml`
- Connection strings injected as job-level environment variables

**Design discrepancy for EA review:**
> LLD §2.7 (Testing Standards table) describes integration tests at PR-time;
> Roadmap §11.1 Stage 8 places them at develop-merge-time. Implementation follows
> the Roadmap as the more specific, pipeline-stage-level source. EA should confirm
> this interpretation is acceptable, or raise an ECR if PR-time integration tests
> are required by policy.

**EA focus areas:**
- Confirm `needs: [build]` ordering (integration only runs after build/scan/push succeeds)
- Confirm PR-time vs merge-time trigger is acceptable (discrepancy noted above)
- Confirm test-only credentials (`POSTGRES_PASSWORD: test`) are scoped to ephemeral containers only

---

## AR-044 — WP-004-11: Stage 9 Staging Deployment

| Field | Value |
|-------|-------|
| Review ID | AR-044 |
| Work Package | WP-004-11 |
| WP Title | Release Automation — Stage 9 Staging Deployment |
| Implementation Commit | `267c9b5` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (deploy-staging job); `infra/playbooks/deploy-rolling.yml`; `infra/environments/staging/inventory.yml` |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 9; LLD v2.0 Ch. 18 `deploy-staging` job; LLD v2.0 §18.2 (`deploy-rolling.yml` 7-step playbook) |

**Scope implemented:**
- `deploy-staging` job: `needs: [test-integration]`; `if: github.ref == 'refs/heads/develop'`; `environment: staging`
- `deploy-rolling.yml`: serial=1, max_fail_percentage=0; 7 steps per LLD §18.2:
  [1] drain VM from Nginx upstream; [2] wait 30s; [3] pull image; [4] alembic upgrade head (first VM only);
  [5] restart systemd unit; [6] health check poll (retries=24, delay=5); [7] re-enable upstream
- Deployment credentials from `staging` GitHub Environment secrets

**Open flag requiring Project Owner decision:**
> **FLAG:** Staging VMs may not yet be provisioned. WP-003-14 in its Release 1 scope
> provisioned Local Dev/Shared Dev/Integration only. WP-004-11 extends that scope to
> Staging. Project Owner must confirm Staging environment is provisioned (real VMs
> reachable by the Ansible inventory) before the deploy-staging job can be exercised.
> Until confirmed, this is an unvalidated mechanism — workflow YAML is correct but
> untested against a live Staging target.

**EA focus areas:**
- Confirm 7-step playbook matches LLD §18.2 exactly (steps, delegate_to for Nginx mgmt)
- Confirm `max_fail_percentage: 0` + `serial: 1` is the documented "automatic rollback" mechanism
- Confirm Staging provisioning status with Project Owner before APPROVED

---

## AR-045 — WP-004-12: Stage 10 Load Testing

| Field | Value |
|-------|-------|
| Review ID | AR-045 |
| Work Package | WP-004-12 |
| WP Title | Release Automation — Stage 10 Load Testing |
| Implementation Commit | `0817def` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/load-test.yml`; `loadtest/scaffold-load-test.js`; `LOAD_TESTING.md` |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 10 |

**Scope implemented:**
- k6 ramping-arrival-rate to 1,000 RPS; threshold: `http_req_duration['p(95)<500']`; `abortOnFail: false` (Alert+review, not hard block — per Roadmap "Alert + review" policy)
- `load-test.yml`: weekly cron `0 2 * * 1` (Monday 2am UTC) + `workflow_dispatch`
- Staging-only target safeguard documented in `LOAD_TESTING.md`

**EA focus areas:**
- Confirm `abortOnFail: false` correctly implements Roadmap's "Alert + review" (not hard-block) policy
- Confirm 1,000 RPS target and P95 ≤ 500ms threshold match Roadmap §11.1 Stage 10 exactly
- Confirm notification fires on threshold breach (same `NOTIFY_WEBHOOK_URL` as WP-004-07)
- Note: `/health` endpoint only — not representative of future business-endpoint load; flagged in WP spec

---

## AR-046 — WP-004-13: Stage 12 Production Deployment & Rollback

| Field | Value |
|-------|-------|
| Review ID | AR-046 |
| Work Package | WP-004-13 |
| WP Title | Release Automation — Stage 12 Production Deployment & Rollback |
| Implementation Commit | `fd09d56` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `.github/workflows/service-ci-cd.yml` (deploy-production job); `ROLLBACK_PROCEDURE.md`; `infra/environments/production/inventory.yml` |
| Architecture Sources | Roadmap v1.0 §11.1 Stage 12; Roadmap Production Stability metric (15-min rollback); LLD v2.0 Ch. 18 `deploy-production` job; LLD v2.0 §18.2 |
| **Review Priority** | **HIGHEST — production deployment controls** |
| DevSecOps Co-Review | Required |
| Security Co-Review | Required |
| Ops Co-Review | Required |

**Scope implemented:**
- `deploy-production` job: `needs: [deploy-staging]`; `if: github.ref == 'refs/heads/main'`; `environment: production` (GitHub manual-approval gate)
- Reuses same `deploy-rolling.yml` playbook as WP-004-11, targeting production inventory
- `ROLLBACK_PROCEDURE.md`: copy-paste executable, targets 15-minute MTTR

**Critical EA review items:**
1. **Manual approval gate** — Confirm `environment: production` with required reviewer configured in GitHub. The human-approval requirement is a hard governance control (GOV-002: "AI agents cannot self-approve or self-merge"). Verify the environment is correctly configured in the GitHub repository settings with a named required approver.
2. **`needs: [deploy-staging]`** — Confirm production deploy is unreachable until Staging succeeds. Also confirm Stage 11 DAST (AR-041) is a documented gate before production promotion, even if not technically enforced as a GitHub Actions `needs:` dependency (DAST is manual-trigger).
3. **ROLLBACK_PROCEDURE.md** — EA should read and exercise the rollback procedure. Per WP-004-13's Definition of Done, a timed rollback drill must be executed and recorded. Confirm the drill was performed and MTTR was within 15 minutes.
4. **Production credentials** — Confirm production deployment credentials are in the `production` GitHub Environment scoped secrets and not shared with Staging/Dev.

---

## AR-047 — WP-004-14: DORA Metrics & Pipeline Observability

| Field | Value |
|-------|-------|
| Review ID | AR-047 |
| Work Package | WP-004-14 |
| WP Title | Release Automation — DORA Metrics & Pipeline Observability |
| Implementation Commit | `d9a7bce` |
| Merge Commit | `41ad963` (develop/v1.1) |
| Primary Files | `scripts/dora-metrics.py`; `.github/workflows/dora-report.yml`; `DORA_METRICS.md`; `reports/dora/` |
| Architecture Sources | Roadmap v1.0 §Delivery Metrics (DORA) section; `release-exit-criteria.md` §6 |

**Scope implemented:**
- `scripts/dora-metrics.py`: queries GitHub Actions API for `deploy-staging`/`deploy-production` run history; computes all 4 DORA metrics (Deployment Frequency, Lead Time, Change Failure Rate, MTTR); renders Markdown report
- `dora-report.yml`: weekly cron + `workflow_dispatch`
- `DORA_METRICS.md`: metric definitions and data source documentation
- Read-only GitHub API token (no deploy permissions)

**EA focus areas:**
- Confirm all 4 DORA metrics are computed (not just 2 or 3)
- Confirm MTTR reflects WP-004-13's actual timed rollback drill (not a placeholder)
- Confirm API token scope is read-only
- Per `release-exit-criteria.md` §6: this WP's completion is a Release 1 exit criterion — EA should confirm the first real DORA report has been generated from actual pipeline runs (not synthetic data)

---

## Open Operational Items — Carried Forward

These are **not implementation tasks**. They require Project Owner or Platform Lead action.

| # | Item | Owner | Prerequisite For |
|---|------|-------|-----------------|
| 1 | Confirm GitHub Advanced Security (GHAS) availability for CodeQL (AR-035) | Project Owner | AR-035 APPROVED |
| 2 | Provision `NOTIFY_WEBHOOK_URL` secret (notification channel confirmation) | Project Owner | AR-040 fully met |
| 3 | Confirm Gitleaks licence tier compatibility | Project Owner | AR-042 APPROVED |
| 4 | Confirm Staging VMs provisioned (WP-003-14 scope extension) | Project Owner | AR-044 APPROVED |
| 5 | Execute one-time full-history Gitleaks baseline scan; record result in `SECRETS_SCANNING.md` | Platform Lead | AR-042 APPROVED; Release 1 exit criterion |

---

## Review Completion Tracking

| AR ID | WP | Outcome | Score | Date | Reviewer |
|-------|----|---------|-------|------|---------|
| AR-034 | WP-004-01 | **APPROVED** | 99/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-035 | WP-004-02 | **APPROVED WITH CONDITIONS** | 92/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-036 | WP-004-03 | **APPROVED** | 98/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-037 | WP-004-04 | **APPROVED** | 100/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-038 | WP-004-05 | **APPROVED** | 97/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-039 | WP-004-06 | **APPROVED** | 98/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-040 | WP-004-07 | **APPROVED WITH CONDITIONS** | 97/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-041 | WP-004-08 | **APPROVED WITH CONDITIONS** | 88/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-042 | WP-004-09 | **APPROVED WITH CONDITIONS** | 93/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-043 | WP-004-10 | **APPROVED** | 98/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-044 | WP-004-11 | **APPROVED WITH CONDITIONS** | 92/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-045 | WP-004-12 | **APPROVED** | 98/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-046 | WP-004-13 | **APPROVED WITH CONDITIONS** | 92/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |
| AR-047 | WP-004-14 | **APPROVED** | 97/100 | 2026-07-03 | Enterprise Architect (EECR-CHG-059) |

**Batch Review Complete: 2026-07-03 | EECR-CHG-059**
- 8 WPs APPROVED outright: AR-034, AR-036, AR-037, AR-038, AR-039, AR-043, AR-045, AR-047
- 6 WPs APPROVED WITH CONDITIONS: AR-035, AR-040, AR-041, AR-042, AR-044, AR-046
- 0 WPs REJECTED or CHANGES REQUIRED
- Average score (14 WPs): **95.6 / 100**
- EPIC-004 status: **IMPLEMENTATION COMPLETE — CONDITIONALLY CLOSED** (6 conditions outstanding)

See `architecture-review-register.md` AR-034..047 for full scored assessments and condition details.
See `change-log.md` EECR-CHG-059 for the formal change record.
