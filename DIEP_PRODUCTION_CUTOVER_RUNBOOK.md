# DIEP Production Cutover Runbook
## Phase 17 HA Components — Production Promotion Playbook

**Date:** 2026-06-17  
**Version:** 1.0  
**Classification:** Internal — Engineering and Operations  
**Scope:** Step-by-step instructions for promoting all 6 Phase 17 HA components from validated isolated environments to production  
**Prerequisites:** All Phase 18 mandatory gap items (SEC-1→5, INFRA-1→4, EMQX-1→2, MON-1→4) must be closed before executing any maintenance window

---

## Pre-Cutover Calendar

```
T-30 days:  Gap assessment reviewed, ownership assigned
T-14 days:  All security prerequisites (SEC-1→5) complete
T-7 days:   Monitoring prerequisites (MON-1→4) active; CLUSTER_ID extracted
T-1 day:    Final backup taken; team confirmed available; rollback plans reviewed
MW1 (~D0):  K1 PITR + K4 Redis Sentinel  (2–4 hours)
MW2 (~D7):  K6 MinIO HA                  (2–3 hours + 24h soak)
MW3 (~D10): K3 Kafka HA                  (3–4 hours + 24h soak)
MW4 (~D14): K2 PostgreSQL HA             (4–6 hours + 48h soak)
MW5 (~D20): K5 EMQX HA                  (4–6 hours + soak)
```

---

## 1. Pre-Cutover Activities

### T-30 Days

- [ ] Review `PHASE18_PRODUCTION_GAP_ANALYSIS.md` with engineering and operations leads
- [ ] Assign named owner for each SEC, INFRA, EMQX, MON gap item
- [ ] Confirm production host has sufficient disk and memory for additional containers:
  - Patroni 3-node cluster: +2 Postgres instances (~2 GB RAM + storage each)
  - Kafka 3-broker cluster: +2 broker instances (~2 GB RAM each)
  - Redis Sentinel: 3 sentinel containers (<100 MB RAM total) + 1 replica
  - MinIO 4-node: +3 MinIO instances; confirm host has 4 separate data paths for EC:2
  - EMQX 3-node: +2 EMQX instances (~1.6 GB RAM each); note total EMQX memory requirement ~5 GB
- [ ] Verify nightly backup cron is running: `crontab -l` → confirm `scripts/install-backup-cron.sh` entries
- [ ] Verify backup currency: latest pg_dump < 24h old; WAL shipping will be added in MW1
- [ ] Check DIEP Root CA expiry: `openssl x509 -in certs/ca.crt -noout -dates` → should report 2036
- [ ] Schedule all 5 maintenance windows with stakeholder notification
- [ ] Confirm escalation matrix is distributed to on-call team (Section 5 of this document)

### T-14 Days

