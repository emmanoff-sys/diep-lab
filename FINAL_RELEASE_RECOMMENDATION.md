# DIEP v1.0 — Final Release Recommendation

**Date:** 2026-06-26 (supersedes this file's prior version, written earlier
the same day at the conclusion of the Configuration & Deployment Audit —
see that version in git history on `release/v1.0-rc-qualification` for the
original branch-divergence discovery this recommendation now acts on.)

**Inputs:** `BRANCH_DIFFERENCE_REPORT.md`, `RECONCILIATION_PLAN.md`,
`RC2_VALIDATION_REPORT.md` (all in this worktree,
`.claude/worktrees/rc2-reconciliation`, branch `release/v1.0-rc2`).

---

## 1. What changed since the last recommendation

The prior recommendation ("merge after configuration reconciliation")
identified that `feature/adms-topology-import` and
`feature/dlms-driver`/`release/v1.0-rc-qualification` are unmerged sibling
branches, each with live functionality the other lacks, and recommended
reconciling them before any further "point this service at one branch"
fixes. That reconciliation has now been done:

- `release/v1.0-rc2` = `release/v1.0-rc-qualification` (33 commits) +
  `feature/adms-topology-import` (3 commits), merged with **zero file
  conflicts** (predicted by the git analysis, confirmed by actually running
  the merge).
- Validated in a sandboxed throwaway environment: topology API routes
  present, telemetry auth and tenant isolation regression-tested and
  passing, AMI/MDM/OPC-UA/CIM code confirmed untouched by the merge.
- One real (but pre-existing, not merge-caused) finding surfaced: a DB
  migration gap (`sql/021`'s `phases` column was never applied to the live
  database), blocking only the standalone bulk-importer CLI, not the live
  `POST /topology/versions` API endpoint. See `RC2_VALIDATION_REPORT.md`.

## 2. What has *not* changed / not yet done

- **`release/v1.0-rc2` is not live anywhere.** `diep-fastapi` still runs
  `release/v1.0-rc-qualification` (i.e., still 404s on
  `/topology/versions` today). Cutting it over was deliberately not done
  in this sprint — the brief asked for git reconciliation and validation,
  not a live deployment decision, and an attempt to also verify this
  against the live container was correctly declined for exceeding that
  scope. This is the most concrete, actionable next step once the user
  wants it: the same recreate-and-verify pattern already used for
  `fastapi`/`node-exporter`/`prometheus`/`wal-shipper`/`grafana`/
  `redis-exporter` earlier in this engagement, pointed at this worktree.
- **The `sql/021`-and-onward migration backlog is unresolved.** Not
  applied in this sprint (a schema change, outside "git integration
  sprint, not a feature sprint"); blocks the bulk topology importer CLI
  only, not the live API.
- **The broader 21-service deployment-source divergence** (Category B from
  the Configuration & Deployment Audit — content-identical, low risk,
  deliberately left alone) is unchanged and unaffected by this sprint.
- **Items already flagged as open before this sprint and still open:**
  operational-interface authentication (Prometheus/Alertmanager/kafka-ui/
  cAdvisor/Node-RED), the host-cron backup-monitoring gap (`backup-db.sh`
  always runs from the main checkout, which itself is now `release/v1.0-rc2`'s
  sibling-no-more — see §3), the host write-durability defect, production
  hardware sizing, and a true multi-day soak.

## 3. A clarifying note now that the branches are merged

With `feature/adms-topology-import`'s unique commits absorbed into
`release/v1.0-rc2`, the main checkout's branch
(`feature/adms-topology-import`) no longer has anything `release/v1.0-rc2`
lacks. **This resolves the host-cron backup-monitoring gap's root cause as
well**, once `release/v1.0-rc2` (not the current main checkout) becomes
what the crontab and the rest of the live stack are sourced from — that
cutover hasn't happened yet (§2), but the branch-level blocker that made it
impossible to do safely before is now gone.

## 4. Recommendation

# 2 — Merge after configuration reconciliation (reconciliation now complete; cutover still pending)

The branch-level reconciliation this recommendation previously called for
is done, validated, and carries no open conflicts. **Do not merge
`release/v1.0-rc2` into `main` yet** — per the sprint's own instruction,
and because:

1. It has not been run live anywhere yet. Merging an unvalidated-in-
   production candidate into `main` and only then discovering an
   integration problem is the wrong order of operations.
2. The migration backlog (§2) should be resolved or explicitly accepted as
   a known gap before the branch that owns the importer that depends on it
   is declared final.

**Recommended next steps, in order, each its own explicit decision point:**

1. Cut over `diep-fastapi` to `release/v1.0-rc2` (the worktree at
   `.claude/worktrees/rc2-reconciliation`), using the same
   recreate-and-verify pattern already established and proven safe in this
   engagement. This is low-risk: the merge is clean, sandboxed-validated,
   and additive (restores a previously-live endpoint; doesn't remove
   anything Branch B's `fastapi` currently does).
2. Decide on the `sql/021`+ migration backlog — apply it (it's additive/
   idempotent by the migrations' own design) or explicitly defer with a
   documented reason.
3. Once `diep-fastapi` is confirmed healthy on `release/v1.0-rc2` and the
   migration decision is made, `release/v1.0-rc2` is ready to merge into
   `main` and be tagged as Release 1.0 — at that point every piece of work
   named in this sprint's success criteria (Topology Import, Production
   Recovery/Hardening, AMI, MDM, OPC UA, CIM, Deployment Audit, Security
   fixes, Qualification work) is present on one branch, with no functional
   loss in either direction.
4. Separately and not blocking the above: resolve the remaining
   operational-interface auth gaps and decide on the host instability
   defect before scaling production load.

This is real, demonstrated progress: the central uncertainty from the
prior recommendation — "can these two branches even be combined without
losing something?" — is now answered with evidence (clean merge, passing
regression tests, one isolated and well-understood pre-existing gap) rather
than inferred from risk. What remains is operational sequencing, not open
technical risk.
