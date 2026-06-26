# DIEP v1.0 — Final Release Recommendation

**Date:** 2026-06-26
**Inputs:** `DEPLOYMENT_INVENTORY.md`, `CONFIGURATION_DRIFT_REPORT.md`,
`SERVICE_RECONCILIATION_REPORT.md`, `RELEASE_MANIFEST_v1.0.md`, and one
finding (§2 below) surfaced while researching this recommendation that
isn't captured in the earlier four documents and is added here in full.

---

## 1. What this audit fixed

10 of 31 running containers are now confirmed, live-verified, traceable to
the Release 1.0 worktree (`release/v1.0-rc-qualification` @ `8180a200`):
`fastapi`, `node-exporter` (corrected prior session), and `cim`, `ingestor`,
`mdm`, `opcua-connector` (already correct), plus `redis-exporter`,
`grafana`, `wal-shipper`, and `prometheus` (corrected this audit, with one
regression found and fixed along the way — see
`SERVICE_RECONCILIATION_REPORT.md` §4.4). Prometheus now correctly loads all
qualified alert rules, including the entire backup/WAL dead-man's-switch
group that had silently never been active.

## 2. A new, more fundamental finding: this is not one wrong branch, it's
two branches, each missing the other's live functionality

Every fix so far in this audit (and the prior session's) proceeded from a
mental model of "the worktree has the right code, the main checkout has
stale/wrong code, point everything at the worktree." **That model is
incomplete, and acting on it has already caused one real, live functional
regression.**

Git topology, checked directly for this recommendation:

- `main` tip: `238a70e`.
- `feature/adms-topology-import` (checked out in the main checkout
  directory) and `feature/dlms-driver` (the ancestor of this RC worktree's
  `release/v1.0-rc-qualification`) are **sibling branches**, both forked
  from `main` at the exact same commit `238a70e`. Neither contains the
  other's work. `feature/adms-topology-import` has 3 commits not on
  `feature/dlms-driver`'s line; `feature/dlms-driver` has 14 (plus 18 more
  on the RC worktree) not on `feature/adms-topology-import`'s line.

