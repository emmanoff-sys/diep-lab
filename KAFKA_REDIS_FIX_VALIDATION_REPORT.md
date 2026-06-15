# Kafka / Kafka-Exporter / Redis — Fix & Validation Report

Date: 2026-06-15
Related: [KAFKA_REDIS_ROOT_CAUSE_ANALYSIS.md](KAFKA_REDIS_ROOT_CAUSE_ANALYSIS.md)

## 1. Summary

Both root causes identified in the root-cause analysis were fixed by
**repairing corrupted on-disk metadata in place**, with no configuration
changes, no image/version changes, and no volume deletion. All three
containers (`diep-kafka`, `diep-kafka-exporter`, `diep-redis`) are now
running cleanly, the command and telemetry flows are confirmed working
end-to-end, and the `KafkaOutage` alert has resolved in both Prometheus and
Alertmanager.

| Service | Fix applied | Result |
|---|---|---|
| `diep-kafka` | Overwrote the two corrupted checkpoint files (`log-start-offset-checkpoint`, `recovery-point-offset-checkpoint`) with the valid empty `OffsetCheckpointFile` format (`"0\n0\n"`), then `docker restart diep-kafka`. | Broker started cleanly, loaded all 51 log directories, `__consumer_offsets` (incl. `diep-command-dispatcher` group, 19,851 records) recovered. RestartCount reset to 0, no further crash loop. |
| `diep-redis` | Stopped container, ran `redis-check-aof --fix` on `appendonlydir/appendonly.aof.1.incr.aof` (truncated the final corrupted 1,167 bytes of 29,872,902), then `docker start diep-redis`. | "DB loaded from incr file ... Ready to accept connections tcp". RestartCount reset to 0, no further crash loop. |
| `diep-kafka-exporter` | No direct fix needed — recovered automatically via existing `restart: unless-stopped` once `diep-kafka` was reachable. | `Listening on HTTP :9308`, successfully scraping `diep-kafka:9092`, `up{job="kafka-exporter"}=1`, `kafka_brokers=1`. |

## 2. Backups taken (preserved, nothing deleted)

`backups/kafka-redis-20260615045613/`:
- `log-start-offset-checkpoint.bak` — original corrupted Kafka checkpoint (4 bytes)
- `recovery-point-offset-checkpoint.bak` — original corrupted Kafka checkpoint (1217 bytes)
- `redis-data-full/` — full pre-fix copy of the Redis data volume, including
  the original 29,872,902-byte `appendonly.aof.1.incr.aof`, `dump.rdb`,
  `appendonly.aof.1.base.rdb`, and `appendonly.aof.manifest`.

No Kafka or Redis Docker volumes (`diep-lab_kafka-data`, `diep-lab_redis-data`)
were deleted or recreated at any point — only the two corrupted checkpoint
files and the tail of the Redis AOF were modified in place.

## 3. Fix execution detail

### 3.1 Kafka checkpoint repair

```
docker exec diep-kafka sh -c "printf '0\n0\n' > /var/lib/kafka/data/log-start-offset-checkpoint \
  && printf '0\n0\n' > /var/lib/kafka/data/recovery-point-offset-checkpoint"
docker restart diep-kafka
```

Post-restart log evidence:
- No `LogDirFailureChannel` / `Shutdown broker because all log dirs ... have failed` errors.
- `Loaded 51 logs ...` completed successfully.
- `[GroupCoordinator id=1] Finished loading of metadata from __consumer_offsets-0 ... Loaded 19851 records which total to 2765201 bytes.`
- `diep-command-dispatcher` consumer group rejoined automatically.

### 3.2 Redis AOF repair

```
docker stop diep-redis
docker run --rm -v diep-lab_redis-data:/data redis:7-alpine redis-check-aof /data/appendonlydir/appendonly.aof.1.incr.aof
  -> AOF analyzed: size=29872902, ok_up_to=29871735, diff=1167, "not valid, use --fix"

docker run --rm -v diep-lab_redis-data:/data redis:7-alpine sh -c \
  "echo y | redis-check-aof --fix /data/appendonlydir/appendonly.aof.1.incr.aof"
  -> Successfully truncated AOF ... from 29872902 bytes ... to 29871735 bytes

docker start diep-redis
```

