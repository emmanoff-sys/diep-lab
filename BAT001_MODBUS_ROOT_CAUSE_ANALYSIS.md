# BAT001 Modbus Transaction-ID Mismatch — Root Cause Analysis

**Date:** 2026-06-14
**Scope:** `diep-battery-edge` (BAT001 / `battery_bms` driver) and its shared Modbus
transport in `drivers/sunspec/transport.py`. No other services analyzed or changed.

---

## 1. Symptom recap (from `DIEP_FULL_PLATFORM_VALIDATION_REPORT.md`)

- Every Modbus transaction issued by `diep-battery-edge` fails with:
  `IOError: Modbus transaction id mismatch (sent N, got N-1)` (or `N+1`).
- BAT001 telemetry stopped (`telemetry` table has no BAT001 rows after
  `2026-06-13 04:20:09Z`, ~6 minutes after the container's current start).
- DERMS commands routed to BAT001 (Battery Dispatch, Peak Shaving, Demand
  Response, Microgrid/Load Optimization) reach `ACKED` at the Kafka/MQTT/
  dispatcher layer but the **device-level result is `FAILED`**, because
  `BatteryBmsDriver.execute_command()` raises the mismatch error, which
  `Runner._on_command()` converts to `CommandResult("FAILED", str(exc))`.

---

## 2. Where transaction IDs are generated

`drivers/sunspec/transport.py`, `_BuiltinModbusClient` (the pure-socket Modbus
TCP client used by `battery_bms` — `pymodbus` is **not installed** in
`diep-battery-edge`, confirmed via `python3 -c "import pymodbus"` → `ModuleNotFoundError`,
so the built-in client is the one in use):

```python
def __init__(self, host, port=502, unit=1, timeout=5.0):
    ...
    self._tx = 0

def _next_tx(self) -> int:
    self._tx = (self._tx + 1) & 0xFFFF
    return self._tx

def _txn(self, pdu: bytes) -> bytes:
    if self.sock is None:
        raise ConnectionError("Modbus client not connected")
    tx = self._next_tx()
    frame = struct.pack(">HHHB", tx, 0, len(pdu) + 1, self.unit) + pdu
    self.sock.sendall(frame)
    header = self._recv_exact(7)
    rx_tx, proto, length, _unit = struct.unpack(">HHHB", header)
    body = self._recv_exact(length - 1)
    if rx_tx != tx:
        raise IOError(f"Modbus transaction id mismatch (sent {tx}, got {rx_tx})")
    ...
```

`_tx` is a plain instance counter, incremented once per `_txn()` call
(line 47, pre-fix). One `_BuiltinModbusClient` instance == one TCP socket
(`self.sock`), created once in `connect()` and reused for the life of the
driver process.

---

## 3. Request/response trace

### 3.1 Single-threaded path (correct)

`BatteryBmsDriver.read_telemetry()` calls `client.read_holding(4000, 19)` →
one `_txn()` call (19 registers < `_MAX_READ`=125, so no chunking).
`BatteryBmsDriver._write_control()` calls `client.write_registers(...)` 1–3
times per command (`cmd_mode`, `power_setpoint_kw` (f32, 2 regs),
`target_soc`) → 1–3 `_txn()` calls.

The server side, `ModbusTcpServer._handle()`:

```python
header = self._recv_exact(conn, 7)
tx, proto, length, unit = struct.unpack(">HHHB", header)
pdu = self._recv_exact(conn, length - 1)
resp_pdu = self._dispatch(pdu)
frame = struct.pack(">HHHB", tx, 0, len(resp_pdu) + 1, unit) + resp_pdu
conn.sendall(frame)
```

reads exactly one MBAP header + PDU, dispatches it, and echoes the same `tx`
back. In isolation, for a single caller issuing one `_txn()` at a time, this
is correct framing — request *N* always gets response *N*.

**Confirmed by direct test** (fresh, single-threaded connection to the live
BAT001 simulator on `127.0.0.1:1702`):

```
0 [17096, 0, 17455, 0, 0, 0, 0, 0, 16864, 0, 17092, 0, 0, 1, 16968, 0, 100, 17096, 0]
1 [17096, 0, 17455, 0, 0, 0, 0, 0, 16864, 0, 17092, 0, 0, 1, 16968, 0, 100, 17096, 0]
...
```
5/5 reads succeeded, no mismatch — **the framing and the simulator are correct.**

### 3.2 Concurrent path (the actual production path — broken)

`drivers/diep_driver/runner.py` `Runner.run()`:

- **Main thread**: `while True: read_telemetry() -> normalize -> publish; sleep(interval)`
  — for BAT001, `interval=5`s, one `read_holding()` (one `_txn()`) per cycle.
- **paho MQTT network thread** (`transport.connect()` calls `client.loop_start()`,
  which runs `_on_command()` as a callback whenever a command arrives on
  `diep/battery/BAT001/cmd`): `execute_command()` → `_write_control()` → 1–3
  `write_registers()` calls (1–3 `_txn()` calls).

**Both threads call `_txn()` on the same `_BuiltinModbusClient` instance —
i.e., the same `self.sock` — with no synchronization.** `_next_tx()`,
`sock.sendall()`, and `_recv_exact()` are all unprotected.

When a DERMS command for BAT001 arrives while the telemetry loop is mid-`_txn`
(or vice versa), the two threads' `sendall`/`recv` calls interleave on one TCP
stream:

1. Thread A allocates `tx=N`, sends its request frame.
2. Thread B allocates `tx=N+1`, sends its request frame, before A has read a
   response.
3. The simulator processes both requests in arrival order and replies with
   `tx=N` then `tx=N+1`.
4. Thread B's `recv` runs first and consumes the **first** response on the
   socket — the one tagged `tx=N` (A's), while B sent `tx=N+1` →
   `"Modbus transaction id mismatch (sent N+1, got N)"`.
5. Thread A's subsequent `recv` then consumes B's response (`tx=N+1`) while
   expecting `tx=N` → `"sent N, got N+1"`.
6. Because TCP is a byte stream and `_recv_exact` has now read the *wrong*
   number of header/body bytes for at least one side, the stream is
   **permanently misaligned** for the remaining lifetime of the connection —
   every subsequent `_txn()` on either thread also reads a stale/foreign
   frame and raises the same off-by-one mismatch, with no self-recovery.

This exactly matches the observed symptom: a clean, deterministic
`sent N, got N±1` pattern (not random garbage — both sides are still sending
well-formed MBAP frames, just reading each other's), occurring on *every*
transaction from the moment of the first concurrent access onward, which is
why telemetry stopped completely (~6 minutes after start, i.e., shortly after
the first DERMS command was dispatched to BAT001 during validation) rather
than failing intermittently.

### 3.3 Reproduction

Ran 50 concurrent `read_holding()` calls (simulating the telemetry loop)
against 50 concurrent `write_registers()` calls (simulating command handling)
on **one shared `_BuiltinModbusClient`**, against the live BAT001 simulator
(`127.0.0.1:1702` inside `diep-battery-edge`):

```
errors: 55
('read', 1, 'Modbus transaction id mismatch (sent 3, got 2)')
('write', 0, 'Modbus transaction id mismatch (sent 2, got 3)')
('write', 1, 'Modbus transaction id mismatch (sent 5, got 4)')
('read', 2, 'Modbus transaction id mismatch (sent 4, got 5)')
('write', 3, 'Modbus transaction id mismatch (sent 8, got 7)')
...
('read', 3, 'timed out')
```

55/100 transactions failed with the exact `sent N, got N±1` signature
reported by the platform validation, reproduced on demand against the real
BAT001 simulator.

---

## 4. Findings against the investigation checklist

| Question | Finding |
|---|---|
| Is Modbus TCP framing incorrect? | **No.** MBAP header packing/unpacking on both client (`_txn`) and server (`_handle`) is correct (`>HHHB`: tx, proto=0, length, unit). |
| Does the driver increment the transaction ID twice per request? | **No.** `_next_tx()` is called exactly once per `_txn()` call. |
| Does the simulator return incorrect transaction IDs? | **No.** `ModbusTcpServer._handle()` echoes back exactly the `tx` it received, for every request, in the order received. Verified correct with a single-threaded client (§3.1). |
| Is the transport validation logic (`rx_tx != tx` check) incorrect? | **No.** The check itself is correct — it is correctly detecting a real desync. |
| **Root cause** | **`_BuiltinModbusClient` is not thread-safe.** `Runner` shares one client/socket between the telemetry-poll thread and the paho MQTT command-callback thread. Concurrent, unsynchronized `sendall`/`recv` calls on the same TCP stream let one thread consume the response frame intended for the other, producing the off-by-one mismatch and permanently desynchronizing the stream thereafter. |

---

## 5. Fix

Add a `threading.Lock` to `_BuiltinModbusClient`, held for the entire
request/response cycle (`tx` allocation through `recv` of the response) in
`_txn()`. This serializes all Modbus transactions issued by a given client
instance, regardless of which thread issues them, eliminating the
interleaved-stream race while preserving the existing single-connection
design (no protocol or framing changes).

Scope: `drivers/sunspec/transport.py` only (`_BuiltinModbusClient`), which is
reused verbatim by `battery_bms.transport` (`from sunspec.transport import
open_modbus, ModbusTcpServer`). No other service, driver, or simulator is
modified.

See `BAT001_FIX_VALIDATION_REPORT.md` for the implementation, regression test,
and post-fix validation evidence.
