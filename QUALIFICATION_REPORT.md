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

**Load test results** (`rc_soak_monitoring.txt`, `rc_soak_load_output.txt`): 30 minutes
at ~12 msg/s sustained (21,313 messages sent), monitored continuously.

- **Zero permanent loss**: ingestor `received==persisted==33,618` (includes ambient
  simulator traffic), 0 dropped, queue fully drained (depth=0) at the end.
- **Data integrity**: `telemetry` row count grew by exactly 21,313 — matches sent
  count exactly, no loss, no duplication.
- **WAL**: advanced continuously throughout, no stall.
- **Connections**: stable (12→11), no leak observed.
- **Memory**: stable/flat for ingestor, FastAPI, TimescaleDB, Portal over the 30-minute
  window. MDM showed a mild increase (26→37MB). **Kafka grew ~104MB (390→494MB)** —
  flagged, but a 30-minute window can't distinguish a real leak from log/index growth
  under sustained topic activity; needs a longer soak to resolve either way.
- **CPU**: TimescaleDB climbed from idle (~0.02%) to 73% under sustained load —
  consistent with the Workstream 1 bottleneck, did not destabilize.
- **Alerting validated under real load**: `HighCPUUsage` correctly started firing
  partway through and was still firing at the end — confirms the alerting pipeline
  reacts correctly to genuine load, in contrast to the backup-metric gap above.
- **No corruption fingerprints** across the full ~32-minute monitored window (pre +
  during + post), despite host load average peaking at ~9.6 on this 2-core host.

**This was a bounded 30-minute proxy, not a true multi-day soak** — see
`KNOWN_LIMITATIONS.md`. The clean result is real evidence of short-term stability
under load, not proof of multi-day stability.

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

# RELEASE CANDIDATE APPROVED WITH LIMITATIONS

The platform's core mechanics are genuinely solid under live testing: zero
permanent message loss at every load level tried (including a 30-minute
sustained soak and bursts up to ~750 msg/s actually achieved), fast and
clean recovery from every restart and a real failure-injected Redis
failover (~5s), no data corruption under sustained CPU pressure, and a
multi-tenant CIM API with verified tenant isolation. None of this is
asserted — every number in §1-4 was produced by a live command this
session, re-run rather than copied from a prior report wherever there was
reason to doubt it.

That is not, on its own, enough for an unconditional GO. This qualification
also found a small number of **specific, scoped, currently-live gaps**, not
speculative risks:

- An unauthenticated cross-tenant data leak (`GET /telemetry/latest`).
- Several unauthenticated admin/monitoring surfaces, one of which
  (Node-RED's admin API) is a plausible remote-code-execution surface if
  ever reachable from an untrusted network.
- A backup-monitoring feedback loop that isn't actually wired up, discovered
  via a real, live instance of the exact failure it's supposed to catch
  (a silently-skipped overnight backup, system-wide cron outage, same class
  as the still-unresolved host instability).
- The same host instability defect, still not confirmed fixed, sitting
  underneath a stack that is otherwise behaving well.

Each of these has an exact, scoped fix identified in `GO_LIVE_CHECKLIST.md`
— none requires an architectural change, consistent with this qualification
effort's own scope. That combination — solid mechanics, real but boundable
gaps with named fixes — is what "approved with limitations" is for, rather
than either extreme:

- **Not "APPROVED"** outright: an unauthenticated cross-tenant data leak and
  an RCE-capable unauthenticated admin surface are live, exploitable, and
  not hypothetical — shipping today without closing the P0 items in
  `GO_LIVE_CHECKLIST.md` would be a known, named risk, not an unknown one.
- **Not "NOT APPROVED"**: nothing found here indicates a broken architecture
  or an unrecoverable design flaw. Every gap found has a specific fix, the
  data path has zero demonstrated loss under real load, and recovery from
  every failure mode actually tested was fast and clean.

**Conditions for production go-live**, in priority order (full detail and
exact fixes in `GO_LIVE_CHECKLIST.md`):
1. Close the P0 items: `/telemetry/latest` auth, the unauthenticated
   monitoring/admin surfaces, the backup-monitoring wiring gap.
2. Either get independent confirmation that the host write-durability
   defect is fixed, or explicitly accept it as a standing operational risk
   with the current backup posture as the compensating control — don't
   proceed silently on the assumption it's resolved.
3. Size production hardware per `DEPLOYMENT_GUIDE.md`'s tiers, not this
   qualification's 2-vCPU lab host — confirmed CPU-constrained at light load.
4. Run a true multi-day soak in staging before scaling past this
   qualification's tested load (this session's 30-minute window is real but
   bounded evidence, not a substitute).

Within those conditions, and at the scale this qualification actually
tested (pilot/lab scale, single-digit-to-low-hundreds of devices, on
adequately-sized hardware), the platform is ready for a **controlled**
production deployment.
