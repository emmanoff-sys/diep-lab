# DIEP Phase 24 — Production Cutover Operations Runbook

**Scope:** orchestrating and validating an MW2 production cutover with the
Phase 24 Production Cutover Automation framework.
**Audience:** release manager / on-call SRE (the `admin` role).
**Safety posture:** the framework is **read-only against infrastructure** and
performs **no destructive actions**. It records, attests, validates, and stores
evidence; it never restarts services, runs migrations, or mutates a live
component. The only writes are to the additive evidence tables
(`platform_deployment_runs`, `platform_deployment_events`) and to Prometheus
gauges.

Related: [PHASE24_CUTOVER_CHECKLIST.md](PHASE24_CUTOVER_CHECKLIST.md) ·
[PHASE24_ROLLBACK_PROCEDURE.md](PHASE24_ROLLBACK_PROCEDURE.md) ·
[MW2_READINESS_OPERATOR_RUNBOOK.md](MW2_READINESS_OPERATOR_RUNBOOK.md).

---

## 1. Prerequisites

- The MW2 readiness migration (`sql/022_platform_readiness.sql`) and the cutover
  migration (`sql/023_production_cutover.sql`) are applied to the database.
- A current MW2 readiness assessment exists (run
  `scripts/run_mw2_readiness_check.py` first if needed).
- You hold an `admin` API token. `engineer`/`admin`/`service` may read status and
  history; only `admin` may start or validate a cutover.

### Configuration (environment, all optional with safe defaults)

| Variable | Default | Purpose |
|---|---|---|
| `DEPLOY_PASS_THRESHOLD` | inherits `READINESS_PASS_THRESHOLD` (90) | min validation score for GO |
| `DEPLOY_FASTAPI_URL` | inherits `READINESS_FASTAPI_URL` | FastAPI `/readyz` probe |
| `DEPLOY_PORTAL_URL` | `http://127.0.0.1:3000/api/health` | portal reachability probe (GET only) |
| `DEPLOY_MINIO_HEALTH_URL` | `http://127.0.0.1:9000/minio/health/ready` | MinIO archive accessibility |
| `DEPLOY_PROMETHEUS_URL` | `http://127.0.0.1:9090` | Prometheus targets |
| `DEPLOY_GRAFANA_URL` | `http://127.0.0.1:3001` | Grafana `/api/health` |
| `DEPLOY_BACKUP_DIR` | `/backups` | directory scanned for DB backups |
| `DEPLOY_BACKUP_GLOBS` | `*.sql.gz,*.dump,*.sql,*.tar.zst` | backup artifact patterns |
| `DEPLOY_BACKUP_MAX_AGE_HOURS` | `24` | backups older than this WARN |

Kafka/Redis/container probes inherit the `READINESS_*` configuration.

---

## 2. Cutover workflow

### 2.1 Pre-flight (read-only posture check)

```
GET /deployment/status?live=true
```

Returns the latest cutover record and a **fresh pre-cutover validation**. Confirm
`pre_cutover_now.status == "PASS"` before scheduling. The six pre-cutover checks:

1. `mw2_readiness_certification` — MW2 readiness is PASS and meets its threshold.
2. `critical_containers_healthy` — every critical container is running/healthy.
3. `database_backups_present` — a recent backup artifact exists.
4. `minio_archive_accessible` — MinIO health endpoint responds 2xx.
5. `kafka_health` — Kafka broker/exporter healthy.
6. `redis_health` — Redis reachable.

### 2.2 Start the cutover

```
POST /deployment/cutover/start
{
  "change_ref": "CHG-1234",
  "checklist": [
    {"item": "NOC notified", "done": true},
    {"item": "Maintenance window open", "done": true}
  ],
  "notes": "MW2 window 02:00-04:00 WAT"
}
```

This generates the deployment ID + timestamp, captures a read-only **baseline**
(container snapshot + readiness reference), runs pre-cutover validation, and
records the checklist + operator as **audit events**. The operator is taken from
the authenticated principal — checklist items are *attestations*, not executed
actions. The record opens with `status=STARTED`, `deployment_status=IN_PROGRESS`.

> Perform the actual cutover steps using your existing change procedure. Phase 24
> records and validates; it does not execute infrastructure changes.

### 2.3 Validate (post-cutover gate)

After the change is applied:

```
POST /deployment/cutover/validate
{ "deployment_id": "<id>" }     # omit to validate the latest in-flight cutover
```

Runs the six post-cutover checks — `fastapi_readyz`, `portal_login`,
`redis_connectivity`, `kafka_metrics`, `prometheus_targets`,
`grafana_availability` — scores them 0–100, and derives the gate:

- **GO** — `status=VALIDATED`, all critical checks pass and score ≥ threshold.
- **NO-GO** — `status=FAILED`; see [the rollback procedure](PHASE24_ROLLBACK_PROCEDURE.md).

Duration, score, evidence, and the audit trail are persisted automatically.

### 2.4 Review evidence / history

```
GET /deployment/status            # latest record incl. baseline, validations, evidence, events
GET /deployment/history?limit=20  # past cutovers, newest first
```

---

## 3. Metrics (Prometheus, refreshed on `/metrics` scrape)

| Metric | Meaning |
|---|---|
| `diep_deployment_status` | latest gate: GO=1, IN_PROGRESS=0.5, NO-GO/FAILED=0 |
| `diep_deployment_validation_score` | latest post-cutover validation score (0–100) |
| `diep_deployment_duration_seconds` | duration of the latest completed cutover |
| `diep_deployment_last_run_timestamp_seconds` | start time of the latest cutover |

Suggested alert: page if `diep_deployment_status == 0` after a `cutover/validate`.

## 4. OpenAPI

All four endpoints are documented in the live OpenAPI schema at `/openapi.json`
and the Swagger UI at `/docs` (tag: **deployment**), with request/response models.

## 5. Decision rule

GO only when the post-cutover validation is PASS **and** the pre-cutover gate was
PASS at start. Any critical-check FAIL is an automatic NO-GO → initiate rollback.
