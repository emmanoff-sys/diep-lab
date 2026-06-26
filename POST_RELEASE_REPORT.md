# DIEP — Post-Release Report (v1.0.0)

**Date:** 2026-06-26
**Tag:** `v1.0.0` @ `d83064935bdd3be69b5ed86e70355721715fa201`, pushed to
`origin/main` (`git@github.com:emmanoff-sys/diep-lab.git`).

---

## 1. Release summary

DIEP v1.0.0 combines two previously-diverged lines of work that had been
unmerged since both branched from the same commit (`main` @ `238a70e`):

- `feature/dlms-driver` → `release/v1.0-rc-qualification` → `release/v1.0-rc2`
  (33 commits): DLMS/COSEM driver, AMI contract, MDM, OPC UA connector,
  CIM/IEC 61968 adapter, full RC qualification (performance/capacity/HA/
  soak/security), the `/telemetry/latest` auth fix, the deployment-source-
  integrity audit and remediation.
- `feature/adms-topology-import` (3 commits): GeoJSON/CIM bulk topology
  importer, `POST /topology/versions`, network-model-version audit
  stamping.

These were reconciled via `release/v1.0-rc2` (a clean, zero-conflict
`git merge`), validated, cut over to production (`diep-fastapi`), and
merged into `main` as `d830649`, tagged `v1.0.0`.

## 2. Deployment summary

- `diep-fastapi` recreated from `release/v1.0-rc2`: 14.5s cutover, ~26s to
  fully `/readyz`-ready, zero regressions (see `PRODUCTION_CUTOVER_REPORT.md`).
- `sql/021_network_electrical.sql` applied to the live database
  2026-06-26T15:04:35Z: fixed `GET /topology/validate` and `GET
  /topology/adjacency` (both 500 → 200), confirmed live with real data (see
  `DATABASE_MIGRATION_REVIEW.md`).
- `release/v1.0-rc2` merged into `main` (`d830649`), tagged `v1.0.0`, pushed
  to `origin/main` and `origin/v1.0.0`. Confirmed in sync with the remote
  post-push (`git rev-list --left-right --count origin/main...main` → `0 0`).
- 10 of 31 running containers (`fastapi`, `cim`, `ingestor`, `mdm`,
  `opcua-connector`, `node-exporter`, `prometheus`, `wal-shipper`,
  `grafana`, `redis-exporter`) are correctly sourced from a Release 1.0
  worktree (`fastapi` from `release/v1.0-rc2`; the other 9 from
  `release/v1.0-rc-qualification`, content-identical to `rc2` for every
  file they mount).

## 3. Lessons learned (carried across this entire engagement)

- **A relative bind mount resolves against whatever directory `docker
  compose` was invoked from, not against "the intended" branch.** This one
  mechanism caused or contributed to nearly every major finding across
  this engagement: `diep-ingestor`, `mosquitto/config/acl`, `diep-fastapi`,
  `diep-node-exporter`, `diep-prometheus`, `diep-wal-shipper`,
  `diep-grafana`, `diep-redis-exporter` were all, at different points,
  bind-mounted from the wrong checkout.
- **Two sibling branches can each carry live functionality the other
  lacks — "point it at the newer/more-hardened branch" is not a universally
  safe fix.** Recreating `diep-fastapi` from the RC worktree (to close the
  telemetry-auth gap) silently removed `POST /topology/versions` until this
  was caught and the branches were reconciled. Always diff *both*
  directions before recreating a service from a different source.
- **A "fixed" finding should be re-verified against the live system, not
  just the worktree used to test it.** The backup-monitoring gap was
  "corrected" twice before the real root cause (the host crontab always
  runs from the main checkout) was found on a third pass.
- **`docker run --env-file` does not strip inline comments the way
  `docker-compose`'s `env_file:` does** — caused a throwaway test
  container to silently run with auth disabled.
- **Docker silently creates a bind-mount source as an empty directory if
  it doesn't exist** — caused a real (caught-and-fixed) regression when
  `diep-prometheus` was recreated from a worktree that had never had its
  gitignored runtime secrets directory populated.
- **A live, reachable-database test failure is real signal, not noise** —
  the topology importer's own test caught `sql/021`'s un-applied state,
  which turned out to already be breaking two production endpoints,
  independent of anything in this engagement's later sprints.

