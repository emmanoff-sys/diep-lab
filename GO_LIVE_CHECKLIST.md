# DIEP v1.0 — Go-Live Checklist

Derived from this RC's qualification (`QUALIFICATION_REPORT.md`). Items are
grouped by priority; each names the exact gap and the specific fix, not a
vague "harden security" placeholder.

## Update, 2026-06-26 (remediation sprint)

- [x] **`GET /telemetry/latest` has no authentication — CLOSED.**
  `fastapi/app.py`'s `latest_telemetry()` now requires `require_role(viewer/
  operator/engineer/admin/service)` and scopes the query by tenant (joins
  through `devices.tenant_id`); access is logged via `auth.audit()`. 6
  automated tests added (`tests/test_fastapi_telemetry_auth.py`), all
  passing. **Also found and fixed a deployment-integrity bug discovered
  while verifying this live**: the `diep-fastapi` container had been
  bind-mounted from the main checkout, not this RC worktree, so the fix
  was not actually live until the container was recreated from the correct
  source — see the new "Deployment Source Verification" permanent control
  below, and `validation/evidence/rc2_fastapi_bindmount_correction.txt` for
  full before/after evidence (live 401 unauthenticated, live tenant
  isolation with real minted JWTs, zero regressions).

## Permanent release gate — Deployment Source Verification

**Before every qualification or production deployment**, for every
bind-mounted service: verify `docker inspect <container> --format
'{{json .Mounts}}'` and the `com.docker.compose.project.*` labels actually
point at the intended git worktree/branch, not just that a compose file or
relative path *exists*. A standalone compose file, a relative bind mount,
or a recent `docker compose restart` are **not** evidence of what's
actually live — `restart` does not change which directory a relative mount
resolves from. This is now the third service this class of bug has hit
(`diep-ingestor`, `mosquitto/config/acl`, and now `diep-fastapi`) — treat it
as a standing release-gate check, not a one-off fix, on every service in
`docker-compose.yml` before signing off on a deployment.

## Must-fix before production go-live (P0)

- [x] ~~`GET /telemetry/latest` has no authentication~~ — **CLOSED**, see
  "Update, 2026-06-26" above.
- [ ] **Prometheus, Alertmanager, kafka-ui, cAdvisor, Node-RED admin API are
  unauthenticated on all interfaces.** Bind to `127.0.0.1` (matching Phase
  22 SEC-4's treatment of the data services) and/or put behind the
  Caddy auth boundary; for Node-RED specifically, wire up `adminAuth` in
  `settings.js` against the existing `nodered/.config.users.json`.
- [x] ~~Backup success is not actually monitored~~ — **CLOSED, and this item
  was actually a false finding from the original qualification pass.**
  `scripts/backup-db.sh` already wrote `diep_last_backup_timestamp_seconds`
  and already called `alert_backup_failure()` on failure (Phase 22 MON-5);
  the qualification session had read/run the main checkout's stale copy by
  mistake. `diep-node-exporter` had the same wrong-checkout bind-mount bug
  (fixed alongside `diep-fastapi`'s), which is why even a correct metric
  write wasn't reaching Prometheus. Live-verified 2026-06-26: metric
  updates and is visible in Prometheus within one scrape interval,
  `BackupFailed` posts to and resolves from Alertmanager correctly, real
  SMTP delivery confirmed via Alertmanager's logs. See
  `validation/evidence/rc2_backup_monitoring_correction.txt`.
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
