# DIEP v1.0 — Deployment Guide

Sizing and deployment guidance derived from this RC's qualification testing
(`QUALIFICATION_REPORT.md` §1-2), not theoretical estimates. All figures are
against the actual live stack on `feature/dlms-driver`'s architecture
(AMI → MDM → ingestor → FastAPI → TimescaleDB, single-instance Kafka/
TimescaleDB/MQTT/MinIO, Redis Sentinel HA).

## Sizing Tiers

The throughput-only ceiling (~15 msg/s sustained, confirmed by load testing)
and this qualification's own test host's resource headroom (2 vCPU / 7.2GB
RAM, already spiking to ~99.9% CPU and using swap at only 10 simulated
devices) are **two separate constraints** — size for whichever binds first.

| Tier | vCPU | RAM | Meters @ 15-min polling | Notes |
|---|---|---|---|---|
| Pilot/Lab (this qualification's host) | 2 | 8GB | ~50-200 | Matches what was actually tested. CPU headroom is the binding constraint here, not the ~15 msg/s data-path ceiling — this qualification's own host already shows CPU spikes to ~99.9% and active swap use at 10 devices. Do not scale meter count up on hardware this small without re-testing headroom. |
| Small production | 4 | 16GB | ~1,000-2,000 | Gives the data path room to actually reach closer to its ~15 msg/s ceiling without the host itself being the bottleneck. Not tested directly in this qualification — sized by extrapolation, re-validate before committing. |
| Medium+ | — | — | >2,000 | **Requires the Performance section's tuning recommendations (batched/`COPY` inserts, connection pooling) to be implemented first** — the ~15 msg/s ceiling is a data-path limit, not a hardware one, and more vCPU/RAM alone won't raise it. Treat as a prerequisite, not a future nice-to-have, before sizing for a fleet this large. |

## Storage Planning

- `telemetry` hypertable: ~335 bytes/row (measured, including indexes/TOAST/
  chunk overhead — **use `hypertable_size('telemetry')`, not
  `pg_total_relation_size('telemetry')`**, which undercounts by ~750x on a
  TimescaleDB hypertable since the parent table itself holds no data).
- At full sustained ceiling (15 msg/s, 24/7): ~434MB/day raw, plateauing
  around ~39GB once the 90-day retention policy starts dropping chunks.
- `telemetry_1m` continuous aggregate: two orders of magnitude smaller,
  retained 180 days — not a meaningful storage driver by comparison.
- Plan disk headroom for backups separately: this qualification found the
  scheduled backup cron can silently miss a run during a host-instability
  episode (see `KNOWN_LIMITATIONS.md`) — budget for occasional manual
  catch-up runs, and monitor `BackupStale`/`BaseBackupStale` actively rather
  than assuming the cron alone is sufficient.

## High Availability Footprint

Only Redis (Sentinel, 3-node quorum) and PITR/backups are deployed as HA in
this stack today. Kafka, TimescaleDB, MQTT, and MinIO are single-instance
with restart-based recovery (5-15s observed in this qualification), not live
failover. If a deployment requires live failover for any of those four,
the validated-but-unmerged K2/K3/K5/K6 designs in this repo's
`docker-compose-*-ha-validation.yml` files are the starting point — they are
not currently wired into `docker-compose.yml` and would need real
integration work, not just enabling a flag.

## Network / Exposure Checklist Before Go-Live

See `SECURITY_GUIDE.md` for the full list. At minimum, before exposing this
deployment beyond a trusted lab network: bind Prometheus/Alertmanager/
kafka-ui/cAdvisor/Node-RED to loopback or put them behind authentication,
and decide whether the legacy plaintext Portal/Grafana/FastAPI ports should
be closed now that Caddy's TLS termination is live.

## What This Guide Does Not Cover

Day-2 operational procedures (startup/shutdown/backup/restore/DR drills) are
already documented in `DIEP_OPERATIONS_MANUAL.md` and
`DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md` — this guide is sizing/deployment
only; see `OPERATIONS_GUIDE.md` for the current-state pointer into those.
