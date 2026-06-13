# DIEP Protocol Adapter Framework (Phase 9B)

> **Status:** Wave-1 design + non-breaking SDK skeleton. The `drivers/` SDK described here is
> created as **new code only** — it does not modify the running simulators, ingestor,
> dispatcher, or any existing service.

## 1. Purpose

Real field devices speak heterogeneous protocols (DLMS/COSEM, Modbus, OCPP, SunSpec,
IEC 60870-5-104, IEC 61850, DNP3, BACnet). The platform's internal contract is uniform:
MQTT telemetry on `diep/<domain>/<device_id>` and commands/acks on `.../cmd` and `.../ack`.

The adapter framework is the **translation layer** that lets any protocol present as a
standard DIEP device. Its design goal: **a real driver and the existing simulator are
interchangeable behind the same MQTT contract**, so the digital twins, DERMS, AI analytics,
and certification suite work unchanged whether the source is simulated or real.

```
Field device ──(native protocol)──▶ Protocol Adapter ──(normalize)──▶ MQTT ──▶ DIEP
        ◀───(native command)─────── Protocol Adapter ◀──(cmd)──────── MQTT ◀─── DIEP
```

## 2. The normalized contract (the integration seam)

Every adapter publishes **canonical telemetry** — the same fields the existing telemetry
ingestor and `/telemetry` schema already use — so no backend change is needed:

```
voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw
```

- **Telemetry topic:** `diep/<domain>/<device_id>` (3-level — the ingestor already subscribes `diep/+/+`).
- **Command topic (subscribe):** `diep/<domain>/<device_id>/cmd` (4-level — dispatcher publishes here).
- **Ack topic (publish):** `diep/<domain>/<device_id>/ack` — payload `{command_id, device_id, status, error, acked_at}`.
- **Domains:** `meter`, `battery`, `solar`, `charger`, `microgrid` (matches the dispatcher `DOMAIN_MAP`).

Adapters MAY also include device-native fields (e.g. `soh`, `session_energy_kwh`) in the
telemetry payload; the ingestor ignores unknown fields, and future twin enhancements can use them.

## 3. Driver lifecycle (the required 7 operations)

The program requires each adapter to support connect / read / normalize / publish / receive /
execute / ack. These map to `BaseDriver` (in `drivers/diep_driver/base.py`) plus a generic
`Runner` that owns the MQTT loop so individual drivers only implement protocol logic:

| Requirement | Where | Notes |
|-------------|-------|-------|
| Connect | `BaseDriver.connect()` | Open the protocol session (TCP/serial/CAN/WebSocket) |
| Read telemetry | `BaseDriver.read_telemetry()` | Return a **native** dict from the device |
| Normalize | `BaseDriver.normalize(native)` | Map native → canonical schema (default + override) |
| Publish MQTT | `Runner` | Publishes canonical telemetry on the interval |
| Receive command | `Runner` | Subscribes `.../cmd`, parses, dispatches |
| Execute command | `BaseDriver.execute_command(type, params)` | Returns `(status, error)` |
| Publish ACK | `Runner` | Publishes `.../ack` with the command_id and result |

This separation means a new protocol driver is typically ~`connect` + `read_telemetry` +
`normalize` + `execute_command` + `supported_commands` — the MQTT/TLS/loop/ack plumbing is shared.

## 4. SDK layout (`drivers/`)

```
drivers/
  diep_driver/            # shared SDK (the framework itself)
    base.py               # BaseDriver ABC — the 7-operation interface
    normalize.py          # CANONICAL_FIELDS + helpers (coerce/clamp)
    mqtt_client.py        # paho wrapper; TLS-ready (mTLS hooks for 9J)
    registry.py           # name -> driver class registry/factory
    runner.py             # generic telemetry+command loop driving a BaseDriver
  modbus/driver.py        # 9C/9D/9E transport — Modbus TCP/RTU (stub)
  sunspec/driver.py       # 9D/9E — SunSpec over Modbus (stub)
  dlms/driver.py          # 9C — DLMS/COSEM meters (stub)
  ocpp/driver.py          # 9F — OCPP 1.6/2.0.1 CSMS (server role — see note)
  iec104/driver.py        # 9G — IEC 60870-5-104 client (stub)
  iec61850/driver.py      # 9G — IEC 61850 MMS client (stub)
  dnp3/driver.py          # DNP3 outstation client (stub)
  bacnet/driver.py        # building integration (unscoped in 9C–9G — see note)
```

Each protocol package ships a **runnable stub** that subclasses `BaseDriver`, declares its
domain and command vocabulary, and raises `NotImplementedError` with vendor/register-map TODOs.
This makes the framework real and importable now, with clear seams for Wave 2/3 implementation.

## 5. Per-protocol implementation notes

- **Modbus (9C/9D/9E):** synchronous register polling (TCP 502 / RTU). Per-vendor register maps
  are the real work; structure them as data (YAML/JSON), not code. Use `pymodbus`.
- **SunSpec (9D/9E):** standardized Modbus model maps (e.g. model 101/103 inverter, 802 battery).
  Covers Huawei/Sungrow/SMA/Fronius/Solis with far less per-vendor effort — **best first driver.**
- **DLMS/COSEM (9C):** OBIS-code object model over HDLC/TCP; association + security suites.
  Highest meter complexity; use a vetted DLMS stack. L+G/Itron/Hexing/EDMI OBIS maps differ.
- **OCPP (9F) — architectural exception:** the charger is the *client*; DIEP runs the **Central
  System (CSMS)** that chargers dial into over WebSocket. `drivers/ocpp/` is therefore a small
  service (not a poller): it terminates OCPP, maps `BootNotification/MeterValues` → telemetry and
  `RemoteStartTransaction/RemoteStopTransaction/SetChargingProfile` → commands. Use `ocpp` (mobilityhouse).
- **IEC 60870-5-104 (9G):** TCP SCADA telemetry/control (ASDU). Client polls/receives from RTUs.
- **IEC 61850 (9G):** MMS + GOOSE; substation-grade, safety-critical. Largest lift; needs vendor
  ICD/SCL files and careful test isolation. Often paired with a certified gateway.
- **DNP3:** common in utility RTUs; outstation polling. `pydnp3`/`dnp3-python`.
- **BACnet:** building HVAC/meters. **Not owned by any 9C–9G sub-phase** — recommend scoping under
  smart-city/building integration or deferring.

## 6. Where adapters run

Adapters run **on the edge gateway** (see `DIEP_EDGE_GATEWAY_ARCHITECTURE.md`), not on the
central platform — they need LAN/serial/CAN proximity to devices and provide store-and-forward
during backhaul outages. The same driver can also run centrally against a TCP-reachable device
for lab testing. The MQTT client connects out to the platform broker over **TLS (mTLS in 9J)**.

## 7. Testing without field hardware

Each driver can be validated against a **protocol simulator** (e.g. a Modbus TCP slave / SunSpec
test server / local OCPP charge-point sim) before real devices exist. The certification suite
(9I) runs the same six tests against simulated and real endpoints identically — because both
present the identical normalized MQTT contract.
