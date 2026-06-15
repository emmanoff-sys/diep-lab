# BAT001 Modbus Fix — Validation Report

**Date:** 2026-06-14
**Scope:** `drivers/sunspec/transport.py` (`_BuiltinModbusClient`), used (verbatim,
via `battery_bms.transport`) by the `diep-battery-edge` container running BAT001.
Root cause: `BAT001_MODBUS_ROOT_CAUSE_ANALYSIS.md`.

---

## 1. Fix implemented

`drivers/sunspec/transport.py` — `_BuiltinModbusClient`:

- Added `self._lock = threading.Lock()` in `__init__`.
- `_txn()` now holds that lock for the entire request/response cycle:
  transaction-ID allocation (`_next_tx()`), `sock.sendall(frame)`, and both
  `_recv_exact()` calls (header + body). The mismatch/exception checks remain
  outside the lock (no I/O).

This serializes all Modbus transactions issued by a given client/socket across
threads, so the telemetry-poll loop (`Runner.run`, main thread) and the MQTT
command callback (`Runner._on_command`, paho network thread) can no longer
interleave `sendall`/`recv` on the shared socket.

No protocol, framing, register-map, or simulator changes. `_PymodbusClient`,
`ModbusTcpServer`, and every other driver/simulator are unchanged. Only
`drivers/sunspec/transport.py` was edited (3 lines added, 1 line re-indented
into the `with` block).

---

## 2. Regression test added

