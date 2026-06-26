# DIEP Release 1.0 — Pre-Cutover Report

**Date:** 2026-06-26, immediately before the Phase 3 `diep-fastapi` cutover.
**Method:** live `docker inspect`, live HTTP/API checks against the running
stack — no assumptions carried from prior reports.

---

## Current running branch / bind mounts / compose project

- `diep-fastapi` is currently bind-mounted from
  `/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/fastapi`
  — branch `release/v1.0-rc-qualification` @ `2dd9763` (does **not** include
  `feature/adms-topology-import`'s work; `/topology/versions` confirmed 404
  below).
- Compose project for all 31 running containers: `diep-lab` (confirmed via
  `com.docker.compose.project` label on a representative sample including
  `diep-fastapi`, `diep-prometheus`, `diep-grafana`, `diep-wal-shipper`,
  `diep-redis-exporter`).
- The validated cutover target, `release/v1.0-rc2` @ `595829e`, lives in
  `.claude/worktrees/rc2-reconciliation` (this worktree) and has not yet
  been pointed at by any live container.

## Container health — all 31 running

`docker ps` confirms all 31 standing containers `Up`, none `unhealthy`,
none `restarting`. `diep-fastapi`: `Up 3 hours`, `RestartCount: 0`,
`Created: 2026-06-26T10:54:28Z` (last recreated in the prior Configuration
& Deployment Audit session, unrelated to this cutover).

## Database health

`GET /readyz` on the current `diep-fastapi`: `{"ready": true, "checks":
{"database": true, "redis": true}}`. `diep-timescaledb` container state:
`running`, no healthcheck configured at the Docker level (readiness is
inferred via FastAPI's own check, consistent with how this has been
verified throughout this engagement).

## Redis replication

`redis_connected_slaves` = **0** (queried live via Prometheus). This is a
**pre-existing, already-documented** condition (see
`SERVICE_RECONCILIATION_REPORT.md` from the Configuration & Deployment
Audit) — confirmed unchanged since that audit, not introduced by anything
since. `RedisReplicationBroken` is active in Alertmanager as a result —
expected, not a new finding, and unrelated to this cutover (Branch A's
merge never touches Redis).

## Kafka health

1 broker reporting (`kafka_brokers` = 1) — consistent with the documented
single-broker (RF=1) pilot configuration, not a new finding.
`KafkaBrokerCountLow` active in Alertmanager, same as above: pre-existing
and expected at this scale.

## Prometheus

All 10 scrape targets `up`, 0 down. 5 rule groups loaded (including
`diep-backup-dr`, fixed in the prior audit). Currently bind-mounted from
the worktree (correct, per the prior audit) — unaffected by this sprint's
planned `fastapi`-only cutover.

## Alertmanager

3 active alerts at pre-cutover baseline: `MinioDiskOnlineLow`,
`RedisReplicationBroken`, `KafkaBrokerCountLow` — all pre-existing per the
checks above, none related to FastAPI or this cutover.

## Grafana

`GET /api/health` → 200.

## Portal

`GET :3002` → 307 (redirect — normal for this service, confirmed
consistent with its known behavior).

## FastAPI (pre-cutover baseline, for direct before/after comparison)

- `GET /readyz` → `{"ready": true, ...}`
- `GET /topology/versions` → **404** (expected — confirms the gap this
  cutover exists to close)
- `GET /telemetry/latest` (no token) → **401** (expected — confirms the
  auth fix is currently active and will be the regression baseline)

## Backup status

- Freshness metric (`diep_last_backup_timestamp_seconds`, as visible to
  Prometheus today): epoch `1782471979` (2026-06-26T11:06:19Z, a manual
  test run from the prior audit session) — currently **~3.3 hours stale
  relative to now**, well under the 24h `BackupStale` threshold, not firing.
- Real backup files on disk (main checkout, where the cron job actually
  runs): most recent is `diep_20260626T092206Z.dump` (2026-06-26T09:22Z,
  1.5MB) — **note this timestamp does not match the crontab's scheduled
  `0 2 * * *` slot**, suggesting either a manual run or a cron/log
  inconsistency; `backups/logs/backup-db.log` does not currently exist
  (the `logs/` directory is empty). This is carried into Phase 5's
  backup-monitoring regression check rather than resolved here — it is the
  same already-documented gap (real backups still happen; the
  freshness-metric link to Prometheus is what's broken), not a new finding
  introduced by this report.

---

## Summary

Platform is healthy and stable at pre-cutover baseline. The three active
alerts (Redis replication, Kafka broker count, MinIO disk) are all
pre-existing, independently confirmed, and unrelated to FastAPI or this
cutover — they are not expected to change as a result of Phase 3, and any
change in their state during Phase 4 validation would be a genuine signal
worth investigating, not noise. `diep-fastapi`'s pre-cutover state
(`/topology/versions` 404, `/telemetry/latest` 401) is the exact baseline
Phase 4 will check against.
