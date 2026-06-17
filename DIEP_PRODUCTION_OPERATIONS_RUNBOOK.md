# DIEP Production Operations Runbook
## HA Platform — Day-2 Operating Procedures

**Date:** 2026-06-17  
**Version:** 1.0  
**Classification:** Internal — Operations  
**Scope:** Ongoing operational procedures for DIEP production after Phase 17 HA cutover  
**Prerequisite:** `DIEP_PRODUCTION_CUTOVER_RUNBOOK.md` completed; all 5 maintenance windows done

---

## Overview

This runbook covers recurring operational tasks for the HA-enabled DIEP production platform. It is organized into daily, weekly, and monthly cycles, followed by tier-specific health check procedures and alert response playbooks.

All commands assume the operator is on the Docker Compose host with access to the production stack. Replace `$REDIS_PASSWORD`, `$KAFKA_SASL_USERNAME`, `$KAFKA_SASL_PASSWORD`, and `$EMQX_API_KEY` with values from the production `.env` or secrets manager.

---

## 1. Daily Checks

Target: complete within 15 minutes each morning before business-hours device activity ramps.

### 1.1 Platform Health Overview

```bash
# All containers running
docker compose ps

# API health
curl -sf http://localhost:8000/healthz && echo "API OK"
curl -sf http://localhost:8000/readyz && echo "All services ready"

# FastAPI metrics summary (last 5 min error rate)
curl -sf http://localhost:8000/metrics | grep http_requests_total
```

**Pass criteria:** All containers show `Up (healthy)`. `/healthz` and `/readyz` return 200 with all sub-checks true.

**If any container is not `Up (healthy)`:** See Section 10 (Alert Response) for the relevant tier.

### 1.2 Latest Backup Age

```bash
# Verify a pg_dump completed in the last 25 hours
docker exec minio-ha-0 mc ls local/diep-backups/ | tail -3
# Most recent object should be dated today or yesterday

# Verify WAL archive is flowing (latest WAL < 2 min old)
docker exec minio-ha-0 mc ls local/diep-wal-archive/ | tail -3
# Timestamp should be within the last 70 seconds
```

**Pass criteria:** Latest backup object < 25h old. Latest WAL segment < 2 min old (reflecting `archive_timeout=60` + ~10s shipping).

**If backup age > 25h:** Investigate `backup-db.sh` cron; check MinIO HA connectivity; see Section 10.5.

### 1.3 Alertmanager — No Unexpected Firing Alerts

```bash
curl -sf http://localhost:9093/api/v2/alerts | python3 -m json.tool | grep '"status"'
# Expect: all "active" alerts are either silenced or known/expected
```

**Pass criteria:** No unsilenced firing alerts.

**If alerts are firing:** Address per Section 10 before proceeding.

### 1.4 Telemetry Flow Spot Check

```bash
# Most recent telemetry reading (last 5 min)
docker exec pg-ha-1 psql -U diep_user -d diep_db \
  -c "SELECT device_id, time, value FROM telemetry_readings ORDER BY time DESC LIMIT 5;"
```

**Pass criteria:** At least 1 row per connected device within the last 5 minutes. For sites with overnight device inactivity, verify at least 1 reading today.

---

## 2. Weekly Checks

Target: complete within 30 minutes, typically on Monday morning.

### 2.1 Backup Restore Verification

```bash
scripts/verify-backup.sh
```

**Pass criteria:** Script exits 0. If the verify script performs a pg_restore to a test schema, confirm row count matches expected baseline.

### 2.2 WAL Archive Continuity

```bash
# Confirm WAL segment timestamps have no gap > 5 minutes
docker exec minio-ha-0 mc ls local/diep-wal-archive/ | \
  awk '{print $1, $2}' | tail -20
# Look for consistent timestamp progression without large gaps
```

**Pass criteria:** No gap larger than 5 minutes between consecutive WAL segment timestamps (reflects `archive_timeout=60` interval).

