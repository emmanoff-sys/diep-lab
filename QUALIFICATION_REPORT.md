# DIEP v1.0 Release Candidate — Qualification Report

**Date:** 2026-06-26
**Qualified branch:** `feature/dlms-driver` @ `5e0e81f` (AMI Contract / MDM / OPC UA / CIM/IEC 61968 / E2E SIT), qualification work on `release/v1.0-rc-qualification`
**Method:** live testing against the actual running stack on this host, not a re-statement of prior reports. Where prior evidence (`PERFORMANCE_REPORT.md`, K1-K6 HA validation reports, `CIM_INTEROPERABILITY_REPORT.md`) was reused, it was re-confirmed against the live system first, not cited on faith — consistent with this project's own prior lesson about not trusting a claimed check count or "could not verify" reason without re-running it (see `CIM_INTEROPERABILITY_REPORT.md`'s 68/68→81/81 correction, committed as part of this effort's housekeeping).

Raw command output backing every number below is in `validation/evidence/rc_*` (this branch) and the pre-existing `validation/evidence/*` (from the 2026-06-25 sprint).

---

## 1. Performance

**Throughput ceiling: ~15 msg/s sustained**, reconfirmed today with no regression from yesterday's `PERFORMANCE_REPORT.md`:
- `sustained_test.py` (`validation/evidence/rc_sustained_test_output.txt`): 8/12/15 msg/s all hold a near-empty queue (max depth 0-1) for a full 20s run; 18 msg/s oscillates/grows; 22 and 30 msg/s grow unbounded within the run but still fully drain within 180s afterward.
- `load_test.py` 6-tier burst re-run (`rc_load_test_output.txt`): the apparent "0 delivered within window" results at the 2000/5000 msg/s tiers are the same measurement-timeout artifact the original report identified, not real loss — confirmed by draining the backlog and checking the ingestor's own counters: `received==persisted==9540`, 0 dropped.
- Bottleneck unchanged: TimescaleDB's single-row `INSERT` write path (87% CPU at peak in yesterday's report).

**New: clean steady-state latency** (the one gap `PERFORMANCE_REPORT.md` itself flagged — its own latency numbers were either harness-artifact-tainted or from an overloaded state). `steady_state_latency.py` at 12 msg/s for 60s, continuous publish+poll (not batch-then-poll): **708/708 delivered, 0 lost — p50=0.66s, p95=5.34s, p99=5.72s, max=6.28s** (`rc_steady_state_latency_12mps.txt`).

**Resource snapshot** (idle baseline, `rc_resource_snapshot.txt`): MDM 26MB/0.02% CPU, OPC UA connector 20MB/0.02%, CIM 46MB/0.21%, ingestor 34MB/0.11%, FastAPI 65MB/0.22%, TimescaleDB 76MB/0.02%, Kafka 487MB/1.81% (heaviest idle footprint), MQTT 3.6MB, Portal 215MB/5.21%.