## 4. Known limitations at this release (full detail in `KNOWN_LIMITATIONS.md`)

- Operational-interface authentication (Prometheus, Alertmanager,
  kafka-ui, cAdvisor, Node-RED admin API) — still open.
- Backup-monitoring's freshness metric is not wired to the *actual*
  cron-scheduled backup runs — the host crontab still runs from a
  checkout whose branch-divergence root cause this release resolves, but
  the crontab itself has not yet been repointed (see §5).
- Redis replication (`redis_connected_slaves` observed at 0, live,
  uninvestigated root cause — possibly related to the documented Sentinel
  "tilt mode" pattern, not confirmed).
- Single-broker Kafka (RF=1) — by design for this pilot scale, not yet
  addressed for production.
- Host write-durability defect (`HOST_VM_INSTABILITY_FINDINGS_20260624.md`)
  — still not confirmed fixed at the hypervisor/host level.
- Production hardware sizing and a true multi-day soak — not yet done;
  this engagement's soak testing was bounded to ~30 minutes.
- TLS is additive (Caddy), not enforced — legacy plaintext ports still work.
- Two RC worktrees (`dlms-driver-validation`, `rc2-reconciliation`) and the
  original main checkout (still on `feature/adms-topology-import`) remain
  as three separate live bind-mount sources for different subsets of the
  31 running containers. Content-identical where they overlap, but this is
  a deployment-source-integrity item in its own right — see §5 and
  `RELEASE_COMPLETE.md`'s backlog.

## 5. Deferred enhancements / explicitly not done in this release

- **Applying the rest of the reconciliation to the live container fleet.**
  Only `diep-fastapi` was cut over to `release/v1.0-rc2` specifically. The
  other 30 containers were not touched in this closure sprint — touching
  them (especially the 21 still sourced from the original main checkout,
  which itself has not been switched to `main`) requires the same
  one-at-a-time, verify-after-each-step discipline used for `fastapi`,
  `prometheus`, `wal-shipper`, `grafana`, and `redis-exporter` earlier in
  this engagement. This was explicitly deferred during worktree
  consolidation (Phase 6) rather than rushed — see `RELEASE_COMPLETE.md`'s
  remaining backlog for the recommended approach.
- **Repointing the production crontab** (`backup-db.sh`,
  `backup-pg-basebackup.sh`, `backup-config.sh`, `verify-backup.sh`) at a
  `main`-based checkout, once one exists as the permanent live source.
- **Deleting the now-fully-merged feature/RC branches**
  (`feature/adms-topology-import`, `feature/dlms-driver`,
  `release/v1.0-rc-qualification`, `release/v1.0-rc2`). Not done — see
  `RELEASE_COMPLETE.md` for why this is deliberately left as a follow-up
  decision rather than an automatic cleanup action.
- Operational-interface auth, Redis replication investigation, Kafka HA,
  host instability resolution, hardware sizing, multi-day soak — all
  pre-existing, all still open, none addressed in this closure sprint
  (out of scope: "no new features, no refactoring, no architecture
  changes").

## 6. Operational recommendations

1. **Before any further deployment-source work**, decide where the single,
   permanent, `main`-based live checkout should live — likely the existing
   main checkout directory (`/home/emmanoff_lab/projects/diep-lab`), once
   its branch is switched to `main` via the same careful, per-container
   migration process already proven safe in this engagement (not an
   in-place `git checkout` while 21 containers are live-mounted from it).
2. Once that's done, retire `dlms-driver-validation` and `rc2-reconciliation`
   as worktrees (their content is now fully part of `main`) and repoint the
   production crontab.
3. Decide on `sql/021`'s seed-data scope going forward — it was applied as
   a one-time backfill for the Abuja Site A pilot; future sites/imports
   should rely on the bulk importer (`topology/loader.py`) or
   `POST /topology/nodes`/`POST /topology/edges`, not a repeat of this
   specific migration.
4. Schedule the still-open P0/P1 items from `GO_LIVE_CHECKLIST.md`
   (operational-interface auth foremost) before scaling beyond this
   release's tested load.
5. Investigate `redis_connected_slaves=0` before relying on Redis Sentinel
   failover in a real incident.
