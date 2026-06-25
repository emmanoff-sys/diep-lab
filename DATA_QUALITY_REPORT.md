# DIEP — Data Quality & Topology Validation Report (SIT, 2026-06-25)

Covers sprint Deliverables 5 (Quality Validation) and 7 (Topology
Validation).

## 1. All 8 contract quality flags — propagation verified

`contracts.quality.Quality` defines 8 flags. Every one was driven through
both the real DB path (via the live ingestor) and MDM (quality engine),
confirming whether each survives **unchanged** end to end, per the contract's
"never silently overwrite" requirement.

| Flag | DB metadata preserves it? | MDM preserves it (no transition)? | Notes |
|---|---|---|---|
| GOOD | Yes | N/A (baseline) | Scenario A |
| ESTIMATED | Yes | Yes | Scenario D; contract auto-sets `estimated=True` when quality=ESTIMATED, confirmed |
| SUBSTITUTED | Yes | Yes | Quality-flags supplement |
| INVALID (driver-flagged) | Yes | Yes | Scenario C case 1 |
| MISSING | Yes | Yes | Quality-flags supplement |
| COMMUNICATION_FAILURE | Yes | Yes | Scenario C case 1 |
| OUT_OF_RANGE (driver-flagged) | — (not separately tested driver-flagged; GOOD-but-out-of-range was, see below) | — | |
| DUPLICATE | Yes | Yes | Quality-flags supplement |

**MDM-initiated escalation** (the other half of "quality validation" — what
MDM does when the driver says GOOD but the data isn't): confirmed live, not
just via direct invocation. The real running MDM service's
`mdm_quality_transitions_total` counter (Prometheus, scraped during this
sprint) shows real escalations:

```
mdm_quality_transitions_total{reason="out_of_range"} 5
mdm_quality_transitions_total{reason="non_finite_value"} 2
```

Three of the five `out_of_range` transitions trace to an unplanned source:
Scenario B's ordering sub-test published `voltage=3200/3201/3202` (a typo in
test data — `200.0 + sequence_number` where `sequence_number` happened to be
in the thousands) — which MDM correctly caught and escalated live, on real
broker traffic, not a contrived test input. Left in this report because it's
better evidence than a deliberately-clean test would have been: the quality
engine fires correctly even on accidental bad data, not just rehearsed bad
data.

**The one finding that matters most here** (detailed in
`INTEGRATION_VALIDATION_REPORT.md` §0/Scenario C): a `GOOD`-flagged, truly
out-of-range or non-finite value gets escalated correctly by MDM — on a
stream nothing reads. The database, which everything else in the platform
actually queries, either keeps showing `GOOD` forever (out-of-range case) or
never receives the row at all (non-finite case — a `NaN` value crashes the
ingestor's HTTP POST and is silently dropped, no quality flag involved at
all). **Quality validation passes for "does the flag get reinterpreted
correctly"; it does not currently pass for "does that reinterpretation reach
anything that matters."**

## 2. Topology / device metadata enrichment

Verified against the platform's real `grid_nodes` table (a feeder →
transformer → meter chain registered for this sprint — not a fabricated
result; see `validation/scripts/00_fixtures.sql`), for two devices under two
different tenants:

| Device | Tenant | Resolved tenant_id | Resolved site_id | Resolved device_type | Resolved feeder_id | Resolved transformer_id |
|---|---|---|---|---|---|---|
| SIT-METER-001 | sit-tenant | sit-tenant | SIT Validation Site | smartmeter | SIT-FDR-01 | SIT-TX-01 |
| SIT-METER-006 | sit-tenant-b | sit-tenant-b | SIT Validation Site | smartmeter | SIT-FDR-01 | SIT-TX-01 |

Both correct — confirms enrichment resolves per-device, not by accident of
test ordering, and correctly attributes cross-tenant devices sharing the same
physical feeder/transformer (a realistic topology: multiple tenants' meters
on shared distribution infrastructure).

`asset_class` is aliased to `device_type` (`"smartmeter"` in both cases) —
this is `services/mdm/enrichment.py`'s documented behavior (the platform has
no separate asset-classification taxonomy yet), not a bug.

### 2.1 The tenant-reconciliation gap (new finding, surfaced by this sprint's own fixture mistake)

While setting up fixtures, `SIT-METER-001..005` were briefly registered
without `devices.tenant_id` (defaulting to `'default'`). MDM's enrichment
correctly returned `tenant_id='default'` from the registry — while the
envelope itself, self-reported by the "device," said `tenant_id='sit-tenant'`.
**MDM never compared the two.** It surfaced only because this report's own
test asserted the envelope's value, not the registry's. Once the fixture was
corrected (with explicit confirmation — see `INTEGRATION_VALIDATION_REPORT.md`
§3) the values agreed and the check passed — but the underlying behavior
(no cross-check between self-reported and registry-derived tenant_id) is
unchanged and is a real, if narrow, tenant-isolation gap: nothing in this
pipeline would catch a device whose envelope claims a tenant_id different
from what it's registered under. See `SYSTEM_ACCEPTANCE_REPORT.md`
recommendations.

### 2.2 Unmapped devices

Not re-exercised live this sprint (already unit-tested per `MDM_DESIGN.md`
§4 / `tests/test_mdm_enrichment.py`): a device with no `grid_nodes` entry
gets an honest `None` for `feeder_id`/`transformer_id`, not a guessed value.
Cited here, not re-verified, since this sprint's fixtures are all fully
mapped by design.

## 3. Round 2 (Post-SIT stabilization sprint)

§1's "one finding that matters most" — quality escalation happening
correctly but reaching nobody — is fixed. Re-tested live (not re-invoked
directly): an `OUT_OF_RANGE` reading now shows that flag in
`telemetry.metadata` itself, and a `NaN` reading produces a DB row with an
explicit `rejected_reason` rather than vanishing. See
`INTEGRATION_VALIDATION_REPORT.md` §4.2 for the live confirmation and
`SYSTEM_ACCEPTANCE_REPORT.md` for the architecture change (Work Item 4)
that did it. **"Quality validation passes for 'does the flag get
reinterpreted correctly'" now also passes for "does that reinterpretation
reach anything that matters"** — the qualifier this report's Round 1
deliberately withheld.

The tenant-reconciliation gap (§2.1) and unmapped-device behavior (§2.2)
are unchanged this round — neither was in this sprint's 6 work items
(see `SYSTEM_ACCEPTANCE_REPORT.md`'s scope-discipline note), so they
remain open findings, not regressions.

Also confirmed this round, via `services/opcua/mdm_consumer.py` (Work Item
5): MDM's enrichment metadata (`tenant_id`/`site_id`/`feeder_id`/
`transformer_id`) now also reaches a *second* consumer (the OPC UA
connector's `/health` endpoint) unchanged, for `SIT-METER-006` under
`sit-tenant-b` — the same cross-tenant-shared-infrastructure topology
case §2 validated for the DB path, now confirmed reaching a different
consumer too. See `INTEGRATION_VALIDATION_REPORT.md` Scenario G.
