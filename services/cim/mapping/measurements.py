"""Maps `telemetry` rows to Measurement (the type definition) and
MeasurementValue (an actual reading) -- the "no information loss" module.

Every MeasurementValue carries the original (rawValue, rawUnit) alongside
any CIM-base-unit conversion (value, unitSymbol, unitMultiplier), and the
exact quality/estimated/timestamp/correlation_id from the source row's
metadata -- nothing here re-interprets or discards what MDM/the ingestor
already determined. `metadata.quality`'s keys are the authoritative "what
was actually measured" signal (set per envelope_to_legacy_body() for every
measurement present in that reading, not just the always-present flat
columns, which default to 0.0 when a device doesn't report a field) --
Measurement/MeasurementValue are built from those keys, not from
nonzero-column guessing.

`telemetry` has no `tenant_id` column (confirmed against every migration
that's touched this table) -- tenant scoping joins through
`devices.tenant_id`, never `metadata->>'tenant_id'` (operator-set,
unindexed, and a possible source of disagreement -- see LIMITATIONS.md).
"""
from __future__ import annotations

from .. import db, identifiers, units
from ..models import Measurement, MeasurementValue

# measurement_type -> canonical unit lives in units.py (MEASUREMENT_TYPE_UNITS)
# now, alongside the unit-conversion table itself -- single source of truth,
# not duplicated here.

_TELEMETRY_SELECT = (
    "SELECT t.time, t.device_id, t.voltage, t.current, t.power_kw, t.frequency, "
    "t.solar_kw, t.battery_soc, t.grid_import_kw, t.grid_export_kw, "
    "t.power_factor, t.energy_import_kwh, t.energy_export_kwh, t.temperature, t.soh, "
    "t.metadata FROM telemetry t JOIN devices d ON d.device_id = t.device_id"
)


def measurement_from(device_id: str, measurement_type: str) -> Measurement:
    canonical_unit = units.MEASUREMENT_TYPE_UNITS.get(measurement_type)
    unit_symbol = unit_multiplier = None
    if canonical_unit is not None:
        try:
            unit_symbol, unit_multiplier, _ = units.to_cim_unit(canonical_unit)
        except units.CimUnitError:
            pass
    return Measurement(
        mRID=identifiers.mrid_for("Measurement", device_id, measurement_type),
        name=f"{device_id}/{measurement_type}",
        measurementType=measurement_type,
        unitSymbol=unit_symbol,
        unitMultiplier=unit_multiplier,
        deviceMRID=identifiers.mrid_for("EndDevice", device_id),
    )


def list_measurements(*, tenant_id: str | None, device_id: str | None = None,
                       measurement_type: str | None = None, limit: int, offset: int) -> list[Measurement]:
    clauses, params = db.build_filter([
        ("d.tenant_id = %s", tenant_id), ("t.device_id = %s", device_id),
    ])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(
        "SELECT DISTINCT t.device_id, jsonb_object_keys(t.metadata->'quality') AS measurement_type "
        "FROM telemetry t JOIN devices d ON d.device_id = t.device_id "
        f"{where} ORDER BY t.device_id, measurement_type",
        params,
    )
    if measurement_type:
        rows = [r for r in rows if r["measurement_type"] == measurement_type]
    rows = rows[offset:offset + limit]
    return [measurement_from(r["device_id"], r["measurement_type"]) for r in rows]


def measurement_value_from_row(row: dict, measurement_type: str,
                                tenant_lookup: dict[str, str | None]) -> MeasurementValue | None:
    quality_block = (row.get("metadata") or {}).get("quality", {}).get(measurement_type)
    if quality_block is None:
        return None
    raw_value = row.get(measurement_type)
    canonical_unit = units.MEASUREMENT_TYPE_UNITS.get(measurement_type)
    cim_value = unit_symbol = unit_multiplier = None
    if canonical_unit is not None and raw_value is not None:
        try:
            unit_symbol, unit_multiplier, _ = units.to_cim_unit(canonical_unit)
            cim_value = units.base_unit_value(raw_value, canonical_unit)
        except units.CimUnitError:
            pass
    device_id = row["device_id"]
    timestamp = row["time"].isoformat() if hasattr(row["time"], "isoformat") else str(row["time"])
    correlation_id = (row.get("metadata") or {}).get("correlation_id")
    return MeasurementValue(
        mRID=identifiers.mrid_for("MeasurementValue", device_id, measurement_type, timestamp, correlation_id or ""),
        name=f"{device_id}/{measurement_type}@{timestamp}",
        measurementMRID=identifiers.mrid_for("Measurement", device_id, measurement_type),
        deviceMRID=identifiers.mrid_for("EndDevice", device_id),
        value=cim_value,
        unitSymbol=unit_symbol,
        unitMultiplier=unit_multiplier,
        rawValue=raw_value,
        rawUnit=canonical_unit,
        timeStamp=timestamp,
        quality=quality_block.get("quality"),
        estimated=bool(quality_block.get("estimated", False)),
        tenantId=tenant_lookup.get(device_id),
        sourceCorrelationId=correlation_id,
    )


def _device_tenant_lookup(device_ids: set[str]) -> dict[str, str | None]:
    if not device_ids:
        return {}
    rows = db.query_all(
        "SELECT device_id, tenant_id FROM devices WHERE device_id = ANY(%s)",
        (list(device_ids),),
    )
    return {r["device_id"]: r["tenant_id"] for r in rows}


def list_measurement_values(*, tenant_id: str | None, device_id: str | None = None,
                             measurement_type: str | None = None, since=None, until=None,
                             limit: int, offset: int) -> list[MeasurementValue]:
    clauses, params = db.build_filter([
        ("d.tenant_id = %s", tenant_id), ("t.device_id = %s", device_id),
        ("t.time >= %s", since), ("t.time <= %s", until),
    ])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    # Overfetch: one telemetry row expands into several measurement_types
    # (this platform's devices report up to ~10 fields per reading) --
    # pagination below is therefore approximate for a device reporting
    # more than that, documented in LIMITATIONS.md; correctness over
    # query efficiency for this read-side adapter (no perf work this sprint).
    rows = db.query_all(
        f"{_TELEMETRY_SELECT} {where} ORDER BY t.time DESC LIMIT %s",
        params + ((limit + offset) * 10 + 50,),
    )
    tenant_lookup = (
        {r["device_id"]: tenant_id for r in rows} if tenant_id
        else _device_tenant_lookup({r["device_id"] for r in rows})
    )

    values: list[MeasurementValue] = []
    for row in rows:
        quality_keys = (row.get("metadata") or {}).get("quality", {}).keys()
        for mtype in quality_keys:
            if measurement_type and mtype != measurement_type:
                continue
            mv = measurement_value_from_row(row, mtype, tenant_lookup)
            if mv is not None:
                values.append(mv)
    return values[offset:offset + limit]
