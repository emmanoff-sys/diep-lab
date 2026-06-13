# DIEP Phase 9F — EV Charger (OCPP) Driver

> **Status:** Implemented and operational. Device **EVSE900** is **PRODUCTION_READY**.
> Date: 2026-06-05 · Scope: EV-charging vertical via an OCPP 1.6 Central System.
> **Reuses the canonical schema, MQTT, dispatcher, twin, onboarding & certification
> unchanged** — but introduces a new *transport shape* (see §2).

---

## 1. Summary

DIEP now integrates **EV chargers over OCPP 1.6J**. Unlike the three Modbus polling
drivers (9C/9D/9E), an OCPP charger is a WebSocket **client** that dials into a Central
System (**CSMS**) **server**. Phase 9F therefore delivers a small CSMS that bridges OCPP
to the DIEP data/command plane: inbound `MeterValues` become canonical telemetry on
`diep/charger/EVSE900`, and platform commands (`start_charging` / `stop_charging` /
`set_limit`) become OCPP `RemoteStartTransaction` / `RemoteStopTransaction` /
`SetChargingProfile`. EVSE900 has been driven through onboarding to **PRODUCTION_READY**.

Four verticals now run behind the DIEP integration framework:

| Device | Type | Protocol | Transport | Status |
|--------|------|----------|-----------|--------|
| INV900 | solar_inverter | SunSpec/Modbus | poll | PRODUCTION_READY |
| MTR900 | smartmeter | Modbus TCP | poll | PRODUCTION_READY |
| BAT900 | battery | Modbus TCP | poll | PRODUCTION_READY |
| **EVSE900** | **ev_charger** | **OCPP 1.6J** | **WebSocket / CSMS** | **PRODUCTION_READY** |

---

## 2. Architecture — the CSMS server-role exception

```
[ EV charge point ] --WebSocket(OCPP 1.6J)--> [ CSMS (WS server) ]
   (WS CLIENT)         BootNotification             |  on_telemetry / send_command
                       StatusNotification           v
                       StartTransaction      [ CsmsMqttBridge ] -- normalize -->
                       MeterValues ----------------> publish  diep/charger/EVSE900
                       StopTransaction              subscribe diep/charger/+/cmd
                                                         |                 ^
   RemoteStart/Stop  <--- OCPP CALL over WS ------------'                  |
   SetChargingProfile ---> CALLRESULT --> ack ----> diep/charger/EVSE900/ack
```

- **`Csms`** (`driver.py`) — the protocol+transport core: a WebSocket server that
  accepts charge points (path = charger id), answers their CP-initiated CALLs, and
  issues CSMS-initiated CALLs with CALLRESULT correlation. **No MQTT dependency** →
  unit-testable headless.
- **`CsmsMqttBridge`** — wires the core to DIEP via the SDK's `MqttTransport` and
  `normalize_canonical`: publishes telemetry, subscribes the command topic, translates,
  and acks. It only handles chargers **connected to this CSMS**, so it coexists with the
  legacy EV001 charger on the same broker without double-acking.
- **`transport.py`** — a dependency-free RFC 6455 WebSocket server + client (handshake,
  text frames, client masking, ping/pong). Production swaps this for `websockets` +
  the `ocpp` library; the message layer is unchanged.
- **`models.py`** — OCPP-J framing (CALL/CALLRESULT/CALLERROR) + the MeterValues →
  canonical mapping.

**Reused unchanged:** the canonical telemetry schema, the ingestor, FastAPI `/telemetry`,
the Kafka/dispatcher command bus (incl. the race-safe ack), onboarding/certification, the
digital twin, and `ALLOWED_COMMANDS["ev_charger"]`. `domain = "charger"` matches the
dispatcher `DOMAIN_MAP` (`ev_charger → charger`), so no dispatcher change was needed.

**What is NOT reused:** the `BaseDriver` poll loop (`connect()/read_telemetry()`). OCPP is
event-driven and inbound-connection, so the CSMS runs as a service (its own `__main__` /
`docker-compose-ocpp.yml`), not under the per-device `Runner`. A registry stub
(`@register("ocpp_csms")`) signposts this exception.

---

## 3. OCPP message mapping

### Inbound (charge point → CSMS)
| OCPP action | CSMS handling |
|-------------|---------------|
| `BootNotification` | record vendor/model; reply `{status: Accepted, interval, currentTime}` |
| `Heartbeat` | reply `{currentTime}` |
| `StatusNotification` | track connector status (Available/Charging/Finishing) |
| `StartTransaction` | assign `transactionId`; reply `{transactionId, idTagInfo: Accepted}` |
| `MeterValues` | map sampledValues → canonical telemetry → publish |
| `StopTransaction` | clear transaction; reply `{idTagInfo: Accepted}` |

