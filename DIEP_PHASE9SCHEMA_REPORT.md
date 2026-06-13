# DIEP Phase 9-Schema — Canonical Telemetry Extension

> **Status:** Implemented and verified across all five verticals. Date: 2026-06-06.
> Additive + nullable — zero breakage; legacy devices keep ingesting. Closes the gap
> flagged in every device phase (9C–9G) and recommended in the 9D report §6.

---

## 1. The gap (and why it mattered)

The Phase 9C–9G drivers publish device-class fields on MQTT, but `/telemetry` only persisted
the **8 canonical fields** — so these were **dropped** before TimescaleDB and the digital
twin (confirmed live in 9D: `BAT900` twin showed `temperature: null`, `state: null`). Across
five verticals the orphaned fields were:

| Vertical | Orphaned fields |
|----------|-----------------|
| 9C meter | power_factor, energy_import_kwh, energy_export_kwh |
| 9D battery | temperature, soh, state |
| 9F charger | session_energy_kwh, vehicle_soc, connector_status |
| 9G microgrid | load_kw, setpoint_kw, grid_connected, mode |

---

## 2. What changed (additive, backward-compatible)

- **`sql/009_schema_extension.sql`** — `ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS` for
  six broadly-useful typed metrics (all nullable): `power_factor`, `energy_import_kwh`,
  `energy_export_kwh`, `temperature`, `soh`, `state`. The device-specific long tail reuses
  the existing (previously unused) **`telemetry.metadata` JSONB** column. Wired into `init-db.sh`.
- **`fastapi/app.py`** — `TelemetryPayload` gains the six optional typed fields + an `extra`
  dict; `/telemetry` INSERT writes the typed columns + `metadata` (the extra JSONB);
  `_persist_state` mirrors all of them to the Redis twin.
- **`ingestor/telemetry_ingestor.py`** — `normalize()` forwards the typed extended fields and
  collects the device-specific long tail into `extra` (→ `metadata`).

No driver changes — the drivers already publish these fields; the pipeline now accepts them.

**Design choice:** typed columns for the common, queryable/Grafana-friendly metrics; JSONB
`metadata` for the per-device long tail (no per-vertical schema churn).

---

## 3. Verification (live)

| Vertical | Evidence (latest row) |
|----------|----------------------|
| Battery (BAT900) | `temperature=29.2, soh=98.0, state=CHARGING` (typed columns) |
| Meter (MTR900) | `power_factor=0.980, energy_import_kwh=1003.60, energy_export_kwh=200.00` |
| Charger (EVSE900) | `metadata = {vehicle_soc:35.0, connector_status:"Available", session_energy_kwh:0.0}` |
| Microgrid (MGC900) | `metadata = {mode:"grid_connected", load_kw:20.44, setpoint_kw:0.0, grid_connected:true}` |
| **Twin gap closed** | `/state/BAT900` now returns `temperature:29.2, soh:98.0, state:"CHARGING"` (was null in 9D) |

**No breakage:** 5/5 verticals PRODUCTION_READY; 0 ingestor errors; legacy devices (which
don't send extended fields) ingest fine with NULL extended columns; 36 telemetry rows in the
last 20 s.

---

## 4. Remaining / follow-ups

- **Grafana/analytics** can now chart power_factor, energy, temperature, SoH, etc.; dashboards
  to be added in observability (Phase 10C).
- **Digital-twin headline metrics** could surface the new fields per device type (a small
  `digitaltwin/app.py` `HEADLINE_METRICS` addition) — cosmetic, deferred.
- **InfluxDB** is still write-unused (the recurring finding) — wire a measurement or retire
  it as part of **Phase 9-Data** (next: retention, continuous aggregates, backups/PITR).

---

## 5. Result

Every field the five drivers produce is now first-class: queryable typed columns for the
common metrics, JSONB for the long tail, and all of it visible in the digital twin. The
canonical contract is complete for the current device fleet — additively, with no migration
risk and no driver changes.
