# DIEP Phase 9G — Microgrid Controller (IEC 60870-5-104)

> **Status:** Implemented and operational (stage **9G-a**, IEC-104). Device **MGC900**
> is **PRODUCTION_READY**. Date: 2026-06-05 · Scope: microgrid-controller vertical over
> IEC 60870-5-104. **Reuses the SDK polling Runner, MQTT, dispatcher, twin, onboarding &
> certification unchanged.** IEC 61850 (stage 9G-b) is scoped as future work (§7).

---

## 1. Summary

DIEP now integrates a **microgrid controller over IEC 60870-5-104** — a pollable
master/slave SCADA protocol. Unlike OCPP (9F, an event-driven server), IEC-104 returns
to the **polling** model, so this driver subclasses `BaseDriver` and is hosted by the
shared `Runner` exactly like the Modbus drivers (9C/9D/9E). The controller publishes
canonical telemetry to `diep/microgrid/MGC900`, accepts `island` / `grid_connect` /
`set_setpoint` over the full command bus, and has been certified to **PRODUCTION_READY**.

**This completes the Phase 9 device-integration program — five real protocol verticals
behind one Driver SDK Framework:**

| Device | Type | Protocol | Transport model | Status |
|--------|------|----------|-----------------|--------|
| INV900 | solar_inverter | SunSpec/Modbus | poll | PRODUCTION_READY |
| MTR900 | smartmeter | Modbus TCP | poll | PRODUCTION_READY |
| BAT900 | battery | Modbus TCP | poll | PRODUCTION_READY |
| EVSE900 | ev_charger | OCPP 1.6J | WebSocket / CSMS server | PRODUCTION_READY |
| **MGC900** | **microgrid** | **IEC 60870-5-104** | **poll (SCADA master)** | **PRODUCTION_READY** |

---

## 2. Architecture

```
[ Microgrid RTU / sim ] --IEC-104/TCP--> [ MicrogridIec104Driver ] --> [ Runner (SDK) ]
  controlled station       APCI I/S/U          GI poll / decode            publish + cmd/ack
  IOA dataset              ASDU                 canonical map                     |
                                                                  MQTT diep/microgrid/MGC900(/cmd,/ack)
                                                                                  |
   [ ingestor ] --> [ FastAPI /telemetry ] --> TimescaleDB + Redis(twin)
   [ API /commands ] --> Kafka --> [ dispatcher ] --> MQTT cmd --> driver --> IEC-104 C_SC/C_SE
                                                  ^---------- MQTT ack <-----------'
```

- **`transport.py`** — minimal IEC-104 over TCP: APCI **I/S/U** frames, STARTDT handshake,
  sequence tracking, a threaded controlled-station server (RTU) and a controlling-station
  client (the driver/master). Dependency-free.
- **`models.py`** — ASDU encode/decode for the needed types, the microgrid IOA map, and
  the measurement → canonical mapping.
- **`driver.py`** — `BaseDriver` subclass: GI poll → canonical telemetry; C_SC/C_SE commands.
- **`sim.py`** — IEC-104 RTU with the microgrid islanding/droop physics.

**Reused unchanged:** SDK (`BaseDriver`, `Runner`, `normalize`, `registry`), the ingestor,
`/telemetry`, the Kafka/dispatcher command bus (race-safe ack), onboarding/certification,
the digital twin. `domain = "microgrid"` matches the dispatcher `DOMAIN_MAP` and
`ALLOWED_COMMANDS["microgrid"]` already contained the commands → **zero `app.py` change**.

---

## 3. Protocol mapping (IEC-104 → DIEP canonical)

Monitor direction (RTU → master), gathered via General Interrogation (C_IC):

| IOA | Type | Quantity | Canonical field |
|----:|------|----------|-----------------|
| 1001 | M_ME_NC_1 | frequency (Hz) | `frequency` |
| 1002 | M_ME_NC_1 | PCC power (kW, ±) | `power_kw` (+ `grid_import_kw`/`grid_export_kw`) |
| 1003 | M_ME_NC_1 | solar (kW) | `solar_kw` |
| 1004 | M_ME_NC_1 | load (kW) | *extra* `load_kw` |
| 1005 | M_ME_NC_1 | voltage (V) | `voltage` |
| 1006 | M_ME_NC_1 | setpoint (kW) | *extra* `setpoint_kw` |
| 2001 | M_SP_NA_1 | grid-connection status | *extra* `grid_connected` / `mode` |

