# Rollback Procedure — DAEP / RE-OS

**Authority:** WP-004-13 | Roadmap v1.0 §11.1 Stage 12 ("Automatic rollback") | Roadmap Production Stability success metric ("rollback available within 15 minutes")

**This document is designed to be executed copy-paste under time pressure
during an active incident. Keep it open. Read every step before proceeding.**

---

## Step 1 — Identify the previous known-good commit SHA

```bash
# Find the SHA of the last successful production deployment before this failure.
# Every deployment logs its image_tag in the GitHub Actions run history:
gh run list --workflow=service-ci-cd.yml --branch=main --status=success \
  --json headSha,createdAt,conclusion \
  --limit 5
```

Note the `headSha` of the last successful run prior to the current failure.
That SHA is your **rollback target**.

## Step 2 — Execute the rollback

```bash
ansible-playbook infra/playbooks/deploy-rolling.yml \
  -i infra/environments/production/inventory.yml \
  -e "service=<SERVICE_NAME> image_tag=<PREVIOUS_KNOWN_GOOD_SHA>" \
  --private-key <PATH_TO_DEPLOY_KEY>
```

Replace `<SERVICE_NAME>`, `<PREVIOUS_KNOWN_GOOD_SHA>`, and
`<PATH_TO_DEPLOY_KEY>` with real values.

The same `deploy-rolling.yml` 7-step playbook runs, but with the previous
image tag. Steps [1/7]–[7/7] proceed exactly as a forward deployment — the
playbook doesn't distinguish rollback from deploy.

## Step 3 — Verify recovery

```bash
curl -sf https://api.reos.internal/health
# Expected: {"status": "ok"}
```

Confirm all VMs are healthy via Consul (`consul catalog services`) and
that the previous image version is actually running:

```bash
docker inspect reos-<SERVICE_NAME> --format='{{.Config.Image}}'
# Expected: registry.internal:5000/reos/<SERVICE_NAME>:<PREVIOUS_KNOWN_GOOD_SHA>
```

## Step 4 — Record the incident

Document:
- What was deployed (which SHA, which service)
- When the failure was detected and how
- Time from first alert to rollback complete (target: ≤15 minutes)
- Root cause (once determined — can be deferred to after recovery)

**Target: rollback complete within 15 minutes of the decision to roll back.**
This is the Roadmap's Production Stability success metric. Time starts
when the decision to roll back is made, not from the initial deployment.

---

## Mechanism: Why Rollback Is Automatic for Partial Failures

`infra/playbooks/deploy-rolling.yml` runs with `serial: 1` (one VM at a
time) and `max_fail_percentage: 0` (any single VM failure aborts the
entire play). If the new version's health check fails on VM 1 (step [6/7]),
the play aborts before VM 2 is ever touched — most of the fleet remains on
the previous version automatically. This is the "Automatic rollback" in the
Roadmap's Stage 12 policy.

For a full fleet-wide failure (all VMs deployed before the health check
failure was detected), this manual procedure is the documented recovery path.

---

## Preventing the "Bad Tag Is Gone" Problem

Every built image is tagged with `github.sha` and pushed to the internal
registry (WP-004-07). Tags are immutable (pushed once, never overwritten —
`CONTAINER_REGISTRY.md`). A previous SHA's image is always pullable unless
explicitly deleted — delete no image from the registry without confirming it
is not the current production rollback target.
