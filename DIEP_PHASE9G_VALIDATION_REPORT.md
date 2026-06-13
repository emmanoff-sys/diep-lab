# DIEP Phase 9G — Validation Report (Microgrid Controller / IEC-104, MGC900)

> Date: 2026-06-05 · Device: **MGC900** (`microgrid`, IEC 60870-5-104) ·
> Result: **PRODUCTION_READY**. Companion to `DIEP_PHASE9G_MICROGRID_REPORT.md`.
> Includes the **Phase 9 device-integration program wrap-up** (§5–6).

---

## 1. Environment

- Driver `drivers/microgrid_iec104/` on the Phase 9 Driver SDK (polling Runner); an
  in-container IEC-104 RTU simulator + edge agent; container `diep-microgrid-edge` on
  `diep-lab_diep-net`.
- RTU listens IEC-104/TCP `:2404` (CA=1); telemetry `diep/microgrid/MGC900`.

---

## 2. Host selftest (no broker, no deps)

`python -m microgrid_iec104.selftest` → **SELFTEST PASSED — all checks green** (15 checks):
STARTDT connect + interrogation telemetry, canonical + extras, frequency ~50 Hz,
starts grid-connected, `set_setpoint`→PCC tracks 12.5 kW, `island`→PCC 0 + frequency
off-nominal (droop), `grid_connect`→PCC restored, plus failure cases.

---

## 3. Required demonstrations (live)

| # | Requirement | Evidence | Result |
|---|-------------|----------|--------|
| 1 | Live telemetry | `diep/microgrid/MGC900` → Timescale; 34+ rows, freq ~50, solar varying | ✓ |
| 2 | Set-setpoint | `set_setpoint 10` → `power_kw=10.0`, ACKED (C_SE) | ✓ |
| 3 | Island | `island` → `power_kw=0`, frequency 50.43 (off-nominal droop), breaker OPEN, ACKED | ✓ |
| 4 | Grid-connect | `grid_connect` → `power_kw=10.0`, freq 50.01, breaker CLOSED, ACKED | ✓ |
| 5 | Twin updates | `/state/MGC900` frequency/power/solar/last_command update live | ✓ (canonical) |
| 6 | Certification | enroll→validate→certify→approve → **PRODUCTION_READY** | ✓ |

**Command audit trail (`commands`, MGC900):**
```
set_setpoint | ACKED | phase9g
island       | ACKED | phase9g
grid_connect | ACKED | phase9g
```

**Islanding behaviour (item 3):** issuing `island` opened the PCC breaker (C_SC) → PCC
collapsed to 0 kW and the frequency left nominal (50.43 Hz) as the islanded grid's residual
imbalance bent it via droop; `grid_connect` reclosed the breaker and PCC returned to the
10 kW setpoint with frequency back at ~50 Hz.

**Certification result:**
```
certified: True   failed: []   pending: []
connectivity PASS · telemetry PASS · command PASS · ack PASS · failover SKIPPED · security SKIPPED
```

---

## 4. Data-plane verification matrix

| Store / view | Written? | Evidence |
|--------------|----------|----------|
| TimescaleDB (`telemetry`) | ✓ | 34+ MGC900 rows (canonical 8 fields) |
| Redis twin (`current_state`) | ✓ | `/state/MGC900` freq/power/solar/last_command |
| Fleet view (`/fleet/overview`) | ✓ | `microgrid: {ONLINE: 2}` (MG001 + MGC900) |
| InfluxDB | ✗ | no `.write()` path (unchanged across all verticals) |

Extras `load_kw`, `setpoint_kw`, `grid_connected`/`mode` reach MQTT but not the
twin/Timescale (no canonical column) — see driver report §7.

---

## 5. Phase 9 device-integration — program wrap-up

Five real protocol verticals are now certified and live behind one Driver SDK Framework,
spanning **three fundamentally different transport models**:

| Vertical | Device | Protocol | Transport model | New transport built |
|----------|--------|----------|-----------------|---------------------|
| 9E | INV900 | SunSpec/Modbus | poll | Modbus TCP (built-in/pymodbus) |
| 9C | MTR900 | Modbus | poll | (reused 9E) |
| 9D | BAT900 | Modbus | poll | (reused 9E) — DERMS-dispatchable |
| 9F | EVSE900 | OCPP 1.6J | event-driven WebSocket **server** (CSMS) | WebSocket + OCPP-J |
| 9G-a | MGC900 | IEC 60870-5-104 | poll (SCADA master) | IEC-104 APCI/ASDU |

```
INV900   sunspec          PRODUCTION_READY
MTR900   modbus           PRODUCTION_READY
BAT900   modbus           PRODUCTION_READY   (DERMS-dispatchable)
EVSE900  ocpp1.6j         PRODUCTION_READY
MGC900   iec60870-5-104   PRODUCTION_READY
```

**What the program proved:** the SDK's canonical contract, MQTT plane, dispatcher/ack bus,
onboarding, certification, twin, and DERMS absorb radically different field protocols by
swapping only the transport + register/message map — including a non-polling, inbound-
connection server role (OCPP). Each vertical ships a dependency-free simulator and an
all-green host selftest, so the whole fleet is reproducible with no field hardware.

---

## 6. Recommendations (program-level, in priority order)

1. **Phase 9G-b — IEC 61850 (MMS/GOOSE).** The remaining microgrid protocol; substation/IED
   modelling (logical nodes, datasets, reports, GOOSE). Needs heavyweight tooling
   (libiec61850) and is real-time/safety-critical — its own sub-project, sequenced **after**
   security (9J). Not a lab-simulator-friendly target the way IEC-104 was.
2. **Canonical schema extension (deferred since 9C; reinforced every phase since).**
   Orphaned device-native fields now span all five verticals: `power_factor`,
   `energy_import/export_kwh` (meter); `temperature`, `soh`, `state` (battery);
   `session_energy_kwh`, `vehicle_soc`, `connector_status` (charger); `load_kw`,
   `setpoint_kw`, `grid_connected`/`mode` (microgrid). Land the additive, nullable
   `telemetry` columns + `TelemetryPayload`/ingestor/twin pass-through proposed in the 9D
   report §6, in its own change window (with the `init-db.sh` drift-reconcile step).
3. **Phase 9J — Security baseline.** No TLS/auth anywhere (MQTT plaintext, `ws://` for OCPP,
   no API auth, hardcoded creds). This now gates real field deployment of **all** verticals,
   and is a hard prerequisite for microgrid breaker/islanding control. Highest priority
   before any non-simulated device.
4. **Phase 9K — High availability.** Every service is single-node; the certification
   `failover` test is honestly SKIPPED across all five verticals. Needed for production SLAs.
5. **InfluxDB decision.** Provisioned but never written across the entire program — either
   wire a measurement (e.g. high-rate energy) or retire the dependency. TimescaleDB is the
   sole telemetry store today.
6. **OCPP 2.0.1 + Security Profiles** and **IEC-104 full window/timeout state machine** are
   per-vertical hardening items to fold into 9J / productionization.

**Recommended next action:** Phase **9J (security)** — it unblocks field deployment of the
five certified verticals and is the safety prerequisite for microgrid control — followed by
the **schema extension** (cheap, high-leverage, unblocks first-class telemetry for every
device), then **9G-b** and **9K**.