### 2.3 Certificate Expiry Review

```bash
# DIEP Root CA
openssl x509 -in certs/ca.crt -noout -enddate
# Expected: Dec 31 2035 (10-year CA from 2026)

# EMQX server cert
openssl x509 -in certs/emqx-server.crt -noout -enddate

# Device certs (sample 3)
for cert in certs/INV001.crt certs/BAT001.crt certs/dispatcher.crt; do
  echo -n "$cert: "
  openssl x509 -in $cert -noout -enddate
done
```

**Pass criteria:** All certificates > 90 days from expiry. Alert if any cert < 30 days. Root CA expiry is 2036 — no action needed until 2034.

### 2.4 Kafka Consumer Lag

```bash
docker exec diep-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  --describe --all-groups
```

**Pass criteria:** All consumer groups show LAG = 0 or < 10 (minor transient lag is normal). Persistent lag > 100 indicates a stalled consumer.

### 2.5 Disk Usage Trend

```bash
df -h
docker system df
```

**Pass criteria:** No volume > 80% full. WAL archive and backup volumes growing at expected rate (≤ 1 GB/day per environment).

**If any volume > 80%:** Investigate backup retention; run `scripts/backup-db.sh` with cleanup; escalate if WAL archive is filling.

### 2.6 TimescaleDB Chunk and Compression Health

```bash
docker exec pg-ha-1 psql -U diep_user -d diep_db -c "
SELECT chunk_schema, chunk_name, is_compressed, range_start, range_end
FROM timescaledb_information.chunks
ORDER BY range_end DESC LIMIT 10;
"
```

**Pass criteria:** Recent chunks (last 7 days) exist and match expected cadence. Old chunks are compressed (is_compressed = true for chunks > retention threshold).

---

## 3. Monthly Checks

Target: scheduled maintenance window, typically first Monday of the month.

### 3.1 PITR Drill

Perform a point-in-time recovery to a timestamp 24h ago in an isolated test environment. Do not use production volumes.

```bash
# Start a test container with access to the WAL archive volume (read-only)
docker run --rm \
  -v diep-wal-archive:/mnt/wal-archive:ro \
  -v /tmp/pitr-test-$(date +%Y%m):/var/lib/postgresql/data \
  timescale/timescaledb-ha:pg16 \
  bash -c "
    pg_restore_target=$(date -d '24 hours ago' '+%Y-%m-%d %H:%M:%S')
    # Full PITR procedure per K1_PITR_IMPLEMENTATION_PLAN.md §6
    echo restore_command = \"cp /mnt/wal-archive/%f %p\" >> /var/lib/postgresql/data/postgresql.conf
    echo recovery_target_time = \"'$pg_restore_target'\" >> /var/lib/postgresql/data/recovery.conf
  "
```

**Pass criteria:** Restore completes. Row count at T-24h matches expected. PITR time is ≤ 20 minutes for a full restore. WAL promote completes in ≤ 15s.

### 3.2 Patroni Failover Drill (Planned)

```bash
# Planned graceful switchover — no data loss
docker exec pg-ha-1 patronictl -c /etc/patroni/patroni.yml list
# Note current Leader

docker exec pg-ha-1 patronictl -c /etc/patroni/patroni.yml \
  switchover --master $(docker exec pg-ha-1 patronictl list | grep Leader | awk '{print $2}') \
  --candidate pg-ha-2 --force

sleep 30
docker exec pg-ha-1 patronictl list
# Verify pg-ha-2 is now Leader; original primary rejoined as Replica
```

**Pass criteria:** Switchover completes within 35s. `/readyz` returns true throughout (HAProxy transparently reroutes). Original primary rejoins as standby within 30s.

### 3.3 Kafka Broker Resilience Drill

