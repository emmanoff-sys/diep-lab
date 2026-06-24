# DIEP — Post-Cutover Hypercare Plan

> **READY-TO-RUN — NOT ACTIVE.** This plan *activates only* after the 48h
> observation window completes clean (2026-06-26T11:29:15Z), a passing MW2
> assessment issues **GO**, the Phase 24 cutover executes, and post-cutover
> validation (§D of [`EXECUTION_CHECKLIST.md`](EXECUTION_CHECKLIST.md)) passes.
> It is a **planning document**, not an action log. Nothing here runs until GO.
> Gate decisions remain **CONDITIONAL GO / NO-GO** until then.

---

## 0. Purpose & activation gate

Hypercare is **intensified monitoring** for the first **48–72 hours** after the
live cutover, before transitioning to steady-state operations. Its job is to
catch cutover-induced regressions (config drift, restart loops, data-path
failures, alert storms) early, while rollback is still cheap.

**Activation criteria — ALL must be true (else do not start hypercare):**
1. Observation window completed clean (no critical restarts, no corruption
   recurrence) through 2026-06-26T11:29:15Z.
2. Fresh MW2 run = **PASS** (score ≥ 90, no critical FAIL).
3. Phase 24 cutover executed per [`PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md`](../../PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md).
4. Post-cutover validation D1–D9 in [`EXECUTION_CHECKLIST.md`](EXECUTION_CHECKLIST.md) all green.

If any criterion fails → **do not enter hypercare**; execute rollback
([`PHASE24_ROLLBACK_PROCEDURE.md`](../../PHASE24_ROLLBACK_PROCEDURE.md)) instead.

---

## 1. Scope & duration

- **Duration:** 72h recommended (48h minimum), clock starting at successful
  cutover validation. A non-negotiable checkpoint at **24h** and **48h**.
- **Coverage:** all 7 critical services + 3 sentinels + the monitoring/alerting
  stack itself (Prometheus, Grafana, Alertmanager, exporters).
- **Posture:** read-mostly. No non-urgent changes. Every change is logged as a
  deployment event (`POST /deployment/cutover/...` is record-only by design).

---

## 2. Watch surfaces (concrete — bind to what actually exists)

**Metrics (Prometheus @ diep-prometheus:9090):**
- `diep_readiness_score` — MW2 composite (target ≥ 90)
- `diep_deployment_status` — gate metric (`1=GO`, `0.5=IN_PROGRESS`, `0=NO_GO`)
- `diep_deployment_validation_score`, `diep_deployment_duration_seconds`
- Per-service container health + restart count (cAdvisor / docker)
- `node_*` (disk, memory, CPU), `pg_*` (Postgres exporter), `redis_*`, `kafka_*`

**Dashboards (Grafana @ diep-grafana:3000):** readiness, deployment gate, infra
(resource/disk/mem), Redis HA, Kafka lag. Confirm `GET /api/health` → 200.

**Alerts (Alertmanager @ diep-alertmanager:9093, rules in `prometheus/alerts.yml`):**
- Any firing alert during hypercare is treated as **priority-1** until triaged.
- Backup-alert path (`scripts/lib-backup-alert.sh`) — confirm a basebackup still
  lands in `diep-pg-basebackups` on schedule.

**API probes:** `/readyz`, `/controls/readiness`, `/controls/readiness/history`,
`/deployment/status`, `/deployment/history`.

---

## 3. Cadence

| Window | Check frequency | What |
|---|---|---|
| 0–6h | every 30 min | full §5 checklist + scan firing alerts |
| 6–24h | every 1h | §5 checklist + MW2 score trend |
| 24–48h | every 2h | §5 checklist |
| 48–72h | every 4h | §5 checklist (winding down) |

At **24h** and **48h**: run the full MW2 assessment
(`scripts/run_mw2_readiness_check.py`) and record the persisted report.

---

## 4. Escalation triggers & decision rules

**Immediate rollback** ([`PHASE24_ROLLBACK_PROCEDURE.md`](../../PHASE24_ROLLBACK_PROCEDURE.md))
— any of:
- A critical container enters a restart loop (RestartCount rising) **and** the
  throwaway-DB-free rollback re-pin doesn't clear it within one check interval.
