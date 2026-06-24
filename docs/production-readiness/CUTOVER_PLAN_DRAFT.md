# DIEP Production Cutover Plan — DRAFT (PLANNING ONLY)

> **STATUS BANNER — read first.**
> This is a **planning document, not an authorization and not an action log.**
> Nothing here is to be executed. As of writing, the standing decisions are
> **MW2 = NO-GO · Production = DENIED · DO-NOT-GO-LIVE**, held until the 48h
> stability window completes clean (**target 2026-06-26T11:29:15Z**) *and* a fresh
> MW2 host assessment passes. This draft exists so the cutover is ready to execute
> **once** those gates clear — it does not move them.
> **Author:** Claude (planning assistant) · **Drafted:** 2026-06-24 · **Owner of execution:** human release manager / `admin`.

---

## 0. Context & scope

- **What's being deployed:** the current `main` branch — which now includes the
  **MW2 readiness engine** (`fastapi/readiness.py`, `sql/022`) and **Phase 24
  Production Cutover Automation** (`fastapi/deployment.py`, `routers/deployment.py`,
  `sql/023`) — onto the live stack.
- **Why a cutover is required (not a no-op):** the **live containers run a
  pre-Phase-24 image** and the **live database is at migration `021`** — it lacks
  `sql/022_platform_readiness.sql` and `sql/023_production_cutover.sql`. So the
  readiness/deployment APIs and their tables do not yet exist in production.
- **Incident overlay:** this cutover follows the 2026-06-24 host
  durability/corruption incident — see
  [`HOST_VM_INSTABILITY_FINDINGS_20260624.md`](../../HOST_VM_INSTABILITY_FINDINGS_20260624.md).
  Permanent kafka data loss from that incident is a **known prior event** (§5), not
  something this plan repairs.
- **Execution runbook (finalized, ready-to-run, not run):** the concrete
  copy-paste migration/rollback commands and the full post-cutover smoke checklist
  live in [`EXECUTION_CHECKLIST.md`](EXECUTION_CHECKLIST.md). §2 and §4 below are the
  plan/rationale; that file is what you follow on execution day.

---

## 1. Pre-cutover checklist (everything true before a GO decision)

A GO requires **all** of the following ✅. None may be assumed.

| # | Gate | Source of truth | Status (2026-06-24) |
|---|---|---|---|
| 1 | **48h stability window clean** — no critical-container restart, no corruption symptom | container `StartedAt`/`restarts`, logs | ⏳ running, target 2026-06-26T11:29:15Z |
| 2 | **Fresh MW2 readiness run PASS** — all gates incl. `critical_service_uptime` ≥ window | `scripts/run_mw2_readiness_check.py` on host | ⏳ gated on #1 |
| 3 | **Host durability fix documented as applied** — datastore write-through + barriers, clean-shutdown discipline | operator confirmation + incident doc addendum | ✅ confirmed/recorded (HOST_VM…md) |
| 4 | **PR #13 merged** (M7 structural-graph) + any other open PRs resolved | `gh pr list` | ✅ #13 merged (07b12a3); zero open PRs (CI fix #16 also merged) |
| 5 | **Full pytest suite green** on the cutover commit | containerized `pytest tests/ -q` | ⚠️ re-run required on final commit (last clean: 80 passed / 77 skipped) |
| 6 | **M7↔M6 unification status explicit** — done OR formally deferred (not silently dropped) | `ADMS_PHASE6_FOLLOWUPS.md` | 🟡 **deferred follow-up** (documented; not a blocker — see §3) |
| 7 | **Migrations staged & validated** on throwaway DB (`022`,`023` apply on top of `021`) | prior validation | ✅ validated additively; re-confirm on cutover |
| 8 | **Rollback plan reviewed** | §2.4 + `PHASE24_ROLLBACK_PROCEDURE.md` | ✅ drafted |