```bash
# Kill one non-leader broker
docker stop kafka-2
sleep 5

# Verify cluster is still serving producers and consumers
docker exec diep-kafka kafka-topics.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  --describe --topic diep.commands
# ISR should show 2 remaining brokers (min.isr=2 — still satisfied)

# Restart the stopped broker
docker start kafka-2
sleep 90  # ISR restoration takes ~72s after crash
docker exec kafka-2 kafka-topics.sh \
  --bootstrap-server kafka-2:9092 \
  --describe --topic diep.commands
# ISR should be back to 3
```

**Pass criteria:** No consumer lag increase during single-broker outage. ISR restores to 3 within 90s of broker restart.

### 3.4 Redis Sentinel Failover Drill

```bash
# Stop the Redis primary
docker stop diep-redis
sleep 10

# Verify sentinel promoted the replica
docker exec redis-sentinel-1 redis-cli -p 26379 sentinel masters | grep -A 5 diep-cache
# Should show: flags: master (not master,down)

# Verify application is writing to new primary
curl http://localhost:8000/readyz | python3 -m json.tool | grep redis
# Should show: "redis": true

# Restart original primary (should rejoin as replica)
docker start diep-redis
sleep 25
docker exec diep-redis redis-cli -a $REDIS_PASSWORD info replication | grep role
# Should show: role:slave
```

**Pass criteria:** Failover completes within 10s. `/readyz` returns redis:true within 15s. Original primary rejoins as replica within 25s.

### 3.5 MinIO Single-Node Failure Drill

```bash
# Stop one MinIO node
docker stop minio-ha-1
sleep 5

# Verify reads and writes continue
docker exec minio-ha-0 mc cp /etc/hostname local/diep-backups/health-check-$(date +%s).txt
docker exec minio-ha-0 mc ls local/diep-backups/ | tail -3
# Both should succeed

# Restart the stopped node
docker start minio-ha-1
sleep 10
docker exec minio-ha-0 mc admin info local/ | grep -A 2 "Disks"
# All 4 disks should be online
```

**Pass criteria:** Zero client-visible disruption during single-node failure. Self-heal (disk returns online) within 15s of container restart.

### 3.6 EMQX Rolling Restart Drill

```bash
# Restart nodes one at a time (F4 drill from K5)
for node in emqx-ha-1 emqx-ha-2 emqx-ha-3; do
  echo "Restarting $node..."
  docker compose restart $node
  sleep 25  # Wait for node to rejoin cluster (~15-20s)
  curl -sf http://$node.local:18083/status | python3 -m json.tool | grep node_status
  # Should show: "node_status": "running"
done

# Verify all 3 nodes are in cluster after roll
curl -sf http://emqx-ha-haproxy:18083/api/v5/nodes \
  -H "Authorization: Bearer $EMQX_API_KEY" | python3 -m json.tool | grep running
# Should show 3 nodes running
```

**Pass criteria:** Cluster maintains ≥ 2 healthy nodes throughout rolling restart. All 3 nodes healthy after completion. Subscriber reconnects ≤ 2 (one per core-node restart that held existing TCP connections).

### 3.7 Capacity Review

Review the following growth metrics and project 90-day runway:
- `telemetry_readings` table size: `SELECT pg_size_pretty(pg_total_relation_size('telemetry_readings'));`
- WAL archive volume used: `docker exec minio-ha-0 mc du local/diep-wal-archive/`
- Backup bucket used: `docker exec minio-ha-0 mc du local/diep-backups/`
- Docker volume usage: `docker system df -v`

---

## 4. Backup Verification

### 4.1 Automated Backup Verification

The weekly `scripts/verify-backup.sh` performs an automated restore test. To run manually:

```bash
scripts/verify-backup.sh
# Exit 0 = PASS
# Exit non-zero = see output for failure detail
```

### 4.2 Manual Backup Listing and Age Check

