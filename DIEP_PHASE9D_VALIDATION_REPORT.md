# DIEP Phase 9D — Validation Report (Battery / BMS, BAT900)

> Date: 2026-06-05 · Device: **BAT900** (`battery`, protocol `battery_bms`) ·
> Result: **PRODUCTION_READY**, DERMS-integrated. Companion to
> `DIEP_PHASE9D_BATTERY_DRIVER_REPORT.md`.

---

## 1. Environment

- Driver `drivers/battery_bms/` on the Phase 9 Driver SDK; in-container Modbus-TCP
  battery simulator (`battery_bms.sim`, 200 kWh, SoC 75%) + edge agent; container
  `diep-battery-edge` on `diep-lab_diep-net`.
- Telemetry `diep/battery/BAT900`; command/ack `…/cmd`, `…/ack`.

---

## 2. Host selftest

`python -m battery_bms.selftest` → **SELFTEST PASSED — all checks green** (21 checks):
connect/decode, canonical + extras, 700 V, STANDBY at rest, charge (−power / CHARGING /
SoC↑), discharge (+power / DISCHARGING / SoC↓), set_power_limit cap (≤10 kW), standby
(0 kW), DERMS-shaped `charge {target_soc, max_power_kw}` accepted, validation failures.

---

## 3. Required demonstrations (live)

| # | Requirement | Evidence | Result |
|---|-------------|----------|--------|
| 1 | Live telemetry | `diep/battery/BAT900` → Timescale: SoC 75, V 700; 58+ rows | ✓ |
| 2 | Charge command | `power_kw=-40`, state CHARGING, ACKED | ✓ |
| 3 | Discharge command | `power_kw=+40`, state DISCHARGING, ACKED | ✓ |
| 4 | Standby command | `power_kw=0`, SoC settled 75.000, ACKED | ✓ |
| 5 | Twin updates | `/state/BAT900` battery_soc/power_kw/last_command update live | ✓ (canonical fields) |
| 6 | DERMS dispatch | `/derms/battery_dispatch` → charge → ACK → twin SoC↑ | ✓ |
| 7 | Certification workflow | enroll→validate→certify→approve → **PRODUCTION_READY** | ✓ |

**Command audit trail (`commands`, BAT900):**
```
charge     | ACKED | phase9d
discharge  | ACKED | phase9d
standby    | ACKED | phase9d
charge     | ACKED | derms      <-- DERMS-issued
```

**DERMS chain (item 6), end to end:**
```
POST /derms/battery_dispatch {device_id:BAT900, target_soc:90, max_power_kw:60}
  -> DERMS recommendation: SoC 75 < 90  => command_type = charge
  -> create_command -> Kafka -> dispatcher -> diep/battery/BAT900/cmd
  -> driver: control write mode=1 power=60 target_soc=90
  -> ack -> command ACKED (issued_by=derms)
  -> twin: battery_soc 75.083 (rising), power_kw -60.0, last_command_status ACKED
```

**Certification result:**
```
certified: True   failed: []   pending: []
connectivity PASS · telemetry PASS · command PASS · ack PASS · failover SKIPPED · security SKIPPED
```

---

## 4. Data-plane verification matrix

| Store / view | Written? | Evidence |
|--------------|----------|----------|
| TimescaleDB (`telemetry`) | ✓ | 58+ BAT900 rows (canonical 8 fields) |
| Redis twin (`current_state`) | ✓ | `/state/BAT900` soc/power/voltage/last_command |
| Asset view (`/assets/BAT900`) | ✓ | `asset_metadata.capacity_kwh = 200` (battery_assets) |
| Fleet view (`/fleet/overview`) | ✓ | `battery: {ONLINE: 2}` (BAT001 + BAT900) |
| InfluxDB | ✗ | no `.write()` path in platform (same as 9C) |

Extras `temperature`, `soh`, `state` reach MQTT but **not** the twin/Timescale (no
canonical column) — see §6.

---

## 5. Success criteria

✓ Certified devices: **Smart Meter** (MTR900), **Solar Inverter** (INV900), **Battery**
(BAT900) — all integrated through the Driver SDK Framework and **available to DERMS**:
```
INV900  sunspec  PRODUCTION_READY
MTR900  modbus   PRODUCTION_READY
BAT900  modbus   PRODUCTION_READY   (DERMS-dispatchable)
```

---

## 6. Optional schema-extension evaluation (recommendation only — schema NOT modified)

**Finding.** Three phases have now surfaced device-native fields with no home in the
canonical 8-field schema (`voltage, current, power_kw, frequency, solar_kw, battery_soc,
grid_import_kw, grid_export_kw`):

