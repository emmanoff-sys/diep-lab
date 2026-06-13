# DIEP Phase 9C — Modbus Smart Meter Driver

> **Status:** Implemented and operational. Device **MTR900** is **PRODUCTION_READY**.
> Date: 2026-06-04 · Scope: first real metering vertical on the Phase 9 Driver SDK.
> **Reuses the SunSpec (9E) architecture and transport unchanged — no redesign.**

---

## 1. Summary

DIEP now integrates a **real Modbus smart meter** through the same edge Driver SDK
that powers the SunSpec inverter (9E). The meter publishes canonical telemetry to
`diep/smartmeter/MTR900`, accepts `read_only` / `remote_disconnect` / `remote_connect`
commands over the full Kafka → dispatcher → MQTT → ACK path, and has been driven
through onboarding to **certification (PRODUCTION_READY)**.

Two verticals are now live behind one SDK:

| Device | Type | Protocol | Driver | Status |
|--------|------|----------|--------|--------|
| INV900 | solar_inverter | SunSpec/Modbus | `sunspec` | PRODUCTION_READY |
| **MTR900** | **smartmeter** | **Modbus TCP** | **`modbus_meter`** | **PRODUCTION_READY** |

---

## 2. Architecture (reused, not redesigned)

```
[ Modbus meter / sim ]  --Modbus TCP-->  [ ModbusMeterDriver ]  --> [ Runner (SDK) ]
   holding registers          FC3 read         decode/normalize        publish + cmd/ack
   3000..3014                 FC16 write        canonical schema             |
                                                                              v
                                                       MQTT  diep/smartmeter/MTR900(/cmd,/ack)
                                                                              |
                          [ ingestor ] --HTTP--> [ FastAPI /telemetry ] --> TimescaleDB + Redis(twin)
                          [ API /commands ] --> Kafka --> [ dispatcher ] --> MQTT cmd --> driver
                                                              ^---------- MQTT ack <---------'
```

Reused verbatim from earlier phases:

- **`drivers/diep_driver/`** — `BaseDriver`, `Runner`, `normalize` (canonical schema),
  `registry`, `mqtt_client`. The meter driver subclasses `BaseDriver` and implements
  only `connect` / `read_telemetry` / `execute_command`.
- **`drivers/modbus_meter/transport.py`** — a thin re-export of the SunSpec
  `transport.py` (`open_modbus`, `ModbusTcpServer`). One Modbus transport for the whole
  edge; pymodbus on the gateway, built-in pure-socket client elsewhere.
- **Dispatcher / Kafka / MQTT / onboarding / certification** — untouched. The meter
  rides the same command bus and the same `device_onboarding` / `device_certifications`
  workflow built in Phase 9H/9I.

New code is confined to **`drivers/modbus_meter/`** plus two additive integration edits
(see §6).

### Why `domain = "smartmeter"`
The dispatcher maps `device_type → domain` via `DOMAIN_MAP`, falling back to the
`device_type` string when absent. `smartmeter` is not in `DOMAIN_MAP`, so the command
topic is `diep/smartmeter/<id>/cmd`. Setting the driver's `domain = "smartmeter"` makes
telemetry (`diep/smartmeter/<id>`) and commands line up **without editing the dispatcher**.

---

## 3. Protocol mapping (Modbus → DIEP canonical)

The driver reads one holding-register block, decodes it, and maps onto the platform's
canonical 8-field telemetry schema, adding meter-specific extras to the MQTT payload.

| Meter measurement | Canonical field | Mapping |
|-------------------|-----------------|---------|
| Phase voltage (V) | `voltage` | direct |
| Current (A) | `current` | direct |
| Active power (kW, signed) | `power_kw` | direct (+ = import) |
| Frequency (Hz) | `frequency` | direct |
| Active power split | `grid_import_kw` / `grid_export_kw` | `max(0, ±power_kw)` |
| — | `solar_kw`, `battery_soc` | `0.0` (not a meter quantity) |
| Power factor | *extra* `power_factor` | payload only (see Gaps) |
| Cumulative import (kWh) | *extra* `energy_import_kwh` | payload only |
| Cumulative export (kWh) | *extra* `energy_export_kwh` | payload only |
| Control relay (1/0) | *extra* `relay_state` | payload only |

**Observed canonical payload (MTR900, live):**
```json
{"device_id":"MTR900","device_type":"smartmeter","voltage":230.0,"current":15.53,
 "power_kw":3.5,"frequency":50.0,"power_factor":0.98,
 "energy_import_kwh":1000.0,"energy_export_kwh":200.0,"relay_state":1}
```