- [ ] **SEC-1:** Rotate 6 passwords in production `.env`:
  - Generate cryptographically random values: `openssl rand -base64 32` (one per credential)
  - Update `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, `DB_PASSWORD`
  - Restart affected services and verify `/healthz` returns 200
- [ ] **SEC-2:** Externalize Kafka SASL credential:
  - Add `KAFKA_SASL_USERNAME` and `KAFKA_SASL_PASSWORD` to `.env`
  - Replace 4 hardcoded occurrences in `docker-compose.yml`, `command_dispatcher.py`, `fastapi/app.py`, and the 4th location
  - Restart affected services; verify Kafka producer/consumer reconnect
- [ ] **SEC-3:** Enable Caddy TLS:
  - Provision TLS certificate for the production domain
  - Enable Caddy reverse proxy in `docker-compose.yml`
  - Verify HTTPS on :443 for API, Portal, Grafana
  - Verify HTTP → HTTPS redirect enforced
- [ ] **SEC-4:** Restrict infra port bindings:
  - Change Postgres 5432, Redis 6379, Kafka 9092/9094, MinIO 9000/9002 from `0.0.0.0:XXXX:XXXX` to `127.0.0.1:XXXX:XXXX` or remove host binding entirely (internal network only)
  - Verify FastAPI can still reach all infra services via Docker internal network
- [ ] **SEC-5:** Replace EMQX admin password:
  - Generate a new admin credential and store in secrets manager
  - EMQX admin password will be set at cluster initialization time during MW5
- [ ] Pin floating Docker image tags:
  - `docker inspect diep-timescaledb --format '{{.Image}}'` → note digest
  - Update `docker-compose.yml` to pin image tags to specific digests for: timescaledb, redis, kafka, mosquitto, minio
- [ ] Write Kafka SASL rotation runbook (so credential can be rotated in future without code changes)

### T-7 Days

- [ ] **MON-1:** Add EMQX cluster node count alert to Alertmanager:
  ```yaml
  - alert: EMQXClusterDegraded
    expr: emqx_cluster_nodes_running < 3
    for: 2m
    labels: { severity: critical }
    annotations:
      summary: "EMQX cluster has fewer than 3 nodes"
  ```
- [ ] **MON-2:** Add Kafka broker count alert (via `kafka-exporter` or custom probe)
- [ ] **MON-3:** Add MinIO disk alert:
  ```yaml
  - alert: MinioDiskDegraded
    expr: minio_cluster_disk_online_total < 4
    for: 2m
    labels: { severity: critical }
    annotations:
      summary: "MinIO cluster has fewer than 4 disks online"
  ```
- [ ] **MON-4:** Add Patroni primary health alert (REST API probe to `/primary`)
- [ ] **INFRA-4:** Extract Kafka CLUSTER_ID:
  ```bash
  docker exec diep-kafka cat /var/lib/kafka/data/meta.properties | grep cluster.id
  ```
  Record value: `CLUSTER_ID=<value>`. Required for K3 MW (all 3 KRaft voters must share this ID).
- [ ] Run full backup restore test: `scripts/verify-backup.sh` → confirm PASS
- [ ] Confirm Alertmanager email routing is functional: send test alert per `ALERTMANAGER_EMAIL_TEST_REPORT.md` procedure
- [ ] Review and distribute rollback procedures (Section 4 of this runbook) with on-call team
- [ ] Verify all K-stage reference Docker Compose files are committed and accessible:
  - `docker-compose-pitr-validation.yml`
  - `docker-compose-redis-sentinel-validation.yml`
  - `docker-compose-kafka-ha-validation.yml`
  - `docker-compose-postgres-ha-validation.yml`
  - `docker-compose-minio-ha-validation.yml`
  - `docker-compose-emqx-ha-validation.yml`

### T-1 Day

- [ ] Manual pre-cutover pg_dump snapshot:
  ```bash
  docker exec diep-timescaledb pg_dump -U diep_user -d diep_db -F custom -f /var/lib/postgresql/data/pre_cutover_$(date +%Y%m%d).dump
  docker cp diep-timescaledb:/var/lib/postgresql/data/pre_cutover_$(date +%Y%m%d).dump ./pre_cutover_backup/
  ```
- [ ] Verify disk space for additional containers: `df -h` — confirm > 50 GB free
- [ ] Verify Prometheus scrape targets are all UP: Grafana → Prometheus Targets view
- [ ] Confirm no active Alertmanager silences that would hide post-cutover issues
- [ ] Confirm on-call coverage for the maintenance window duration + 4h post-window monitoring period
- [ ] Notify active DIEP device operators of planned maintenance window and expected behavior (brief failover periods)

---

## 2. Cutover Day — Per-Component Maintenance Windows

### MW1: K1 PITR + K4 Redis Sentinel (2–4 hours)

**Pre-window validation:**
- [ ] Current Postgres is healthy: `docker exec diep-timescaledb pg_isready -U diep_user -d diep_db`
- [ ] Current Redis is healthy: `docker exec diep-redis redis-cli -a $REDIS_PASSWORD ping` → PONG
- [ ] Latest backup < 24h old

**K1 PITR steps:**

- [ ] **INFRA-1:** Set WAL archive volume ownership:
  ```bash
  docker exec diep-timescaledb chown 70:70 /var/lib/postgresql/wal-archive
  docker exec diep-timescaledb ls -la /var/lib/postgresql/ | grep wal-archive
  # Should show: drwxr-xr-x ... 70 70 ... wal-archive
  ```
- [ ] Enable WAL archiving (requires Postgres restart):
  - In `docker-compose.yml` or Postgres config: set `archive_mode=on`, `archive_command`, `archive_timeout=60`
  - Per K1 implementation plan: the `mc mirror` sidecar (`minio-mc-shipper`) must also be added to compose
  - `docker compose up -d` to apply changes (Postgres will restart)
- [ ] Verify WAL segments appear in MinIO within 70s:
  ```bash
  sleep 65 && docker exec diep-minio mc ls local/diep-wal-archive/ | tail -5
  ```
- [ ] Take initial base backup to MinIO:
  ```bash
  docker exec diep-timescaledb pg_basebackup -h localhost -U diep_user -D /var/lib/postgresql/basebackup -Fp -Xs
  ```
- [ ] Verify `/readyz` → `{"timescaledb": true}` ✅

**K4 Redis Sentinel steps:**

- [ ] **INFRA-2:** Confirm static IPAM for Redis tier is configured in compose network
- [ ] Add `redis-replica` and `redis-sentinel-{1,2,3}` to `docker-compose.yml` (from K4 reference compose)
- [ ] Start new services: `docker compose up -d redis-replica redis-sentinel-1 redis-sentinel-2 redis-sentinel-3`
- [ ] Verify replica sync:
  ```bash
  docker exec diep-redis redis-cli -a $REDIS_PASSWORD info replication | grep role
  # Should show: role:master, connected_slaves:1
  docker exec redis-replica redis-cli -a $REDIS_PASSWORD info replication | grep role
  # Should show: role:slave
  ```
- [ ] Verify sentinel quorum:
  ```bash
  docker exec redis-sentinel-1 redis-cli -p 26379 sentinel masters
  # Should show: diep-cache master, quorum 2, num-slaves 1, num-other-sentinels 2
  ```
- [ ] Switch application Redis connection from direct URL to Sentinel-aware client:
  - Update `REDIS_URL` env var to Sentinel URL format: `sentinel://redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379/diep-cache`
  - Or update application code to use `redis.sentinel.Sentinel(...).master_for('diep-cache')` pattern
  - `docker compose up -d fastapi` to apply
