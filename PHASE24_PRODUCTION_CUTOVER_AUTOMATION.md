# DIEP Phase 24 — Production Cutover Automation — Release Notes

**Branch:** `feature/phase24-cutover-automation` (stacked on
`feature/mw2-readiness-verification`) → `main`
**Constraints honoured:** production-safe, **no destructive actions**, read-only
against infrastructure, full audit logging, additive-only schema, no `.env`
changes, **no new runtime dependencies**.

---

## Objective

A deployment orchestration and verification framework that executes and validates
MW2 cutover activities — pre-cutover gating, a record-only execution workflow,
post-cutover validation, evidence collection, metrics, and operator docs.

## What it does (and deliberately does NOT do)

It **records, attests, validates, and stores evidence**. Every infrastructure
interaction is a **read-only probe** (HTTP GET, `docker inspect`, Redis PING,
directory listing). It **does not** restart services, run migrations, redeploy
images, or mutate any live component — those remain human-executed via the
standard change procedure. The only writes are to two additive evidence tables
and to Prometheus gauges.

## Built on MW2 readiness

Phase 24 stacks on the MW2 readiness engine (`fastapi/readiness.py`,
`sql/022_platform_readiness.sql`): pre-cutover validation reuses the scored
readiness assessment and the container inspector rather than re-implementing them.

## Components

- **`fastapi/deployment.py`** — service engine:
  - Pre-cutover validation (req 1): `mw2_readiness_certification`,
    `critical_containers_healthy`, `database_backups_present`,
    `minio_archive_accessible`, `kafka_health`, `redis_health`.
  - Cutover execution workflow (req 2): `start_cutover` generates the deployment
    ID + timestamp, captures a read-only baseline, records operator actions and
    the attested checklist as audit events. No destructive action.
  - Post-cutover validation (req 3): `fastapi_readyz`, `portal_login`,
    `redis_connectivity`, `kafka_metrics`, `prometheus_targets`,
    `grafana_availability`, scored to a 0–100 validation score → GO/NO-GO gate.
  - Evidence collection (req 4): deployment reports, readiness reports, health
    snapshots, and an append-only audit trail persisted as JSONB.
  - Metrics (req 6): `diep_deployment_status`,
    `diep_deployment_validation_score`, `diep_deployment_duration_seconds`
    (+ `diep_deployment_last_run_timestamp_seconds`).
- **`fastapi/routers/deployment.py`** — API (req 5):
  - `GET  /deployment/status` — latest record (+ optional live pre-cutover posture).
  - `POST /deployment/cutover/start` — begin a cutover (admin).
  - `POST /deployment/cutover/validate` — post-cutover gate (admin).
  - `GET  /deployment/history` — past cutovers.
  - OpenAPI (req 7) auto-served at `/openapi.json` and `/docs` (tag `deployment`).
- **`sql/023_production_cutover.sql`** — additive `platform_deployment_runs` +
  `platform_deployment_events` (audit) tables. No changes to existing tables.
- **Docs (req 7):** [operations runbook](PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md),
  [rollback procedure](PHASE24_ROLLBACK_PROCEDURE.md),
  [cutover checklist](PHASE24_CUTOVER_CHECKLIST.md).
- **Tests:** `tests/test_deployment_unit.py` (pure scoring/checks/validation),
  `tests/test_deployment_api.py` (endpoints + RBAC via TestClient).

## Authorization

`admin` may start/validate a cutover (highest-privilege, attesting action);
`engineer`/`admin`/`service` may read status and history. Operators are rejected
from the deployment surface (403).

## Validation

See the PR description for the containerized `pytest` counts and the isolated
throwaway-DB end-to-end run (migrations `022`+`023` applied; live stack untouched).

## Follow-ups (not in scope here)

- Optional authenticated portal-login probe (currently a read-only reachability
  GET, to stay non-mutating by default).
- Wiring a scheduled pre-cutover gate into CI/cron alongside the MW2 readiness job.
