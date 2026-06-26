# DIEP — CIM / IEC 61968 Interoperability Report

Final deliverable of the CIM/IEC 61968 integration sprint that followed
`READY_FOR_CIM.md` (commit `e77ec73`, verdict READY FOR CIM). Full detail
in `CIM_MAPPING_GUIDE.md`, `IEC61968_PROFILE.md`, `SUPPORTED_OBJECTS.md`,
`LIMITATIONS.md`, `API_REFERENCE.md` — this report is the conclusion.

## Recommendation: the platform is ready for standards-based integration with external utility systems, within the scope this sprint built

A new, standalone, read-only `services/cim/` REST API now sits on top of
the trusted measurement stream `READY_FOR_CIM.md` validated, translating
it into CIM/IEC 61968 information model objects (Meter, EndDevice,
UsagePoint, ServicePoint, Customer, Transformer, Feeder, ConnectivityNode,
Terminal, Measurement, MeasurementValue, Asset) without changing AMI, MDM,
OPC UA, the database schema, or the existing FastAPI APIs in any way —
confirmed by inspection: every change this sprint made is additive, under
`services/cim/`, `tests/test_cim_*.py`, `docker-compose-cim.yml`, and
these 6 documents.

This recommendation is **scoped, not unconditional** — read §4 before
connecting a real external system.

## 1. What was verified, and how

Two independent verification passes, both live, neither against mocks —
plus one gap in test-suite execution, stated plainly rather than rounded
up:

**Live deployment verification** (`docker-compose-cim.yml`, real
container, real network, real database, exercised directly with `curl`)
covered: authentication (`401` for missing/bad token), **tenant
isolation** (a `sit-tenant`-scoped token cannot see `sit-tenant-b`'s
devices and vice versa, confirmed both directions — a cross-tenant detail
request returns `404`, not a leak), mapping correctness
(`Meter.deviceType`, feeder/transformer ancestry resolved correctly), the
`UsagePoint` deduplication (`SP-001/002/003` sharing one node+meter
correctly collapses to one `UsagePoint` listing all 3 customers — not
three duplicate points), `Terminal` synthesis for a real `grid_edges` row,
both export formats (JSON shape, well-formed CIM/RDF-style XML), and
validation rejecting a profile/object-type mismatch and an unknown object
type with the documented error codes. This is the verification this
report's confidence actually rests on.

**Round-trip data integrity** — `MeasurementValue` rows fetched live for
`SIT-METER-006` reproduced this sprint's own earlier SIT test data exactly:
a `frequency=999.0 Hz` reading still carries `quality=OUT_OF_RANGE` (MDM's
escalation, unchanged), and a `power_kw=17.25 kW` reading converts
correctly to `value=17250.0, unitSymbol=W, unitMultiplier=k` while
`rawValue=17.25, rawUnit=kW` stays alongside it — with the exact
`sourceCorrelationId` from the original envelope intact. This is the
concrete demonstration of "no information loss," not an assertion of it.

**Automated test suite** (`tests/test_cim_*.py`, 14 files, no pytest
binary available in this dev shell — same constraint as every prior phase
on this branch, run via direct script execution): **68/68 checks passed**
across 13 of the 14 files — units, identifiers/mRID determinism,
validation, profiles, JSON/XML export round-trips, every mapping module
(database calls monkeypatched out so the transformation logic is isolated
from the live SQL, which the deployment pass above separately proves), the
topology-walk cross-check against `services/mdm/enrichment.py` on the same
fixture graph, and `auth.py`'s tenant-resolution logic (run inside the live
container, where `fastapi`/`prometheus_client` are actually installed).

**One file did not run**: `tests/test_cim_api.py`'s FastAPI `TestClient`
suite (13 further checks) needs `starlette.testclient`, which in this
environment's installed package versions requires a package named
`httpx2` — confirmed neither `httpx` nor `httpx2` is installed in the live
container, and installing an unfamiliar, unverified package name on request
was correctly declined (see `LIMITATIONS.md` §9). The same routes that
file would have exercised were independently covered by the live `curl`
verification above, so the functional ground isn't actually unverified —
the *file* just didn't execute. Don't round this up to "81/81" — it's
68/68 plus a separate, real gap in this one file's own execution.

## 2. Scope discipline

No changes were made to AMI, MDM, OPC UA, the database schema, or the
existing FastAPI APIs. CIM authenticates and scopes tenancy entirely on
its own (`services/cim/auth.py`) rather than importing `fastapi/auth.py`
— a deliberate decoupling, not an oversight (see
`CIM_MAPPING_GUIDE.md` §1). No CIM-side database writes exist anywhere in
this codebase.

## 3. What this closes from the original SIT findings

The original SIT (`SYSTEM_ACCEPTANCE_REPORT.md`) flagged "no
tenant-scoped telemetry read API" as a real, unaddressed gap (finding
4-6, explicitly left open through the post-SIT stabilization sprint).
**CIM does not repeat that mistake**: every route is tenant-filtered from
the start, verified live in both directions. This is the first
externally-facing read API on this platform with tenant scoping built in
from day one.

## 4. What "ready" does not mean — read before connecting a real system

1. **Spec conformance is asserted, not verified.** Every CIM class,
   attribute, and unit symbol is spec-shaped from established CIM/IEC
   61968-61970 modeling knowledge — this environment has no access to the
   official UML/RDF/XSD artifacts to validate against. Before any real
   exchange with an external utility system, validate the actual payload
   shapes against that system's accepted schema. See `LIMITATIONS.md` §1.
2. **Coverage is intentionally narrow.** Asset management is DER-only;
   network-model classes cover only Transformer/Feeder (not
   substations/switches/reclosers); billing, work-order management, GIS
   detail, and CGMES export are not implemented at all. See
   `IEC61968_PROFILE.md` §6 and `SUPPORTED_OBJECTS.md` for the complete
   list — nothing here is a surprise gap, every one is named.
3. **The underlying throughput ceiling from the prior sprint is
   unchanged.** CIM is a read-side adapter and doesn't touch the
   FastAPI/TimescaleDB write path `READY_FOR_CIM.md` flagged (~15 msg/s
   sustained) — that caveat still stands, independently of this sprint.
4. **`tenant_id='default'` is broader than a real tenant boundary** and
   the original tenant-id self-report-vs-registry reconciliation gap
   (SIT finding) is still open — CIM's access control uses the registry
   value, which avoids the worst case, but doesn't fix the underlying gap.
   See `LIMITATIONS.md` §2/§4.

## 5. Conclusion

The specific, narrow question this report answers — *can this platform's
governed measurement stream be exposed as CIM/IEC 61968 objects to an
external system without touching the existing pipeline* — is answered
**yes**, confirmed live, not just by design. Whether to actually connect
a specific external utility system is a separate decision that depends on
that system's own schema requirements, which §4's caveats are written to
make easy to check against.