```bash
# List last 5 pg_dump backups with timestamps
docker exec minio-ha-0 mc ls --recursive local/diep-backups/ | grep ".dump" | tail -5

# List last 5 config backups
docker exec minio-ha-0 mc ls --recursive local/diep-config-backups/ | tail -5

# Verify pg_dump is not corrupted (check custom-format header)
docker exec minio-ha-0 mc cat local/diep-backups/latest.dump | head -c 5 | xxd
# Should show: 50 47 44 4d 50 (PGDMP magic bytes)
```

### 4.3 Manual pg_dump Trigger

```bash
# Trigger an on-demand backup outside the scheduled window
docker exec diep-timescaledb bash scripts/backup-db.sh
# Or if backup runs from host:
bash scripts/backup-db.sh
```

### 4.4 Backup Retention Verification

```bash
# Confirm old backups are being pruned (retention policy enforced)
docker exec minio-ha-0 mc ls --recursive local/diep-backups/ | wc -l
# Count should reflect the retention window (e.g., if 30-day retention, < 35 dump files)
```

---

## 5. PITR Verification

### 5.1 WAL Archive Freshness

```bash
# Latest WAL segment should be < 70s old
docker exec minio-ha-0 mc ls local/diep-wal-archive/ | tail -1
# Timestamp should be within the last 70 seconds

# Force WAL switch and verify it archives
docker exec pg-ha-1 psql -U diep_user -d diep_db \
  -c "SELECT pg_switch_wal();"
sleep 15
docker exec minio-ha-0 mc ls local/diep-wal-archive/ | tail -1
# New WAL segment should appear
```

### 5.2 Base Backup Freshness

```bash
# A base backup should have been taken at initial cutover
# Verify it is present and accessible
docker exec minio-ha-0 mc ls local/diep-pg-basebackups/
```

**Recommendation:** Take a fresh base backup monthly (after the monthly drill) to reduce PITR restore time:

```bash
docker exec pg-ha-1 pg_basebackup \
  -h localhost -U diep_user \
  -D /tmp/monthly-basebackup \
  -Fp -Xs -P
docker exec minio-ha-0 mc cp -r /tmp/monthly-basebackup \
  local/diep-pg-basebackups/$(date +%Y%m)/
```

### 5.3 PITR RPO Check

The current `archive_timeout=60` bounds RPO to ≤ 65s. To measure actual shipping latency:

```bash
# Record pre-switch LSN
docker exec pg-ha-1 psql -U diep_user -d diep_db \
  -c "SELECT pg_walfile_name(pg_current_wal_lsn());"

# Switch WAL and time how long until it appears in MinIO
docker exec pg-ha-1 psql -U diep_user -d diep_db \
  -c "SELECT pg_switch_wal();"
date  # Record switch time

# Poll until new WAL appears
while true; do
  docker exec minio-ha-0 mc ls local/diep-wal-archive/ | tail -1
  sleep 2
done
# Record appearance time — difference is shipping latency (expected: ~10–15s)
```

---

## 6. Kafka Cluster Health Checks

### 6.1 Broker Membership

```bash
docker exec diep-kafka kafka-metadata-quorum.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  describe --status
```

**Expected:** 3 observers: 1 Leader, 2 Followers. All caught up (`LAG` ≈ 0 for all voters).

### 6.2 ISR (In-Sync Replicas) Status

```bash
docker exec diep-kafka kafka-topics.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  --describe --topic diep.commands
```

**Expected output:**
```
Topic: diep.commands    PartitionCount: 6    ReplicationFactor: 3    Configs: min.insync.replicas=2
    Partition: 0    Leader: 1    Replicas: 1,2,3    Isr: 1,2,3
    ...
```

**Degraded state:** If any partition shows `Isr` with fewer than 3 brokers, a broker has fallen behind. If `Isr` drops to 1, producers with `acks="all"` will fail (below min.insync.replicas=2).

### 6.3 Consumer Group Lag

