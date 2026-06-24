# DIEP Cutover — Execution Checklist (concrete runbook)

> **PLANNING / READY-TO-RUN — NOT EXECUTED.** Companion to
> [`CUTOVER_PLAN_DRAFT.md`](CUTOVER_PLAN_DRAFT.md). Every command here is reviewed
> and copy-paste ready for **execution day only**, by a human (`admin`), **after**
> the 48h window completes clean (2026-06-26T11:29:15Z) **and** a passing MW2 run.
> Nothing in this file has been run. Gate decisions remain **NO-GO / DENIED**.

---

## A. DB migration — REVIEWED, ready-to-run (do not run yet)

Live DB is at migration `021`; it needs `022` and `023`. **Both reviewed:**

| Migration | Creates | Idempotent? | Additive? | FK deps |
|---|---|---|---|---|
| `sql/022_platform_readiness.sql` | `platform_readiness_reports` + 3 indexes | ✅ `CREATE TABLE/INDEX IF NOT EXISTS` | ✅ new table only | `tenants(tenant_id)` (exists) |
| `sql/023_production_cutover.sql` | `platform_deployment_runs`, `platform_deployment_events` + indexes | ✅ `IF NOT EXISTS` | ✅ new tables only | `tenants(tenant_id)`, `platform_deployment_runs(deployment_id)` |

- **No `ALTER`/`DROP` of existing objects** — zero risk to existing data.
- **Idempotent** — safe to re-run; `IF NOT EXISTS` no-ops if already applied.
- Validated additively on a throwaway DB (full `000→023` apply) in prior sessions.

**A.1 — Backup first (mandatory):**
```bash
# Force a fresh basebackup + WAL checkpoint to MinIO before touching schema
docker exec diep-timescaledb psql -U diep -d diep -c "SELECT pg_create_restore_point('pre_cutover_022_023');"
# (plus your standard basebackup job — confirm a new object lands in diep-pg-basebackups)
```

**A.2 — Apply (in order):**
```bash
docker exec -i diep-timescaledb psql -U diep -d diep -v ON_ERROR_STOP=1 < sql/022_platform_readiness.sql
docker exec -i diep-timescaledb psql -U diep -d diep -v ON_ERROR_STOP=1 < sql/023_production_cutover.sql
```

**A.3 — Verify applied:**
```bash
docker exec diep-timescaledb psql -U diep -d diep -c "\dt platform_readiness_reports platform_deployment_runs platform_deployment_events"
# expect all 3 tables present
```

---

## B. Image roll (v1.0.0-rc1 → v1.0.0)

```bash
# Build from the GO commit (origin/main 07b12a3 or later), tag rc1
docker build -t diep-api:v1.0.0-rc1 fastapi/
# Point the live service at the new tag (compose override or image pin), then:
docker compose up -d --no-deps diep-fastapi      # restarts ONLY the API container
# On clean validation + GO: promote the SAME image (no rebuild)
docker tag diep-api:v1.0.0-rc1 diep-api:v1.0.0
docker compose up -d --no-deps diep-fastapi
```
Record both tags + image digests in the Phase 24 deployment evidence.

---

## C. ROLLBACK — exact commands (if cutover fails partway)

**C.1 — App rollback (primary):**
```bash
# Re-pin diep-fastapi to the PRE-cutover image tag (record it before cutover!)
#   e.g. export PREV_TAG=<pre-phase24-digest-or-tag>
docker compose up -d --no-deps diep-fastapi     # with the previous tag pinned
docker exec diep-fastapi wget -qO- http://localhost:8000/readyz   # expect ready:true
```

**C.2 — DB rollback (usually NOT needed):**
Migrations `022`/`023` are additive (new tables, evidence-only) — **leave them in
place**; old code ignores them. Only if a clean revert is explicitly mandated:
```bash
# Order matters: events FK-references runs
docker exec diep-timescaledb psql -U diep -d diep -c "DROP TABLE IF EXISTS platform_deployment_events;"
docker exec diep-timescaledb psql -U diep -d diep -c "DROP TABLE IF EXISTS platform_deployment_runs;"
docker exec diep-timescaledb psql -U diep -d diep -c "DROP TABLE IF EXISTS platform_readiness_reports;"
```
These tables hold only readiness/deployment **evidence** — no operational data is lost.

