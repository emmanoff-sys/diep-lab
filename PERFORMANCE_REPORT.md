# DIEP — Performance & Resilience Validation Report (SIT, 2026-06-25)

Covers sprint Deliverables 3 (Performance) and 4 (Resilience). Measured
against the live `ingestor → FastAPI → TimescaleDB` path — the only path
actually wired end-to-end (see `INTEGRATION_VALIDATION_REPORT.md` §0). MDM
runs as an independent subscriber to the same input and is included where
its own live metrics are relevant, but is not on this critical path.

## 1. Throughput and latency

### 1.1 Method

A single long-lived process (`validation/performance/load_test.py`, run via
a throwaway `python:3.12` container with one MQTT connection and one DB
connection — not the container-per-message harness used for the integration
scenarios, which would add ~2-3s of its own overhead per message and make
any throughput/latency number meaningless) published bursts at four target
rates for 5 seconds each, then polled TimescaleDB for each message's
`correlation_id` to measure delivery.

**Latency caveat, stated plainly:** the 1 and 10 msg/s tiers' latency
numbers below are an artifact of this harness's batch-then-poll design (it
finishes the entire 5s publish burst before starting to poll), not real
steady-state pipeline latency — a message sent at the start of an
otherwise-keeping-up burst is recorded as "slow" only because polling hadn't
started yet. At 100 and 1000 msg/s this stops being a measurement artifact:
the pipeline genuinely cannot keep up at those rates (§1.3), so the
apparent latency there reflects real queueing delay, not harness timing.
True sub-second per-message latency at low rates was not isolated by this
harness — flagged rather than estimated.

### 1.2 Results

| Tier (requested) | Actual publish rate achieved | Sent | Delivered (within window) | Lost | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| 1 msg/s | 1.0 msg/s | 5 | 5 | 0 | 3.04s* | 5.04s* | 5.04s* | 5.04s* |
| 10 msg/s | 9.9 msg/s | 50 | 50 | 0 | 2.57s* | 4.84s* | 5.04s* | 5.04s* |
| 100 msg/s | 89.7 msg/s | 449 | 414 | 35 | 14.72s | 29.04s | 30.04s | 30.30s |
| 1000 msg/s | 510.3 msg/s | 2552 | 372 | 2180 | 18.51s | 32.83s | 33.97s | 34.18s |

\* Harness-artifact latency, see caveat above — actual delivery was 100%
within the burst for these two tiers.

Re-checked several minutes after the test (not just within the original
poll window): the 1000 msg/s tier's delivered count did **not** continue
climbing — 2180 messages were not delayed, they were **permanently lost**.

### 1.3 Root cause (confirmed, not inferred)

```
[2026-06-25 17:15:30,352] [diep-ingestor] WARNING: MQTT disconnected (rc=Keep alive timeout)
```

`ingestor/telemetry_ingestor.py`'s `on_message` callback runs synchronously
in paho's network-loop thread and does a **blocking** `requests.post(...)` to
FastAPI (HTTP) followed by a DB write, per message, one at a time. At 100+
msg/s sustained, that callback can't return fast enough for the same thread
to also service MQTT's keepalive PINGREQ/PINGRESP — the broker disconnects
the ingestor for keepalive timeout. The telemetry topic is QoS 0: **the
broker does not queue/redeliver missed messages across a disconnect.**
Messages published during that gap are gone, not delayed. The ingestor's own
reconnect logic *does* work (confirmed in §2.4 below) and the container
never crashed — this is a throughput ceiling and a silent-loss bug, not a
crash bug.

**Practical ceiling:** clean delivery somewhere between 10 and 89.7 msg/s
sustained; loss becomes severe (85%+) at ~510 msg/s actually achieved
client-side. For reference, this is well below what even a modest AMI
deployment (hundreds of meters polling every few seconds) would need.

### 1.4 MDM's own load behavior

MDM, as an independent subscriber to the same raw topic, also received the
full load-test burst. `mdm_measurements_processed_total` (the real, live
counter) climbed by thousands of measurements over the course of this
sprint's combined scenario + load traffic — confirmed live via Prometheus
(`diep-mdm` job, scraped successfully after this sprint added it — see
`SYSTEM_ACCEPTANCE_REPORT.md`). A precise MDM-only throughput-under-the-same-
burst number was not isolated (no clean before/after counter snapshot taken
at the exact load-test boundary) — flagged as a gap in this report's own
measurement, not claimed.

## 2. Resilience

Graceful `docker compose restart <service>` per target (not the destructive
resets from the documented host-instability incident — see
`HOST_VM_INSTABILITY_FINDINGS_20260624.md`), verified before/after.

| Service | Crash on restart? | Recovered cleanly? | Evidence |
|---|---|---|---|
| Redis | No | Yes | `redis_up` Prometheus metric = 1 post-restart; FastAPI `/health` unaffected throughout |
| Kafka | No | Yes | Topic list intact (`__consumer_offsets`, `diep.commands`) post-restart; `kafka_brokers`=1; no error/corruption lines in logs |
| FastAPI | No | Yes | `/health` returns 200 within seconds; Prometheus `up{job="diep-fastapi"}`=1 |
| TimescaleDB | No | Yes | `pg_isready` accepting connections immediately; row count consistent (no loss, no duplication); **no corruption signatures** matching the documented incident fingerprint (`FATAL`/`PANIC`/`corrupt`/`replorigin` all absent from post-restart logs) |
| MQTT broker | No | Yes | Both ingestor and MDM detected the disconnect and reconnected within ~3s; a live publish-and-verify round-trip immediately after confirmed the full pipeline resumed correctly |

### 2.1 AMI / MQTT reconnect — qualified pass

Beyond the deliberate broker restart above, §1.3's overload-induced
disconnect is itself a real, **unplanned** reconnect test: the ingestor
detected the keepalive-timeout disconnect and reconnected on its own,
without crashing or requiring intervention. The qualification: reconnect
itself is clean, but **QoS 0 means whatever was in flight during the gap is
gone**, not buffered. "No crashes, recovers" — yes. "No data loss" — no,
not under this specific failure mode. Both halves are reported, not just
the positive one.

### 2.2 What was not tested

- DNS/network-partition-style failures (only process-level restarts).
- Concurrent multi-service failure (each service was restarted in isolation).
- TimescaleDB failover/replica promotion (this stack runs a single instance
  for the `diep` database — WAL shipping/backup exist per the Production
  Hardening sprint, but a live failover drill was out of scope here).
