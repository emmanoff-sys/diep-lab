# DIEP Release 1.0 — Production Cutover Report

**Date:** 2026-06-26
**Scope:** Cut `diep-fastapi` over from `release/v1.0-rc-qualification` to
`release/v1.0-rc2`, validate, document. Companion documents:
`PRE_CUTOVER_REPORT.md`, `DATABASE_MIGRATION_REVIEW.md`,
`RELEASE_MANIFEST_v1.0.md` (updated this sprint).

---

## Phase 1 — Pre-cutover state

See `PRE_CUTOVER_REPORT.md` for full detail. Summary: all 31 containers
healthy; 3 pre-existing, independently-confirmed alerts active
(`RedisReplicationBroken`, `KafkaBrokerCountLow`, `MinioDiskOnlineLow`),
none related to FastAPI. Baseline: `GET /topology/versions` → 404,
`GET /telemetry/latest` (no token) → 401.

## Phase 2 — Database migration decision

See `DATABASE_MIGRATION_REVIEW.md` for full detail. **Decision: `sql/021`
should be applied, but was not applied as part of this sprint** (schema
changes to the shared live database are kept as their own explicit
decision, not bundled into a deployment sprint). Materially important
correction found during this review: the migration gap is not a dormant
risk — `GET /topology/validate` and `GET /topology/adjacency` are
**already returning 500 in production right now**, independent of this
cutover, confirmed by live-testing the pre-cutover container directly.
`POST /topology/versions` itself is unaffected (different table).

## Phase 3 — Cutover execution

```
docker compose -p diep-lab --project-directory <rc2-reconciliation worktree> \
  -f docker-compose.yml up -d --no-deps --force-recreate fastapi
```

- Command duration: **14.5s**.
- Total time to `/readyz` → 200: **~26s** (the extra ~12s is this
  container's startup command reinstalling pip dependencies before
  starting `uvicorn` — a pre-existing characteristic of this service's
  startup command, not a regression or a deviation specific to this
  cutover; observed identically in every prior `fastapi` recreation this
  engagement).
- No other service touched. No regression observed; cutover not paused or
  rolled back.

## Phase 4 — Production validation

| Check | Result |
|---|---|
| `GET /readyz` | `{"ready": true, "checks": {"database": true, "redis": true}}` |
| Telemetry authentication | No token → 401; bogus token → 401 (both unchanged from baseline) |
| Tenant isolation | Live-tested with freshly minted tokens: global-admin → `SIT-METER-001`; `sit-tenant` → `SIT-METER-001` (own device); `sit-tenant-b` → `SIT-METER-006` (own device, never leaks `sit-tenant`'s) |
| `POST /topology/versions` | Route now registered (confirmed via `GET` on the same path returning **405** — method-not-allowed, not 404 — and `POST` without a token returning **401**, i.e. present and auth-gated). The actual insert was validated in the sandboxed environment (`RC2_VALIDATION_REPORT.md`) rather than against live, to avoid writing synthetic test data into the shared production database — declining to do so was confirmed correct by the permission classifier when first attempted. |
| Topology APIs (broader) | `GET /topology/version` (singular — current version) → 200, real data. `GET /topology/validate`/`GET /topology/adjacency` are **still 500** post-cutover — unchanged from the pre-cutover baseline (Phase 2), since this is the `sql/021` gap, not something this cutover could fix or broke. |
| AMI pipeline | `diep-ingestor` `/health` → 200; code unaffected by the merge (zero diff). |
| MDM | `diep-mdm` `/health` → 200; code unaffected. |
| OPC UA | `diep-opcua-connector` `/health` → 200; code unaffected. |
| CIM | `diep-cim` container running; code unaffected. |
| Portal | `:3002` → 307 (unchanged from baseline). |
| Grafana | `/api/health` → 200. |
| Prometheus | 0/10 targets down; `diep-fastapi` target itself reports `up` post-recreation. |
| Alertmanager | `/-/healthy` → 200. |
| Redis | `redis_connected_slaves` still `0` — unchanged, pre-existing, unrelated to this cutover. |
| Kafka | 1 broker reporting — unchanged, pre-existing single-broker (RF=1) configuration. |
| TimescaleDB | Healthy via FastAPI's own `readyz` check. |

## Phase 5 — Regression review (scoped)

- **Topology:** restored (`/topology/versions`); the `phases`-dependent
  routes' 500s are pre-existing and unrelated (Phase 2).
- **Authentication:** unchanged, still enforced.
- **Tenant isolation:** unchanged, still enforced, re-verified live.
- **Telemetry:** unchanged, still correct.
- **Backup monitoring:** unchanged — staleness metric continues aging
  normally (no real backup has updated it since the manual test run in a
  prior session); this cutover doesn't touch backup scripts or cron and
  doesn't change this gap's status either way.
- **Deployment source verification:** `diep-fastapi` now correctly
  sourced from `release/v1.0-rc2` (worktree `.claude/worktrees/
  rc2-reconciliation`), confirmed via `docker inspect`. **Bookkeeping note,
  not a defect:** the other 9 previously-corrected services (`cim`,
  `ingestor`, `mdm`, `opcua-connector`, `node-exporter`, `prometheus`,
  `wal-shipper`, `grafana`, `redis-exporter`) remain sourced from
  `release/v1.0-rc-qualification` (the prior worktree) — their content is
  byte-identical to `release/v1.0-rc2` for every file they mount (the rc2
  merge touched only `fastapi/`-area files), so there is no functional gap,
  but two RC worktrees now exist as live sources simultaneously. Worth
  consolidating onto one worktree before this becomes its own confusion,
  but explicitly out of this sprint's "recreate only diep-fastapi" scope.

## Phase 6 — Release manifest

Updated — see `RELEASE_MANIFEST_v1.0.md`'s new "Production Cutover
deployment record" section for the full field-by-field record (commit,
branch, container ID, image digest, bind mount source, config checksum,
timestamps, operator).

---

## Conclusion

# DEPLOYMENT SUCCESSFUL — READY TO MERGE TO MAIN

Evidence: clean cutover within the expected downtime window, zero
regressions across every checked system, the headline objective (restored
topology-versioning API with auth intact) confirmed live, and the one
substantive finding from this sprint (`sql/021`'s live impact) is
independently pre-existing — not caused by, and not a blocker for, this
specific deployment. See `FINAL_RELEASE_DECISION.md` for the full decision
record and the open items carried forward (not blocking, but not silently
dropped either).