The 3 commits unique to `feature/adms-topology-import`
(`8bab151`, `c1b52fc`, `d411dcc` — all from **today**, 2026-06-26, i.e. this
is the user's actively in-progress branch, not stale work) modify:

- `fastapi/routers/topology.py` — adds `POST /topology/versions`.
- `fastapi/common.py` — adds `current_model_version()`.
- `fastapi/routers/{automation,controls,dms,oc_flisr,oms}.py` — wires
  network-model-version stamping into every audit-relevant write path.
- `sql/024`, `sql/025` — supporting schema fixes.
- A new standalone `topology/` CLI package (GeoJSON/CIM importer) — not
  bind-mounted into any running container, invoked manually; unaffected by
  any of this audit's container actions.

**None of this exists on `release/v1.0-rc-qualification`.** Confirmed live:

```
GET  /topology/versions  -> 404
POST /topology/versions  -> 404
```

against the currently-running `diep-fastapi` — which was recreated from the
RC worktree in the *prior* session, in the name of closing the
`/telemetry/latest` auth gap. That fix was correct and necessary, and the
telemetry-auth verification done at the time was thorough and accurate **for
what it checked**. It did not check whether the recreation removed
functionality that had been live from the other branch — and it had: the
`/telemetry/latest` security fix and the topology-versioning feature were
never on the same branch until this gap was found just now. This is a
genuine, currently-live regression, not a hypothetical risk, caused by
treating "the RC worktree" as unconditionally authoritative for a service
that was actually receiving contributions from both lines of work.

**This was not corrected in this audit.** Restoring it requires either
cherry-picking the 3 commits onto the RC worktree's branch or merging the
two branches — both are git-history actions on the user's actively open
feature branch, which this audit's mandate ("no architectural changes, no
API redesign") does not cover and which deserve the user's own decision
about how their concurrent branches should be reconciled, not a unilateral
fix buried inside a deployment-integrity audit.

## 3. Other items still open (carried from the four reports above)

- **Backup monitoring's success path is not live in production** (only in
  this audit's evidence, via a manual test run). The real, cron-scheduled
  `backup-db.sh`/`backup-pg-basebackup.sh` always execute from the main
  checkout, whose committed versions (on `feature/adms-topology-import`)
  lack the freshness-metric code that exists only on
  `release/v1.0-rc-qualification`. Same branch-divergence root cause as §2,
  on host cron rather than in a container — no Phase 4 action could reach
  it.
- **`mosquitto/config/acl`'s correct, live content has no committed home**
  on the main checkout's branch (uncommitted working-tree edit only,
  coincidentally matching the RC worktree's committed content).
- Operational-interface authentication (Prometheus, Alertmanager, kafka-ui,
  cAdvisor, Node-RED) — out of this audit's scope, unchanged from
  `GO_LIVE_CHECKLIST.md`'s existing P0 item.
- `redis_connected_slaves == 0` (now correctly alerting, for the first time,
  via this audit's Prometheus fix) — a real, pre-existing condition,
  uninvestigated; likely related to the documented Sentinel "tilt mode"
  pattern but not confirmed.

---

## 4. Recommendation

# 2 — Merge after configuration reconciliation

**Not** "Merge Release 1.0 into main" as originally framed: that action
alone would re-create §2's regression in the opposite direction, discarding
`feature/adms-topology-import`'s 3 commits the same way `feature/dlms-driver`'s
work was previously missing from the main checkout. **Both branches carry
live, real, currently-deployed functionality the other lacks.** A clean
release requires reconciling them with each other before either is treated
as the single source of truth — not just reconciling configuration around
a single, already-correct branch, which was this engagement's working
assumption up to this point.

**Why not Option 1 (merge as-is):** would regress the topology-versioning
feature on the next deployment from main.

**Why not Option 3 (do not merge):** the deployment-source-integrity problem
this whole engagement has been chasing — 25 of 31 containers untracked
against any single coherent branch — does not resolve itself by leaving
things as they are; every week this continues, the two branches' unmerged,
overlapping-on-the-same-files work gets harder to reconcile, and the
current live stack remains a hand-assembled, non-reproducible combination
of two diverged branches that nothing in version control actually
describes.

**Concrete reconciliation steps, in order, before merging to `main`:**

1. Decide, with the user, how `feature/adms-topology-import`'s 3 commits
   and `release/v1.0-rc-qualification`'s 32 commits should combine —
   likely a merge or rebase of one onto the other, touching
   `fastapi/common.py` and the 5 routers in §2 (the only real overlap risk;
   everything else in both branches is in non-overlapping files/services).
2. Re-run this audit's container-recreation pattern for `fastapi` once that
   combined branch exists, and re-verify both the telemetry-auth fix *and*
   the `/topology/versions` endpoint live together.
3. Resolve the backup-monitoring cron gap (§3) as part of the same merge —
   it's the same two files (`backup-db.sh`, `backup-pg-basebackup.sh`) that
   need the same reconciliation treatment, just on a host cron path instead
   of a container.
4. Decide what to do about `mosquitto/config/acl`'s uncommitted edit (commit
   it to whichever branch becomes authoritative).
5. Only then merge the reconciled branch to `main`, and repoint the
   production crontab and any remaining `docker compose` operations at a
   single, post-merge checkout — closing the deployment-source-integrity
   gap permanently rather than container-by-container.

This is real, verified progress, not a stall: 10 of 31 containers are now
correctly and reproducibly sourced, a live alerting gap (the entire backup/
WAL dead-man's-switch) is now active for the first time, and the
single most consequential finding of this entire audit — that two
unmerged branches are both partially live in production — is now visible
and precisely scoped, where before it was invisible.