- [ ] Verify `/readyz` → `{"redis": true}` ✅
- [ ] Confirm drill: kill `diep-redis`, observe `+switch-master` in sentinel logs, verify `/readyz` recovers within 15s
  ```bash
  docker stop diep-redis
  docker logs redis-sentinel-1 --tail=20 | grep switch-master
  sleep 10 && curl http://localhost:8000/readyz
  docker start diep-redis
  ```

**Post-MW1 validation:**
- [ ] Telemetry flow: at least 1 device posting readings visible in Grafana
- [ ] API: `POST /api/v1/commands` returns 202
- [ ] Audit trail: `audit_events` has new rows
- [ ] No Alertmanager firing alerts
- [ ] **48h soak:** monitor WAL shipping latency and Redis Sentinel quorum daily

---

### MW2: K6 MinIO HA (2–3 hours + 24h soak)

**Pre-window validation:**
- [ ] Latest WAL archive write to `diep-minio` successful (WAL shipping active from MW1)
- [ ] Current MinIO is healthy: `docker exec diep-minio mc admin info local`
- [ ] Verify object counts before migration: `docker exec diep-minio mc ls --recursive local/diep-backups | wc -l`

**MinIO HA steps:**

- [ ] Start 4-node MinIO cluster (from K6 reference compose):
  ```bash
  docker compose up -d minio-ha-0 minio-ha-1 minio-ha-2 minio-ha-3
  ```
- [ ] Verify cluster formation:
  ```bash
  docker exec minio-ha-0 mc admin info local/
  # Should show: 4 drives online, EC:2 enabled
  ```
- [ ] **INFRA-3:** Mirror existing buckets from `diep-minio` to HA cluster:
  ```bash
  docker exec minio-ha-0 mc mirror local/diep-backups ha-cluster/diep-backups --overwrite
  docker exec minio-ha-0 mc mirror local/diep-config-backups ha-cluster/diep-config-backups --overwrite
  ```
- [ ] Verify object counts match:
  ```bash
  docker exec diep-minio mc ls --recursive local/diep-backups | wc -l
  docker exec minio-ha-0 mc ls --recursive ha-cluster/diep-backups | wc -l
  # Counts must match
  ```
- [ ] Switch WAL shipper (`ship-wal.sh` / mc mirror sidecar), `backup-db.sh`, and `backup-config.sh` to HA cluster endpoint:
  - Update `MINIO_ENDPOINT` in compose / `.env` to HA cluster load balancer address
  - `docker compose up -d` to apply
