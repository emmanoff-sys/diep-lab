# DIEP v1.0 — Go-Live Checklist

Derived from this RC's qualification (`QUALIFICATION_REPORT.md`). Items are
grouped by priority; each names the exact gap and the specific fix, not a
vague "harden security" placeholder.

## Must-fix before production go-live (P0)

- [ ] **`GET /telemetry/latest` has no authentication.** Add the same
  role/tenant dependency `/telemetry` (POST) already has
  (`fastapi/app.py:1960`), and filter the query by the caller's tenant.
- [ ] **Prometheus, Alertmanager, kafka-ui, cAdvisor, Node-RED admin API are
  unauthenticated on all interfaces.** Bind to `127.0.0.1` (matching Phase
  22 SEC-4's treatment of the data services) and/or put behind the
  Caddy auth boundary; for Node-RED specifically, wire up `adminAuth` in
  `settings.js` against the existing `nodered/.config.users.json`.
- [ ] **Backup success is not actually monitored.** `scripts/backup-db.sh`
  never writes `diep_last_backup_timestamp_seconds` (the metric
  `BackupStale` depends on) and never calls the `alert_backup_failure()`
  helper it already sources. Add a write of that textfile metric (matching
  `diep_wal_shipper.prom`'s existing pattern) as the last step on success,
  and call `alert_backup_failure()` in a trap on non-zero exit.
- [ ] **Confirm the underlying host write-durability defect
  (`HOST_VM_INSTABILITY_FINDINGS_20260624.md`) is actually fixed**, or
  explicitly accept it as a standing operational risk before scaling beyond
  this qualification's tested load — it caused this qualification's own
  backup-cron gap (system-wide cron silently missed a ~4h window overnight)
  and has previously corrupted Kafka/Redis/TimescaleDB.

## Should-fix before production go-live (P1)

- [ ] **TLS is additive, not enforced.** Decide whether to close the legacy
  plaintext Portal (3002) / Grafana (3001) / FastAPI (8000) ports now that
  Caddy's HTTPS termination (Phase 22 SEC-3) is live and working.
- [ ] **Reconcile the live TimescaleDB password with `.env`** — they've
  drifted apart (rotated in `.env`, never applied to the running database).
  Either `ALTER USER` the live password to match, or update `.env` to the
  value actually in use, then document which is authoritative going forward.
- [ ] **Throughput ceiling is ~15 msg/s**, bottlenecked at TimescaleDB's
  single-row insert path. Before onboarding a fleet that needs more than
  that sustained (see `DEPLOYMENT_GUIDE.md`'s sizing table), implement
  batched/`COPY` inserts or a connection pool sized to the ingestor's
  workers — re-test after, don't assume the fix works without re-measuring.
- [ ] **This qualification's host (2 vCPU/7.2GB) is already CPU/memory
  constrained at light load** (99.9% CPU spike, active swap, observed via
  Prometheus's own history at only 10 simulated devices). Size production
  hardware per `DEPLOYMENT_GUIDE.md`'s tiers, not this lab host's spec.
- [ ] **Run a real multi-day soak in staging** — this qualification's soak
  test was a bounded ~30-minute window by necessity, not a substitute for
  one.

## Worth doing, not blocking (P2)

- [ ] Delete or clearly quarantine the dead `docker-compose-timescale.yml`
  (hardcoded weak password, not live) and the `*-ha-validation.yml`/
  `*-pitr-validation.yml` files if they're no longer needed for re-running
  those validations, to remove the risk of someone running one by mistake.
- [ ] Rotate `DIEP_ADMIN_USER` off its literal default (`"admin"`) if this
  deployment's threat model calls for not using a guessable admin username
  — `DIEP_ADMIN_KEY`/`DIEP_ADMIN_PASSWORD` are already confirmed rotated to
  strong values.
- [ ] Decide on a path for the K2 (Postgres/Patroni), K3 (Kafka KRaft),
  K5 (MQTT/EMQX), K6 (MinIO erasure-coded) HA designs — they're validated
  in isolation but were never merged into `docker-compose.yml`. Either plan
  the integration work or update the documents that currently read as
  "production-ready HA" to be explicit that they describe a validated,
  not-yet-deployed design.
- [ ] Investigate Redis Sentinel's recurring "tilt mode" episodes (one
  lasting >90 minutes over a 24h window) — while tilt is active, automatic
  failover is suspended. Likely the same root cause as the host instability
  finding above, but confirm rather than assume.
- [ ] Put device certificate rotation on a calendar (current expiry
  2028-09-22/23 — no urgency, but don't let it become urgent).

## Already verified clean — no action needed

- Kafka SASL credentials sourced from `.env`, no hardcoded literal live.
- CIM tenant isolation enforced and verified (cross-tenant request → 404).
- Redis Sentinel failover works automatically in ~5s when not in tilt mode;
  FastAPI's Sentinel-aware client requires no manual reconfiguration.
- FastAPI/MQTT/Kafka/TimescaleDB/Portal all recover cleanly from a graceful
  restart in 5-15 seconds, confirmed live.
- `.env` correctly gitignored, never committed.
- No near-term certificate expiry risk.