**C.3 — Decision rule:** any **critical** post-cutover check FAIL → roll back app
(C.1), keep DB additive tables, re-validate the restored stack (§D). Reference
[`PHASE24_ROLLBACK_PROCEDURE.md`](../../PHASE24_ROLLBACK_PROCEDURE.md).

---

## D. POST-CUTOVER SMOKE CHECKLIST (run top-to-bottom; all must pass)

```bash
RP=$(grep -E '^REDIS_PASSWORD=' .env | head -1 | cut -d= -f2-)
```

- [ ] **D1 — API readiness:**
  ```bash
  docker exec diep-fastapi wget -qO- http://localhost:8000/readyz
  # expect {"ready": true, ... "checks": {"database": true, "redis": true}}
  ```
- [ ] **D2 — All 7 critical + 3 sentinels running, restarts=0:**
  ```bash
  for c in diep-fastapi diep-timescaledb diep-minio diep-redis diep-redis-replica \
           diep-kafka diep-kafka-exporter diep-redis-sentinel-1 diep-redis-sentinel-2 diep-redis-sentinel-3; do
    docker inspect -f '{{.Name}} {{.State.Status}} restarts={{.RestartCount}}' $c; done
  # expect all "running restarts=0"
  ```
- [ ] **D3 — No corruption symptoms:**
  ```bash
  docker logs --since 10m diep-redis diep-redis-replica 2>&1 | grep -c 'Bad file'   # expect 0
  docker logs diep-kafka 2>&1 | awk '/Kafka Server started/{s=1}s' | grep -cE 'ERROR|Malformed|KafkaStorageException'  # expect 0
  docker exec diep-redis-sentinel-1 redis-cli -p 26379 SENTINEL ckquorum diep-master   # expect OK
  ```
- [ ] **D4 — Redis HA healthy:**
  ```bash
  docker exec diep-redis redis-cli -a "$RP" INFO replication | grep -E 'role:|connected_slaves:|master_link_status:'
  # expect one master, one connected slave (link up)
  ```
- [ ] **D5 — Kafka + exporter:**
  ```bash
  docker exec diep-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list  # expect __consumer_offsets, diep.commands
  docker exec diep-kafka-exporter wget -qO- http://localhost:9308/metrics | grep '^kafka_brokers '  # expect kafka_brokers 1
  ```
- [ ] **D6 — New surface live (Phase 24 + readiness):**
  ```bash
  docker exec diep-timescaledb psql -U diep -d diep -c "\dt platform_readiness_reports platform_deployment_runs platform_deployment_events"
  # /controls/readiness and /deployment/status respond (admin token) — see PHASE24_CUTOVER_OPERATIONS_RUNBOOK.md
  ```
- [ ] **D7 — Phase 24 post-cutover gate:** `POST /deployment/cutover/validate` →
  score ≥ threshold, `deployment_status=GO` (FastAPI/portal/Redis/Kafka/Prometheus/Grafana).
- [ ] **D8 — Functional smoke:** portal login OK; one `diep.commands` round-trip;
  a readiness run persists + scrapes (`diep_readiness_score`, `diep_deployment_status`).
- [ ] **D9 — Metrics/alerts:** Prometheus targets up, Grafana `/api/health` ok, no new firing alerts.

**Any D1–D7 failure → NO-GO → execute §C rollback.**

---

## E. Known prior event (do not treat as a to-do)
Permanent kafka data loss from the 2026-06-24 incident (`diep.commands` backlog,
`__consumer_offsets`, topic configs) — see
[`HOST_VM_INSTABILITY_FINDINGS_20260624.md`](../../HOST_VM_INSTABILITY_FINDINGS_20260624.md).
The cutover does not restore it and is not blocked by it. Reference it in the
`v1.0.0` release notes for auditability.
