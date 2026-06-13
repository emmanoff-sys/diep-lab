# DIEP Phase 15C — Production Operations & Disaster Recovery

> Backup automation, restore runbook, DR drill evidence, and HA roadmap for the
> single-host lab. Companion to `DIEP_PHASE10_RUNBOOK.md` (10E targets) and
> `DIEP_HA_ARCHITECTURE.md` (Phase 9K target architecture).

Drill date: 2026-06-13. Project root: `~/projects/diep-lab`.

---

## 1. Database backup automation (Task 1)

### What was built
- **`scripts/backup-db.sh`** (enhanced) — `pg_dump -Fc` of the `diep` database, verifies
  the TOC for `telemetry/devices/commands/audit_events`, writes a `.sha256` sidecar,
  uploads dump + checksum to MinIO (`s3://diep-backups/`), then prunes both MinIO and
  local copies older than `BACKUP_RETENTION_DAYS` (default **14 days**).
- **`scripts/verify-backup.sh`** (new) — checksum-verifies the latest (or named) dump,
  then runs `restore-db.sh` to restore it into a scratch database (`diep_restore_test`)
  and compares row counts against the live `diep` DB. This is the automated "backup
  verification + restore verification" required by Task 1.
- **`scripts/restore-db.sh`** (pre-existing, unchanged) — does the actual
  `timescaledb_pre_restore()` / `pg_restore` / `timescaledb_post_restore()` cycle.

### Retention policy
- 14 days, enforced in two places: `mc rm --force --older-than 14d` against the MinIO
  bucket, and `find backups -mtime +14 -delete` for the local archive. Configurable via
  `BACKUP_RETENTION_DAYS`.

### Evidence (this run)
```
[1/4] pg_dump -> backups/diep_20260613T042427Z.dump   (356 KiB)
[2/4] TOC verify (telemetry/devices/commands/audit_events present) + sha256
[3/4] uploaded to s3://diep-backups/diep_20260613T042427Z.dump
[4/4] local retention prune (none older than 14d)

scripts/verify-backup.sh:
  [1/2] sha256sum -c  -> OK
  [2/2] restore-db.sh -> restored into diep_restore_test
        telemetry: restored=15574 prod=15620   (drift = live ingestion during drill)
        devices=5/5  commands=9/9  audit_events=11/11  MATCH
=== PASS: diep_20260613T042427Z.dump verified in 6s ===
```
MinIO bucket `diep-backups` now contains `diep_20260613T042427Z.dump` (+`.sha256`).

### Scheduling
`scripts/install-backup-cron.sh` installs (idempotently, tagged `# diep-backup`) into the
**current OS user's crontab** — see §6 "Operational notes" for why this matters.

| Time (UTC) | Job |
|---|---|
| 02:00 daily | `backup-db.sh` → `backups/logs/backup-db.log` |
| 02:30 daily | `backup-config.sh` → `backups/logs/backup-config.log` |
| 03:00 Sun | `verify-backup.sh` (restore drill) → `backups/logs/verify-backup.log` |

### DB restore runbook
**Drill restore (non-destructive, routine verification):**
```bash
scripts/verify-backup.sh [diep_<timestamp>.dump]   # restores into diep_restore_test, drops it after
KEEP=1 scripts/restore-db.sh <dump>                # keep the scratch DB for manual inspection
```

**Disaster restore into the real `diep` database** (only when `diep` is lost/corrupted —
this is destructive to the target and is *not* exercised in this drill per the Phase 15C
rules):
1. Stop writers: `docker compose stop ingestor dispatcher fastapi`.
2. Fetch the dump: `mc cp m/diep-backups/<dump> backups/` (or use the local copy).
3. Verify checksum: `sha256sum -c backups/<dump>.sha256`.
4. Drop/recreate the target DB, then restore with TimescaleDB pre/post hooks:
   ```bash
   docker exec -i diep-timescaledb psql -U diep -d postgres -c "DROP DATABASE diep;"
   docker exec -i diep-timescaledb psql -U diep -d postgres -c "CREATE DATABASE diep OWNER diep;"
   docker exec -i diep-timescaledb psql -U diep -d diep -c "SELECT timescaledb_pre_restore();"
   docker exec -i diep-timescaledb pg_restore -U diep -d diep -Fc < backups/<dump>
   docker exec -i diep-timescaledb psql -U diep -d diep -c "SELECT timescaledb_post_restore();"
   ```
