# CIM Service — Limitations

Every caveat in one place, stated plainly. If something here later turns
out to matter for a real integration, this is where to start.

## 1. Spec conformance is not verified

Every CIM class/attribute name (`services/cim/models/`) and unit symbol
(`services/cim/units.py`) is **spec-shaped from established CIM/IEC
61968-61970 modeling knowledge, not independently verified against the
official UML/RDF/XSD artifacts** — this environment has no access to
them. The JSON export (`serialization/json_export.py`) is this platform's
own clean shape, not a claim of CIM-JSON-LD conformance. The XML export
(`serialization/xml_export.py`) is CIM/RDF-*style* (`<cim:ClassName
rdf:ID="...">`), using a placeholder namespace URI
(`http://diep.local/cim/spec-shaped#`), not the official IEC 61970-301
namespace, and not validated against the official RDF/XSD schema. Same
discipline as `drivers/dlms/VALIDATION.md` and
`services/opcua/VALIDATION.md` — before any real interoperability claim
to an external utility system, validate against the actual standard
artifacts.

## 2. Tenant scoping for telemetry joins through `devices`, not `metadata`

`telemetry` has no `tenant_id` column (confirmed against every migration
that's touched the table — `sql/000_schema.sql`'s `CREATE TABLE` and
every later `ALTER TABLE telemetry`, none add it). CIM's
`Measurement`/`MeasurementValue` tenant scoping joins through
`devices.tenant_id`, treated as authoritative — **not**
`metadata->>'tenant_id'` (operator-set at envelope-creation time,
unindexed, and a real possible source of disagreement with the registry:
this is the same class of gap the original SIT flagged for MDM —
"MDM never reconciles a device's self-reported tenant_id against the
device registry's" — CIM avoids it by simply not trusting the
self-reported value for access control, but the underlying disagreement,
if it exists, is invisible from CIM's output alone).

## 3. The original telemetry `unit` string isn't persisted per row

The ingestor's `envelope_to_legacy_body()` does not store the original
`unit` string in `telemetry.metadata` — only `{quality, estimated}` per
measurement_type. CIM infers canonical units from a fixed
`measurement_type -> unit` table (`services/cim/units.py`'s
`MEASUREMENT_TYPE_UNITS`, mirroring `services/mdm/units.py`'s
convention), not from stored per-row data, since none exists. If a future
driver ever published the *same* `measurement_type` under a *different*
unit, CIM would not detect it — it would apply the fixed table's unit
regardless, silently wrong in that specific case. No driver does this
today.

## 4. `tenant_id='default'` is broader than a real tenant boundary

Every table defaults `tenant_id='default'` when unset. A CIM token scoped
to `'default'` would see every legacy/unattributed row across the whole
platform — broader than a real customer-facing tenant boundary should
probably be. Worth deciding explicitly (reject `'default'` as a valid CIM
tenant scope, or accept the breadth) before exposing a `'default'`-scoped
token externally.

## 5. `MeasurementValue` pagination is approximate for high-field devices

One `telemetry` row expands into several `MeasurementValue` objects (one
per measurement_type present). `list_measurement_values`'s SQL `LIMIT`
overfetches rows (`(limit + offset) * 10 + 50`) to account for this, but
a device reporting more than ~10 fields per reading could still see
`limit`/`offset` behave approximately rather than exactly. Correctness
over query efficiency was the explicit tradeoff for this read-side
adapter — no performance work was in this sprint's scope (see
`READY_FOR_CIM.md`'s own throughput caveat, which is about the write
path, not this).

## 6. Export profiles don't yet filter individual fields

`serialization/profiles.py`'s `PROFILES` dict restricts which **object
types** an export profile includes (e.g. `metering` excludes `Feeder`
entirely), but does not yet restrict which **fields** of an included
object are exported — the per-class field-allowlist slot exists in the
data structure but is unpopulated (`None` for every class today). A
`metering` export today still includes every field of every included
class.

## 7. Asset lifecycle, billing, GIS, and CGMES are not modeled

No installation date, maintenance history, warranty, or manufacturer data
exists anywhere in this platform's schema — `Asset.to_dict()` will never
have these regardless of mapping effort. Billing/rating, work-order
management, detailed conductor/structure GIS models, and CGMES power-flow
export are not implemented at all (see `IEC61968_PROFILE.md` §6 for the
full unsupported-profile list) — not partially built, not planned for a
quick follow-up.

## 8. Dependency versions are unpinned, independently of the main app

`docker-compose-cim.yml`'s `pip install fastapi uvicorn[standard]
pydantic ...` is unpinned at container start — same pattern as
`docker-compose-fastapi.yml`, but CIM's FastAPI/Pydantic version is
whatever's latest *at CIM's own container's last rebuild*, independently
of the main app's. A future Pydantic major-version break could hit one
service and not the other on different schedules.

## 9. Test-only dependency note

`tests/test_cim_api.py` uses `fastapi.testclient.TestClient`, which in
this environment's package versions requires `httpx2` (not the more
commonly expected `httpx`) to be installed — a transitive dependency of
`starlette.testclient` here, not of the CIM service itself at runtime.
`docker-compose-cim.yml` does not (and should not) install it; only the
test invocation does.

## 10. Network model coverage is read-only and incomplete

CIM reads `grid_nodes`/`grid_edges` exactly as `feature/adms-topology-import`
(a separate branch) populates them, with no validation of its own.
Substations, switches, reclosers, buses, and DER/load nodes have no
dedicated CIM equipment class (only `ConnectivityNode`, generically) —
see `SUPPORTED_OBJECTS.md`. Electrical attributes (impedance, length,
ampacity) exist in `grid_edges` but are not exposed on any of the 12
implemented classes.
