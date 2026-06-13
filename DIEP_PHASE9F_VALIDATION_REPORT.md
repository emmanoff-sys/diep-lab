# DIEP Phase 9F — Validation Report (EV Charger / OCPP, EVSE900)

> Date: 2026-06-05 · Device: **EVSE900** (`ev_charger`, OCPP 1.6J) ·
> Result: **PRODUCTION_READY**. Companion to `DIEP_PHASE9F_OCPP_CHARGER_REPORT.md`.

---

## 1. Environment

- CSMS `drivers/ocpp_csms/` (WebSocket server + MQTT bridge) + an in-container OCPP
  charge-point simulator; container `diep-ocpp-csms` on `diep-lab_diep-net`.
- CSMS listens on `ws://0.0.0.0:9000`; charge point dials `ws://…:9000/EVSE900`.
- Telemetry `diep/charger/EVSE900`; command/ack `…/cmd`, `…/ack`.

---

## 2. Host selftest (no broker, no deps)

`python -m ocpp_csms.selftest` → **SELFTEST PASSED — all checks green** (14 checks):
WebSocket handshake + charge-point registration, MeterValues → canonical (voltage,
extras), idle power 0, `start_charging`→RemoteStart (power>0, connector Charging),
`set_limit`→SetChargingProfile (power capped ≤5 kW), `stop_charging`→RemoteStop (power 0),
plus failure cases (missing param, unknown command, command to an absent charger).

---

## 3. Required demonstrations (live)

| # | Requirement | Evidence | Result |
|---|-------------|----------|--------|
| 1 | Live telemetry | ingestor `Ingested diep/charger/EVSE900` ; 136+ Timescale rows | ✓ |
| 2 | Charge command | `start_charging` → RemoteStart → `power_kw=13.45`, ACKED | ✓ |
| 3 | Set-limit command | `set_limit 5kW` → SetChargingProfile → `power_kw=3.16`, ACKED | ✓ |
| 4 | Stop command | `stop_charging` → RemoteStop → `power_kw=0`, ACKED | ✓ |
| 5 | Twin updates | `/state/EVSE900` power/voltage/grid_import/last_seen update live | ✓ (canonical) |
| 6 | Certification workflow | enroll→validate→certify→approve → **PRODUCTION_READY** | ✓ |

**Command audit trail (`commands`, EVSE900):**
```
start_charging | ACKED | phase9f
set_limit      | ACKED | phase9f
stop_charging  | ACKED | phase9f
```

**Full command chain (item 2-4), end to end:**
```
POST /commands {device_id:EVSE900, command_type:start_charging, params:{max_power_kw:22}}
  -> Kafka -> dispatcher -> diep/charger/EVSE900/cmd
  -> CSMS bridge -> OCPP RemoteStartTransaction (CALL over WebSocket)
  -> charge point: begin session, StatusNotification(Charging), StartTransaction
  -> CALLRESULT {status: Accepted} -> ack -> command ACKED
  -> MeterValues -> telemetry power_kw 13.45 -> twin update
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
| TimescaleDB (`telemetry`) | ✓ | 136+ EVSE900 rows (canonical 8 fields) |
| Redis twin (`current_state`) | ✓ | `/state/EVSE900` power/voltage/grid_import/last_command |
| Asset view (`/assets/EVSE900`) | ✓ | `asset_metadata.max_power_kw = 22` (ev_chargers) |
| Fleet view (`/fleet/overview`) | ✓ | `ev_charger: {ONLINE: 2}` (EV001 + EVSE900) |
| InfluxDB | ✗ | no `.write()` path (same as 9C/9D) |

Extras `session_energy_kwh`, `vehicle_soc`, `connector_status` reach MQTT but not the
twin/Timescale (no canonical column) — see driver report §7.

**Coexistence check:** the legacy MQTT-native EV001 charger and the OCPP EVSE900 both
publish telemetry and accept commands independently; the CSMS bridge ignores commands for
chargers not connected to it, so there is no double-ack.

---

## 5. Success criteria

✓ Certified devices integrated through the DIEP framework:
```
INV900   sunspec    PRODUCTION_READY
MTR900   modbus     PRODUCTION_READY
BAT900   modbus     PRODUCTION_READY   (DERMS-dispatchable)
EVSE900  ocpp1.6j   PRODUCTION_READY
```
Smart Meter ✓ · Solar Inverter ✓ · Battery ✓ · **EV Charger ✓**.

---

## 6. Next-vertical recommendation — Phase 9G (Microgrid Controller)

9G is the **last and largest** Wave-2/3 vertical, and it is qualitatively harder than the
four built so far. Recommendation: **do the foundational work first, then sequence 9G in
two stages.**

**Do these before/alongside 9G:**
1. **Schema extension (deferred since 9C).** Four phases have now produced orphaned fields
   (`power_factor`, energy counters, `temperature`, `soh`, `state`, `session_energy_kwh`,
   `vehicle_soc`, `connector_status`). Microgrid adds more (per-feeder flows, breaker
   states). Land the additive `telemetry` columns + `TelemetryPayload`/ingestor/twin
   pass-through (proposed in the 9D report §6) so 9G telemetry is first-class.
2. **Security baseline (9J).** Microgrid control is **safety-critical** (islanding,
   breaker operations). TLS + auth on MQTT/API and the broker should precede field actuation.

**Then build 9G in two stages by protocol risk:**
- **9G-a — IEC 60870-5-104 (tractable, do first).** IEC-104 is a pollable TCP master/slave
  protocol — close to the Modbus model. Reuse the SDK poll `Runner` + a new `iec104`
  transport; map measured values (M_ME) → canonical, and commands
  (`island`/`grid_connect`/`set_setpoint`, already in `ALLOWED_COMMANDS["microgrid"]`) →
  single/double commands (C_SC/C_DC). A `c104`-style sim makes it hardware-free, like 9C/9D.
- **9G-b — IEC 61850 (MMS/GOOSE, highest effort/risk).** Needs heavyweight tooling
  (libiec61850) and models substations/IEDs (logical nodes, datasets, reports). Treat as
  its own sub-project after 9G-a; GOOSE is real-time/safety-critical and likely out of
  scope for a lab simulator.

**Rationale for order:** the EV/OCPP work just proved the framework can absorb a
fundamentally different transport (event-driven server) without disturbing the data plane,
DERMS, or onboarding. 9G-a (IEC-104) returns to the *polling* shape and is low-risk reuse;
9G-b (61850) is the genuine frontier and benefits most from the schema + security
groundwork. A microgrid simulator already runs in the stack, so 9G-a can be validated
end-to-end immediately once the IEC-104 transport exists.

**Also recommended (cross-cutting, post-9G):** revisit **OCPP 2.0.1** and **wss:// +
OCPP Security Profiles** as part of 9J, and decide InfluxDB's role (still provisioned but
unwritten across all four verticals).
