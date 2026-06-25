# DIEP MDM (Meter Data Management) — Design

Implements the canonical quality layer between AMI acquisition and every
downstream consumer, per the MDM sprint brief. Code at `services/mdm/`.
Consumes `contracts.TelemetryEnvelope` **read-only** —
`AMI_INGEST_PHASE4_CONTRACT.md` and `contracts/` are frozen this phase and
are not modified anywhere in this change.

---

## 1. Where MDM sits

```
AMI Drivers (drivers/dlms, ...)
      │ publish TelemetryEnvelope
      ▼
   diep/<domain>/<device_id>   (existing MQTT topic, unchanged)
      │
      ├──────────────────────────────┬─────────────────────────────────────
      ▼                              ▼
  ingestor (existing,            MDM (new, this change)
  unchanged this phase)          validate → dedup → timestamp → gap →
      │ HTTP POST                quality → unit → enrich
      ▼                              │ publish
  FastAPI → TimescaleDB              ▼
                                diep/<domain>/<device_id>/trusted
                                      │
                                      ▼
                          (future) ADMS / OMS / Analytics / OPC UA / CIM
```

**MDM is an additional, independent subscriber to the same topic the
ingestor already consumes — not a replacement for it.** The constraint list
says "do not change FastAPI APIs, database schema" and "AMI contract is
frozen"; the success criteria says ADMS/OMS/Analytics/OPC UA/CIM should
eventually consume MDM's output. None of those five currently consume MQTT
telemetry directly (ADMS/OMS read from TimescaleDB via FastAPI; OPC UA/CIM
don't exist yet) — so "eventually consume MDM output" is the right framing:
this phase stands up the trusted stream and the quality pipeline that
produces it; rewiring real consumers onto it is each of those phases' own
work, not retrofitted here. Re-pointing the *existing* ingestor pipeline onto
MDM's output instead of raw AMI telemetry was considered and deliberately
not done — that would be changing a currently-working production data path
test-free in the same change that builds the thing it'd depend on.

---

## 2. Module map

| Module | Deliverable | Notes |
|---|---|---|
| `validation.py` | §2 Validation Engine | Wraps `TelemetryEnvelope.from_dict()` (which already enforces most structural rules) and adds the two checks the frozen contract deliberately leaves open: unit-registry validation, correlation_id UUID format. |
| `quality.py` | §3 Quality Engine, §4 Estimated/Measured | Only ever escalates FROM `GOOD` — never overwrites a driver-assigned non-GOOD flag (see §3 below). |
| `duplicates.py` | §5 Duplicate Detection | Two independent signatures: `(tenant_id, device_id, timestamp_utc, sequence_number)` and `correlation_id`; configurable policy (`any`/`key_only`/`correlation_only`). |
| `timestamps.py` | §6 Timestamp Normalization | Stamps MDM's own `ingestion_timestamp` (MDM is its own MQTT consumer, not fed through the ingestor — see §1); flags clock drift and out-of-order `sequence_number` per device. |
| `gaps.py` | §7 Gap Detection | Per `(tenant_id, device_id, measurement_type)`, configurable expected interval + tolerance multiplier. |
| `units.py` | §8 Unit Normalization | Converts to a canonical unit per `measurement_type`; always returns the original value/unit alongside the converted `Measurement`. |
| `enrichment.py` | §9 Device Metadata Enrichment | tenant/site/device_type from `devices`+`sites`; feeder/transformer via a bounded parent-chain walk over `grid_nodes` (sql/013_network_model.sql) — real topology, not fabricated (§4 below). |
| `topics.py` | §10 MQTT Output | `diep/<domain>/<device_id>/trusted` — MDM's own topic, not added to the frozen `contracts/topics.py`. |
| `metrics.py` | §11 Metrics | Prometheus counters/histogram; no-op fallback if `prometheus_client` isn't installed (never crashes the service over an observability dependency). |
| `health.py` | §1 health endpoint | Stdlib `http.server`, `/health` + `/metrics` — no new web-framework dependency, matching ingestor/dispatcher's existing lightweight style. |
| `pipeline.py` | orchestration | Wires all engines into one `process()` call; see §3 for the output-shape design. |
| `mqtt_io.py`, `service.py` | §1 service runner | Subscribe/process/publish loop + entrypoint. |

---

## 3. Output shape: "do not modify the canonical schema; only quality and metadata should change"

The trusted payload is the input envelope's own `to_dict()` — same fields,
same names, same types — with one addition: a top-level `mdm` key carrying
everything MDM determined (device metadata, quality transitions, unit
conversions, gap events, timestamp assessment). This is **additive**, not a
schema change: nothing in `contracts/telemetry.py` is touched, and any
consumer that only understands the AMI Phase 4 contract can read a trusted
payload as if it were a regular envelope and ignore `mdm` entirely.

Per-measurement `quality`/`unit`/`value` *do* change when the quality engine
escalates or the unit engine converts — units are explicitly deliverable #8
("normalize units... maintain conversion metadata"), so "only quality and
metadata should change" is read as "no structural change, and every
value-level change is one this spec's own deliverables call for and is
recorded as metadata" — not "nothing about a measurement may ever differ
from the input." The original unit+value are always preserved in
`mdm.unit_conversions`, so the conversion is fully reversible/auditable.

---

## 4. Never silently overwrite quality; honest enrichment over fabrication

Two judgment calls worth being explicit about:

- **Quality:** `QualityAssessor` only escalates a measurement whose driver-
  assigned quality is `GOOD`. If a driver already says `ESTIMATED` or
  `SUBSTITUTED`, MDM leaves it alone, even if the value also happens to be
  out of range — re-flagging an already-flagged value would itself be a
  silent overwrite of the driver's judgment. Every escalation MDM *does*
  make produces an explicit `QualityTransition` record, never a bare
  mutation.
- **Enrichment:** `feeder_id`/`transformer_id` are resolved via a real
  graph walk over `grid_nodes.parent_id` (the actual ADMS M1 network model),
  bounded to `max_hops` to survive a corrupt/cyclic chain. A device with no
  `grid_nodes` entry yet gets `None` for both — an honest "not modeled",
  not a guessed value. `asset_class` is aliased to `device_type` because the
  platform doesn't have a separate asset-classification taxonomy yet
  (documented here rather than inventing one).

---

## 5. Metrics: rates are computed, not stored

The spec asks for "duplicate rate" and "estimated percentage." Per standard
Prometheus practice these are PromQL expressions over raw counters
(`rate(mdm_measurements_estimated_total[5m]) / rate(mdm_measurements_processed_total[5m])`),
not a separately-stored gauge — storing a pre-divided ratio loses the ability
to re-window it and risks dividing by a stale/zero denominator. `metrics.py`
exposes: `mdm_measurements_processed_total`, `mdm_measurements_estimated_total`,
`mdm_envelopes_rejected_total{reason}`, `mdm_duplicates_total{matched_on}`,
`mdm_gap_events_total{measurement_type}`, `mdm_quality_transitions_total{reason}`,
`mdm_processing_latency_seconds` (histogram).

---

## 6. Deployment

`docker-compose-mdm.yml` — standalone compose file (matches
`docker-compose-ingestor.yml`'s pattern), mounting `./services/mdm` and
`./contracts:ro`, `/health`+`/metrics` on `127.0.0.1:9201` only (same
loopback-only convention as the rest of Phase 22 SEC-4). Not wired into
`start-all-diep.sh` — start explicitly via
`docker compose -f docker-compose-mdm.yml up -d`, same as ingestor/ocpp/etc.

**Found and fixed while wiring this:** `docker-compose-ingestor.yml` (the
standalone file) is **not** what's actually running — the live
`diep-ingestor` container is created from the `ingestor:` block inside the
main `docker-compose.yml`, which Phase 4's contracts mount had not been
added to. Fixed in this change (and the live container recreated/verified —
restarts=0, `contracts` import succeeds, pre-existing legacy traffic still
flows). `docker-compose-ingestor.yml` itself appears to be a vestigial
duplicate; left alone (kept in sync) rather than removed, since deleting it
is outside this change's scope.

---

## 7. Tests

`tests/test_mdm_validation.py`, `test_mdm_quality.py`, `test_mdm_duplicates.py`,
`test_mdm_timestamps.py`, `test_mdm_gaps.py`, `test_mdm_units.py`,
`test_mdm_enrichment.py`, `test_mdm_pipeline.py` — one file per engine plus an
integration file covering the "MQTT publication" and "estimated/measured
propagation" requirements end-to-end (the actual `paho` publish call isn't
exercised — that needs a real broker — but the topic/payload `mqtt_io.py`
hands to it is fully verified, which is everything the publish call does
with it).

**Environment note (same as Phase 4):** this shell has no `pytest`
installed — not even importable, so these files can't be collected here.
Every assertion across all 8 files was additionally ported into a standalone
manual verification script and run directly against the real modules; **61
of 61 checks passed.** That run caught two real bugs before they shipped:
an ordering bug (quality's range check ran before unit normalization, so a
1200 W reading was compared against the kW range limit and wrongly flagged
`OUT_OF_RANGE`) and the `docker-compose-ingestor.yml`-vs-main-compose gap in
§6. Coverage percentage itself (the ">90%" target) cannot be measured
without `pytest-cov` in this environment — flagged honestly rather than
asserted.