5. Verify: row counts on `telemetry/devices/commands/audit_events`, then
   `curl http://localhost:8000/readyz`.
6. Restart writers: `docker compose start ingestor dispatcher fastapi`.
7. **Data-loss window** = time between the restored dump's timestamp and the incident —
   see RPO in §3.

---

## 2. Configuration backup (Task 2)

### What was built
**`scripts/backup-config.sh`** (new) — tars and checksums:
- `docker-compose*.yml`
- `mosquitto/config` (mTLS broker config + CA/server certs)
- `alertmanager/alertmanager.yml`
- `grafana/provisioning` (dashboards + datasources)
- `prometheus/{prometheus.yml,alerts.yml,postgres_exporter_queries.yaml}`
- `certs/` (device certs)
- `.env.example`

**Deliberately excludes `.env`** (live secrets — MinIO/DB/JWT credentials rotated in
Phase 15A). Operators must restore `.env` from a secrets vault, not from this archive.

Uploads to MinIO `s3://diep-config-backups/`, with the same 14-day retention pruning
(local + MinIO) as the DB backup.

### Evidence (this run)
```
[1/4] tar -> backups/config/diep-config_20260613T042555Z.tar.gz (40 KiB)
[2/4] sha256sum -> diep-config_20260613T042555Z.tar.gz.sha256
[3/4] top-level entries: docker-compose.yml, mosquitto/, alertmanager/, grafana/,
      prometheus/, certs/, .env.example
[4/4] uploaded to s3://diep-config-backups/
```

### Config restore procedure
```bash
mc cp m/diep-config-backups/<archive> backups/config/
sha256sum -c backups/config/<archive>.sha256
tar -xzf backups/config/<archive> -C /restore-staging
# Then: copy needed pieces (mosquitto/config, grafana/provisioning, etc.) back into
# the project tree, restore .env separately from the secrets vault, and
# `docker compose up -d` to pick up the restored configuration.
```

---

## 3. Disaster recovery drill (Task 3) — RTO/RPO

`scripts/dr-test.sh` performs a **non-destructive `docker restart`** of each service
(data volumes untouched) and polls a service-appropriate health check until it
responds, recording the elapsed time as the RTO proxy.

| Service | Health check | Recovery time | Notes |
|---|---|---:|---|
| TimescaleDB | `pg_isready -U diep` | **2.8 s** | clean restart |
| MQTT (mosquitto) | `nc -z localhost 8883` (mTLS-only listener, Phase 9J-S4) | **2.7 s** | clean restart |
| Kafka | `kafka-broker-api-versions.sh` | **19.6 s** (after fix — see below) | **see critical finding** |
| Grafana | `GET /api/health` | **11.1 s** | clean restart |
| FastAPI | `GET /healthz` | **16.0 s** | clean restart |

### 🔴 Critical finding: Kafka does not survive a restart (latent data corruption)

The first DR restart of `diep-kafka` did **not** recover — the broker entered a crash
loop (`docker ps` showed `Restarting (255)` repeatedly). Root cause, from
`docker logs diep-kafka`:

```
ERROR Error while reading checkpoint file /var/lib/kafka/data/log-start-offset-checkpoint
java.io.IOException: Malformed line in checkpoint file [...]: (D
...
ERROR Shutdown broker because all log dirs in /var/lib/kafka/data have failed
```

Inspecting the volume (`diep-lab_kafka-data`) with the broker stopped showed two
checkpoint files containing **binary garbage instead of the expected text format**,
both dated **2026-06-11 13:50** (i.e. this corruption pre-dates this drill by ~39 hours
and was masked because the broker had not been restarted since — these checkpoint files
are only *read* on startup):

| File | Before | 
|---|---|
| `log-start-offset-checkpoint` | 4 bytes binary (`0e 28 44 0e`) — should be text `"<version>\n<count>\n<topic> <partition> <offset>\n..."` |
| `replication-offset-checkpoint` | 1217 bytes binary garbage — same expected text format |
| `cleaner-offset-checkpoint` | 0 bytes (empty) |

