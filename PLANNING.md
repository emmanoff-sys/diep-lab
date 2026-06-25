# PLANNING — Integration Gap Roadmap (OPC UA, MDM, CIM/IEC 61968)

Decision record for the three standards-based integration layers currently
missing from DIEP. Companion to the ami-ingest (DLMS/COSEM) work on
`feature/dlms-driver`. Documentation only — no code.

## Sequencing

1. **ami-ingest must finish first.** Phase 2 (HDLC transport) → Phase 4 (MQTT
   contract alignment) must complete **before OPC UA or CIM/IEC 61968 work
   starts.** Both depend on a *pinned* MQTT/Kafka message schema that **does not
   exist yet** — DIEP's payloads are currently ad hoc JSON and the downstream
   consumer contract has not been located/pinned. "DIEP's existing schema"
   cannot be assumed by the later layers.

2. **MDM VEE *tuning* is gated on ami-ingest's real-meter validation**, not on
   "MDM built." MDM may be *built* against synthetic/simulator data, but it must
   **not be treated as billing/outage-ready** until real meter data flows and
   VEE thresholds are calibrated against it. (ami-ingest's DLMS encoding is
   currently a minimal, not-yet-meter-validated subset — see
   `drivers/dlms/VALIDATION.md`.)

## Cross-layer correctness contract

3. **The estimated/measured flag on MDM output is a hard cross-layer contract.**
   ADMS state estimation consumes meter data and must **not** silently treat
   MDM-estimated values as ground truth. In any future MDM scoping, flag this as
   a **correctness requirement spanning MDM → ADMS**, not an internal MDM field.

## Build / scoping shape

4. **The three future layers need three different prompt skeletons**, not copies
   of the ami-ingest Phase 1–6 template:
   - **OPC UA** = driver pattern — another `drivers/<proto>/` `BaseDriver`
     package reusing Runner / `edge_agent` / `MqttTransport` (like
     `drivers/dlms`).
   - **MDM** = Kafka consumer + DB writer + admin API (shape closer to
     `ingestor/` or a FastAPI service; not a field driver).
   - **CIM / IEC 61968** = cross-cutting translation + schema-validation layer
     at the publish boundary (not a single service).

## Risk to budget for

5. **CIM tooling risk.** Python tooling for IEC 61968-9 / CGMES is thin and
   partly Java/Eclipse-based. Budget discovery time for this the way the
   defective `gurux-dlms` 1.0.200 release consumed ami-ingest Phase 1. Each
   layer's Phase 0 should be *"validate the primary library actually works in
   this environment against a simulator"* before building on it.

---

**Overall order:** ami-ingest (finish) → MDM (build; gate tuning on real data)
→ OPC UA (parallelizable; driver pattern) → CIM/IEC 61968 (last, once the
underlying data is stable enough to standardize).

## Addendum, 2026-06-25 — OPC UA built at `services/opcua/`, not `drivers/opcua/`

Item 4 above called OPC UA "another `drivers/<proto>/` `BaseDriver` package
reusing Runner / `edge_agent` / `MqttTransport` (like `drivers/dlms`)." The
Phases 1–3 sprint that actually built it explicitly specified
`services/opcua/` and explicitly excluded MQTT/Kafka publishing from this
phase's scope ("the connector should terminate after producing validated
internal measurements... publishing will be implemented in the next
sprint"). Given that exclusion, there is nothing to reuse Runner/
`MqttTransport` *for* yet — the driver-pattern rationale in item 4 was
specifically about reusing the publish path, which doesn't exist in this
phase. The connector instead followed the MDM service's shape (async
service, stdlib health/metrics endpoint, no FastAPI) since that's the
closer structural match for "owns its own async lifecycle, publishes
nothing yet."

**This is a real, intentional divergence from item 4, not an oversight** —
recorded here so the next reader doesn't assume `drivers/opcua/` exists or
search for it. If/when the next sprint adds MQTT/Kafka publishing, revisit
whether to keep `services/opcua/` as-is (publish from the service directly,
matching MDM's `mqtt_io.py` pattern) or fold it into the `drivers/`
Runner/`BaseDriver`/`MqttTransport` pattern at that point — both are
plausible; not decided here. See `services/opcua/VALIDATION.md` for what in
the Phases 1–3 build is genuinely verified vs. faked-against-asyncua's
documented surface (asyncua is not installed in this dev environment, unlike
Phase 0's discovery pass).
