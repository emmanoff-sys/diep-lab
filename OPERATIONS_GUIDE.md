# DIEP v1.0 — Operations Guide

This is a current-state summary and pointer document, not a replacement for
the existing, detailed runbooks — `DIEP_OPERATIONS_MANUAL.md` (startup/
shutdown/backup/restore/DR procedures, monitoring, escalation) and
`DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md` (Day-2 daily/weekly checks) already
cover those in depth and are still accurate in structure. What follows is
what changed or was newly confirmed by this RC's qualification
(`QUALIFICATION_REPORT.md`) that those documents should be read alongside.

## Updates to Day-2 Procedures From This Qualification

- **Restarting a service** (`docker compose restart <service>`): confirmed
  clean for FastAPI, MQTT, Kafka, TimescaleDB, and (newly tested) Portal —
  all recover in 5-15 seconds. No change to the existing runbook's
  procedure.
- **Recovering from a hard failure** (process killed, not gracefully
  stopped): `restart: unless-stopped` does **not** auto-recover a
  `docker kill`'d or `docker stop`'d container — both are treated as manual
  actions by Docker. If you ever need to forcibly kill a container (e.g. to
  break a stuck process), follow up with an explicit `docker start
  <container>` — do not wait for self-healing, it will not happen. This
  applies to every service in `docker-compose.yml` using `unless-stopped`,
  not just the one tested.
- **Redis failover**: confirmed working automatically via Sentinel in ~5
  seconds when Sentinel is not in "tilt mode." Tilt mode (which suspends
  automatic failover) has recurred multiple times over a 24h period,
  correlated with host instability — if a failover doesn't happen
  automatically during an incident, check `docker exec diep-redis-sentinel-1
  redis-cli -p 26379 info sentinel` for `sentinel_tilt:1` before assuming
  Sentinel itself is broken.
- **Backup verification**: do not trust the existence of old backup files in
  `backups/` as proof the cron is currently working — confirmed this
  session that cron can silently skip its scheduled run during a host
  stall. Check `curl -s http://localhost:9090/api/v1/query --data-urlencode
  'query=time()-diep_last_backup_timestamp_seconds'` directly, and be aware
  (per `KNOWN_LIMITATIONS.md`) that this metric is not currently updated by
  `backup-db.sh` on a fresh run — until that's fixed, the metric reflects
  whenever it was last manually set, not necessarily the most recent
  successful backup.

## Daily Check Additions

In addition to `DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md` §1's existing daily
checks, add:
- `curl -s http://localhost:9090/api/v1/alerts` — confirm only expected
  alerts are firing (as of this qualification, `KafkaBrokerCountLow` and
  `MinioDiskOnlineLow` are expected/pre-accepted since K3/K6 HA aren't
  deployed; anything else firing is new and should be investigated).
- Spot-check that the legacy plaintext ports (8000/3001/3002) and the
  unauthenticated monitoring ports (9090/9093/8081/8080/1880) are still
  intentionally reachable from wherever they're reachable from — see
  `SECURITY_GUIDE.md`.

## Escalation

Unchanged from `DIEP_OPERATIONS_MANUAL.md` §7, with one addition: if Kafka,
Redis, or TimescaleDB show repeated unexpected restarts or any of the
corruption fingerprints in `HOST_VM_INSTABILITY_FINDINGS_20260624.md`
(`PANIC`, `FATAL`, `corrupt`, `replorigin`), treat it as the known recurring
host-instability issue, not a fresh incident — confirm via `uptime` load
average and container restart counts, and do not chain repeated destructive
repairs (e.g. `pg_resetwal`) without re-confirming with whoever's on call
each time, since this failure mode has been shown to recur within minutes.
