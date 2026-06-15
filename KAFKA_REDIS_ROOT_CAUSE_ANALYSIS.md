# Kafka / Kafka-Exporter / Redis Crash Loop — Root Cause Analysis

Date: 2026-06-15
Scope: `diep-kafka`, `diep-kafka-exporter`, `diep-redis` (project `diep-lab`)

## 1. Summary

`diep-kafka`, `diep-kafka-exporter`, and `diep-redis` were all in restart/crash
loops, with the `KafkaOutage` alert firing in Alertmanager. Investigation
found **two independent data-corruption issues**, both with the **same
file-modification timestamp (2026-06-14 15:49 UTC)**, pointing to a single
underlying incident (an unclean shutdown/abrupt write interruption affecting
both the Kafka and Redis data volumes at the same moment):

| Container | Root cause | Independent or downstream? |
|---|---|---|
| `diep-kafka` | Two checkpoint files (`log-start-offset-checkpoint`, `recovery-point-offset-checkpoint`) in `/var/lib/kafka/data` contained random binary garbage instead of the valid text checkpoint format. Kafka's `LogDirFailureChannel` marked the log directory as failed on every startup, causing the broker to shut down immediately. | **Independent** root cause (own volume corruption). |
| `diep-kafka-exporter` | `kafka: client has run out of available brokers to talk to: dial tcp ...:9092: connect: connection refused` / DNS lookup failures for `diep-kafka`. | **Downstream/dependent** — exporter cannot connect because `diep-kafka` itself was down. |
| `diep-redis` | The AOF incremental file `appendonlydir/appendonly.aof.1.incr.aof` (29,872,902 bytes) had its final 1,167 bytes corrupted/incomplete (an interrupted RESP command), causing `Bad file format reading the append only file ... appendonly.aof.1.incr.aof` and `exit(1)` on every startup. | **Independent** root cause (own volume corruption), but **same timestamp** as the Kafka corruption — likely the same underlying incident (e.g., abrupt host/Docker shutdown) that interrupted writes to both volumes simultaneously. |

`diep-kafka-ui` remained healthy throughout (it tolerates a down broker and
just shows the cluster as unreachable in its UI).

## 2. Evidence collected

### 2.1 Container states / restart counts / exit codes (before fix)

```
diep-kafka          RestartCount=15  ExitCode=0  Status=running (crash-looping, ~1 min lifetime)
diep-kafka-exporter RestartCount=27  ExitCode=255 Status=restarting
diep-redis          RestartCount=27  ExitCode=1  Status=restarting
```

`docker ps -a` at the time of investigation showed all three flapping between
`Up Ns` and `Restarting (...)`.

### 2.2 diep-kafka logs

Repeated on every startup cycle:

```
ERROR Error while reading checkpoint file /var/lib/kafka/data/recovery-point-offset-checkpoint (org.apache.kafka.storage.internals.log.LogDirFailureChannel)
java.nio.charset.MalformedInputException: Input length = 1
WARN Error occurred while reading recovery-point-offset-checkpoint file of directory /var/lib/kafka/data, resetting the recovery checkpoint to 0

ERROR Error while reading checkpoint file /var/lib/kafka/data/log-start-offset-checkpoint (org.apache.kafka.storage.internals.log.LogDirFailureChannel)
java.io.IOException: Malformed line in checkpoint file [/var/lib/kafka/data/log-start-offset-checkpoint]: /Д
WARN Error occurred while reading log-start-offset-checkpoint file of directory /var/lib/kafka/data, resetting to the base offset of the first segment

WARN [ReplicaManager broker=1] Stopping serving replicas in dir /var/lib/kafka/data with uuid ... because the log directory has failed.
WARN Stopping serving logs in dir /var/lib/kafka/data (kafka.log.LogManager)
ERROR Shutdown broker because all log dirs in /var/lib/kafka/data have failed (kafka.log.LogManager)
```

Even though Kafka *attempts* to recover from a malformed checkpoint by
resetting to a default value, the act of hitting the `IOException` /
`MalformedInputException` while reading the file causes the
`LogDirFailureChannel` to mark the entire log directory (`/var/lib/kafka/data`)
as failed, which then triggers a full broker shutdown — hence the crash loop.

### 2.3 File-level evidence (diep-kafka)

```
-rw-r--r-- 1 appuser appuser    4 Jun 14 15:49 log-start-offset-checkpoint
-rw-r--r-- 1 appuser appuser 1217 Jun 14 15:49 recovery-point-offset-checkpoint
-rw-r--r-- 1 appuser appuser    4 Jun 13 04:39 cleaner-offset-checkpoint   (intact, valid: "0\n0\n")
```

- `log-start-offset-checkpoint` (4 bytes) contained raw binary `2f 18 d0 94`
  — not valid text.
- `recovery-point-offset-checkpoint` (1217 bytes) contained ~1.2KB of random
  binary data resembling raw Kafka log-segment bytes, not the expected
  `version / count / "topic partition offset"...` text format.
- The intact `cleaner-offset-checkpoint` (also a `OffsetCheckpointFile`,
  4 bytes, content `"0\n0\n"`) demonstrates the correct valid-empty format for
  this checkpoint file type.
- All 51 partition log directories (`__consumer_offsets-0..49`,
  `diep.commands-0`, `__cluster_metadata-0`) and their segment files were
  present and untouched — **no log/segment data was lost**.

### 2.4 diep-kafka-exporter logs

```
F0615 04:46:18.326165 1 kafka_exporter.go:1061] Error Init Kafka Client: kafka: client has run out of available brokers to talk to: dial tcp 172.18.0.16:9092: connect: connection refused
F0615 04:46:54.143779 1 kafka_exporter.go:1061] Error Init Kafka Client: kafka: client has run out of available brokers to talk to: dial tcp: lookup diep-kafka on 127.0.0.11:53: server misbehaving
```

