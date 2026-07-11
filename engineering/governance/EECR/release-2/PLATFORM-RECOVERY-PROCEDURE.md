# Platform Recovery Procedure
### RE-OS Development Platform | Disaster Recovery and Container Recovery Guide

---

## 1. VM Recovery Procedure

### 1.1 Trigger Conditions

This procedure applies when:
- VM becomes unresponsive or unreachable
- Hypervisor reports VM error or power loss
- Write-ack corruption observed (containers report I/O errors or unexpected data loss)
- Platform stack fails to start after VM reboot

### 1.2 VM Recovery Steps

**Step 1 — Assess VM state via hypervisor**
- Check VM power state, CPU/memory, disk I/O errors in hypervisor console
- Review hypervisor event log for storage/hardware events

**Step 2 — Attempt graceful recovery**
- If VM is reachable: SSH in, run `docker ps` to assess container state
- If VM is not reachable: perform hard reset via hypervisor

**Step 3 — Platform stack start**
- Follow the Platform Restart Procedure (`PLATFORM-RESTART-PROCEDURE.md`)

**Step 4 — Data integrity check**
- Verify TimescaleDB table counts: `docker exec diep-timescaledb psql -U diep -d diep -c "SELECT count(*) FROM telemetry;"`
- Verify Kafka topics intact: `docker exec diep-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list`
- Verify Redis data: `docker exec diep-redis redis-cli -a $RPASS dbsize`

**Step 5 — WAL recovery (if database data loss)**
If TimescaleDB data is corrupted or missing, restore from WAL archive:
- Identify the last valid WAL segment in MinIO
- Follow the Snapshot Restoration Procedure to roll back to a known-good snapshot
- Apply WAL segments forward to the desired recovery point

**Step 6 — Post-recovery verification**
- Run the full post-recovery verification checklist (Section 3 below)
- Produce a Platform Recovery Verification Report

---

## 2. Container Recovery Guide

### 2.1 Individual Container Recovery

```bash
# Restart a single container
docker restart <container-name>

# View container logs before restart
docker logs <container-name> --tail 100

# Rebuild and restart (if image issues)
docker compose up -d --force-recreate <service-name>
```

### 2.2 TimescaleDB Recovery

TimescaleDB is the most critical container. Never force-remove it without data safety assessment.

```bash
# Check DB status
docker exec diep-timescaledb psql -U diep -d diep -c "\l"

# If container is in exit state — check logs first
docker logs diep-timescaledb --tail 50

# Safe restart (only if no I/O errors in logs)
docker restart diep-timescaledb

# Verify after restart
docker exec diep-timescaledb psql -U diep -d diep -c "SELECT version(), NOW();"
```

### 2.3 Kafka Recovery

```bash
# Check Kafka health
docker logs diep-kafka --tail 30

# Restart Kafka (consumers will automatically reconnect)
docker restart diep-kafka

# After restart, verify broker
docker exec diep-kafka /opt/kafka/bin/kafka-broker-api-versions.sh \
  --bootstrap-server localhost:9092 | head -3
```

Note: kafka-exporter will restart multiple times after Kafka restart — this is expected.
Wait 2–5 minutes for exporter to stabilise.

### 2.4 Redis Sentinel Recovery

```bash
RPASS=$(grep REDIS_PASSWORD .env | cut -d= -f2)

# Check master status
docker exec diep-redis redis-cli -a "$RPASS" info replication | grep role

# If replica is not syncing, restart replica
docker restart diep-redis-replica

# Verify sentinel quorum
docker exec diep-redis-sentinel-1 redis-cli -p 26379 -a "$RPASS" \
  sentinel masters 2>&1 | grep -E "name|status|num-slaves"
```

### 2.5 Prometheus Recovery

Prometheus exits cleanly when the VM is shut down (exit code 0). It does not auto-restart.

```bash
docker start diep-prometheus
sleep 5
PROM_IP=$(docker inspect diep-prometheus \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec diep-alertmanager wget -qO- "http://${PROM_IP}:9090/-/healthy"
```

### 2.6 WAL Shipper Recovery

The WAL shipper requires the correct MinIO alias to be set after any restart:

```bash
MINIO_IP=$(docker inspect diep-minio \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec diep-wal-shipper mc alias set diep-minio \
  "http://${MINIO_IP}:9000" diepadmin "$(grep MINIO_ROOT_PASSWORD .env | cut -d= -f2)"
```

This is handled automatically by the ship-wal.sh script on each cycle.

---

## 3. Post-Recovery Verification Checklist

Run after any recovery event before resuming engineering work:

```
[ ] git status — confirm on expected branch and commit
[ ] docker ps — confirm all containers running (25 expected)
[ ] curl http://localhost:8000/healthz — FastAPI healthy
[ ] TimescaleDB psql query succeeds
[ ] Kafka consumer group lag = 0
[ ] Redis PING returns PONG
[ ] Redis replication role = master
[ ] WAL shipper logs show: shipped=1 (recent cycle)
[ ] Prometheus healthy (start manually if needed)
[ ] Disk utilisation < 85%
[ ] Memory available > 500 MiB
[ ] No persistent errors in any container log
[ ] Produce Platform Recovery Verification Report
[ ] Take VM snapshot (hypervisor)
```

---

## 4. Backup Verification Procedure

### 4.1 WAL Archive Verification

```bash
# Set MinIO alias (if not already set)
MINIO_IP=$(docker inspect diep-minio --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec diep-wal-shipper mc alias set diep-minio \
  "http://${MINIO_IP}:9000" diepadmin "$(grep MINIO_ROOT_PASSWORD .env | cut -d= -f2)"

# List recent WAL segments
docker exec diep-wal-shipper mc ls diep-minio/diep-wal-archive | tail -10

# Current WAL LSN in database
docker exec diep-timescaledb psql -U diep -d diep \
  -c "SELECT pg_current_wal_lsn(), pg_walfile_name(pg_current_wal_lsn());"
```

Expected: WAL segments appearing every ~60 seconds, LSN advancing monotonically.

### 4.2 Verify WAL segment integrity

```bash
# Count total WAL segments
docker exec diep-wal-shipper mc ls diep-minio/diep-wal-archive | wc -l

# Verify most recent segment matches current WAL LSN
```

---

*Last updated: 2026-07-11T02:10:00Z*