Post-restart log evidence:
```
DB loaded from base file appendonly.aof.1.base.rdb: 0.001 seconds
DB loaded from incr file appendonly.aof.1.incr.aof: 1.149 seconds
DB loaded from append only file: 1.150 seconds
Opening AOF incr file appendonly.aof.1.incr.aof on server start
Ready to accept connections tcp
```

## 4. Post-fix validation

### 4.1 Container states (no crash loop)

```
diep-kafka:          RestartCount=0  Status=running  (Up 4 minutes)
diep-redis:          RestartCount=0  Status=running  (Up 4 minutes)
diep-kafka-exporter: Status=running  (Up 4 minutes, connected)
```

### 4.2 Kafka broker health

```
kafka-topics.sh --list
  __consumer_offsets
  diep.commands

kafka-topics.sh --describe --topic diep.commands
  Topic: diep.commands  PartitionCount: 1  ReplicationFactor: 1  Configs: min.insync.replicas=1
  Partition: 0  Leader: 1  Replicas: 1  Isr: 1
```

Topic available, single broker is leader and in-sync.

### 4.3 Consumer groups

```
kafka-consumer-groups.sh --list
  diep-command-dispatcher

kafka-consumer-groups.sh --describe --group diep-command-dispatcher
  TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG  CONSUMER-ID
  diep.commands  0         21             21             0    kafka-python-2.3.2-...
```

Group is active, fully caught up (lag=0).

### 4.4 Redis persistence and authentication

```
redis-cli info persistence:
  aof_enabled:1
  aof_last_bgrewrite_status:ok
  aof_last_write_status:ok
  rdb_last_bgsave_status:ok
  loading:0
```

Authentication: `redis-cli ping` without credentials → `NOAUTH Authentication
required.`; with `${ALERT_...}`-style `REDIS_PASSWORD` from `.env` → `PONG`.
`requirepass` is enforced as configured (Phase 15A), unaffected by the fix.

Data integrity: `dbsize=13`, all 5 expected device state keys present
(`state:EV001`, `state:METER001`, `state:INV001`, `state:MG001`,
`state:BAT001`).

### 4.5 Command flow validation (dispatcher → Kafka)

`diep-dispatcher` logs show successful SASL authentication to
`diep-kafka:9094`, rejoining `diep-command-dispatcher` (generation 35), and
partition assignment for `diep.commands-0` — confirmed end-to-end by the
consumer-group describe output above (lag=0, current offset 21).

### 4.6 Telemetry flow validation (ingestor → MQTT → Redis/FastAPI)

`diep-ingestor` logs show continuous successful ingestion for all 5
simulated devices (BAT001, EV001, INV001, MG001, METER001) with live
power/SoC values, e.g.:
```
Ingested diep/solar/INV001 -> INV001 (power_kw=8.935, soc=0.0)
Ingested diep/smartmeter/METER001 -> METER001 (power_kw=2.027, soc=0.0)
```

### 4.7 KafkaOutage alert resolution

```
Prometheus /api/v1/query up{job="kafka-exporter"}  -> 1
Prometheus /api/v1/query kafka_brokers             -> 1
Prometheus /api/v1/rules  KafkaOutage              -> state: "inactive", alerts: []

Alertmanager /api/v2/alerts -> [] (no active alerts)
alertmanager_notifications_total{integration="email"}        -> 3, increasing, 0 failures
alertmanager_notifications_failed_total{integration="email"} -> 0 for every reason
```

`KafkaOutage` has transitioned from `firing` to `inactive`/resolved with no
further Alertmanager configuration changes required, completing the
follow-up noted in `ALERTMANAGER_EMAIL_TEST_REPORT.md`.

## 5. Outstanding items

None. All three previously crash-looping containers (`diep-kafka`,
`diep-kafka-exporter`, `diep-redis`) are running normally with
`RestartCount=0` (Kafka/Redis) and a connected exporter, command and
telemetry pipelines are flowing, and the `KafkaOutage` alert is resolved.
