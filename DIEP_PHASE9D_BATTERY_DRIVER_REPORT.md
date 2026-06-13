# DIEP Phase 9D — Battery / BMS Driver

> **Status:** Implemented and operational. Device **BAT900** is **PRODUCTION_READY**
> and DERMS-integrated. Date: 2026-06-05 · Scope: storage vertical on the Phase 9
> Driver SDK. **Reuses the SunSpec (9E) / meter (9C) architecture unchanged.**

---

## 1. Summary

DIEP now integrates a **real battery / BMS** through the same edge Driver SDK and
Modbus transport as the SunSpec inverter (9E) and the smart meter (9C). The battery
publishes canonical storage telemetry to `diep/battery/BAT900`, accepts
`charge` / `discharge` / `standby` / `idle` / `set_power_limit` / `set_soc_target`
over the full Kafka → dispatcher → MQTT → ACK path, is **actuated by DERMS**
(`/derms/battery_dispatch`), and has been certified to **PRODUCTION_READY**.

Three verticals now run behind one SDK:

| Device | Type | Protocol | Driver | Status |
|--------|------|----------|--------|--------|
| INV900 | solar_inverter | SunSpec/Modbus | `sunspec` | PRODUCTION_READY |
| MTR900 | smartmeter | Modbus TCP | `modbus_meter` | PRODUCTION_READY |
| **BAT900** | **battery** | **Modbus TCP** | **`battery_bms`** | **PRODUCTION_READY** |

---

## 2. Architecture (reused, not redesigned)

```
[ Battery BMS / sim ] --Modbus TCP--> [ BatteryBmsDriver ] --> [ Runner (SDK) ]
  holding regs 4000.. FC3 read/FC16 write  decode/normalize       publish + cmd/ack
                                                                         |
                                                  MQTT diep/battery/BAT900(/cmd,/ack)
                                                                         |
   [ ingestor ] --> [ FastAPI /telemetry ] --> TimescaleDB + Redis(twin)
   [ DERMS /derms/battery_dispatch ] --> create_command --> Kafka --> [ dispatcher ]
                                                              --> MQTT cmd --> driver
                                                  ^---------- MQTT ack <---------'
```

Reused verbatim: `diep_driver` SDK (`BaseDriver`, `Runner`, `normalize`, `registry`,
`mqtt_client`); the SunSpec **Modbus transport** (`transport.py` re-export); the
dispatcher, Kafka, MQTT, onboarding/certification workflow, the digital-twin
aggregation, and the **DERMS** dispatch path. New code is confined to
`drivers/battery_bms/` plus additive integration edits (§6).

`domain = "battery"` matches the dispatcher `DOMAIN_MAP` and the existing
`ALLOWED_COMMANDS["battery"]`, so DERMS (which already dispatches charge/discharge/idle
to batteries) actuates this driver with no DERMS change.

---

## 3. Canonical telemetry mapping

| BMS measurement | Canonical field | Notes |
|-----------------|-----------------|-------|
| State of charge (%) | `battery_soc` | direct |
| DC bus voltage (V) | `voltage` | ~700 V |
| Current (A) | `current` | magnitude |
| Active power (kW, signed) | `power_kw` | **− = charging, + = discharging** |
| Temperature (°C) | *extra* `temperature` | payload/twin only (schema gap) |
| State of health (%) | *extra* `soh` | payload only |
| Operating state | *extra* `state` / `mode` | STANDBY / CHARGING / DISCHARGING / FAULT |

**Sign convention:** `power_kw` is **negative for charging**, positive for discharging,
per the Phase 9D canonical example. This is the **opposite** of the legacy BAT001
simulator (+ = charging) — see §8 for the standardization recommendation.

**Observed canonical payload (BAT900, charging under DERMS):**
```json
{"device_id":"BAT900","device_type":"battery","battery_soc":75.08,"power_kw":-60.0,
 "voltage":700.0,"current":85.7,"temperature":30.4,"soh":98.0,"state":"CHARGING"}
```

---

## 4. Register mapping (`models.py`)

Vendor maps are expressed as **data** (swap in Huawei / BYD / Sungrow / Victron, or a
SunSpec storage model 802/803/124, without code change). Reference profile:

