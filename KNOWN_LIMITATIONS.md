# DIEP v1.0 — Known Limitations

Consolidated from this RC's qualification work (`QUALIFICATION_REPORT.md`) and
carried-forward items from prior validation/SIT reports that are still open.
Every item here is either independently verified during this qualification
or explicitly marked as carried forward from an earlier report without
re-verification.

## Performance / scale

- **~15 msg/s sustained throughput ceiling** on the AMI → MDM → ingestor →
  FastAPI → TimescaleDB path, bottlenecked at TimescaleDB's single-row
  `INSERT` write path (87% CPU at peak). Re-confirmed 2026-06-26, no
  regression. At 15-minute AMI polling intervals this supports ~13,500
  meters in throughput terms alone — see `DEPLOYMENT_GUIDE.md` for why the
  *host's* own headroom is the tighter constraint at small scale.
- **This host (2 vCPU / 7.2GB RAM) already shows CPU spiking to ~99.9% and
  swap in active use at today's light (10-device) load.** Capacity planning
  in `QUALIFICATION_REPORT.md` §2 is throughput-bound; the host itself is a
  second, currently tighter constraint that wasn't part of the original
  ~15 msg/s figure.
- A true multi-day/multi-week soak was not performed — this qualification's
  soak test was a bounded ~30-minute window (see `QUALIFICATION_REPORT.md`
  §4). Run a real extended soak in staging before scaling much beyond this
  qualification's tested load.
- During that 30-minute soak, Kafka's memory grew ~104MB (390→494MB) while
  every other service was flat. Not conclusively a leak vs. log/index
  growth under sustained topic activity — a 30-minute window can't tell the
  difference. Worth a specific check during the real extended soak above.

## High Availability

- **Only Redis (Sentinel) and PITR/backups are actually deployed as HA in
  production.** The K2 (Postgres/Patroni), K3 (Kafka KRaft 3-broker), K5
  (MQTT/EMQX cluster), and K6 (MinIO erasure-coded) designs are validated
  only in isolated, never-merged `docker-compose-*-ha-validation.yml` files.
  Production runs single-instance Kafka, TimescaleDB, Mosquitto, and MinIO —
  each recovers via restart (confirmed clean, 5-15s) but has no live
  failover. If any of these documents are read as "production-ready HA,"
  that claim is about the validated design, not the deployed reality.
- **Redis Sentinel's automatic failover is suspended during "tilt mode,"**
  which this host's Sentinel instances entered and exited repeatedly over a
  24h window (one episode >90 minutes), correlated with the documented host
  CPU/IO instability. A failover attempted during a tilt episode has not
  been tested and should not be assumed to behave like this qualification's
  clean ~5s result.
- Docker's `restart: unless-stopped` does not auto-recover a container after
  `docker kill`/`docker stop` — both are treated as manual actions. An
  operator must explicitly `docker start` it back. A rejoining Redis primary
  briefly (~8-20s) comes back as a second standalone master before Sentinel
  demotes it — a narrow, self-healing split-brain window.

## Backups / DR

- The system-wide cron (not just this project's entries — root's own routine
  hourly jobs too) silently failed to fire for a ~4 hour window overnight on
  2026-06-25/26, skipping the scheduled 02:00/02:30 backup jobs. Same class
  of issue as the documented host instability. No reboot occurred; cron
  simply didn't trigger.
- `scripts/backup-db.sh` does not write the `diep_last_backup_timestamp_seconds`
  metric that the `BackupStale` Prometheus alert depends on, and never calls
  the `alert_backup_failure()` helper it sources, on success or failure. The
  backup mechanics (pg_dump, checksum, MinIO upload, size-verify, retention
  prune) are real and were proven working live this session — the
  monitoring feedback loop for them specifically is not wired up. See
  `GO_LIVE_CHECKLIST.md`.
- The underlying hypervisor-level write-durability defect documented in
  `HOST_VM_INSTABILITY_FINDINGS_20260624.md` is **still not confirmed
  fixed**. The zero-backup gap it exposed has been closed (cron-installed,
  restore-tested backups — modulo the cron-reliability finding above), but
  the root cause itself remains unresolved and outside guest-level remediation.

## Security

- ~~`GET /telemetry/latest` has no authentication dependency at all~~ —
  **CLOSED 2026-06-26**, see `SECURITY_GUIDE.md`. (A related deployment-
  integrity bug surfaced while closing this — `diep-fastapi` was bind-mounted
  from the wrong checkout, so the fix wasn't live until corrected — see the
  new "Deployment Source Verification" item in `GO_LIVE_CHECKLIST.md`.)
- Prometheus, Alertmanager, kafka-ui, cAdvisor, and Node-RED's admin API are
  all reachable with zero authentication on this host's network interfaces.
  Node-RED's unauthenticated `GET /flows` is the most serious of these (its
  admin API can also deploy flows = arbitrary JS execution when `adminAuth`
  isn't enforced; this qualification only confirmed the read side).
- TLS for Portal/Grafana/API (Phase 22 SEC-3) is live but additive — the
  original plaintext ports still work in parallel, so TLS is not actually
  enforced end-to-end yet.
- The live TimescaleDB password has drifted from what's currently in `.env`
  (rotated in `.env` after the running container/volume was created, and
  Postgres doesn't reapply `POSTGRES_PASSWORD` to an existing data
  directory). A future redeploy from current `.env` would not match the
  password in active use today.
- `docker-compose-timescale.yml` (confirmed not live) has a hardcoded weak
  password, as do the various `*-ha-validation.yml`/`*-pitr-validation.yml`
  files — all dead/isolated configs, not active exposures, but a hygiene
  risk if anyone runs one by mistake.

## Carried forward from prior reports (not re-verified this session)

- DLMS/COSEM wire profile is hand-rolled (stdlib only), simplified ACSE
  body/scalar encoding, **not validated against real hardware**
  (`drivers/dlms/VALIDATION.md`).
- OPC UA connector was built and tested against `asyncua`'s documented
  surface using injected fakes; `asyncua` itself was never installed in the
  bare dev shell for this connector (only inside its own container) —
  **re-validate against a real OPC UA server with asyncua actually
  installed before connecting to real OT hardware** (`services/opcua/VALIDATION.md`).
- CIM/IEC 61968 class/attribute/unit mappings are spec-shaped from modeling
  knowledge, **not independently verified against the official UML/RDF/XSD
  artifacts** (no access to them in this environment) — see `LIMITATIONS.md`
  (CIM-specific) for the full list, including the DER-only `Asset` coverage
  gap (smartmeters have no `Asset` record by design, not a bug).
- MDM's `trusted` topic has exactly two consumers in practice (the ingestor
  and the OPC UA connector's `mdm_consumer.py`) — there is no broader
  ecosystem of trusted-stream consumers yet.
- Lower-priority SIT findings still open: telemetry reads beyond
  `/telemetry/latest` have inconsistent tenant scoping in places; MDM does
  not reconcile a device's self-reported `tenant_id` against the device
  registry's; duplicate-drop events are logged at DEBUG (invisible at
  default INFO level) in both the ingestor and MDM.