> **Decision rule:** GO only when 1–8 are ✅. Item 4 (PR #13) has closed; item 5
> (pytest) is the only *code* gate still to re-confirm on the final commit;
> everything else is time/operational.

---

## 2. Cutover plan

**Executor: human release manager (`admin`).** The Phase 24 framework **records and
validates** the cutover — it does **not** execute image builds, migrations, or
restarts. Every step below is performed by a person via the standard change
procedure; Phase 24 wraps it in evidence/audit.

### 2.1 Image build & tag strategy (ties to v1.0.0-rc1 → v1.0.0)
1. Build the API image from the GO commit on `main` (must include `readiness.py`,
   `deployment.py`, `routers/deployment.py`, and the `httpx` runtime dep).
2. Tag **`v1.0.0-rc1`**. Deploy rc1 to a **non-production / validation** target
   first; run §4 post-cutover validation there.
3. On a clean rc1 validation **and** a GO decision, **promote the same image** to
   **`v1.0.0`** (re-tag, do not rebuild) and deploy to production.
4. Record both tags + digests in the deployment evidence
   (`POST /deployment/cutover/start` checklist).

### 2.2 DB migration order (additive only)
Live DB is at `021`. Apply, in order, against the live DB **inside the cutover
window** (each is additive — new tables only, no `ALTER` of existing tables):
1. `sql/022_platform_readiness.sql` → `platform_readiness_reports`
2. `sql/023_production_cutover.sql` → `platform_deployment_runs`, `platform_deployment_events`
- **Nothing newer than 023 exists.** Take a fresh DB backup (basebackup + WAL
  checkpoint to MinIO) immediately before applying.

### 2.3 Deploy sequence (happy path)
1. Pre-cutover gate: capture baseline + run MW2 readiness (the cutover's own
   `POST /deployment/cutover/start` once the new image is staged; on the live
   path, run `scripts/run_mw2_readiness_check.py` first).
2. DB backup → apply migrations `022`, `023`.
3. Roll the API image to `v1.0.0-rc1` (then `v1.0.0` on promotion); restart
   `diep-fastapi` (and any service consuming the new code).
4. Confirm `/readyz` 200 and the new `/deployment/*` + `/controls/readiness`
   endpoints respond.
5. Run §4 post-cutover validation → derive GO/NO-GO → record evidence.

### 2.4 Rollback (if cutover fails partway) — see `PHASE24_ROLLBACK_PROCEDURE.md`
- **App:** redeploy the prior (pre-Phase-24) image tag; restart `diep-fastapi`.
- **DB:** migrations `022`/`023` are **additive (new tables only)** → safe to
  **leave in place** on rollback (no data dependency from old code). If a clean
  revert is mandated, `DROP TABLE platform_deployment_events, platform_deployment_runs, platform_readiness_reports;`
  (these hold only evidence, no operational data).
- **Decision rule:** any **critical** post-cutover check FAIL → NO-GO → roll back
  app image, keep DB additive tables, re-validate the restored stack.
- **Executor:** human; Phase 24 records the rollback decision + re-validation only.

---

## 3. Production-readiness gates beyond MW2 — blocking vs housekeeping

Pulled from [`PRODUCTION_DEPLOYMENT_TRACKER.md`](../../PRODUCTION_DEPLOYMENT_TRACKER.md)
(last updated 2026-06-17) and related docs. **Operator to confirm MW1↔MW2
sequencing** — the taxonomy below is transcribed from the tracker, not re-derived.

### 3.1 Genuinely blocking (must close before production GO)
- **48h window + clean MW2 run** (this incident's gate) — §1.
- **PR #13 merge** ✅ (merged 07b12a3) + **full pytest green** on the cutover commit — §1 items 4–5.
- **MW1 execution & sign-off** — per the tracker, the MW1 *infra prerequisites* are
  largely closed (**7/10 gate items 🟢**: SEC-1,2,3,4, MON-2,3, INFRA-2), but **MW1
  itself (K1 PITR + K4 Redis-Sentinel cutover, app→Sentinel-aware client, failover
  drill) has NOT been executed** and still needs explicit scheduling/sign-off.
  *Confirm whether MW1 is a prerequisite of, or parallel to, this MW2 cutover.*

### 3.2 Partial — deferred to a future milestone (tracked, not bugs)
- **SEC-5** → blocked on **K5/MW5**
- **MON-1** → blocked on **K5/MW5**
- **MON-4** → blocked on **K2/MW4**
- **SEC-6** (backup-at-rest encryption) — intentionally **not** in the MW1 gate.
> These are correctly-partial pending future HA milestones; they should be listed
> as *known-open with a milestone owner*, not silently treated as closed.

### 3.3 Housekeeping (unfinished, **non-blocking**)
- **CI `build-scan-sign` (roadmap issue #4):** ✅ **stabilized by PR #16** — build +
  Trivy scan + SBOM now run (and pass) on every PR; registry push/sign and
  deploy-staging are gated behind a real registry token / `vars.DEPLOY_ENABLED`, so
  they no longer fail on every PR. The underlying roadmap item (wire a real
  registry/cluster) remains open, but it no longer destabilizes PR status.
- **M7↔M6 unification** + **M6 impedance-distance refinement** — documented
  enhancement follow-ups in [`ADMS_PHASE6_FOLLOWUPS.md`](../../ADMS_PHASE6_FOLLOWUPS.md);
  **not** wired, **not** a deployment blocker.

---

## 4. Post-cutover validation + go-forward stability policy

### 4.1 Immediate post-cutover checks (smoke + health)
- **`/readyz` 200**, `{"database":true,"redis":true}`.
- **7 critical services + 3 sentinels** all `running`, `restarts=0`
  (fastapi, timescaledb, minio, redis, redis-replica, kafka, kafka-exporter,
  sentinel-1/-2/-3).
- **No corruption symptoms:** redis no `Bad file`, kafka no KRaft/Malformed errors,
  `SENTINEL ckquorum diep-master` = OK, `kafka_brokers 1`.
- **New surface live:** `/controls/readiness`, `/deployment/status` respond;
  `platform_readiness_reports` + `platform_deployment_runs` tables exist.
- **Phase 24 post-cutover gate** (`POST /deployment/cutover/validate`):
  FastAPI · portal · Redis · Kafka · Prometheus · Grafana → score → GO/NO-GO.
- **Smoke:** one command round-trip on `diep.commands`; portal login; a readiness
  run persists & scrapes (`diep_readiness_score`, `diep_deployment_status`).

### 4.2 Go-forward stability-observation policy (proposal for operator sign-off)
- The **48h hold is incident-specific** (response to repeated unclean-reset
  corruption on this host) — **not** proposed as the standing per-deploy default.
- **Proposed standing policy:** routine deploys get the **MW2 24h window**
  (existing `READINESS_MIN_UPTIME_SECONDS=86400`); the **48h** window applies only
  after a **host/hypervisor-level change or a durability incident**. Escalate back
  to 48h on any future corruption recurrence.
- **Trigger to reset the clock going forward:** any critical-container restart or
  corruption symptom resets the window and requires a fresh MW2 run.

---

## 5. Kafka data-loss disclosure (known prior event — not a plan to-do)

During the 2026-06-24 host-durability incident, kafka KRaft metadata was
**reformatted (option A)** because no kafka backup existed (MinIO/`wal-archive`
hold only PostgreSQL PITR). **Permanently lost:** the `diep.commands` message
backlog (~28 KB), all `__consumer_offsets` consumer positions, and topic configs.
`cluster.id` was preserved; topics were re-created empty. Full record:
[`HOST_VM_INSTABILITY_FINDINGS_20260624.md`](../../HOST_VM_INSTABILITY_FINDINGS_20260624.md)
(“Recovery Complete” addendum).

**Implications for this plan:**
- This loss is **historical and accepted** — the cutover does **not** restore it
  and is **not** blocked by it.
- **Recommended follow-up (separate from cutover):** add **kafka to the backup
  strategy** (topic configs + offsets at minimum) so a future incident isn't a
  reformat. Tracked as a post-cutover improvement, not a GO gate.
- Any release notes / go-live authorization for `v1.0.0` should **reference this
  loss as a known prior event** for auditability.

---

## Appendix — referenced artifacts
- Phase 24 ops docs: [`PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md`](../../PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md) · [`PHASE24_ROLLBACK_PROCEDURE.md`](../../PHASE24_ROLLBACK_PROCEDURE.md) · [`PHASE24_CUTOVER_CHECKLIST.md`](../../PHASE24_CUTOVER_CHECKLIST.md)
- Incident: [`HOST_VM_INSTABILITY_FINDINGS_20260624.md`](../../HOST_VM_INSTABILITY_FINDINGS_20260624.md)
- Gate tracking: [`PRODUCTION_DEPLOYMENT_TRACKER.md`](../../PRODUCTION_DEPLOYMENT_TRACKER.md) · [`MW1_VERIFICATION_REPORT.md`](../../MW1_VERIFICATION_REPORT.md)
- Migrations: `sql/022_platform_readiness.sql` · `sql/023_production_cutover.sql`
- Follow-ups: [`ADMS_PHASE6_FOLLOWUPS.md`](../../ADMS_PHASE6_FOLLOWUPS.md)

> **Reminder:** DRAFT / planning only. Does not authorize anything. MW2 NO-GO ·
> Production DENIED · DO-NOT-GO-LIVE remain in force until the window completes and
> a clean MW2 run says otherwise.