```bash
docker exec diep-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  --describe --group diep-telemetry-ingestor

docker exec diep-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  --describe --group diep-command-dispatcher
```

**Expected:** LAG = 0 for all partitions in each consumer group.

**If LAG > 100 and growing:** Check if the consumer container is running and healthy. Check consumer logs for errors.

### 6.4 Controller Election Health

```bash
docker exec diep-kafka kafka-metadata-quorum.sh \
  --bootstrap-server localhost:9094 \
  --command-config /etc/kafka/client.properties \
  describe --replication
```

**Expected:** All 3 brokers are replicated quorum members with `Status: Voter`.

---

## 7. Redis Sentinel Health Checks

### 7.1 Sentinel Master Status

```bash
docker exec redis-sentinel-1 redis-cli -p 26379 sentinel masters
```

**Expected key fields:**
- `flags: master` (NOT `master,down` or `s_down` or `o_down`)
- `num-slaves: 1`
- `num-other-sentinels: 2`
- `quorum: 2`

### 7.2 Replica Replication Lag

```bash
REDIS_PRIMARY=$(docker exec redis-sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name diep-cache | head -1)
docker exec diep-redis redis-cli -a $REDIS_PASSWORD \
  -h $REDIS_PRIMARY info replication | grep -E "role|connected_slaves|slave0"
```

**Expected:** `role:master`, `connected_slaves:1`, `slave0: ip=<replica-ip>,state=online,lag=0`.

### 7.3 Tilt Detection

```bash
# Check for +tilt flag in sentinel logs (indicates hostname resolution failure)
docker logs redis-sentinel-1 --tail=50 | grep -i tilt
```

**If `+tilt` appears:** Sentinel entered tilt mode due to hostname resolution failure or clock jump. This is the `resolve-hostnames yes` failure mode documented in K4. Verify that IP-based `sentinel monitor` seeding is in use and that sentinel containers have not had their IPs reassigned. See Section 10.4 for tilt recovery procedure.

### 7.4 Sentinel Quorum Check

```bash
docker exec redis-sentinel-1 redis-cli -p 26379 sentinel ckquorum diep-cache
```

**Expected:** `OK N sentinels, quorum ok` (2/2 quorum required).

---

## 8. EMQX Cluster Health Checks

### 8.1 Cluster Node Count

```bash
curl -sf http://emqx-ha-haproxy:18083/status
# Returns: {"node_status":"running"} from any living backend

curl -sf http://emqx-ha-1.local:18083/api/v5/nodes \
  -H "Authorization: Bearer $EMQX_API_KEY" | python3 -m json.tool | grep '"node_status"'
# Should show "running" 3 times
```

### 8.2 Connected Clients and Sessions

```bash
curl -sf http://emqx-ha-1.local:18083/api/v5/stats \
  -H "Authorization: Bearer $EMQX_API_KEY" | python3 -m json.tool | \
  grep -E '"connections.count"|"sessions.count"'
```

**Expected:** Connections count matches number of active DIEP devices + ingestor + dispatcher.

### 8.3 EMQX ACL / AuthZ Status

```bash
curl -sf http://emqx-ha-1.local:18083/api/v5/authorization/sources \
  -H "Authorization: Bearer $EMQX_API_KEY" | python3 -m json.tool
```

**Expected:** ACL source configured and enabled. Type should match the production ACL backend (file-based or built-in database).

### 8.4 mTLS Certificate Check (Operational)

```bash
# Confirm EMQX is still enforcing client cert requirement
echo | openssl s_client -connect localhost:8883 -CAfile certs/ca.crt 2>&1 | \
  grep -i "certificate required"
# Expected: alert certificate required
```

### 8.5 HAProxy Backend Health

```bash
echo "show stat" | docker exec -i emqx-ha-haproxy socat stdio /var/run/haproxy/admin.sock | \
  grep -E "^emqx_ssl" | cut -d',' -f1,18
# Should show: emqx_ssl,emqx-ha-1,UP and similar for -2 and -3
```