**Tuning recommendations (not implemented — out of this effort's scope per "no architectural changes"):** batch or `COPY`-based inserts into `telemetry` instead of one `INSERT` per `POST /telemetry`; a connection pool sized to the ingestor's 8 workers instead of one connection per request; consider moving the single-row write off the request path entirely (write-behind queue) if throughput beyond ~15 msg/s is required before a larger fleet onboards.

---

## 2. Capacity Planning

**Host:** 2 vCPU / 7.2GB RAM / 146GB disk (57GB free) — not the 4 vCPU the 2026-06-24 host-instability doc assumed; either resized down during remediation or that doc's assumption was wrong from the start, worth reconciling separately. Prometheus's own history shows CPU **already spiking to ~99.9% within the last 24h** on this 2-core host at today's light (10-device) load, average ~66% over 12h; memory 60% used with 2GB of 4GB swap actively in use (`rc_capacity_data.txt`). **This host has materially less headroom than the throughput ceiling alone suggests.**

**Meter-count capacity** (formula: `max_meters = sustained_ceiling_msg_s × polling_interval_s`, ceiling=15 msg/s):

| Polling interval | Max meters (throughput-bound) |
|---|---|
| 15s (DER/battery real-time) | ~225 |
| 1 min | ~900 |
| 5 min | ~4,500 |
| 15 min (typical AMI revenue interval) | ~13,500 |

These are upper bounds from the data-path bottleneck alone. **Given the host's own CPU/memory headroom is already tight at 10 devices, the realistic safe figure for this exact 2-vCPU/7.2GB host is far below the throughput-only ceiling** — see §8 verdict and `DEPLOYMENT_GUIDE.md` for sizing tiers that account for both constraints.

**Storage growth:** `telemetry` hypertable = 18MB for 57,249 rows over 10 devices / ~5.3 days = **~335 bytes/row** (note: `pg_total_relation_size()` on the bare hypertable name undercounts by ~750x on this TimescaleDB setup — chunks hold the data; use `hypertable_size()`). At the confirmed 15 msg/s ceiling run continuously: ~434MB/day, plateauing at ~39GB steady-state once the 90-day raw-telemetry retention policy starts dropping old chunks. The `telemetry_1m` continuous aggregate is two orders of magnitude smaller (688kB for the same dataset) and retained 180 days.

---

## 3. High Availability

Tested what's **actually deployed**, not the aspirational K1-K6 multi-node designs:

**Confirmed gap vs. documentation:** comparing `docker-compose.yml` against K1-K6's validation reports, only **Redis Sentinel (K4)** and **PITR/backups (K1)** were ever adopted into production. Postgres HA/Patroni (K2), Kafka KRaft 3-broker (K3), MQTT/EMQX cluster (K5), and MinIO erasure-coded (K6) exist only in isolated `docker-compose-*-ha-validation.yml` files never merged into the real stack. Production runs single-instance Kafka (`KAFKA_NODE_ID: 1`, RF=1), single-instance TimescaleDB, single Mosquitto broker (not EMQX), single MinIO.

**Redis Sentinel failover (real `docker kill`, not a restart)** — `rc_ha_redis_failover.txt`:
- Failover (kill → switch-master): **~5 seconds**, timed from Sentinel's own logs.
- FastAPI's Sentinel-aware client (`fastapi/redis_client.py`) needed no reconfiguration; every health check from t+44s onward was 200.
- **Two new findings:** (1) Docker's `unless-stopped` restart policy does **not** auto-recover a `docker kill`'d/`stop`'d container — both are treated as manual actions by dockerd, suppressing auto-restart; an operator must run `docker start` explicitly. (2) The rejoining old master briefly (~8-20s) comes back as a second standalone master before Sentinel demotes it — a real, narrow split-brain window, self-healed without further manual action.
- **Separately concerning:** Sentinel's own logs show repeated tilt-mode episodes over the prior 24h, one lasting >90 minutes, which **suspends automatic failover while active** and correlates with the documented host instability. This drill ran during a confirmed non-tilt window and succeeded cleanly — that result does not generalize to a tilt episode, which has recurred multiple times per day historically.

**Restart drills** (`rc_ha_restart_drills.txt`, light re-confirmation of yesterday's results + one new test):

| Service | Recovery | Result |
|---|---|---|
| FastAPI | 13.4s | healthy |
| MQTT | 4.8s | TLS pub/sub round trip ok |
| Kafka | 8.4s | broker count=1, clean metadata reload |
| Portal (**new**) | 14.7s | healthy auth-redirect |
| TimescaleDB | 5.3s | row count unchanged, 0 corruption fingerprints |

No regression; no stop-condition trigger on TimescaleDB.

---

## 4. Long-Duration Stability (Soak)

A bounded ~30-minute window at ~12 msg/s sustained load (not a true multi-day soak — see `KNOWN_LIMITATIONS.md`), continuously monitored. See `validation/evidence/rc_soak_*` for full detail; summary below.

**Backup completion check surfaced two real, live findings** (`rc_soak_backup_completion.txt`), not just a pass/fail:
1. The scheduled 02:00/02:30 UTC daily backup cron silently did not fire today — confirmed system-wide (root's own routine `/etc/cron.hourly` jobs also missing for a ~4h overnight window, no reboot in between), the same class of host-level stall already documented elsewhere, newly observed hitting cron rather than a container. Closed live by running `backup-db.sh` manually (succeeded, verified upload to MinIO).
2. Deeper: `backup-db.sh` **never writes** the `diep_last_backup_timestamp_seconds` metric that `BackupStale` alerts on, and never calls the `alert_backup_failure()` helper it sources, on either success or failure. The backup mechanics are real and proven; the monitoring feedback loop for them is not wired up. Not fixed in this effort (same "qualify, don't redesign" scope as the performance bottleneck) — specified as a `GO_LIVE_CHECKLIST.md` item.

[SOAK_RESULTS_PLACEHOLDER — filled in after the 30-minute window completes]

---

## 5. Security Review

Full detail in `rc_security_review.txt` and `SECURITY_GUIDE.md`. Headlines, all **live-confirmed**, not read off old docs:

1. **Prometheus, Alertmanager, kafka-ui, cAdvisor, and Node-RED's admin API are all reachable with zero authentication** on this host's network interfaces (Phase 22 SEC-4 hardened the data ports — DB/Kafka/Redis/MinIO — but not the monitoring/admin stack). Node-RED's unauthenticated `GET /flows` is the most serious: its admin API can also deploy flows, which means arbitrary JS execution, when `adminAuth` isn't enforced.
2. **`GET /telemetry/latest` has no authentication dependency at all** (not just missing tenant scope, as previously flagged) — live-confirmed returning a full cross-tenant row to an anonymous request.
3. A dead config file (`docker-compose-timescale.yml`) has a hardcoded weak password; confirmed not live. Separately, the live TimescaleDB password has drifted from current `.env`.
4. TLS for Portal/Grafana/API is live (Phase 22 SEC-3) but additive, not enforced — the original plaintext ports still work in parallel.
5. Certs: no near-term expiry risk (2028/2036). Kafka SASL credentials and CIM tenant isolation both re-confirmed correctly fixed/working.

---

## 6. Documentation Freeze

This document, plus `RELEASE_NOTES_v1.0.md`, `DEPLOYMENT_GUIDE.md`, `OPERATIONS_GUIDE.md`, `ADMIN_GUIDE.md`, `SECURITY_GUIDE.md`, `KNOWN_LIMITATIONS.md`, and `GO_LIVE_CHECKLIST.md` (all dated 2026-06-26, this branch) are the current authoritative set for v1.0, **explicitly superseding**:
- `RELEASE_NOTES_v1.0.md`'s 2026-06-13 baseline (predates AMI/MDM/OPC UA/CIM and all HA/performance/security work referenced above).
- `GO_LIVE_AUTHORIZATION_PACKAGE.md`'s 2026-06-17 NO-GO (predates the same).

The ~150 other historical phase/validation reports at the repo root are not individually re-audited here — most are dated point-in-time snapshots from completed phases, and re-litigating all of them wasn't a productive use of this qualification's scope. Where one of them made a specific claim this qualification depended on (K1-K6 HA, the CIM check count, `RELEASE_NOTES_v1.0.md`'s TLS status), it was checked against the live system, not assumed — see §3, §5.

---

## 7. Known Limitations

See `KNOWN_LIMITATIONS.md` for the full, consolidated list.

---

## 8. Final Verdict

[VERDICT_PLACEHOLDER — finalized after §4's soak results are in]