### MeterValues → canonical
| OCPP measurand | Canonical field |
|----------------|-----------------|
| `Power.Active.Import` (W) | `power_kw` (÷1000) + `grid_import_kw` |
| `Voltage` (V) | `voltage` |
| `Current.Import` (A) | `current` |
| `Energy.Active.Import.Register` (Wh) | *extra* `session_energy_kwh` |
| `SoC` (%) | *extra* `vehicle_soc` |
| connector status | *extra* `connector_status` |

**Observed canonical payload (EVSE900, charging):**
```json
{"device_id":"EVSE900","voltage":230.3,"current":58.4,"power_kw":13.45,
 "grid_import_kw":13.45,"session_energy_kwh":0.42,"vehicle_soc":36.1,
 "connector_status":"Charging"}
```

---

## 4. Command mapping

| DIEP command | OCPP CALL | Charge-point effect | Validated |
|--------------|-----------|---------------------|-----------|
| `start_charging` | `RemoteStartTransaction` (+ optional chargingProfile) | begin session | ✓ ACKED |
| `stop_charging` | `RemoteStopTransaction {transactionId}` | end session, power→0 | ✓ ACKED |
| `set_limit` | `SetChargingProfile {chargingSchedulePeriod.limit}` | cap charge rate | ✓ ACKED |

Commands validate against `ALLOWED_COMMANDS["ev_charger"]`, are audited in `commands`
(PENDING → SENT → ACKED), and the ACK is derived from the charge point's OCPP CALLRESULT
status (`Accepted`/`Scheduled` → ACKED, else FAILED). The CSMS correlates each outbound
CALL to its CALLRESULT by `uniqueId` with a timeout.

---

## 5. Integration changes (additive only)

1. `drivers/edge_agent.py` — `import ocpp_csms` for registry discoverability (the CSMS
   still runs as a service, not via the Runner).
2. `ev_chargers` — seeded an EVSE900 row (max_power_kw 22) for the asset/twin view.
3. New files: `drivers/ocpp_csms/{__init__,driver,transport,models,sim,selftest}.py`,
   `drivers/ocpp_csms/devices.json`, `docker-compose-ocpp.yml`.

No existing service logic, schema, topic contract, or DERMS path was modified.
`ALLOWED_COMMANDS["ev_charger"]` already contained the needed commands.

---

## 6. Validation results

See **DIEP_PHASE9F_VALIDATION_REPORT.md**. Headline: host selftest all-green; live
telemetry + Timescale history (136+ rows) + Redis twin; start/set_limit/stop ACKED with
actuation visible; certification → **PRODUCTION_READY**; coexists with legacy EV001.

---

## 7. Remaining gaps

1. **Canonical schema lacks `session_energy_kwh`, `vehicle_soc`, `connector_status`** —
   published on MQTT but dropped at `/telemetry` (same 8-field-schema gap as 9C/9D).
   These are exactly the fields the schema-extension recommendation (9D report §6) would
   add (`vehicle_soc` overlaps battery `soh`/`state` rationale).
2. **OCPP 1.6 only; no 2.0.1, no security profiles.** No TLS on the WS (`ws://` not
   `wss://`), no OCPP Security Profile 1–3 auth — deferred to Phase 9J (TLS/auth).
3. **Minimal CSMS feature set.** Implements Boot/Heartbeat/Status/Start/Stop/MeterValues
   + RemoteStart/Stop/SetChargingProfile. Not implemented: smart-charging schedules over
   time, reservations, firmware update, local auth lists, multi-connector modelling.
4. **Built-in WebSocket/OCPP stack** (for zero-dependency runnability). Production should
   adopt `websockets` + the `ocpp` (mobilityhouse) library behind the same `transport.py`
   seam; vendors: ABB, Schneider, ChargePoint, Delta, Autel.
5. **Security & failover** certification tests remain `SKIPPED` pending Phase 9J / 9K.

---

## 8. Success criteria

✓ **EV Charger (OCPP)** integrated through the DIEP framework (EVSE900, PRODUCTION_READY),
alongside ✓ Smart Meter (MTR900), ✓ Solar Inverter (INV900), ✓ Battery (BAT900) — all
available to the platform's data plane, command bus, twin, onboarding and certification.

**Next-vertical recommendation (9G Microgrid): see validation report §6.**