`172.18.0.16` is `diep-kafka`'s container IP. The exporter is a stateless
client whose own process exits with a fatal error (`F...`, exit code 255)
whenever it cannot reach the broker at startup — entirely consistent with,
and explained by, `diep-kafka` being down. No independent fault was found in
the exporter itself.

### 2.5 diep-redis logs and AOF analysis

```
1:M 15 Jun 2026 04:53:02.693 # Bad file format reading the append only file appendonly.aof.1.incr.aof: make a backup of your AOF file, then use ./redis-check-aof --fix <filename.manifest>
```
(Redis logs `Done loading RDB`, then hits the bad AOF, and `exit(1)` —
restart count 27, `ExitCode=1`.)

```
appendonlydir/
  appendonly.aof.1.base.rdb   88 bytes   (Jun 8 22:11, unchanged)
  appendonly.aof.manifest     88 bytes   (Jun 8 22:11, unchanged)
  appendonly.aof.1.incr.aof   29,872,902 bytes  (Jun 14 15:49)
```

`redis-check-aof` analysis (before fix):

```
AOF analyzed: filename=.../appendonly.aof.1.incr.aof, size=29872902, ok_up_to=29871735, ok_up_to_line=3825783, diff=1167
AOF /data/appendonlydir/appendonly.aof.1.incr.aof is not valid. Use the --fix option to try fixing it.
```

- The first 29,871,735 bytes (3,825,783 RESP commands) are valid — this is
  the bulk of the file, including telemetry `HSET state:<DEVICE_ID> ...`
  writes from `diep-ingestor`/`diep-dispatcher`.
- Only the **final 1,167 bytes** were corrupted/incomplete — a hallmark of a
  write that was interrupted mid-command (e.g., process killed / host
  power-cycled during an `fsync`/`write`), not widespread disk corruption.
- `dump.rdb` (4350 bytes, also Jun 14 15:49) loaded cleanly — only the AOF
  incremental file was affected.

## 3. Relatedness assessment

- **Kafka vs Kafka-exporter**: directly related — exporter failure is a pure
  downstream symptom of the broker being down (DNS/connection-refused errors
  to `diep-kafka:9092`). Fixing the broker is expected to resolve the exporter
  automatically (Docker's `restart: unless-stopped` keeps retrying it).
- **Kafka vs Redis**: **not causally related** to each other (different
  services, different volumes, different corruption types — one is a binary
  garbage overwrite of small checkpoint files, the other is a truncated tail
  on a large append-only file). However, **both corrupted files share the
  exact same mtime (2026-06-14 15:49 UTC)**, which strongly suggests a single
  shared triggering event (e.g., an abrupt Docker daemon/host restart or
  power loss) that interrupted in-flight writes to both volumes at the same
  moment. No host kernel journal entries were available to confirm the event
  (`journalctl -k` returned no entries for that window), but the
  timestamp correlation is the key evidence.
- `diep-redis` requires `requirepass` (`REDIS_PASSWORD` from `.env`,
  Phase 15A) — authentication itself was not implicated in the crash loop;
  the process never got past AOF loading to start serving connections at all.

## 4. Data-loss assessment

- **Kafka**: zero data loss. All topic/partition log segments and the
  `__consumer_offsets` data (including the `diep-command-dispatcher` group's
  ~19,851 offset records) were intact on disk; only two small,
  regeneratable checkpoint files were corrupted.
- **Redis**: effectively zero data loss. At most one partial `HSET`/command
  (1,167 bytes) at the very end of the AOF was discarded by
  `redis-check-aof --fix`; all prior writes (3,825,783 commands) were
  preserved. Post-fix, all 5 device state keys (`state:EV001`,
  `state:METER001`, `state:INV001`, `state:MG001`, `state:BAT001`) and
  `dbsize=13` were confirmed present.

## 5. Backups taken (before any modification)

`backups/kafka-redis-20260615045613/`:
- `log-start-offset-checkpoint.bak` (original corrupted 4-byte file)
- `recovery-point-offset-checkpoint.bak` (original corrupted 1217-byte file)
- `redis-data-full/` — full copy of the Redis data volume
  (`dump.rdb`, `appendonlydir/appendonly.aof.1.base.rdb`,
  `appendonlydir/appendonly.aof.1.incr.aof` at 29,872,902 bytes,
  `appendonlydir/appendonly.aof.manifest`) taken **before** running
  `redis-check-aof --fix`.

No Kafka or Redis volumes were deleted at any point.

## 6. Planned fix (see KAFKA_REDIS_FIX_VALIDATION_REPORT.md for execution/results)

1. Overwrite the two corrupted Kafka checkpoint files with the valid
   "empty" `OffsetCheckpointFile` format (`"0\n0\n"`, matching the intact
   `cleaner-offset-checkpoint`), then restart `diep-kafka`. Kafka will treat
   this as "no checkpointed offsets" and rebuild recovery/log-start state
   from the existing log segments — no segment data is touched or deleted.
2. Run `redis-check-aof --fix` on
   `appendonlydir/appendonly.aof.1.incr.aof` to truncate the 1,167-byte
   incomplete tail, then restart `diep-redis`.
3. Allow `diep-kafka-exporter` to recover automatically via its existing
   `restart: unless-stopped` policy once `diep-kafka` is healthy and
   resolvable via DNS.
4. Confirm `KafkaOutage` (`up{job="kafka-exporter"} == 0 or kafka_brokers == 0`,
   `for: 1m`) clears in Prometheus/Alertmanager and the resolution email is
   sent.