`drivers/sunspec/selftest.py` — new check (§6, "concurrency: shared-client
read/write from two threads"):

- Starts a `ModbusTcpServer`, connects one `_BuiltinModbusClient`.
- Runs 50 `read_holding()` calls on one thread concurrently with 50
  `write_registers()` calls on another thread, both against the **same**
  client/socket — reproducing the BAT001 Runner topology (telemetry-poll
  thread + command-callback thread sharing one client).
- Asserts zero `Modbus transaction id mismatch` / timeout errors.

### Pre-fix reproduction (for record)

Run against the live BAT001 simulator before the fix:

```
errors: 55
('read', 1, 'Modbus transaction id mismatch (sent 3, got 2)')
('write', 0, 'Modbus transaction id mismatch (sent 2, got 3)')
...
('read', 3, 'timed out')
```

### Post-fix selftest run

```
$ cd drivers && python3 -m sunspec.selftest
...
concurrency: shared-client read/write from two threads
  [PASS] concurrent read/write: no transaction id mismatch — 0 error(s), e.g. []

SELFTEST PASSED — all checks green
```

`python3 -m battery_bms.selftest` (unchanged, exercises the same transport via
`battery_bms.transport`) — **SELFTEST PASSED — all checks green** (no
regressions in charge/discharge/standby/set_power_limit/set_soc_target
lifecycle).

---

## 3. Live deployment & telemetry recovery

`./drivers` is bind-mounted into `diep-battery-edge` at `/app`, so the edited
`transport.py` was already present in the container; the running process
(started `2026-06-13T04:14:31Z`, before the fix) needed a restart to load it.

Restarted only `diep-battery-edge` (`docker restart diep-battery-edge`):

- **Before restart** (last 10 log lines, old code): continuous
  `Modbus transaction id mismatch (sent N, got N-1)` every ~5s, e.g.
  `sent 6371, got 6370`, `sent 6372, got 6371` — confirms the bug was live and
  ongoing up to the moment of the fix.
- **After restart** (new code): driver reconnected cleanly
  (`BAT001 connected to 127.0.0.1:1702`, `Runner started for BAT001`), **zero**
  `ERROR`/`mismatch` log lines since.

Telemetry resumed immediately at the normal 5s cadence:

```
device_id |             time              | battery_soc | power_kw | voltage
BAT001    | 2026-06-14 05:45:55.574531+00 |          75 |        0 |     700
BAT001    | 2026-06-14 05:45:50.572565+00 |          75 |        0 |     700
BAT001    | 2026-06-14 05:45:44.237841+00 |          75 |        0 |     700
BAT001    | 2026-06-14 05:45:39.236689+00 |          75 |        0 |     700
BAT001    | 2026-06-14 05:45:34.233672+00 |          75 |        0 |     700
```

---

## 4. Battery Dispatch scenario (DERMS)

`POST /derms/battery_dispatch {"device_id":"BAT001","target_soc":85,"max_power_kw":20}`
→ dispatched as `charge` command `3a036f27-d16e-4891-9464-49967fb22b60`.

```
 command_id  | device_id | command_type | status | error_message |          created_at          |         dispatched_at         |           acked_at
3a036f27-... | BAT001    | charge       | ACKED  |               | 2026-06-14 05:46:11.55962+00 | 2026-06-14 05:46:11.692145+00 | 2026-06-14 05:46:11.833241+00
```

**`ACKED`, ~141 ms dispatch→ack** — previously `FAILED` with a transaction-ID
mismatch error.

Telemetry continued uninterrupted *through* the command (no lock contention
stalls), and SoC began rising as commanded (charging at -20 kW toward
`target_soc=85`):

```
            time              | battery_soc | power_kw | voltage
2026-06-14 05:46:00.576505+00 |          75 |        0 |     700
2026-06-14 05:46:05.578735+00 |          75 |        0 |     700
2026-06-14 05:46:10.581205+00 |          75 |        0 |     700
2026-06-14 05:46:15.583302+00 |      75.014 |     -20  |     700
2026-06-14 05:46:20.584214+00 |      75.028 |     -20  |     700
2026-06-14 05:46:25.585303+00 |      75.042 |     -20  |     700
2026-06-14 05:46:30.586199+00 |      75.056 |     -20  |     700
2026-06-14 05:46:35.587678+00 |      75.069 |     -20  |     700
2026-06-14 05:46:40.589134+00 |      75.083 |     -20  |     700
2026-06-14 05:46:45.590469+00 |      75.097 |     -20  |     700
```

---

## 5. Remaining battery-routed DERMS workflows

All 3 remaining scenarios that previously ended `FAILED` for BAT001 were
re-run:

| Scenario | Request | Resulting command | Status |
|---|---|---|---|
| Peak Shaving | `POST /derms/peak_shaving {"reduction_kw":10,"max_power_kw":15}` | `discharge` `a0d57a84-27c8-446b-975e-4a3d4ff7c70a` | **ACKED** |
| Demand Response | `POST /derms/demand_response {"event_duration_minutes":10,"target_reduction_kw":10}` | `discharge` `07e50354-f597-48a2-bbbc-ae863b39a3c9` | **ACKED** |
| Microgrid / Load Optimization | `POST /derms/load_optimization {"optimization_horizon_hours":1}` | `charge` `a45b7d39-8edd-4cb9-ba3a-5c4b380badba` | **ACKED** |

```
              command_id              | command_type | status | error_message
a0d57a84-27c8-446b-975e-4a3d4ff7c70a | discharge    | ACKED  |
07e50354-f597-48a2-bbbc-ae863b39a3c9 | discharge    | ACKED  |
a45b7d39-8edd-4cb9-ba3a-5c4b380badba | charge       | ACKED  |
```

**5/5 DERMS scenarios now ACK against BAT001** (previously 1/5 — Battery
Dispatch with `site_name` omitted was the only one that didn't hit the Modbus
driver path before this fix in the prior validation pass; all 4
battery-routed scenarios now succeed).

Post-test telemetry confirms the driver kept publishing through all four
back-to-back commands, no errors:

```
            time              | battery_soc | power_kw
2026-06-14 05:48:08.004303+00 |      75.297 |      -10
2026-06-14 05:48:03.003017+00 |       75.29 |      -10
2026-06-14 05:47:58.001418+00 |      75.283 |      -10
```

---

## 6. Summary

| Item | Before | After |
|---|---|---|
| BAT001 telemetry | Stopped (last row `2026-06-13 04:20:09Z`), every Modbus transaction failing | Flowing at normal 5s cadence, 0 errors |
| `diep-battery-edge` log errors | `Modbus transaction id mismatch` every ~5s, continuous | None since restart |
| Battery Dispatch (charge, target_soc) | `FAILED` (Modbus mismatch) | `ACKED` |
| Peak Shaving (discharge) | `FAILED` | `ACKED` |
| Demand Response (discharge) | `FAILED` | `ACKED` |
| Microgrid/Load Optimization (charge) | `FAILED` | `ACKED` |
| Regression coverage | none for concurrent transport access | `sunspec.selftest` §6 — 50×read + 50×write concurrent, asserts 0 mismatches |

**Issue 1 (Critical) from `DIEP_FULL_PLATFORM_VALIDATION_REPORT.md` is
resolved.** The platform's prior **NO-GO for battery-dependent DERMS** is
lifted: all 4 battery-routed DERMS scenarios now complete `PENDING → SENT →
ACKED` end-to-end against BAT001, and BAT001 telemetry has recovered.

Remaining items from the validation report (Issue 2 `site_name` backfill,
Issue 3 Alertmanager placeholder receivers, Issue 4 hardcoded Kafka SASL
credential, EV-charging DERMS endpoint) are unrelated to this Modbus fix and
remain open as previously documented.

### Change footprint

- `drivers/sunspec/transport.py` — added `threading.Lock`, serialized `_txn()`.
- `drivers/sunspec/selftest.py` — added concurrency regression check.
- `diep-battery-edge` container restarted (only service restarted; required to
  load the fixed transport module — no data deleted, no other service
  touched).
- No database writes beyond the 4 intentional DERMS validation commands
  (now `ACKED`) and the normal telemetry stream resuming.
