# DIEP v1.0 — Final Release Validation

**Date:** 2026-06-26
**Scope:** FastAPI deployment-source correction and final security validation
(narrow, targeted task — not a re-run of the full qualification suite, per
instructions).

---

## 1. What this task verified and fixed

### 1.1 `diep-fastapi` deployment-source correction

**Root cause confirmed:** `diep-fastapi` was bind-mounted from the main
checkout (`/home/emmanoff_lab/projects/diep-lab`, branch
`feature/adms-topology-import`), not the RC worktree
(`.claude/worktrees/dlms-driver-validation`, branch
`release/v1.0-rc-qualification`) where the qualification and the
`/telemetry/latest` auth fix actually live. `docker compose restart` does
not change which directory a relative bind mount resolves from, so the fix
was committed to source but **not live** until corrected. `app.py`,
`common.py`, and 6 router files genuinely differ between the two checkouts
(confirmed legitimate branch divergence via `git status`, not stray edits).

**Corrected:** recreated only `diep-fastapi`, same compose project/network/
name/ports/env, sourced from the worktree. Verified: bind mount and compose
labels now point at the worktree; container running; `/readyz` →
`{"ready": true, "checks": {"database": true, "redis": true}}`; startup
logs clean.

### 1.2 Security validation, live, post-correction

- `GET /telemetry/latest`, no token → **401** (was 200 before correction).
- Bogus token → 401.
- Valid service token → 200, real data.
- Tenant isolation, with real minted JWTs against the **running** container
  (not just the automated `TestClient` suite): `sit-tenant` token →
  `SIT-METER-001`/`sit-tenant`; `sit-tenant-b` token → `SIT-METER-006`/
  `sit-tenant-b` (never `sit-tenant`'s data); `acme` token (real account,
  zero real devices) → `{"message": "No telemetry found"}`, not a leak.
- 6 automated tests (`tests/test_fastapi_telemetry_auth.py`), all passing.

### 1.3 Regression validation