- [ ] Verify new WAL segment appears in HA cluster within 70s:
  ```bash
  sleep 70 && docker exec minio-ha-0 mc ls local/diep-wal-archive/ | tail -3
  ```
- [ ] Leave original `diep-minio` running in read-only mode for 24h soak period as fallback

**Post-MW2 validation:**
- [ ] Backup runs to HA MinIO: `scripts/backup-db.sh` → verifies to HA endpoint
- [ ] WAL shipping confirmed to HA endpoint
- [ ] Single-node failure drill: stop `minio-ha-1`, verify reads and writes continue from `minio-ha-0`
  ```bash
  docker stop minio-ha-1
  docker exec minio-ha-0 mc cp /tmp/test-object local/diep-backups/test-$(date +%s).obj
  docker exec minio-ha-0 mc ls local/diep-backups/test*.obj
  docker start minio-ha-1
  ```
- [ ] **24h soak**, then decommission `diep-minio` (after confirming no clients reference it)

---

### MW3: K3 Kafka HA (3–4 hours + 24h soak)

**Pre-window validation:**
- [ ] CLUSTER_ID is noted from T-7 preparation
- [ ] Consumer lag is zero or nominal: check `kafka-ui` dashboard
- [ ] No active Kafka consumer group errors in application logs

**Kafka HA steps:**

- [ ] Drain Kafka consumers: briefly pause `telemetry_ingestor.py` and `command_dispatcher.py` if possible (or accept brief lag during broker expansion)
- [ ] Update `diep-kafka` KRaft voter list to include `kafka-2` and `kafka-3` in `KAFKA_CONTROLLER_QUORUM_VOTERS`
- [ ] Add `kafka-2` and `kafka-3` to `docker-compose.yml` (from K3 reference compose), using the same `CLUSTER_ID`
- [ ] Start new brokers:
  ```bash
  docker compose up -d kafka-2 kafka-3
  ```
- [ ] Verify all 3 brokers joined the quorum:
  ```bash
  docker exec diep-kafka kafka-metadata-quorum.sh --bootstrap-server localhost:9094 \
    --command-config /etc/kafka/client.properties describe --status
  # Should show 3 voters, LeaderEpoch > 0
  ```
- [ ] Rolling restart of `diep-kafka` to apply updated voter config:
  ```bash
  docker compose restart diep-kafka
  # Wait for it to rejoin:
  sleep 30 && docker exec kafka-2 kafka-topics.sh --bootstrap-server kafka-2:9092 --list
  ```
- [ ] Recreate `diep.commands` topic as RF=3, min.insync.replicas=2:
  ```bash
  # First drain / confirm no in-flight messages
  docker exec diep-kafka kafka-topics.sh --bootstrap-server localhost:9092 \
    --command-config /etc/kafka/client.properties \
    --delete --topic diep.commands
  docker exec diep-kafka kafka-topics.sh --bootstrap-server localhost:9092 \
    --command-config /etc/kafka/client.properties \
    --create --topic diep.commands \
    --partitions 6 --replication-factor 3 \
    --config min.insync.replicas=2
  ```
  > **Note:** Use topic `diep.commands.val` nomenclature from K3 if topic name differs. Recreating the topic requires draining all in-flight messages first.
- [ ] Update `KAFKA_BOOTSTRAP` in `.env` to include all 3 brokers: `diep-kafka:9094,kafka-2:9094,kafka-3:9094`
- [ ] `docker compose up -d fastapi telemetry-ingestor command-dispatcher` to apply
- [ ] Verify producer is writing to the 3-broker topic:
  ```bash
  docker exec kafka-2 kafka-topics.sh --bootstrap-server kafka-2:9092 \
    --command-config /etc/kafka/client.properties \
    --describe --topic diep.commands
  # Should show: ReplicationFactor: 3, Isr: kafka-1,kafka-2,kafka-3
  ```

**Post-MW3 validation:**
- [ ] Fault-injection drill: kill one broker, verify consumer continues uninterrupted:
  ```bash
  docker stop kafka-2
  # Let 1 message flow through, then:
  docker start kafka-2
  # Wait for ISR restoration (~72s), then verify ISR shows 3 again
  ```