---

## 4. Register mapping (`models.py`)

Vendor register maps are expressed as **data**, so swapping in a Landis+Gyr / Itron /
Hexing / EDMI / Schneider map is a config change, not a code change. The reference
profile (IEEE-754 float32 measurements, big-endian, high word first):

| Address | Point | Type | Units |
|--------:|-------|------|-------|
| 3000 | voltage | float32 | V |
| 3002 | current | float32 | A |
| 3004 | power_kw | float32 | kW (signed) |
| 3006 | frequency | float32 | Hz |
| 3008 | power_factor | float32 | 0..1 |
| 3010 | energy_import_kwh | float32 | kWh |
| 3012 | energy_export_kwh | float32 | kWh |
| 3014 | relay_state | uint16 | 1=connected, 0=disconnected |

Read: FC3 over the 15-register block. Control: FC16 write to 3014 for the relay.

---

## 5. Command support

| Command | Effect | Transport | Validated |
|---------|--------|-----------|-----------|
| `read_only` | Latches the driver read-only; refuses subsequent actuation | API→Kafka→dispatcher→MQTT→ACK | ✓ |
| `remote_disconnect` | Writes relay register = 0; power/current collapse to 0 | same | ✓ ACKED |
| `remote_connect` | Writes relay register = 1; load restored | same | ✓ ACKED |

All commands are validated against `ALLOWED_COMMANDS["smartmeter"]` in FastAPI, written
to the `commands` audit table (PENDING → SENT/`dispatched_at` → ACKED/`acked_at`), and
mirrored to Redis. The dispatch/ack ordering is race-safe (the dispatched marker never
downgrades a terminal ACKED status — fixed in Phase 9E and confirmed here).

---

## 6. Integration changes (additive only)

1. `fastapi/app.py` — added `"smartmeter": {"read_only","remote_disconnect","remote_connect"}`
   to `ALLOWED_COMMANDS` (enables command validation + audit for meters).
2. `drivers/edge_agent.py` — added `import modbus_meter` so the driver registers.
3. New files: `drivers/modbus_meter/{__init__,driver,transport,models,sim,selftest}.py`,
   `drivers/modbus_meter/devices.json`, `docker-compose-meter.yml`.

No existing service logic, schema, or topic contract was modified.

---

## 7. Validation results

See **DIEP_PHASE9C_VALIDATION_REPORT.md** for evidence. Headline:

- Host selftest (`python -m modbus_meter.selftest`): **all checks green**.
- Live: telemetry in TimescaleDB (50+ rows), Redis twin updating, disconnect/reconnect
  ACKED with actuation visible in telemetry, certification → **PRODUCTION_READY**.

---

## 8. Remaining gaps

1. **Canonical schema lacks meter-native fields.** `power_factor`, `energy_import_kwh`,
   and `energy_export_kwh` are published on MQTT but dropped at `/telemetry` (the
   `TelemetryPayload` model and `telemetry` table carry only the 8 canonical fields), so
   they are **not persisted to TimescaleDB or the Redis twin**. Closing this needs an
   additive schema extension (new nullable columns + payload fields) — deferred to avoid
   touching the shared data plane in this phase.
2. **InfluxDB is provisioned but unwritten.** `INFLUX_CLIENT` is configured in
   `app.py` but nothing calls `.write()`. Telemetry history lives in TimescaleDB; "Influx
   telemetry" is not currently a real path. Recommend either wiring a meter-energy
   measurement into Influx or formally retiring the Influx dependency.
3. **Single vendor profile.** One representative float32 register map is implemented;
   real fleets need per-vendor maps (DLMS/COSEM meters are a separate driver, Phase 9C-DLMS).
4. **Word-order / endianness** is fixed to big-endian high-word-first; some meters use
   word-swapped float32. The map is data-driven but the swap is a one-line `models.py` toggle.
5. **Security & failover** certification tests remain `SKIPPED` pending Phase 9J (TLS/mTLS,
   API auth) and Phase 9K (HA) — identical posture to the SunSpec vertical.

---

## 9. Success criteria

✓ **Smart Meter** integrated through the Driver SDK Framework (MTR900, PRODUCTION_READY).
✓ **Solar Inverter** integrated through the same framework (INV900, PRODUCTION_READY).

Both verticals share `BaseDriver`, the canonical normalization framework, the Modbus
transport, MQTT, the dispatcher, and the onboarding/certification workflow.

**Next vertical recommendation: Phase 9D — Battery / BMS driver.** See the validation
report §6 for rationale and a concrete plan.