---

## 9. MinIO Health Checks

### 9.1 Cluster Disk Status

```bash
docker exec minio-ha-0 mc admin info local/ | grep -E "Disks|Status"
# Expected: 4 disks, all Online
```

### 9.2 Erasure Set Health

```bash
docker exec minio-ha-0 mc admin heal -r local/
# If all healthy, this should report nothing to heal
```

### 9.3 Object Integrity Spot Check

```bash
# Verify most recent backup object is readable
LATEST=$(docker exec minio-ha-0 mc ls local/diep-backups/ | tail -1 | awk '{print $NF}')
docker exec minio-ha-0 mc stat local/diep-backups/$LATEST
# Should show object size > 0 and ETag present (no corruption)
```

### 9.4 Bloom-Cycle Scanner State (2-node failure recovery check)

This check applies only after a 2-of-4 node simultaneous failure event. After both nodes recover:

```bash
# Verify writes are operational (would fail if bloom-cycle state is inconsistent)
docker exec minio-ha-0 mc cp /etc/hostname local/diep-backups/bloom-check-$(date +%s).txt
# If this fails with "write quorum insufficient" despite 4 nodes being up:
# Perform coordinated cluster restart (documented recovery step):
docker compose restart minio-ha-0 minio-ha-1 minio-ha-2 minio-ha-3
sleep 20
docker exec minio-ha-0 mc cp /etc/hostname local/diep-backups/bloom-check-$(date +%s).txt
```

---

## 10. Alert Response Procedures

### 10.1 DatabaseOutage / Patroni Primary Unreachable

**Symptoms:** `curl http://localhost:8000/readyz` → `{"timescaledb": false}`. `DatabaseOutage` alert firing.

**Response:**

1. Check HAProxy is routing to the correct Patroni primary:
   ```bash
   curl http://pg-ha-haproxy:8008/primary
   # 200 = HAProxy can reach primary
   # Non-200 = HAProxy cannot find a healthy primary
   ```

2. Check Patroni cluster state:
   ```bash
   docker exec pg-ha-1 patronictl -c /etc/patroni/patroni.yml list
   # Is there a Leader? Is it Running?
   ```

3. If no Leader (all nodes in standby or stopped):
   - Check if etcd DCS is reachable: `docker exec pg-ha-1 curl http://pg-ha-etcd:2379/health`
   - If etcd is down, Patroni cannot acquire leader lock; restore etcd first
   - If etcd is healthy but no election: check Patroni logs on each node: `docker logs pg-ha-1 --tail=30`

4. If one node crashed (hardware or OOM), Patroni auto-promotes the sync standby. Wait up to 35s for promotion, then verify:
   ```bash
   docker exec pg-ha-1 patronictl list
   curl http://pg-ha-haproxy:8008/primary
   ```

5. If manual failover required:
   ```bash
   docker exec pg-ha-2 patronictl -c /etc/patroni/patroni.yml failover --master <current-leader> --candidate pg-ha-2 --force
   ```

6. Check application reconnection (psycopg2 reconnects on next query via HAProxy):
   ```bash
   curl http://localhost:8000/readyz
   ```

**Escalate to P1 if:** No primary can be elected within 5 minutes. Etcd is unreachable and no Patroni node can acquire the DCS lock.

---

### 10.2 KafkaOutage / Kafka Broker Count < 3

**Symptoms:** `KafkaOutage` alert or `kafka_cluster_nodes_running < 3`. ISR drops below 2 on any partition.

**Response:**

1. Check which broker is down:
   ```bash
   docker compose ps kafka-2 kafka-3 diep-kafka
   ```

2. If a broker container exited, restart it:
   ```bash
   docker compose start kafka-2  # or whichever is down
   sleep 30  # Allow ISR restoration (~72s after crash)
   ```