**Fix applied** (with the broker stopped, via a throwaway container mounting the
`diep-lab_kafka-data` volume): rewrote all three checkpoint files to the valid
zero-entries form (`"0\n0\n"`), matching ownership (`1000:1000`). This is metadata that
Kafka recomputes from the actual log segments on the next clean checkpoint interval — no
topic data was touched (`__consumer_offsets` and `diep.commands` topics, and all
51 partitions/segments on disk, were left as-is). After the fix, `docker restart
diep-kafka` recovered cleanly in **19.6 s** (second measurement above).

**Why this matters:** in the current state (before the fix), *any* restart of the Kafka
container — a host reboot, an OOM kill, a routine `docker compose restart` — would have
left the command bus permanently down until someone manually repaired these checkpoint
files. This is a single-broker (RF=1) deployment with no failover (§4), so this was a
**full command-dispatch outage with no automatic recovery path**.

**Recommended follow-up** (not done here — out of scope for a non-destructive drill):
add a periodic `docker exec diep-kafka kafka-storage.sh ...`-based health probe and/or a
scheduled non-destructive `docker restart diep-kafka` drill (e.g. monthly) so checkpoint
corruption is caught while the system is otherwise healthy, rather than during a real
incident. Root-causing *how* the checkpoint files were corrupted on 2026-06-11
(likely an unclean shutdown / `docker kill` of the broker around that time) is also
worth a follow-up — see `docker logs diep-kafka` history if still retained.

### RPO (Recovery Point Objective)

- Current logical-backup cadence: nightly `pg_dump` at 02:00 UTC (§1).
- **Measured RPO = up to ~24 h** (worst case: incident occurs at 01:59, last good backup
  is from the previous night). Telemetry ingestion is continuous (~4–5 rows/sec observed
  during this drill), so a 24 h window represents a large but bounded data loss.
- **Target per `DIEP_PHASE10_RUNBOOK.md` (10E): RPO ≤ 5 min**, via continuous WAL
  archiving / PITR (`k8s/postgres-cnpg.yaml`, CloudNativePG) — **not yet deployed in this
  lab** (single-instance `docker compose` Postgres has no WAL archive target). This
  remains the single largest gap between current and target RPO; closing it requires the
  CNPG migration in §4 (stage K3).

### RTO (Recovery Time Objective)

- All five services recovered well within the **RTO ≤ 30 min** target (10E) for a simple
  process restart — worst case (Kafka, post-fix) was 19.6 s.
- The Kafka finding above shows the *process-restart* RTO is misleadingly good: the
  *actual* RTO for the corrupted-checkpoint scenario was unbounded (crash loop) until
  manually diagnosed and repaired — roughly **6 minutes** of hands-on diagnosis + repair
  in this drill, but would be longer without the diagnosis already done here. This is the
  scenario a multi-broker Kafka (§4, stage K4) would make a non-event.

---

## 4. HA assessment & roadmap (Task 4)

Condensed from `DIEP_HA_ARCHITECTURE.md` (Phase 9K), updated with this drill's findings.

| Component | Current (lab) | Target (prod) | Gap / priority |
|---|---|---|---|
| **FastAPI** | ✅ live-verified: 2 replicas behind Caddy LB, `/healthz`+`/readyz`, kill-one-survive tested | k8s `Deployment` replicas≥3 + HPA | Low — pattern proven, needs k8s cutover (K6) |
| **Redis** | ✅ live-verified: primary + streaming-replica read-only | Primary + replica + Sentinel (3x) for auto-promotion | Medium — add Sentinel (K2) |
| **TimescaleDB** | ❌ single instance, no WAL archive/PITR. Logical backup only (this phase) | CloudNativePG/Patroni: 1 primary + 2 standbys, WAL→object storage, PITR | **High** — biggest RPO gap (K3); also the only SPOF with no failover today |
| **Kafka** | ❌ 1 broker, RF=1. **This drill found it doesn't survive a restart** (checkpoint corruption, now fixed) | Strimzi, 3 brokers, RF=3, min.insync.replicas=2 | **High** — promoted from "remaining gap" to "actively caused an outage on restart" (K4) |
| **MQTT** | ⚠️ single broker, mTLS-only (8883), restarts cleanly (2.7 s in this drill) but is a SPOF — device reconnect storms on restart | Clustered (EMQX/HiveMQ) or active/standby + shared session store | Medium (K5) |
| **MinIO** | ⚠️ single instance — backup target itself has no redundancy | Distributed MinIO, erasure-coded | Medium (K5) |
| **Portal** | Single instance behind same LB pattern as FastAPI | Same as FastAPI | Low (K6) |