- `diep_readiness_score` drops below 90 **or** `diep_deployment_status` → `0` (NO_GO).
- Corruption symptom recurs: Redis "Bad file", Kafka `KafkaStorageException` /
  `Malformed`, or Sentinel quorum lost (see 2026-06-24 incident fingerprints).
- Data-loss symptom: Kafka consumer-lag climbing unbounded, or `diep.commands`
  not draining.
- Disk > MW2 threshold on any critical volume, or Postgres/Redis unavailable.

**Continue + investigate (no rollback):** isolated non-critical WARN (e.g. a
single non-critical Prometheus target flapping) that self-heals within one
interval. Log it as a deployment event.

> Note: migrations `022`/`023` are additive/evidence-only — rollback is
> **app re-pin only**; leave the new tables in place (see §C of EXECUTION_CHECKLIST).

---

## 5. On-call checklist (copy-paste, every interval)

```bash
RP=$(grep -E '^REDIS_PASSWORD=' .env | head -1 | cut -d= -f2-)
# 1. Critical + sentinels: running, no new restarts
for c in diep-fastapi diep-timescaledb diep-minio diep-redis diep-redis-replica \
         diep-kafka diep-kafka-exporter diep-redis-sentinel-1 diep-redis-sentinel-2 diep-redis-sentinel-3; do
  docker inspect -f '{{.Name}} {{.State.Status}} restarts={{.RestartCount}}' $c; done
# 2. API + readiness/deployment surface
docker exec diep-fastapi wget -qO- http://localhost:8000/readyz
curl -s localhost:8000/controls/readiness | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["status"],d["score"])'
# 3. Corruption fingerprints (all must be 0)
docker logs --since 1h diep-redis diep-redis-replica 2>&1 | grep -c 'Bad file'
docker logs --since 1h diep-kafka 2>&1 | grep -cE 'Malformed|KafkaStorageException'
docker exec diep-redis-sentinel-1 redis-cli -p 26379 SENTINEL ckquorum diep-master
# 4. Redis HA
docker exec diep-redis redis-cli -a "$RP" INFO replication | grep -E 'role:|connected_slaves:|master_link_status:'
# 5. Firing alerts + Grafana health
curl -s localhost:9093/api/v2/alerts | python3 -c 'import sys,json;print(len([a for a in json.load(sys.stdin) if a["status"].get("state")=="alerting"]),"firing")'
curl -s localhost:3000/api/health
```
Record results per interval in the hypercare log. Any non-green → §4.

---

## 6. Exit criteria (hypercare → steady-state)

Exit hypercare to normal operations ([`DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md`](../../DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md))
when **all** hold for the final 24h:
- Zero critical-container restarts.
- Zero firing priority alerts.
- `diep_readiness_score` ≥ 90 stable; `diep_deployment_status` = GO.
- Zero corruption fingerprints.
- Two consecutive scheduled MW2 runs = PASS.
- Backup job confirmed landing on schedule.

If any fails in the final 24h → extend hypercare by 24h and re-evaluate.

---

## 7. Roles, handoff & references

- **Operator (on-call):** runs §5 each interval, triages alerts per §4, owns
  rollback decision with release-manager sign-off.
- **Release manager:** owns GO/NO-GO at each 24h checkpoint; signs exit.
- **References:** [`MW2_READINESS_OPERATOR_RUNBOOK.md`](../../MW2_READINESS_OPERATOR_RUNBOOK.md),
  [`PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md`](../../PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md),
  [`DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md`](../../DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md),
  [`DIEP_OPERATIONS_MANUAL.md`](../../DIEP_OPERATIONS_MANUAL.md).

---

## 8. Known prior event (must remain documented)

**Permanent Kafka data loss — 2026-06-24 incident** (`diep.commands` backlog,
`__consumer_offsets`, topic configs) from the KRaft reformat during host
lost-write recovery. The cutover does **not** restore it and is **not** blocked
by it. This reference, and those in the release notes / readiness / production
reports, must remain in place per the release-freeze record. See
[`HOST_VM_INSTABILITY_FINDINGS_20260624.md`](../../HOST_VM_INSTABILITY_FINDINGS_20260624.md).
