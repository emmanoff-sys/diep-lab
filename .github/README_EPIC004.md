# EPIC-004 — CI/CD, DevSecOps & Release Automation

### DAEP / RE-OS | Official Engineering Guide | Version 0.1.0 (Release 1)

---

## 1. EPIC Overview

EPIC-004 builds the automated delivery pipeline that turns every source-code
commit into a versioned, scanned, tested, signed artifact in the internal
registry — and then deploys it to Staging automatically and to Production
with a manual-approval gate. It is the "trust chain" that every future EPIC
depends on for reliable, auditable delivery.

---

## 2. Pipeline Architecture

```
PR Created                          Merge to develop            Merge to main
     │                                      │                        │
     ▼                                      ▼                        ▼
[Stage 1] Lint & Type             [Stage 5] Build              [Stage 12] Production
[Stage 2] SAST (Bandit/CodeQL)    [Stage 6] Trivy Scan         (manual-approval gate)
[Stage 3] Dependency Scan         [Stage 7] Push to Registry         │
[Stage 4] Unit Tests (80% cov)         │                       (human approves)
     │                            [Stage 8] Integration Tests         │
     └── All required on PR       [Stage 9] Deploy Staging     (same deploy-rolling.yml
                                       │                         against prod inventory)
                              [Stage 10] Load Test (weekly)
                              [Stage 11] DAST Scan (manual)
                              [Stage 14] DORA Report (weekly)
```

All Stages 1–4 run in parallel per PR. Stages 5–9 run sequentially on merge
to `develop`. Stages 10/11 are scheduled/manual. Stage 12 gates on Stage 9
success AND Stage 11 DAST pass.

---

## 3. Workflow Inventory

| Workflow | File | Trigger | Stages |
|----------|------|---------|--------|
| RE-OS Service CI/CD | `service-ci-cd.yml` | PR/push | 1–9, 12 |
| DAST Scan | `dast-scan.yml` | Manual (`workflow_dispatch`) | 11 |
| Load Test | `load-test.yml` | Weekly cron + manual | 10 |
| DORA Report | `dora-report.yml` | Weekly cron + manual | 14 |
| Infrastructure Checks | `infra-checks.yml` | PR to `infra/**` | EPIC-003 WP-003-11 |

**Existing CI (`ci.yml`) is UNTOUCHED** — it serves the operational DIEP
platform (Kubernetes/Helm-based). EPIC-004's workflows are for RE-OS services
only (`service-ci-cd.yml` and the auxiliary workflows above).

---

## 4. Security Gates

| Gate | Stage | Hard-block? | Policy |
|------|-------|------------|--------|
| Zero mypy errors | 1 | Yes | `--strict` |
| Zero Ruff/Black/isort errors | 1 | Yes | per STANDARDS.md |
| No Bandit HIGH+ findings | 2 | Yes | `-ll -ii` |
| CodeQL alerts (if available) | 2 | Yes | requires GitHub Advanced Security |
| No known CVEs (pip-audit) | 3 | Yes | `--strict` |
| 80% test coverage | 4 | Yes | `--cov-fail-under=80` per LLD §2.7 |
| No CRITICAL/HIGH image vulns | 6 | Yes | Trivy exit-code 1 |
| No committed secrets | 9 | Yes | Gitleaks |
| P95 ≤ 500ms @ 1,000 RPS | 10 | **NO** | Alert + review (Roadmap §11.1) |
| No High DAST findings | 11 | Yes (gates Stage 12) | ZAP full scan |

---

## 5. Artifact Promotion Strategy

```
Code commit → PR (Stages 1–4 pass) → merge to develop
    → Stage 5 Docker build (--target production, BuildKit cached)
    → Stage 6 Trivy scan (CRITICAL+HIGH gate)
    → Stage 7 Push to internal registry:
        registry.internal:5000/reos/{service}:{git-sha}    ← every build
        registry.internal:5000/reos/{service}:{semver}     ← release/* → main only (WP-001-10)
```