3. Verify ISR is restored:
   ```bash
   docker exec diep-kafka kafka-topics.sh --bootstrap-server localhost:9094 \
     --command-config /etc/kafka/client.properties \
     --describe --topic diep.commands
   # Verify ISR shows all 3 brokers
   ```

4. If ISR remains at 2 (one broker refused to rejoin): check broker logs:
   ```bash
   docker logs kafka-2 --tail=50 | grep -i error
   ```

5. If consumer lag accumulated during the outage, it will self-drain. No manual action needed unless lag persists > 10 min.

**Escalate to P1 if:** ISR drops below min.insync.replicas=2 — producers with `acks="all"` will fail. This means 2+ brokers are down simultaneously.

---

### 10.3 Redis Sentinel — Primary Failure or +tilt

**Symptoms:** `/readyz` → `{"redis": false}`. Sentinel shows `flags: master,down`.

**Response (automatic failover path):**

1. Redis Sentinel should automatically elect the replica as new primary within ~6–7s. Verify:
   ```bash
   docker exec redis-sentinel-1 redis-cli -p 26379 sentinel masters | grep flags
   # Expected: "flags: master" (no "down" flag)
   ```

2. If failover completed, verify application reconnected:
   ```bash
   curl http://localhost:8000/readyz | python3 -m json.tool | grep redis
   # Expected: "redis": true
   ```

3. Restart original primary (it will rejoin as replica):
   ```bash
   docker start diep-redis
   sleep 25
   docker exec diep-redis redis-cli -a $REDIS_PASSWORD info replication | grep role
   # Expected: role:slave
   ```

**Response (+tilt recovery):**

If sentinel logs show `+tilt` and no failover occurs within 30s:

1. `+tilt` means sentinel is in monitoring-only mode (no failover decisions). Root cause: Docker hostname resolution failure.
2. Verify IP-based sentinel monitor is configured (not hostname): check sentinel config for `sentinel monitor diep-cache <IP>` (not hostname).
3. If container IP changed after restart: update sentinel monitor seeding in entrypoint script and restart sentinels:
   ```bash
   docker compose restart redis-sentinel-1 redis-sentinel-2 redis-sentinel-3
   docker exec redis-sentinel-1 redis-cli -p 26379 sentinel masters
   # flags should return to normal (no tilt)
   ```

**Escalate to P1 if:** Both primary and replica are down simultaneously. Cache is empty until one is restored and the other resyncs.

---

### 10.4 EMQXClusterDegraded / EMQX Node Count < 3

**Symptoms:** `EMQXClusterDegraded` alert. One or more EMQX nodes unreachable from HAProxy.

**Response:**

1. Check which EMQX node is down:
   ```bash
   curl -sf http://emqx-ha-1.local:18083/api/v5/nodes \
     -H "Authorization: Bearer $EMQX_API_KEY" | python3 -m json.tool | grep -E '"name"|"node_status"'
   ```

2. If a node container exited:
   ```bash
   docker compose start emqx-ha-2  # or whichever is down
   sleep 25  # ~15–20s for node to rejoin Mnesia cluster
   curl -sf http://emqx-ha-2.local:18083/status
   ```

3. Verify HAProxy removed the failed node from rotation (existing connections not disrupted):
   ```bash
   echo "show stat" | docker exec -i emqx-ha-haproxy socat stdio /var/run/haproxy/admin.sock | \
     grep emqx_ssl
   ```

4. If a node fails to restart (Mnesia state inconsistency): perform a full volume teardown for that node only:
   ```bash
   docker compose stop emqx-ha-2
   docker volume rm emqx-ha-2-data
   docker compose up -d emqx-ha-2
   # Node bootstraps fresh, joins existing cluster schema
   ```
   > **Note:** This requires node-2 to have been stopped cleanly (not a crash with in-flight Mnesia writes). For crash recovery, consult EMQX documentation on Mnesia schema repair.