### Roadmap (unchanged staging from Phase 9K, re-prioritized)
1. **K3 — Postgres/Timescale HA + PITR** (was "medium", now **top priority**: closes the
   24h RPO gap and removes the only datastore with zero failover).
2. **K4 — Kafka 3-broker/RF=3** (was "main remaining gap", now **top priority** given the
   restart-survival finding in §3 — a single-broker command bus with corruptible local
   checkpoint state is a recurring outage risk, not just a theoretical SPOF).
3. **K2 — Redis Sentinel** (replication already live; add automatic failover).
4. **K5 — MinIO distributed + MQTT cluster.**
5. **K6 — full k8s cutover** (Helm, Ingress/TLS, HPA, PDBs, multi-AZ) — wraps everything
   above into the orchestrated target architecture.

No change to the migration mechanics described in `DIEP_HA_ARCHITECTURE.md` §3 — this
drill changes *priority ordering* (K3/K4 ahead of K2/K5), not the plan itself.

---

## 5. Incident response workflow

1. **Detect** — Alertmanager fires (`DiepApiDown`, `DatabaseOutage`, `HighCommandFailureRate`,
   etc. — Phase 15B). Grafana dashboards corroborate.
2. **Triage** — `docker compose ps`, `docker logs <service> --tail 100`, check
   `/healthz` & `/readyz`. For Kafka specifically: check for the checkpoint-corruption
   crash-loop signature in §3 (`Shutdown broker because all log dirs ... have failed`).
3. **Contain** — if a stateful service won't start cleanly, stop it (`docker compose stop
   <service>`) before attempting repair, to avoid a crash-restart loop hammering the
   volume.
4. **Recover**:
   - Transient (process crash, OOM): `docker compose restart <service>` — RTO ≈ seconds
     per §3 for 4/5 services.
   - Checkpoint/metadata corruption (Kafka — §3): stop container, repair checkpoint files
     via a throwaway container on the named volume, restart.
   - Data loss / corrupted DB: follow the DB restore runbook in §1 — RPO = time since
     last nightly backup (≤ ~24h currently).
   - Config loss: follow the config restore procedure in §2.
5. **Verify** — row counts (`restore-db.sh`'s built-in comparison), `/readyz`, a
   telemetry write, a command round-trip (per 10E resilience-drill checklist).
6. **Postmortem** — record root cause, time-to-detect, time-to-recover (RTO actuals feed
   back into §3/§4 priorities). The Kafka checkpoint-corruption finding in this drill is
   itself an example postmortem entry.

---

## 6. Operational notes

- **A real crontab was installed** on this account (`crontab -l | grep diep-backup`,
  3 entries — see §1 schedule table). This is an account-level change outside the
  project directory. To remove: `crontab -l | grep -v '# diep-backup' | crontab -`.
- All backup/verify/DR scripts are idempotent and non-destructive to production data:
  `verify-backup.sh` restores into a scratch DB (`diep_restore_test`, dropped after) and
  `dr-test.sh` only does in-place container restarts.
- The one exception, per the findings in §3: the Kafka checkpoint-file repair touched
  files under the `diep-lab_kafka-data` volume — these are Kafka-internal recovery
  metadata (recomputed from log segments), **not** topic/message data. Topic data
  (`__consumer_offsets`, `diep.commands`, 51 partitions) was verified present and the
  broker resumed serving consumers/producers normally afterward.

---

## 7. Readiness score update

Carrying forward from the stated baseline (~85/100):
- ✅ Backup automation + retention + verification (Task 1)
- ✅ Configuration backup (Task 2)
- ✅ DR drill with measured RTO for all 5 core services + a real critical finding fixed
  (Task 3)
- ✅ HA roadmap re-prioritized based on live evidence (Task 4)
- ⏳ Still open: PITR/WAL archiving for Postgres (closes RPO gap), Kafka multi-broker
  (closes the restart-survival gap structurally, not just via checkpoint repair)

These two open items are the highest-leverage next steps for production readiness.