PCC follows the platform microgrid convention: `power_kw = pcc_kw`,
`grid_import_kw = max(0, pcc)`, `grid_export_kw = max(0, -pcc)`.

**Observed canonical payload (MGC900, grid-connected at 10 kW setpoint):**
```json
{"device_id":"MGC900","voltage":229.9,"frequency":50.01,"solar_kw":7.15,
 "power_kw":10.0,"grid_import_kw":10.0,"grid_export_kw":0.0,
 "grid_connected":true,"mode":"grid_connected","load_kw":18.2,"setpoint_kw":10.0}
```

---

## 4. Command mapping

| DIEP command | IEC-104 | Effect | Validated |
|--------------|---------|--------|-----------|
| `grid_connect` | C_SC_NA_1 (IOA 3001, close) | breaker close → grid-connected | ✓ ACKED |
| `island` | C_SC_NA_1 (IOA 3001, open) | breaker open → islanded (PCC→0, freq droops) | ✓ ACKED |
| `set_setpoint` | C_SE_NC_1 (IOA 3002, short float) | PCC exchange setpoint | ✓ ACKED |

Each command is sent as an `activation` (COT=6) and the ACK is derived from the RTU's
`activation confirmation` (COT=7); the driver waits for ACTCON with a timeout. Commands
validate against `ALLOWED_COMMANDS["microgrid"]` and audit through `commands`
(PENDING → SENT → ACKED).

---

## 5. Integration changes (additive only)

1. `drivers/edge_agent.py` — added `import microgrid_iec104`.
2. New files: `drivers/microgrid_iec104/{__init__,driver,transport,models,sim,selftest}.py`,
   `drivers/microgrid_iec104/devices.json`, `docker-compose-microgrid-edge.yml`.

**Filename note:** the compose file is `docker-compose-microgrid-edge.yml`, not
`docker-compose-microgrid.yml` (which already runs the legacy MG001 sim). No existing
service logic, schema, topic contract, or DERMS path was modified.

---

## 6. Validation results

See **DIEP_PHASE9G_VALIDATION_REPORT.md**. Headline: host selftest all-green (incl.
islanding droop); live telemetry + Timescale history + Redis twin; set_setpoint/island/
grid_connect ACKED with actuation visible (PCC tracks setpoint; islanding collapses PCC
and bends frequency); certification → **PRODUCTION_READY**.

---

## 7. Remaining gaps

1. **IEC 61850 (stage 9G-b) not implemented.** This phase delivers IEC-104 (9G-a). IEC
   61850 (MMS/GOOSE, substation/IED modelling) needs heavyweight tooling (libiec61850),
   is real-time and safety-critical, and is recommended as its own sub-project — see the
   validation report §6.
2. **Simplified IEC-104 state machine.** The transport implements the APCI I/S/U framing
   and STARTDT handshake with basic sequence tracking, sufficient for poll + command, but
   not the full k/w send/receive window or the t1/t2/t3 timeout state machine a production
   master requires. Production should adopt a vetted stack (e.g. `c104`/lib60870) behind
   the same `transport.py` seam.
3. **Canonical schema lacks `load_kw`, `setpoint_kw`, `grid_connected`/`mode`** — published
   on MQTT but dropped at `/telemetry` (the recurring 8-field-schema gap; see the 9D report
   §6 schema-extension recommendation, which this phase reinforces).
4. **Security & failover** certification tests remain `SKIPPED` pending Phase 9J (TLS/auth)
   and 9K (HA). For microgrid control specifically — islanding and breaker operation are
   **safety-critical** — 9J should precede any field actuation.

---

## 8. Success criteria — Phase 9 device integration complete

✓ **Microgrid Controller** integrated through the Driver SDK Framework (MGC900,
PRODUCTION_READY), alongside ✓ Solar (INV900), ✓ Meter (MTR900), ✓ Battery (BAT900),
✓ EV Charger (EVSE900). **Five real protocol verticals — Modbus/SunSpec, OCPP/WebSocket,
and IEC-104/SCADA — all behind one SDK, all certified PRODUCTION_READY.**

Phase 9 program-level wrap-up and recommendations (9G-b, schema, 9J security, 9K HA) are
in the validation report §6.