| Address | Point | Type | Access |
|--------:|-------|------|--------|
| 4000 | battery_soc | float32 | R |
| 4002 | voltage | float32 | R |
| 4004 | current | float32 | R |
| 4006 | power_kw (signed) | float32 | R |
| 4008 | temperature | float32 | R |
| 4010 | soh | float32 | R |
| 4012 | state (enum) | uint16 | R |
| 4013 | cmd_mode (0=standby,1=charge,2=discharge) | uint16 | **W** |
| 4014 | power_setpoint_kw | float32 | **W** |
| 4016 | target_soc | uint16 | **W** |
| 4017 | power_limit_kw | float32 | **W** |

Read: FC3 over the 19-register block. Control: FC16 writes to the control block.

---

## 5. Command mapping

| Command | Source | Control write | Validated |
|---------|--------|---------------|-----------|
| `charge` | task + **DERMS** | cmd_mode=1, power_setpoint, target_soc | ✓ ACKED |
| `discharge` | task + **DERMS** | cmd_mode=2, power_setpoint, target_soc | ✓ ACKED |
| `standby` | task | cmd_mode=0 | ✓ ACKED |
| `idle` | DERMS/legacy | cmd_mode=0 (alias of standby) | ✓ |
| `set_power_limit` | task | power_limit_kw | ✓ ACKED |
| `set_soc_target` | legacy | target_soc | ✓ |

DERMS passes `{target_soc, max_power_kw}` on charge/discharge; the driver accepts both
`max_power_kw` (DERMS) and `power_kw` (direct). All commands are validated against
`ALLOWED_COMMANDS["battery"]`, audited in the `commands` table (PENDING → SENT → ACKED),
and mirrored to Redis. The dispatch/ack ordering is race-safe (Phase 9E fix).

---

## 6. Integration changes (additive only)

1. `fastapi/app.py` — `ALLOWED_COMMANDS["battery"]` extended with `set_power_limit`,
   `standby` (existing `charge`/`discharge`/`set_soc_target`/`idle` retained → DERMS unaffected).
2. `drivers/edge_agent.py` — added `import battery_bms`.
3. `battery_assets` — seeded a BAT900 row (capacity_kwh 200) for the asset/twin view.
4. New files: `drivers/battery_bms/{__init__,driver,transport,models,sim,selftest}.py`,
   `drivers/battery_bms/devices.json`, `docker-compose-battery-edge.yml`.

**Filename note:** the compose file is `docker-compose-battery-edge.yml`, **not**
`docker-compose-battery.yml`, because the latter already exists and runs the legacy
BAT001 simulator — overwriting it would clobber a running service.

No existing service logic, schema, topic contract, or DERMS path was modified.

---

## 7. Validation results

See **DIEP_PHASE9D_VALIDATION_REPORT.md**. Headline: host selftest all-green; live
telemetry + Timescale history + Redis twin + fleet/asset views; charge/discharge/standby
ACKED with actuation visible; **DERMS dispatch → command → ACK → twin update** confirmed;
certification → **PRODUCTION_READY**.

---

## 8. Remaining gaps

1. **Canonical schema lacks `temperature` and `state`.** Confirmed live: the Redis twin
   shows `temperature: null`, `state: null` for BAT900 because `/telemetry` persists only
   the 8 canonical fields. SoC / power / voltage **do** reach the twin. This strengthens
   the schema-extension case (§ schema recommendation in the validation report).
2. **Power sign convention diverges from legacy BAT001** (− = charging here, + there).
   Recommend standardizing platform-wide (see validation report).
3. **Single vendor profile / no real SunSpec storage model parsing yet** — the reference
   map is representative; production fleets need per-vendor maps. SunSpec storage model
   802 decode is a natural reuse of the 9E model machinery.
4. **Tesla Powerwall** has no open local Modbus/SunSpec parity — best-effort via its
   changing local API only (flagged in the Phase 9 plan §8).
5. **Security & failover** certification tests remain `SKIPPED` pending Phase 9J / 9K.

---

## 9. Success criteria

✓ **Battery** integrated through the Driver SDK Framework (BAT900, PRODUCTION_READY),
**available to DERMS** (verified via `/derms/battery_dispatch`).
✓ **Smart Meter** (MTR900) and ✓ **Solar Inverter** (INV900) likewise certified.

All three share `BaseDriver`, the canonical normalization framework, the Modbus
transport, MQTT, the dispatcher, onboarding/certification, and the digital twin.

**Next-vertical recommendations (9F OCPP, 9G microgrid): see validation report §7.**