- [ ] Consumer lag: confirm lag returns to zero after broker restart
- [ ] No Alertmanager firing on Kafka broker count
- [ ] **24h soak**, then decommission the single-broker configuration (if a separate pilot compose project existed)

---

### MW4: K2 PostgreSQL Patroni HA (4–6 hours + 48h soak)

**Pre-window validation:**
- [ ] K1 WAL archiving is active and WAL segments are flowing to MinIO HA cluster
- [ ] K6 MinIO HA is stable (24h+ soak complete)
- [ ] Pre-cutover pg_dump taken (T-1 step)
- [ ] Etcd (or 3-node etcd cluster) is prepared and running

**Patroni HA steps:**

- [ ] Take `pg_basebackup` from `diep-timescaledb` to MinIO:
  ```bash
  docker exec diep-timescaledb pg_basebackup \
    -h localhost -U diep_user \
    -D /tmp/pg-basebackup-$(date +%Y%m%d) \
    -Fp -Xs -P
  # Mirror to MinIO:
  docker exec minio-ha-0 mc cp -r /tmp/pg-basebackup-$(date +%Y%m%d) \
    local/diep-pg-basebackups/$(date +%Y%m%d)/
  ```
- [ ] Start Patroni cluster from base backup (from K2 reference compose):
  ```bash
  docker compose up -d pg-ha-etcd
  sleep 10
  docker compose up -d pg-ha-1
  sleep 20
  docker compose up -d pg-ha-2 pg-ha-3
  docker compose up -d pg-ha-haproxy
  ```
- [ ] Verify Patroni cluster health:
  ```bash
  docker exec pg-ha-1 patronictl -c /etc/patroni/patroni.yml list
  # Should show: pg-ha-1: Leader (running), pg-ha-2: Replica (running), pg-ha-3: Replica (running)
  curl http://localhost:8008/primary
  # Should return 200
  ```
- [ ] Verify TimescaleDB hypertable integrity:
  ```bash
  docker exec pg-ha-1 psql -U diep_user -d diep_db \
    -c "SELECT count(*) FROM telemetry_readings WHERE time > now() - interval '24h';"
  ```
- [ ] Switch application database host:
  - Update `DB_HOST=pg-ha-haproxy` in `.env`
  - `docker compose up -d fastapi telemetry-ingestor command-dispatcher`
- [ ] Enable K1 WAL archiving on Patroni cluster:
  ```bash
  docker exec pg-ha-1 patronictl -c /etc/patroni/patroni.yml edit-config
  # Add: archive_mode: on, archive_command: ...
  # Patroni propagates to all nodes automatically
  ```
- [ ] Verify `/readyz` → `{"timescaledb": true}` from HAProxy endpoint
- [ ] **48h soak:** `diep-timescaledb` remains running in read-only mode as fallback

**Post-MW4 validation:**
- [ ] Failover drill: `patronictl switchover` (planned, graceful):
  ```bash
  docker exec pg-ha-1 patronictl -c /etc/patroni/patroni.yml switchover --master pg-ha-1 --candidate pg-ha-2
  # Observe: pg-ha-2 becomes Leader; pg-ha-1 rejoins as Replica; HAProxy transparently routes to new primary
  ```
- [ ] Failover drill: kill primary container (unplanned):
  ```bash
  docker stop pg-ha-2  # current Leader after switchover
  sleep 30
  docker exec pg-ha-1 patronictl list  # pg-ha-1 or pg-ha-3 should now be Leader
  # Verify /readyz → {"timescaledb": true}
  docker start pg-ha-2  # rejoins via pg_rewind in ~21s
  ```
- [ ] RPO=0 verification: all rows written before primary kill present on promoted standby
- [ ] WAL archiving continues on timeline 2 (post-failover WAL)
- [ ] **48h soak complete:** decommission `diep-timescaledb` (stop container; retain volume for 7 days before removing)

---

### MW5: K5 EMQX HA (4–6 hours + soak)

**Pre-window validation:**
- [ ] EMQX production admin credential is set (SEC-5 complete)
- [ ] EMQX SSL env var overrides ready (EMQX-1)
- [ ] EMQX node hostnames confirmed to use `.local` suffix (EMQX-2)
- [ ] All existing DIEP device certs are signed by the production DIEP Root CA (validated in K5)
- [ ] `diep-mqtt` (Mosquitto) is running and healthy — it stays running as rollback target

**EMQX HA steps:**