`/health`, `/version`, `/assets`, `/metrics` all 200. Redis `PING` → `True`.
MDM, OPC UA connector, CIM, ingestor all report healthy; ingestor queue
fully drained. Telemetry row count unchanged by the recreation
(78,562 — matches the prior soak's final count exactly).

### 1.4 Unplanned but directly relevant: backup-monitoring finding corrected

While verifying the fix, the same root cause (wrong checkout) was found to
have produced a **false finding in the original qualification report**:
`backup-db.sh` was reported as never writing its freshness metric or
calling its failure-alert helper. Re-verified from the correct directory:
both already existed in the qualified code (Phase 22 MON-5, committed
2026-06-25). `diep-node-exporter` had the identical wrong-checkout
bind-mount bug, which is why even a correct metric write wasn't reaching
Prometheus. **With the user's explicit, separately-confirmed authorization**
(the recreation instructions were scoped to `fastapi` only), `node-exporter`
was also recreated from the worktree. Now live-verified end-to-end: metric
write → visible via node-exporter → visible in Prometheus at the correct
age → `BackupStale` correctly not firing. The failure-alert path
(`alert_backup_failure`) was verified in isolation (posts `BackupFailed` to
Alertmanager, resolves cleanly) rather than by deliberately breaking the
real backup pipeline — an action the safety classifier correctly declined
to authorize implicitly. Alertmanager's logs confirm real SMTP delivery
succeeds (with some retry-needed in-container DNS flakiness, noted, not
blocking). `QUALIFICATION_REPORT.md`, `GO_LIVE_CHECKLIST.md`, and
`KNOWN_LIMITATIONS.md` have all been corrected accordingly.

### 1.5 Permanent preventive control added

`GO_LIVE_CHECKLIST.md` now has a standing "Deployment Source Verification"
release-gate item: verify every bind-mounted service's actual
`docker inspect` mount source and compose labels before any qualification
or production sign-off, every time — a compose file existing or a restart
having been run is not evidence of what's actually live.

---

## 2. A broader finding surfaced during this validation, not yet remediated

Verifying the preventive control above against **all** running containers
(not just the ones already known to be affected) found that **13 of the
running services** are bind-mounted from the main checkout, not this RC
worktree: `wal-shipper`, `caddy`, `oms-detector`, `dispatcher`, `nodered`,
`portal`, all 3 `redis-sentinel` nodes, `grafana`, `ev-charger`,
`prometheus`, `postgres-exporter`, `mqtt`. A content diff against each
service's worktree counterpart found:

- **Identical, harmless** (just imprecise bookkeeping): `oms`, `dispatcher`,
  `redis-sentinel`, `simulator`, `alertmanager`.
- **Differ only in build/runtime artifacts** (`node_modules`, `.next`,
  generated config from running `npm install`/Node-RED's own runtime state)
  — not a source-code concern: `portal`, most of `nodered`.
- **Differ in ways that matter, not yet investigated to resolution:**
  - `wal-shipper/ship-wal.sh` — genuinely different script content.
  - `prometheus/prometheus.yml` and `prometheus/alerts.yml` — genuinely
    different. This session's empirical testing (alert behavior, the MDM/
    OPC UA scrape jobs, `BackupStale`) was against the **live** Prometheus,
    which reads the main checkout's copy — so this session's findings about
    Prometheus *behavior* are accurate for what's deployed, but a fresh
    deployment from the worktree (the qualified branch) would get different
    config than what's actually been tested here.
  - Grafana: the worktree has an AMI/MDM pipeline dashboard
    (`ami-mdm-pipeline.json`) that the live, main-checkout-sourced Grafana
    does not.

**This was not fixed in this task** — it surfaces while auditing the
preventive control just added, goes well beyond this task's scoped
instructions ("recreate only diep-fastapi... do not restart unrelated
services"), and several of these (MQTT broker, Prometheus, Alertmanager,
Redis Sentinel) are higher-risk to touch without individually reviewing
each divergence first. **Recommended as an immediate follow-on task**, using
the same verify-then-recreate-with-explicit-authorization pattern just
demonstrated for `fastapi` and `node-exporter`.

---

## 3. Conclusion

# RELEASE APPROVED WITH LIMITATIONS

This task closed one real P0 (`/telemetry/latest` auth) with genuine live
verification, corrected a false P0 finding (backup monitoring was already
working), and added a permanent control against the bug class that caused
both problems. That is real, verified progress.

It does not change the overall verdict tier from the original qualification
(`QUALIFICATION_REPORT.md` §8), because:

- **Still open, unaddressed by this task:** Prometheus/Alertmanager/
  kafka-ui/cAdvisor/Node-RED remain unauthenticated on this host's network
  interfaces (live-reconfirmed during this task, unchanged); the host
  write-durability defect is still not confirmed fixed; production
  hardware sizing per `DEPLOYMENT_GUIDE.md` has not happened; a true
  multi-day soak has not been run.
- **Newly surfaced, not yet resolved:** the deployment-source divergence
  found in §2 above means the confidence this engagement has in "the
  worktree's code is what's actually been tested" is narrower than
  previously assumed — accurate for `fastapi`, `node-exporter`, `mdm`,
  `opcua-connector`, `cim`, and `ingestor` (all confirmed correctly sourced
  this session or in prior sessions), genuinely uncertain for the 13
  services named in §2 until each is individually reviewed.

Neither of these indicates a broken platform — every gap found across this
whole engagement has had a specific, scoped fix, and the core data path's
correctness and resilience are still the most thoroughly, repeatedly
live-verified parts of this system. But "approved with limitations" remains
the honest read: real progress, real remaining gaps, nothing here justifies
moving to an unconditional approval yet, and nothing here justifies
withdrawing the approval already given.

**Immediate next steps, in order:** (1) resolve the §2 deployment-source
divergence for `prometheus`/`alertmanager`/`wal-shipper`/`grafana` at
minimum, since those are the ones with confirmed *content* differences, not
just bookkeeping; (2) close the remaining `GO_LIVE_CHECKLIST.md` P0 items
(operational-interface auth); (3) get a decision on the host instability
defect; (4) size production hardware and run a real soak before scaling
past this engagement's tested load.