**Escalate to P1 if:** 2 of 3 EMQX nodes are down. HAProxy has no healthy backend. All MQTT device connections are dropped.

---

### 10.5 MinioDiskDegraded / MinIO Disk Count < 4

**Symptoms:** `MinioDiskDegraded` alert. `mc admin info` shows < 4 disks.

**Response:**

1. Identify which node is down:
   ```bash
   docker exec minio-ha-0 mc admin info local/ | grep -i offline
   ```

2. Restart the affected MinIO container:
   ```bash
   docker compose start minio-ha-1  # or whichever is offline
   sleep 10
   docker exec minio-ha-0 mc admin info local/ | grep Disks
   # Should show all 4 Online
   ```

3. Verify reads and writes are operational:
   ```bash
   docker exec minio-ha-0 mc cp /etc/hostname local/diep-backups/health-$(date +%s).txt
   docker exec minio-ha-0 mc ls local/diep-backups/ | tail -1
   ```

4. If 2 nodes went down simultaneously and have now both recovered: check write capability first, as bloom-cycle scanner state may be inconsistent:
   ```bash
   docker exec minio-ha-0 mc cp /etc/hostname local/diep-backups/bloom-check-$(date +%s).txt
   # If this fails with write quorum insufficient despite 4 nodes online:
   docker compose restart minio-ha-0 minio-ha-1 minio-ha-2 minio-ha-3
   sleep 20
   # Retry write — should succeed after coordinated restart
   ```

**Escalate to P1 if:** 3 or more nodes are offline simultaneously (below EC:2 read quorum). Object reads will fail. WAL archiving will fail.

---

### 10.6 DiepApiDown

**Symptoms:** `DiepApiDown` alert. `curl http://localhost:8000/healthz` → connection refused or 5xx.

**Response:**

1. Check FastAPI container status:
   ```bash
   docker compose ps diep-fastapi
   docker logs diep-fastapi --tail=30
   ```

2. If container exited: restart it:
   ```bash
   docker compose start diep-fastapi
   sleep 5
   curl http://localhost:8000/healthz
   ```

3. If FastAPI is running but unhealthy: check `/readyz` for the failing sub-check:
   ```bash
   curl http://localhost:8000/readyz | python3 -m json.tool
   # Identify which backend (timescaledb, redis, kafka) is returning false
   # Then address the corresponding tier per sections 10.1–10.5
   ```

---

## Appendix: Quick Reference Commands

| Check | Command |
|---|---|
| All containers health | `docker compose ps` |
| API health | `curl -sf http://localhost:8000/readyz` |
| Patroni cluster state | `docker exec pg-ha-1 patronictl list` |
| Patroni primary check | `curl http://pg-ha-haproxy:8008/primary` |
| Kafka quorum status | `docker exec diep-kafka kafka-metadata-quorum.sh ... describe --status` |
| Kafka topic ISR | `docker exec diep-kafka kafka-topics.sh ... --describe --topic diep.commands` |
| Redis master info | `docker exec redis-sentinel-1 redis-cli -p 26379 sentinel masters` |
| Redis replication | `docker exec diep-redis redis-cli -a $REDIS_PASSWORD info replication` |
| EMQX cluster nodes | `curl http://emqx-ha-1.local:18083/api/v5/nodes -H "Authorization: Bearer $EMQX_API_KEY"` |
| EMQX HAProxy backends | `echo "show stat" \| socat stdio /var/run/haproxy/admin.sock \| grep emqx_ssl` |
| MinIO disk status | `docker exec minio-ha-0 mc admin info local/ \| grep Disks` |
| Latest WAL archive | `docker exec minio-ha-0 mc ls local/diep-wal-archive/ \| tail -1` |
| Alertmanager alerts | `curl -sf http://localhost:9093/api/v2/alerts` |
| Backup age | `docker exec minio-ha-0 mc ls local/diep-backups/ \| tail -1` |
