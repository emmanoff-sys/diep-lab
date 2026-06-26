# DIEP — Release Complete

**Release 1.0 has been successfully completed.**

---

## Release record

| Field | Value |
|---|---|
| Final commit | `d83064935bdd3be69b5ed86e70355721715fa201` (merge of `release/v1.0-rc2` into `main`) |
| Final tag | `v1.0.0` |
| Deployment timestamp | `diep-fastapi` cutover: 2026-06-26T14:37:37Z; `sql/021` applied: 2026-06-26T15:04:35Z; merge/tag/push: 2026-06-26 ~15:10-15:24Z |
| Release branch | `release/v1.0-rc2` (merged into `main`; both `main` and `v1.0.0` confirmed pushed and in sync with `origin`) |
| Rollback reference | Pre-cutover state: `diep-fastapi` from `release/v1.0-rc-qualification` @ `2dd9763` (`.claude/worktrees/dlms-driver-validation`). Pre-merge state: `main` @ `238a70e`. Full rollback procedure for the `sql/021` schema change is in `DATABASE_MIGRATION_REVIEW.md`. None of these have been exercised — recorded for reference only. |

## Remaining backlog (explicitly not Release 1.0 engineering work — carried
forward as ordinary operational/development backlog)

1. **Full container fleet migration to a single `main`-based source.** Only
   `diep-fastapi` was cut over in this release. 30 other containers remain
   split across the original main checkout (still on
   `feature/adms-topology-import`, 21 containers) and the two RC worktrees
   (`dlms-driver-validation`, `rc2-reconciliation`, 9 + 1 containers).
   Recommended approach: switch the main checkout directory to `main` via
   the same one-container-at-a-time, verify-after-each-step pattern used
   throughout this engagement — never an in-place branch switch while
   containers are live-mounted on it (confirmed unsafe this session: several
   files that differ between the current checkout and `main`, including
   `mosquitto/config/acl` and `docker-compose.yml`, are live-mounted into
   running containers right now).
2. **Repoint the production crontab** at the consolidated checkout once #1
   is done.
3. **Operational-interface authentication** (Prometheus, Alertmanager,
   kafka-ui, cAdvisor, Node-RED) — open since the original qualification.
4. **Investigate `redis_connected_slaves=0`** before relying on Sentinel
   failover in a real incident.
5. **Host write-durability defect, production hardware sizing, true
   multi-day soak** — all still open.
6. **Branch cleanup** (`feature/adms-topology-import`, `feature/dlms-driver`,
   `release/v1.0-rc-qualification`, `release/v1.0-rc2`) — all fully merged
   into `main` now and safe to delete in principle, but **not deleted in
   this release** since (a) 30 containers still depend on the two RC
   worktrees as their live bind-mount source (#1 above must land first),
   and (b) branch deletion wasn't separately, explicitly confirmed beyond
   this task's "consolidate worktrees" instruction, which this release
   reads as being about worktree checkouts, not an unambiguous instruction
   to delete branch history. Recommended once #1 is complete.
7. **TLS enforcement** (currently additive only — legacy plaintext ports
   still work).

## What "complete" means here

Every phase of this Final Release Closure sprint that could be done safely
was done: `sql/021` reviewed and applied with a documented rollback
procedure, `release/v1.0-rc2` merged into `main` with zero conflicts,
`v1.0.0` tagged and pushed, release evidence confirmed archived in the
tagged tree, a clean `develop/v1.1` branch created for future work, and
this report plus `POST_RELEASE_REPORT.md` document the full record.

**One phase (worktree/branch consolidation) was completed only partially,
deliberately:** removing the two RC worktrees or switching the main
checkout to `main` in-place would have broken live, running containers
without the controlled migration process this whole engagement depended on
for safety. That remaining work is real, is listed above, and is ordinary
follow-up engineering — not a sign that Release 1.0 itself is incomplete.
The release artifact (the tagged commit, pushed and verified) is what
"Release 1.0" refers to, and that is done.

No further Release 1.0 *release* engineering work remains open. The items
above are operational backlog for whoever picks up `develop/v1.1` or the
infrastructure consolidation next — tracked, not forgotten, not blocking
this closure.