| Phase | Device | Orphaned fields | Where they currently live |
|-------|--------|-----------------|---------------------------|
| 9C meter | MTR900 | `power_factor`, `energy_import_kwh`, `energy_export_kwh` | MQTT payload only |
| 9D battery | BAT900 | `temperature`, `soh`, `state` | MQTT payload only |

These are dropped at `FastAPI /telemetry` (the `TelemetryPayload` model and `telemetry`
hypertable carry only the 8 fields), so they reach **neither TimescaleDB nor the Redis
twin** — confirmed live (`/state/BAT900` shows `temperature: null`, `state: null`).

**Recommendation: extend the canonical schema — but as a deliberate, backward-compatible
change in its own phase (suggest 9J-adjacent or a dedicated 9-Schema task), not inline.**

Proposed shape (additive, all nullable — no breakage to existing devices/queries):

```
ALTER TABLE telemetry
  ADD COLUMN power_factor      double precision,   -- meters
  ADD COLUMN energy_import_kwh double precision,   -- meters
  ADD COLUMN energy_export_kwh double precision,   -- meters
  ADD COLUMN temperature_c     double precision,   -- battery / thermal
  ADD COLUMN soh_pct           double precision,   -- battery
  ADD COLUMN state             varchar(20);        -- device operating state
```
plus matching optional fields on `TelemetryPayload` and pass-through in `_persist_state`
(twin) and the ingestor `normalize()`.

**Why not now:** the directive is "do not modify schema yet — recommendation only," and a
shared-hypertable migration deserves its own change window with the DB-drift reconcile
step (`init-db.sh`). Until then, the canonical fields fully cover DERMS and control needs;
the extras are diagnostic and are preserved on the MQTT bus.

**Secondary recommendation — standardize the battery power sign.** BAT900 uses
`− = charging` (per the 9D spec) while legacy BAT001 uses `+ = charging`. Pick one
platform-wide (recommend `+ = charging/import` to match the meter/grid `grid_import`
convention) and align both the simulator and any consumers in the same schema phase.

**Tertiary — decide InfluxDB's role.** `INFLUX_CLIENT` is configured but never written.
Either wire a time-series measurement (e.g. high-rate energy) or retire the dependency;
today TimescaleDB is the sole telemetry store.

---

## 7. Next-vertical recommendations

Two verticals remain in Wave 2/3. They differ fundamentally from the three polling
Modbus drivers built so far, so sequencing matters.

### Phase 9F — EV Charger (OCPP) — **higher build effort, do with eyes open**
- **Architecturally different: OCPP is a *server* role, not a poller.** Chargers dial
  **inbound** over WebSocket to a Central System (CSMS). The driver is a long-lived
  **CSMS service**, not a `connect()/read_telemetry()` loop. The `BaseDriver` polling
  contract does **not** fit directly.
- **Plan:** build a small OCPP 1.6J CSMS (WebSocket server) that (a) maps inbound
  `MeterValues`/`StatusNotification` → canonical telemetry on `diep/charger/<id>`, and
  (b) maps `start_charging`/`stop_charging`/`set_limit` (already in
  `ALLOWED_COMMANDS["ev_charger"]`) → OCPP `RemoteStartTransaction` /
  `RemoteStopTransaction` / `SetChargingProfile`. Reuse the SDK's `normalize`, MQTT
  publish, and the dispatcher/ack/onboarding plumbing; replace only the transport.
- **Reuse:** canonical schema, MQTT, dispatcher, onboarding/certification — yes.
  Transport/SDK polling base — **no** (needs an event-driven CSMS host).
- An EV charger simulator that opens an OCPP WebSocket and sends MeterValues lets this be
  validated with no hardware, like the Modbus sims.

### Phase 9G — Microgrid Controller (IEC 60870-5-104 / IEC 61850) — **highest effort/risk**
- IEC-104 is a pollable client (closer to the Modbus model and tractable to reuse the
  SDK loop); **IEC 61850 MMS/GOOSE** needs heavyweight tooling (libiec61850) and is
  safety-critical. `ALLOWED_COMMANDS["microgrid"]` (`island`/`grid_connect`/`set_setpoint`)
  already exists and a microgrid simulator is running.

**Recommended order: 9F (EV/OCPP) next, then 9G (microgrid).** OCPP unlocks a distinct,
high-value device class (EV/smart-city) and, once the CSMS pattern exists, it generalizes
to other inbound-connection devices. 9G is the larger lift and benefits from doing the
schema-extension and security (9J) work first, given its safety-critical surface.
