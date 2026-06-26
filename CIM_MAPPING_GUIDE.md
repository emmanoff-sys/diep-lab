# DIEP CIM Mapping Guide

How `services/cim/` translates the platform's existing data into CIM/IEC
61968 information model objects. Read `LIMITATIONS.md` alongside this —
every CIM-standard attribute name here is **spec-shaped, not
independently verified** against the official IEC 61968/61970 UML/RDF/XSD
artifacts (no access to them in this environment), the same discipline
already established for `drivers/dlms/VALIDATION.md` and
`services/opcua/VALIDATION.md`.

## 1. Why a read-only adapter, not a rewrite

CIM sits entirely downstream of the now-quality-governed production path
(`AMI → MDM → FastAPI → TimescaleDB`, see `READY_FOR_CIM.md`). It reads
`devices`, `sites`, `grid_nodes`, `grid_edges`, `customers`,
`service_points`, `der_assets`, and `telemetry` directly, read-only
(`services/cim/db.py`, the same lazy-`psycopg2` pattern as
`services/mdm/db.py`) — it never writes to the database, never calls
existing FastAPI endpoints, and never touches AMI/MDM/OPC UA. Every CIM
object is mRID-traceable back to a specific row in one of those tables.

## 2. The 12 classes, what they map from, and why

| CIM class | Source | Key/filter | Module |
|---|---|---|---|
| EndDevice | `devices` | every row | `mapping/devices.py` |
| Meter | `devices` | `device_type='smartmeter'` | `mapping/devices.py` |
| Asset | `der_assets` | every row | `mapping/assets.py` |
| Customer | `customers` | every row | `mapping/metering.py` |
| ServicePoint | `service_points` | every row | `mapping/metering.py` |
| UsagePoint | `service_points` (deduplicated) + `devices` (fallback) | see §3 | `mapping/metering.py` |
| ConnectivityNode | `grid_nodes` | every row | `mapping/network.py` |
| Transformer | `grid_nodes` | `node_type='transformer'` | `mapping/network.py` |
| Feeder | `grid_nodes` | `node_type='feeder'` | `mapping/network.py` |
| Terminal | `grid_edges` + leaf `grid_nodes` (synthesized) | see §4 | `mapping/network.py` |
| Measurement | `telemetry.metadata.quality` keys | distinct `(device_id, measurement_type)` | `mapping/measurements.py` |
| MeasurementValue | `telemetry` rows | every row × measurement_type present | `mapping/measurements.py` |

Every class extends `IdentifiedObject` (`models/identified_object.py`):
`mRID` (a deterministic UUID, see §5), `name`, `description`, `aliasName`.

### EndDevice / Meter

`EndDevice` maps any `devices` row (`device_id`, `device_type`, `status`,
`site_name`, `tenant_id`, `location`), plus `feederMRID`/`transformerMRID`
resolved by walking `grid_nodes.parent_id` upward
(`services/cim/topology.py` — see §6). `Meter` is `EndDevice` with one
extra field (`formNumber`, currently always `None` — not modeled) and is
the subset of `devices` rows where `device_type='smartmeter'`.

### Asset

Maps `der_assets` only (`der_id`, `der_type`, `rated_kw`, `rated_kwh`,
`controllable`, `vpp_group`, `node_id`). Smartmeters and any other
non-DER `devices` row have **no** Asset record — there's no physical-asset
table for them in this schema. See `SUPPORTED_OBJECTS.md`.

### Customer / ServicePoint / UsagePoint

`Customer` and `ServicePoint` map 1:1 from their tables. `UsagePoint` does
not: the seed data itself shows why a naive 1:1 from `service_points`
would be wrong — `SP-001`/`SP-002`/`SP-003` (three different customers)
all point at the same `node_id='ND-METER001'` and
`meter_device_id='METER001'` (`sql/013_network_model.sql`). That's one
physical point of delivery shared by three customers, not three points.
`UsagePoint` deduplicates `service_points` by `(node_id,
meter_device_id)`; every `ServicePoint` sharing that pair collapses into
one `UsagePoint`, with all contributing customers listed in
`customerIds`.