All images are **immutable** — the SHA tag is never overwritten. Never delete
an image that might be the current production rollback target.

---

## 6. Rollback Strategy

See `ROLLBACK_PROCEDURE.md` — execute under time pressure. Summary:

1. Identify the previous good SHA via `gh run list`.
2. `ansible-playbook infra/playbooks/deploy-rolling.yml ... -e image_tag=<PREV_SHA>`.
3. Verify health. Record timing.

Target: **≤15 minutes** from decision to rollback complete (Roadmap Production
Stability success metric). The WP-004-13 rollback drill's timed result is the
first real MTTR measurement.

---

## 7. Secrets Handling

- All credentials are GitHub Actions **Encrypted Secrets** — never hardcoded.
- `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` — push credentials (Platform Lead)
- `CODECOV_TOKEN` — Codecov coverage reporting
- `NOTIFY_WEBHOOK_URL` — notification channel (OPEN DECISION — Project Owner)
- `GITLEAKS_LICENSE` — Gitleaks for private repos (confirm tier with Project Owner)
- `ANSIBLE_SSH_KEY` — deployment SSH key (staging/production environment-scoped)
- No secret is committed to any file in this repository.

---

## 8. Platform Lead Actions Required

The following are **human actions** — not triggered autonomously by this
implementation (consistent with WP-001-04/WP-003-11 precedents):

| # | Action | Owner |
|---|--------|-------|
| 1 | Register `lint`, `security`, `dependency-scan`, `test-unit`, `secrets-scan` as required checks on `main`/`develop` | Platform Lead |
| 2 | Create `staging` and `production` GitHub Environments; configure required reviewers on `production` | Platform Lead |
| 3 | Configure all secrets listed in §7 as GitHub Actions secrets | Platform Lead |
| 4 | Confirm CodeQL/GitHub Advanced Security availability (WP-004-02 §24) | Project Owner |
| 5 | Confirm Gitleaks license tier for private repos (WP-004-09) | Project Owner |
| 6 | Confirm notification webhook channel/URL (WP-004-07/12/13 §35) | Project Owner |
| 7 | Provision Staging VMs and confirm Staging-provisioning scope extension (WP-004-11 §35) | Project Owner + DevOps Lead |
| 8 | Execute WP-004-13 rollback drill and record timed MTTR as the first real DORA data point | DevOps Lead |
| 9 | Run full-history Gitleaks baseline scan (WP-004-09 §33 AC, Release 1 exit criterion) | Tech Lead |

---

## 9. Work Package Summary

| WP | Stage | Title | Commit |
|----|-------|-------|--------|
| WP-004-01 | 1 | Lint & Type Check | `fbfebe6` |
| WP-004-02 | 2 | SAST Security (Bandit/CodeQL) | `116ba8e` |
| WP-004-03 | 3 | Dependency Scanning (pip-audit) | `a1394d6` |
| WP-004-04 | 4 | Unit & Component Tests | `e605511` |
| WP-004-05 | 5 | Container Build (BuildKit) | `47bc086` |
| WP-004-06 | 6 | Container Security Scan (Trivy) | `022b7d5` |
| WP-004-07 | 7 | Registry Push + Notification | `8156e36` |
| WP-004-08 | 11 | DAST Scan (OWASP ZAP) | `5bb56db` |
| WP-004-09 | — | Secrets Scanning (Gitleaks) | `c809815` |
| WP-004-10 | 8 | Integration Tests (service containers) | `1c7893c` |
| WP-004-11 | 9 | Staging Deployment (rolling) | `267c9b5` |
| WP-004-12 | 10 | Load Testing (k6, 1,000 RPS) | `0817def` |
| WP-004-13 | 12 | Production Deployment + Rollback | `fd09d56` |
| WP-004-14 | — | DORA Metrics & Pipeline Observability | `d9a7bce` |

---

## 10. Version History

| Version | Date | Change |
|---------|------|--------|
| 0.1.0 | 2026-07-02 | Initial EPIC-004 delivery — all 14 WPs, complete pipeline |
