# DIEP Phase 24 — Production Cutover Rollback Procedure

**When to use:** a `POST /deployment/cutover/validate` returned
`deployment_status = NO_GO` (`status = FAILED`), or a post-cutover smoke check
surfaced a regression within the change window.

**Important:** the Phase 24 framework does **not** perform rollback actions. It
records the rollback decision and re-validates afterwards. The actual revert is
executed with your existing change-management procedure (compose redeploy of the
prior image tags, DB restore, etc.). This document is the operator playbook.

---

## 1. Decision (first 5 minutes)

1. Open the failed record: `GET /deployment/status` (or
   `GET /deployment/history` for the ID). Read `post_cutover.checks` for the
   failing `critical` checks and their `message`/`observed`.
2. If only **non-critical** checks failed (e.g. `prometheus_targets`,
   `grafana_availability`) and the core path (`fastapi_readyz`, `redis`, `kafka`,
   `portal`) is healthy → this is a monitoring gap, **not** a service regression.
   Fix forward; do not roll back the platform.
3. If a **critical** check failed (`fastapi_readyz`, `portal_login`,
   `redis_connectivity`, `kafka_metrics`) → proceed to rollback.

## 2. Rollback execution (your existing procedure)

1. Announce the rollback in the change channel; reference the `deployment_id`.
2. Restore the previous release:
   - **Application:** redeploy the prior image tags
     (`docker compose up -d` against the previous compose/tag pin).
   - **Database:** if a migration was applied and must be reverted, restore from
     the backup validated at pre-cutover (`database_backups_present` recorded the
     artifact in `baseline`/evidence). Follow the DB restore runbook.
   - **Config:** revert any `.env`/secret changes made for the cutover.
3. Confirm critical containers are healthy (`docker ps`, `/readyz`).

## 3. Record + re-validate

1. Mark the rollback in the audit trail and re-run validation to confirm the
   restored state is healthy:

   ```
   POST /deployment/cutover/validate
   { "deployment_id": "<id>" }
   ```

   A PASS here confirms the **restored** platform is healthy. (To keep the failed
   cutover's history intact, you may instead open a fresh record for the rollback
   verification via `POST /deployment/cutover/start` with
   `change_ref: "ROLLBACK-of-<id>"`.)
2. Capture the post-rollback `GET /deployment/status` output for the incident
   record.

## 4. Post-incident

- File the incident with the `deployment_id`, the failing checks, root cause, and
  the rollback timeline (the `platform_deployment_events` audit trail gives exact
  timestamps).
- Re-run `scripts/run_mw2_readiness_check.py` and confirm MW2 readiness is PASS
  before re-attempting the cutover.

## 5. Safety reminder

Phase 24 endpoints never restart, redeploy, or migrate anything. Every action in
section 2 is performed by a human operator through the standard change procedure;
the framework only records the decision and verifies the outcome.
