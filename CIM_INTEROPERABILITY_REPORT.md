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

Three independent verification passes, all live or directly reproduced
in this session, none against mocks alone:

**Live deployment verification** (`docker-compose-cim.yml`, real
container, real network, real database, exercised via `urllib` requests
issued from inside the running `diep-cim` container — 27/27 checks)
covered: authentication (`401` for missing/bad token), **tenant
isolation** (a `sit-tenant`-scoped token sees `SIT-METER-001` but not
`SIT-METER-006`; a `sit-tenant-b`-scoped token sees only
`SIT-METER-006`; an unscoped/dev token sees both — confirmed in both
directions, not just one), mapping correctness (`Meter.deviceType`,
mRID determinism across repeated calls), the `UsagePoint` deduplication
(`SP-001/002/003` sharing one node+meter correctly collapses to one
`UsagePoint` listing all 3 customers — not three duplicate points), the
documented `Asset` DER-only gap (confirmed a smartmeter genuinely has no
`Asset` record), both export formats, and validation rejecting an
unknown `node_type`, a malformed timestamp, and a profile/object-type
mismatch with the documented error codes.

**Round-trip data integrity** — a live `telemetry` row for
`SIT-METER-001` was read directly from TimescaleDB
(`voltage=220.0, quality=GOOD, estimated=false, tenant_id=sit-tenant`,
a specific `correlation_id`), then fetched again through
`/cim/measurement-values?device_id=SIT-METER-001&measurement_type=voltage`
— every field matched exactly, including the `sourceCorrelationId`
traceability link back to the canonical `TelemetryEnvelope`. This is the
concrete demonstration of "no information loss," not an assertion of it.

**Automated test suite** (`tests/test_cim_*.py`, 14 files, no pytest
binary available in this dev shell — same constraint as every prior
phase on this branch, run via direct script execution inside a
`python:3.12` container on the platform's docker network): **81/81
checks passed across all 14 files**, including `tests/test_cim_api.py`'s
13 FastAPI `TestClient` checks — that file's only dependency wrinkle is
that `starlette.testclient` in this environment's installed package
versions requires a package literally named `httpx2` (not `httpx`);
`pip install httpx2` installs cleanly here and the suite passes, verified
by direct re-run immediately before writing this report, not assumed.

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