- [ ] Start 3-node EMQX cluster + HAProxy (from K5 reference compose, with production credentials):
  ```bash
  docker compose up -d emqx-ha-1
  # Wait for emqx-ha-1 healthy (30–45s):
  sleep 45
  docker compose up -d emqx-ha-2 emqx-ha-3 emqx-ha-haproxy
  ```
- [ ] Verify cluster formation (all 3 nodes):
  ```bash
  curl -sf http://localhost:18083/status
  curl -sf http://emqx-ha-1.local:18083/api/v5/nodes -H 'Authorization: Bearer <api-key>'
  # Should show 3 nodes: running
  ```
- [ ] Validate mTLS with production device certs (V1–V3 checks from K5):
  ```bash
  # V1: valid cert connects
  mosquitto_pub -h localhost -p 8883 \
    --cafile certs/ca.crt --cert certs/INV001.crt --key certs/INV001.key \
    -t diep/solar/INV001 -m '{"test":true}' -q 1
  # V2: no cert rejected (openssl s_client without cert → expect certificate_required)
  echo | openssl s_client -connect localhost:8883 -CAfile certs/ca.crt 2>&1 | grep -i "certificate required"
  ```
- [ ] Switch MQTT endpoint from Mosquitto to EMQX HAProxy:
  - Option A: Update DNS/hostname that devices resolve for MQTT broker
  - Option B: Change `MQTT_BROKER` env var in `telemetry_ingestor.py` and `command_dispatcher.py`
  - Update port if necessary (EMQX HAProxy on 8883 matching Mosquitto's current port)
  - `docker compose up -d telemetry-ingestor command-dispatcher`
- [ ] Confirm telemetry flow resumes within 30s of reconnection
- [ ] Run failure drills F1 and F4 against production EMQX:
  - F1: `docker stop emqx-ha-2` → verify 0 reconnects, telemetry continues; `docker start emqx-ha-2`
  - F4: Rolling restart of all 3 nodes one at a time; verify cluster remains available throughout

**Post-MW5 validation:**
- [ ] Telemetry burst: 50 QoS 0 messages from a device → confirm all 50 received by ingestor
- [ ] DERMS round-trip: dispatch command → device receives → ACK received by dispatcher
- [ ] ACL check: INV001 cannot publish to INV900 topic (verify `deny_action=disconnect` fires)
- [ ] EMQX cluster nodes alert does not fire (all 3 nodes healthy)
- [ ] **Soak period (2–7 days):** keep `diep-mqtt` (Mosquitto) running on alternate port as rollback target
- [ ] After soak: decommission `diep-mqtt`

---

## 3. Go-Live Validation

Run the following after all 5 maintenance windows are complete and soak periods are done.

### Infrastructure Validation

- [ ] `docker compose ps` → all production containers are Up and healthy
- [ ] Patroni: `curl http://pg-ha-1.local:8008/cluster` → 3 members, 1 Leader, 2 Replicas
- [ ] Kafka: `kafka-metadata-quorum.sh describe --status` → 3 voters, all caught up
- [ ] Redis: `redis-cli -p 26379 sentinel masters` → 1 master, 1 slave, 2 other sentinels
- [ ] MinIO: `mc admin info` → 4 disks online, EC:2 active
- [ ] EMQX: `curl http://emqx-ha-haproxy:18083/status` → `{"node_status":"running"}`

### Security Validation

- [ ] HTTPS enforced on API, Portal, Grafana (test with `curl -I http://...` → should redirect or return 400)
- [ ] Infra ports not reachable from outside Docker network: `nc -zv <production-host-ip> 5432 6379 9092` → all Connection refused
- [ ] Kafka SASL rejected without credentials: `kafka-topics.sh --list --bootstrap-server ...:9094` → AuthenticationException
- [ ] EMQX mTLS: device without cert rejected: `openssl s_client` without cert → `certificate_required`
- [ ] All `DIEP_*_PASSWORD` values confirmed non-default (spot-check via app auth)

### Certificate Validation

- [ ] DIEP Root CA expiry: `openssl x509 -in certs/ca.crt -noout -enddate` → 2036
- [ ] EMQX server cert expiry: `openssl x509 -in certs/emqx-server.crt -noout -enddate` → confirm > 90 days remaining
- [ ] Device cert expiry (sample): `openssl x509 -in certs/INV001.crt -noout -enddate`

### Database Validation

- [ ] Row count sanity: total `telemetry_readings` count matches expected from pilot deployment
- [ ] TimescaleDB compression working: `SELECT * FROM timescaledb_information.chunks LIMIT 5`
- [ ] WAL archive flowing: `SELECT pg_walfile_name(pg_current_wal_lsn())` → note filename; wait 70s; check MinIO for new WAL file
- [ ] PITR recovery test (in isolated test container — do not use production volumes):
  - Restore to a point in the last 24h and verify row count

### Kafka Validation

- [ ] Publish test command: `kafka-console-producer.sh` → topic `diep.commands` with RF=3
- [ ] ISR shows all 3 brokers: `kafka-topics.sh --describe --topic diep.commands` → ISR: kafka-1,kafka-2,kafka-3
- [ ] Consumer lag: `kafka-consumer-groups.sh --describe` → lag = 0 for all consumer groups

### MQTT Validation

- [ ] DERMS round-trip (INV001): command dispatch → device receive → ACK → dispatcher receive → all within 5s
- [ ] Telemetry burst (50 messages from BAT001): all 50 received by ingestor within 10s
- [ ] ACL: INV001 publish to `diep/solar/INV900` → CONNACK 4 or disconnect

### Monitoring Validation

- [ ] Prometheus targets: all scrape targets in UP state (check Prometheus → Targets)
- [ ] Grafana: TimescaleDB dashboard shows live data from Patroni HAProxy endpoint
- [ ] Alertmanager: no active firing alerts
- [ ] MON-1 through MON-4 alerts are registered: `curl http://alertmanager:9093/api/v2/alerts` → check alert names

### Telemetry and Commands (End-to-End)

- [ ] Post at least one telemetry reading from each device class: INV, BAT, EV, MG, METER
- [ ] Verify readings appear in Grafana DIEP Operations dashboard within 60s
- [ ] Send DERMS command to at least 1 device: `POST /api/v1/derms/grid_import_limit`
- [ ] Verify command ACK received and recorded in `audit_events`

### Portal Validation

- [ ] Login as `viewer`: can view dashboards, cannot issue commands
- [ ] Login as `operator`: can issue DERMS commands, cannot modify configuration
- [ ] Login as `admin`: can access all routes including tenant management

### Audit Trail

- [ ] All above API calls appear in `audit_events` table with correct user, action, timestamp
- [ ] Audit log backup included in next `backup-db.sh` run

---

## 4. Rollback Plan

### Rollback Principles

1. Rollback is per-component — reverting one tier does not require reverting others
2. All original production services were never stopped until after their soak period
3. All rollbacks are reversible without data loss if executed within the soak window

### Per-Component Rollback Procedures

**K1 PITR rollback:**
- Set `archive_mode=off` in Postgres config; restart `diep-timescaledb`
- Stop `minio-mc-shipper` sidecar
- No data loss; WAL archive remains in MinIO and can be re-enabled at any time

**K4 Redis Sentinel rollback:**
- Stop sentinel containers: `docker compose stop redis-sentinel-1 redis-sentinel-2 redis-sentinel-3 redis-replica`
- Revert `REDIS_URL` in `.env` to direct `redis://diep-redis:6379` connection
- `docker compose up -d fastapi`
- Cache state on `diep-redis` is unchanged; no cache loss

**K6 MinIO HA rollback:**
- Revert `MINIO_ENDPOINT` in `.env` to original `diep-minio` endpoint
- `docker compose up -d` to apply
- Original `diep-minio` was kept running during soak; switch back is instant
- Any WAL/backup objects written to HA cluster during soak: `mc mirror` back to `diep-minio`

**K3 Kafka HA rollback:**
- Revert `KAFKA_BOOTSTRAP` to `diep-kafka:9094` only
- Stop `kafka-2`, `kafka-3`: `docker compose stop kafka-2 kafka-3`
- **Caution:** If `diep.commands` was recreated as RF=3 topic, it must be recreated as RF=1 for single-broker mode — this requires draining the topic first
- All messages already consumed are not at risk; in-flight messages during rollback may require re-dispatch

**K2 PostgreSQL HA rollback:**
- Stop Patroni cluster: `docker compose stop pg-ha-1 pg-ha-2 pg-ha-3 pg-ha-haproxy`
- Revert `DB_HOST` in `.env` to `diep-timescaledb`
- Start `diep-timescaledb` if it was suspended: `docker compose start diep-timescaledb`
- **Caution:** Any writes to Patroni primary during the soak period that were not replicated back to `diep-timescaledb` will be lost. This is why the 48h soak runs with both systems available before committing to cutover. Use `pg_dump` comparison or WAL timeline analysis to reconcile if needed.

**K5 EMQX HA rollback:**
- Stop EMQX cluster: `docker compose stop emqx-ha-1 emqx-ha-2 emqx-ha-3 emqx-ha-haproxy`
- Start Mosquitto: `docker compose start diep-mqtt`
- Revert MQTT broker endpoint to Mosquitto (`diep-mqtt:8883`)
- `docker compose up -d telemetry-ingestor command-dispatcher`
- MQTT is stateless for DIEP's usage pattern: rollback is instant, no session state is lost
- All device certs are compatible with both Mosquitto and EMQX — no cert changes needed

---

## 5. Escalation Matrix

### Severity Classification

| Severity | Definition | Example |
|---|---|---|
| P1 — Production Down | All telemetry or DERMS commands unavailable; no HA recovery within 5 min | Patroni cluster fails to elect primary; EMQX cluster down entirely |
| P2 — Degraded | Single component in degraded state but platform functional; HA recovery in progress | Kafka ISR < 3 but broker running; Redis Sentinel in `+tilt`; 1 EMQX node down |
| P3 — Warning | Non-critical anomaly; monitoring alert; performance degradation | WAL archive lag > 5 min; MinIO disk online count = 3 but EC:2 still operational |
| P4 — Informational | Routine operational event; no impact | Successful Patroni switchover drill; Kafka broker restart during rolling upgrade |

### Response Matrix

| Severity | Initial response time | Notification | Escalation path |
|---|---|---|---|
| P1 | Immediate (paged) | On-call engineer + Platform lead + Ops lead | Platform lead → CTO if not resolved within 30 min |
| P2 | Within 15 min | On-call engineer + Platform lead | Platform lead if not resolved within 1h |
| P3 | Within 1h (business hours) | On-call engineer | Platform lead if not resolved within 4h |
| P4 | Next business day | Ticket created | N/A |

### Cutover-Specific Escalation

During an active maintenance window:
- If a step fails and cannot be completed within 30 min: pause MW, notify stakeholders, assess rollback
- If rollback is required: execute per-component rollback procedure (Section 4) and notify affected device operators
- If rollback also fails: P1 escalation immediately

### Contact Information

*(Populate with actual on-call contact details before distributing this runbook)*

| Role | Contact | Reach via |
|---|---|---|
| On-call engineer | [TBD] | PagerDuty / phone |
| Platform lead | [TBD] | Phone / Slack |
| Operations lead | [TBD] | Phone / Slack |
| Database SME | [TBD] | Slack |
| Kafka / Message Bus SME | [TBD] | Slack |

---

## Appendix: Environment Reference

| Service | Production container name | Port | Health check |
|---|---|---|---|
| PostgreSQL (Patroni primary) | `pg-ha-haproxy` (HAProxy routes to Leader) | 5432 | `curl http://pg-ha-1.local:8008/primary` |
| Kafka (3 brokers) | `diep-kafka`, `kafka-2`, `kafka-3` | 9094 (SASL) | `kafka-metadata-quorum.sh describe --status` |
| Redis (Sentinel) | `diep-redis` (primary), `redis-replica`, `redis-sentinel-{1,2,3}` | 6379 (data), 26379 (sentinel) | `redis-cli -p 26379 sentinel masters` |
| MinIO (EC:2 cluster) | `minio-ha-{0..3}` | 9000 (API), 9002 (console) | `mc admin info local/` |
| EMQX (3-node) | `emqx-ha-{1..3}`, `emqx-ha-haproxy` | 8883 (mTLS), 18083 (HTTP API) | `curl http://emqx-ha-haproxy:18083/status` |
| FastAPI | `diep-fastapi` | 8000 | `curl http://localhost:8000/readyz` |
| Telemetry ingestor | `diep-telemetry-ingestor` | — | Application logs |
| Command dispatcher | `diep-command-dispatcher` | — | Application logs |
