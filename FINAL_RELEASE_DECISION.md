# DIEP Release 1.0 — Final Release Decision

**Date:** 2026-06-26
**Inputs:** `PRE_CUTOVER_REPORT.md`, `DATABASE_MIGRATION_REVIEW.md`,
`PRODUCTION_CUTOVER_REPORT.md`, `RELEASE_MANIFEST_v1.0.md`.

---

# DEPLOYMENT SUCCESSFUL

# READY TO MERGE TO MAIN

---

## Supporting evidence

1. **Cutover executed cleanly.** `diep-fastapi` recreated from
   `release/v1.0-rc2` in 14.5s (command) / ~26s (to fully `/readyz`-ready),
   within/near the expected 5–15s window once the service's normal
   pip-install startup overhead (present on every prior recreation in this
   engagement, not new) is accounted for. Zero conflicts, zero rollback,
   zero pause-on-regression triggers.
2. **Zero functional regressions, checked directly, not assumed:**
   telemetry authentication, tenant isolation, FastAPI readiness, the AMI/
   MDM/OPC-UA/CIM services (code untouched by the merge, confirmed
   independently healthy), Portal, Grafana, Prometheus, Alertmanager,
   Redis, Kafka, and TimescaleDB all match or exceed pre-cutover baseline.
3. **The headline objective is restored and live:** `POST /topology/versions`
   now exists and is auth-gated (confirmed via live 401/405 responses);
   `GET /topology/version` returns real, live data. The functionality the
   entire Branch Reconciliation Sprint existed to recover is now actually
   running in production, not just merged in a branch.
4. **The one substantive finding from this sprint — `sql/021`'s live
   impact on `/topology/validate` and `/topology/adjacency` — is
   independently pre-existing**, confirmed to already be broken on the
   *pre-cutover* container, unrelated to this deployment's success or
   failure. It does not meet the bar for "regression caused by this
   cutover," and `POST /topology/versions` (what this sprint's success
   criteria actually asks for) is unaffected by it.

## What "ready to merge to main" does *not* mean

It does not mean every open item from this entire engagement is resolved.
Carried forward, explicitly, rather than implied away:

- **`sql/021` migration:** recommended for application (see
  `DATABASE_MIGRATION_REVIEW.md`), not yet applied. Fixes two already-broken
  read endpoints; independent of the merge-to-main decision.
- **Two RC worktrees currently serve the live stack simultaneously**
  (`rc2-reconciliation` for `fastapi`; `dlms-driver-validation` for the
  other 9 previously-corrected services) — content-identical for every
  file either one mounts, so no functional gap, but worth consolidating
  onto one worktree as a follow-up, not a blocker.
- **Operational-interface authentication** (Prometheus, Alertmanager,
  kafka-ui, cAdvisor, Node-RED) — unchanged, still open, from the original
  qualification.
- **Backup-monitoring's host-cron gap** — unchanged. Note: merging
  `release/v1.0-rc2` to `main` (Phase 8) and eventually repointing the
  crontab at the merged result is the actual fix for this, since it
  resolves the branch-divergence root cause — but that repointing is a
  separate, future action, not automatic from a `main` merge alone.
- **Redis replication (`redis_connected_slaves=0`), single-broker Kafka,
  host write-durability defect, production hardware sizing, true
  multi-day soak** — all unchanged, all pre-existing, all out of this
  sprint's scope.

None of these block the conclusion above: they are unrelated to whether
*this* deployment succeeded, and none regressed as a result of it.

## Rollback point (recorded, not exercised)

Pre-cutover state, if ever needed: recreate `diep-fastapi` from
`release/v1.0-rc-qualification` @ `2dd9763`
(`.claude/worktrees/dlms-driver-validation`) using the same
`--force-recreate` pattern. No data migration is involved in either
direction — the only state change was which code the container runs.

## Recommendation

Proceed to Phase 8 (merge preparation only, per this sprint's explicit
instruction not to execute the merge without separate authorization).
