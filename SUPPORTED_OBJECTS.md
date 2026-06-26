# Supported CIM Objects

The 12 classes this service implements, what's real vs. synthesized, and
every known gap stated plainly rather than left to be discovered.

| Class | Status | Source | Known gaps |
|---|---|---|---|
| **EndDevice** | Real | `devices`, every row | `amrSystem`, `isVirtual`, `timeZoneOffset` are not modeled in this schema — always `None`/`False`. |
| **Meter** | Real | `devices` where `device_type='smartmeter'` | `formNumber` not modeled — always `None`. |
| **Asset** | Real, **DER-only** | `der_assets` | No record for smartmeters or any non-DER device — there is no physical-asset table for them. Asset lifecycle (install date, maintenance, warranty) not modeled at all. |
| **Customer** | Real | `customers`, every row | Only `name`/`address`/`phone`/`priority` exist — no billing/contract/agreement data. |
| **ServicePoint** | Real | `service_points`, every row | — |
| **UsagePoint** | Real + **synthesized fallback** | `service_points` (deduplicated by node+meter) for devices that have one; synthesized from `devices`/`sites` for devices that don't | Synthesized rows are explicitly flagged `synthesized=true` — check this field before treating a UsagePoint as authoritative. `ratedPower`/`connectionState` are not modeled — always `None`. |
| **ConnectivityNode** | Real | `grid_nodes`, every row | — |
| **Terminal** | **Fully synthesized** | 2 per `grid_edges` row + 1 per edge-less `grid_nodes` row | No dedicated table exists; IDs are deterministic, not random, but the objects themselves are derived, not stored. |
| **Transformer** | Real | `grid_nodes` where `node_type='transformer'` | Only `nominalKv` + location — no winding/tap/impedance detail (`PowerTransformerEnd` not implemented). |
| **Feeder** | Real | `grid_nodes` where `node_type='feeder'` | Same as Transformer — minimal attributes. |
| **Measurement** | Real | `telemetry.metadata.quality` keys, distinct `(device_id, measurement_type)` | Definition only — see MeasurementValue for readings. |
| **MeasurementValue** | Real | every `telemetry` row × measurement_type present | — the most complete class; see `CIM_MAPPING_GUIDE.md` §2 for exactly what's preserved. |

## What's explicitly NOT a CIM class here (exists in the schema, not mapped)

- `grid_nodes` rows with `node_type` in `substation`, `switch`, `recloser`,
  `bus`, `meter`, `der`, `load` — all valid `ConnectivityNode`s, but none
  has its own dedicated equipment class (`Substation`, `Switch`/`Breaker`,
  `EnergyConsumer`, etc.) in this implementation. Only `Transformer` and
  `Feeder` got dedicated classes, per the sprint's literal 12-class list.
- `grid_edges`' electrical attributes (`resistance_r_ohm`,
  `reactance_x_ohm`, `length_km`, `ampacity_a`) — not exposed on any of
  the 12 classes (an `ACLineSegment` class would be the natural home; not
  built this sprint).
- `sites` — folded into `siteName` string fields on several classes, not
  its own `Location`/`ServiceLocation` class.

## Tenant scoping (security-relevant, verified live)

Every list/detail route filters by the resolved `tenant_id`
(`services/cim/auth.py`) — a tenant-scoped token sees only its own
tenant's objects. Verified live (`CIM_INTEROPERABILITY_REPORT.md` §3): a
`sit-tenant`-scoped token cannot see `sit-tenant-b`'s devices and vice
versa, despite the unscoped/service token seeing both.