One edge case worth being explicit about: a `service_points` row where
**both** `node_id` and `meter_device_id` are `NULL` is *not* grouped with
other such rows under a shared `NULL` key (`GROUP BY` would otherwise
treat `NULL = NULL` as one group in Postgres) — each gets its own
`UsagePoint`, keyed by `service_point_id` instead. Done in Python, not SQL,
specifically to avoid that silent merge.

Devices with **no** `service_points` row at all (most of this platform's
fixture devices) get a synthesized fallback `UsagePoint` built from
`devices`/`sites` directly, explicitly flagged `synthesized=true` — never
presented as equally authoritative as a real, `service_points`-backed one.

### ConnectivityNode / Transformer / Feeder / Terminal

`ConnectivityNode` maps **every** `grid_nodes` row — its topological
identity (`node_id`, `parentMRID`, coordinates, `nominalKv`) is
independent of whatever else that same row also becomes (`Transformer`/
`Feeder` by `node_type`). `Transformer` and `Feeder` are the `grid_nodes`
subsets filtered by `node_type='transformer'`/`'feeder'`.

`Terminal` has no dedicated table. It's synthesized:

- **Two per `grid_edges` row** — one at `from_node`, one at `to_node`
  (`sequenceNumber` 1/2), since `grid_edges` already models the
  equipment-like connections (`line`/`switch`/`transformer`/`tie`) between
  nodes, and a CIM `Terminal` is exactly "where equipment connects to a
  `ConnectivityNode`".
- **One per `grid_nodes` row with no edge referencing it** — a leaf
  DER/meter node still needs a `Terminal` in real CIM topology even at
  degree 1; without this, every leaf node would have a
  `ConnectivityNode` but never appear as a `Terminal` endpoint, an
  inconsistency worse than synthesizing one.

Terminal IDs are deterministic (`{edge_id}-T1`/`-T2`,
`{node_id}-T1` for leaves — `services/cim/identifiers.py`), never randomly
generated, so re-querying never changes an object's identity.

### Measurement / MeasurementValue

The "no information loss" pair. `Measurement` is the *definition* of what
a device measures — one per `(device_id, measurement_type)` actually seen
in that device's `telemetry.metadata.quality` keys (not the
always-present, 0.0-defaulted flat columns — see §7). `MeasurementValue`
is one actual reading: it carries the value in **both** the original
canonical unit (`rawValue`, `rawUnit`) and the CIM base unit (`value`,
`unitSymbol`, `unitMultiplier`), plus `quality`, `estimated`, `timeStamp`,
and `sourceCorrelationId` — read straight from the source row's
`metadata`, never re-interpreted. `mapping/measurements.py`'s own
docstring states this explicitly: build from `metadata.quality`'s keys,
never from nonzero-column guessing.

## 3. mRID determinism

CIM's mRID is meant to be a stable, globally-unique identifier. This
platform has no persistent mRID-allocation table, so mRIDs are
deterministically derived (`uuid5` over a fixed namespace + the natural
key — `services/cim/identifiers.py`) rather than randomly generated per
call. The same input always yields the same mRID — verified live (see
`CIM_INTEROPERABILITY_REPORT.md` §3) and in
`tests/test_cim_mapping_devices.py::test_mrid_is_deterministic_across_calls`.

## 4. Topology walk reuse

Feeder/transformer ancestry resolution (`services/cim/topology.py`)
reuses the *exact* logic already validated in
`services/mdm/enrichment.py`'s `_walk_to_node_type` (same query shape,
same `max_hops=10` default) rather than reinventing it — both services
read the same `grid_nodes` table and must never disagree. Cross-checked
directly in `tests/test_cim_topology.py`.

## 5. Units (no silent transformations)

`services/cim/units.py` maps each canonical unit this platform actually
produces (`V`, `A`, `kW`, `Hz`, `kWh`, `C`, `%`, `""`) to a `(unit_symbol,
unit_multiplier, scale)` triple. Anything outside that set raises
`CimUnitError` rather than guessing. One real gap: the ingestor's
`envelope_to_legacy_body()` does **not** persist the original `unit`
string per telemetry row (`metadata.quality[type]` carries only
`{quality, estimated}`) — CIM infers units from the fixed
`measurement_type → canonical unit` table the platform's own
`services/mdm/units.py` already uses, not from stored per-row data, since
none exists. See `LIMITATIONS.md`.
