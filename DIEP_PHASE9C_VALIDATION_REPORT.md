# DIEP Phase 9C — Validation Report (Modbus Smart Meter, MTR900)

> Date: 2026-06-04 · Device: **MTR900** (`smartmeter`, protocol `modbus_meter`) ·
> Result: **PRODUCTION_READY**. Companion to `DIEP_PHASE9C_MODBUS_METER_REPORT.md`.

---

## 1. Environment

- Driver: `drivers/modbus_meter/` on the Phase 9 Driver SDK.
- Endpoint: in-container Modbus-TCP meter simulator (`modbus_meter.sim`) + edge agent,
  container `diep-meter-edge` on network `diep-lab_diep-net`.
- Telemetry topic `diep/smartmeter/MTR900`; command/ack `…/cmd`, `…/ack`.
- Stack: MQTT (Mosquitto), ingestor, FastAPI, TimescaleDB, Redis, Kafka, dispatcher.

---

## 2. Host selftest (no broker, no hardware)

`python -m modbus_meter.selftest` → **SELFTEST PASSED — all checks green** (17 checks):
connect + decode, canonical fields, meter extras, V≈230, Hz≈50, power>0, import mirrors
power, PF≈0.98, energy accumulation, remote_disconnect (power→0, relay=0),
remote_connect (power restored, relay=1), read_only latch refuses actuation, unknown
command rejected.

---

## 3. Required demonstrations (live)

| # | Requirement | Evidence | Result |
|---|-------------|----------|--------|
| 1 | Meter telemetry arriving | ingestor: `Ingested diep/smartmeter/MTR900 -> MTR900 (power_kw=4.058)` | ✓ |
| 2 | Meter twin updating | `GET /state/MTR900` live_state `{power_kw:3.298, voltage:230, frequency:50, last_seen:…}` | ✓ |
| 3 | Meter history stored | TimescaleDB `telemetry` — 50+ rows, e.g. `23:48:06 power_kw=4.058 V=230 Hz=50` | ✓ (TimescaleDB) |
| 4 | Remote disconnect | command ACKED; driver `relay -> DISCONNECTED`; telemetry `power_kw=0.000, voltage=0` | ✓ |
| 5 | Remote reconnect | command ACKED; telemetry `power_kw=2.015, voltage=230` | ✓ |
| 6 | ACK processing | both commands: `status=ACKED`, `dispatched_at` and `acked_at` set | ✓ |
| 7 | Certification workflow | enroll→validate→certify→approve → **PRODUCTION_READY** | ✓ |

**Command audit trail (`commands` table, MTR900):**
```
remote_disconnect | ACKED | phase9c-test
remote_connect    | ACKED | phase9c-test
```

**Certification result (`/onboarding/MTR900/certify`):**
```
certified: True   failed: []   pending: []
connectivity PASS · telemetry PASS · command PASS · ack PASS · failover SKIPPED · security SKIPPED
```
`failover`/`security` are honestly **SKIPPED** (deferred to Phase 9K HA / 9J security),
not falsely passed.

---

## 4. Data-plane verification matrix

| Store | Written? | Evidence | Notes |
|-------|----------|----------|-------|
| TimescaleDB (`telemetry`) | ✓ | 50+ MTR900 rows | canonical 8 fields |
| Redis (twin `current_state`) | ✓ | `/state/MTR900`, `/assets/MTR900.current_state` | drives the digital twin |
| InfluxDB | ✗ | no `.write()` path in platform | **gap** — see report §8 |

Meter extras (`power_factor`, `energy_*_kwh`) are present on MQTT but not persisted
(canonical schema has no column) — see report §8.1.

---

## 5. Success criteria

✓ DIEP supports **Smart Meter** (MTR900) and **Solar Inverter** (INV900), both integrated
through the Driver SDK Framework, both PRODUCTION_READY:
```
INV900  sunspec  PRODUCTION_READY
MTR900  modbus   PRODUCTION_READY
```

---

## 6. Recommendation — next vertical: Phase 9D (Battery / BMS)

**Why battery next:** it is the highest-leverage remaining vertical and the cheapest to
build on what now exists.

- **Maximum reuse, minimal new risk.** Most utility/C&I batteries speak **Modbus TCP or
  SunSpec** (storage models 802/803/124). The transport, SDK, MQTT, dispatcher, and
  onboarding/certification are already proven by 9E + 9C. A battery driver is largely a
  new register map + the storage-model decode the SunSpec driver already stubs for
  `battery_soc` (model 802).
- **Canonical fit is clean.** `battery_soc` and `power_kw` (signed: charge/discharge) are
  already first-class canonical fields and already surface in the twin — unlike the meter's
  energy/PF, no schema gap.
- **Commands are well-scoped and already in `ALLOWED_COMMANDS["battery"]`**:
  `charge`, `discharge`, `set_soc_target`, `idle` → map to SunSpec storage controls
  (`StorCtl_Mod`, `InWRte`/`OutWRte`, `MinRsvPct`) or vendor Modbus holding registers.
- **Unlocks DERMS.** A real, certified battery lets the existing DERMS battery-dispatch /
  peak-shaving / demand-response paths actuate a real device instead of a simulator —
  the natural next integration milestone.

**Suggested 9D plan (mirrors 9C/9E):**
1. `drivers/modbus_battery/` — `models.py` (SunSpec storage model 802/803 **or** a vendor
   Modbus map: SoC, SoH, DC/AC power, charge/discharge limits), reuse `transport.py`.
2. `driver.py` — `domain = "battery"`; decode SoC/power; `execute_command` for
   charge/discharge/set_soc_target/idle via storage-control registers.
3. `sim.py` — battery Modbus endpoint with an SoC integrator that responds to commands.
4. `selftest.py`, `devices.json`, `docker-compose-battery-edge.yml`.
5. Deploy **BAT900**, register, run a DERMS dispatch through it, onboard → certify →
   PRODUCTION_READY.
6. Reports: `DIEP_PHASE9D_BATTERY_REPORT.md`, `DIEP_PHASE9D_VALIDATION_REPORT.md`.

**Risk note:** vendor diversity is higher than meters (Huawei/BYD/Sungrow/Victron via
Modbus/SunSpec are tractable; **Tesla Powerwall** has no open local Modbus/SunSpec parity
and should be treated as best-effort via its changing local API — flagged in the Phase 9
plan §8).
