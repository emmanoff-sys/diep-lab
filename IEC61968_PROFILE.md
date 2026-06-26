# IEC 61968 Profile — What This Service Implements

## 1. Scope, stated plainly

This service implements a **deliberately narrow subset** of IEC
61968/61970's full information model — exactly the four functional areas
the sprint scoped: **Metering, Asset management, Network model,
Measurements**. It is not, and does not claim to be, a complete or
certified IEC 61968 implementation. Real IEC 61968/CGMES tooling is a
large, mostly Java/Eclipse-based ecosystem (this was already flagged as a
risk in `PLANNING.md` before this sprint started: "Python tooling for
IEC 61968-9 / CGMES is thin and partly Java/Eclipse-based") — building a
full, schema-validated implementation from scratch in this environment
was never the goal.

Every class/attribute name used here is **spec-shaped from established
CIM/IEC 61968-61970 modeling knowledge** (the `IdentifiedObject` base, the
`Asset`/`EndDevice`/`Meter` hierarchy, `UsagePoint`'s independence from
`Asset`, the `ConductingEquipment → Terminal → ConnectivityNode` topology
pattern, the `Measurement`/`MeasurementValue` pattern from the IEC 61970
Meas package) — **not independently verified against the official
UML/RDF/XSD artifacts**, which this environment has no access to. Same
discipline as `drivers/dlms/VALIDATION.md` and
`services/opcua/VALIDATION.md`: stated once, prominently, not glossed
over.

## 2. Metering — implemented

`EndDevice`, `Meter`, `UsagePoint`, `ServicePoint`, `Customer`,
`Measurement`, `MeasurementValue`. See `CIM_MAPPING_GUIDE.md` §2 for the
exact source-table mapping. Quality (the platform's own 8-value `Quality`
enum, not a CIM `MeasurementValue.Quality` bitmask — see
`LIMITATIONS.md`), `estimated`, timestamps, and units all propagate
unchanged from the canonical telemetry contract.

## 3. Asset management — partially implemented

`Asset` is implemented, but **DER-only** (`der_assets`: battery, solar,
ev_charger, microgrid). Smartmeters and any other device type have no
Asset record — there is no physical-asset table for them in this schema.
Asset lifecycle (installation date, maintenance history, warranty,
manufacturer info — IEC 61968-3/-4 territory) is **not implemented at
all**: `der_assets` doesn't carry that data, so there's nothing to map.

## 4. Network model — implemented (read side only)

`ConnectivityNode`, `Terminal`, `Transformer`, `Feeder`. Maps from
`grid_nodes`/`grid_edges`, the same tables `feature/adms-topology-import`
(a separate, unrelated branch — see `PLANNING.md`'s addendum) populates
from GeoJSON/CIM network exports. CIM here is **read-only against that
model** — it does not import, validate, or modify network topology
itself; that's the topology-import branch's job, explicitly out of this
sprint's scope.

Substations, switches, reclosers, buses, DER/load nodes exist in
`grid_nodes` (and are valid `ConnectivityNode` rows) but have **no
dedicated CIM equipment class** in this implementation — only
`Transformer` and `Feeder` got one, per the sprint's literal 12-class
list. A `Switch`/`Breaker`/`PowerTransformerEnd` class would be the
natural next addition if network-model coverage needs to deepen.

## 5. Measurements — implemented

`Measurement` (the type definition) and `MeasurementValue` (the reading),
both reading `telemetry`/`telemetry.metadata`. This is the most complete
coverage of the four areas: every measurement type the ingestor can
produce (`ingestor/telemetry_ingestor.py`'s `CANONICAL_FIELDS` +
`EXTENDED_NUMERIC`) has a unit mapping (`services/cim/units.py`), and
every quality value is preserved verbatim.

## 6. Explicitly unsupported profiles (not started, not partially built)

- **IEC 61968-9 (Interface for Meter Reading and Control)** message
  exchange formats (MR-xxx message types) — this service exposes a REST
  API, not the 61968-9 messaging profile.
- **CGMES** (Common Grid Model Exchange Standard) and any power-flow /
  state-estimation model export — `feature/adms-topology-import`'s GeoJSON
  importer is the closest thing in this repo, and it's a different layer
  entirely.
- **Asset maintenance / work order management** (IEC 61968-4) — no work
  order, inspection, or maintenance-history data exists anywhere in this
  platform's schema to map.
- **Billing / rating** (IEC 61968-9's billing determinants, or any
  tariff/rate-plan model) — `customers.priority` (standard/medical/
  critical) is the only billing-adjacent field that exists, and it isn't
  mapped to anything billing-specific.
- **GIS extensions** (detailed conductor/pole/structure asset models) —
  out of scope; `grid_edges`' electrical attributes (R/X impedance,
  length, ampacity) are exposed via `ACLineSegment`-adjacent fields on
  none of the 12 implemented classes (a gap, not a hidden feature — see
  `LIMITATIONS.md`).
- **CIM-JSON-LD / RDF/XML schema conformance** — the JSON and XML export
  formats are this platform's own clean shapes (see
  `services/cim/serialization/`), not validated against any official
  exchange-format schema. See `LIMITATIONS.md`.
