# PAR-002 — Phase 2 Architecture & Deployment Readiness Review
## DAEP / RE-OS ADMS Programme

**Document ID:** PAR-002-PHASE-2-ARCHITECTURE-AND-DEPLOYMENT-READINESS-REVIEW
**Programme:** DAEP / RE-OS Advanced Distribution Management System
**Review Type:** Programme Architecture Review
**Baseline Under Review:** `develop/v1.1 @ e55b0b8` (post WP-011-04 closure)
**Review Date:** 2026-07-10
**Conducted By:** Programme Engineering Manager / Release Engineering Lead
(AI-assisted: Claude Sonnet 4.6 — assessment only; no engineering authorised)
**Status:** COMPLETE — APPROVED FOR PROGRAMME DECISION

---

## 1. PAR-002 Executive Summary

The RE-OS ADMS platform has reached a structurally significant milestone. All authorised
Phase 2 connector work under EPIC-011 is complete and baseline-integrated: the SCADA
integration framework (WP-011-02), GIS topology adapter (WP-011-03), and AMI metering
connector (WP-011-04) are merged, governed, and validated at 954 passing tests with zero
active quality-gate findings. The platform's engineering foundation — spanning Production
ADMS Runtime (WP-006), Topology Services (WP-007), Operational Network State (WP-008),
Operations and Decision Support (WP-009), Operational Intelligence (WP-010), Operator
Applications (EPIC-013 phase 1), and the full External Integration connector suite
(EPIC-011) — is coherent, layered, and well-tested.

The review identifies three material gaps that must be resolved before production deployment:

1. **Reliability primitives parity.** `EventBuffer`, `DeadLetterQueue`, and
   `ExponentialBackoff` exist only in `scada_connector/reliability.py`. Neither the GIS
   nor the AMI connector implements equivalent buffering or retry semantics. Under network
   interruption, events from these connectors are silently dropped rather than queued.

2. **Connector observability.** All three connectors carry only an in-process
   `ConnectorHealth` dataclass. No Prometheus metrics, no structured HTTP health endpoint,
   and no per-connector operational logging pipeline are implemented. Operators have no
   visibility into connector state without direct process inspection.

3. **Production deployment is explicitly denied.** `CUTOVER_PLAN_DRAFT.md` records
   MW2=NO-GO and Production=DENIED as of 2026-06-24. No authorised deployment artefacts
   exist and the host VM infrastructure has a documented write-ack/persistence gap
   (kafka/redis/timescaledb). A dedicated deployment readiness work package is required
   before any operational use.

**Strategic recommendation:** Authorise Option D (Deployment and Operational Rollout) as
the immediate next programme phase under a new PAO (PAO-026). This resolves all three gaps,
establishes production-ready connector deployments, and is a hard dependency on all
subsequent analytics epics. Option B (EPIC-012 Advanced Grid Analytics) should follow as
the next engineering epic — the `adms_operational_intelligence` layer is feature-complete
and provides the correct analytical substrate for state estimation and power flow analytics.

---

## 2. Architecture Assessment Report

### 2.1 Platform Layer Map

The integrated platform is organised in five distinct horizontal layers:

```
┌─────────────────────────────────────────────────────────────────────┐
│  OPERATOR APPLICATIONS (EPIC-013)                                   │
│  adms_operator_api  •  adms_operator_ui                             │
├─────────────────────────────────────────────────────────────────────┤
│  OPERATIONAL INTELLIGENCE (WP-010)                                  │
│  adms_operational_intelligence                                      │
│  ContingencyAnalysisService  FaultLocationAssistanceService         │
│  RestorationOptimisationService  ScenarioSimulationService          │
│  DecisionExplanationService  RuleEngine                             │
├─────────────────────────────────────────────────────────────────────┤
│  OPERATIONAL STATE & OPERATIONS (WP-008 / WP-009)                  │
│  adms_operational_state  •  adms_operations                         │
├─────────────────────────────────────────────────────────────────────┤
│  TOPOLOGY & RUNTIME FOUNDATION (WP-006 / WP-007)                   │
│  adms_topology_import  •  adms_topology_services                    │
│  cim  •  audit-service  •  identity-service  •  mdm  •  opcua      │
├─────────────────────────────────────────────────────────────────────┤
│  EXTERNAL INTEGRATION (EPIC-011)                                    │
│  scada_connector  •  gis_connector  •  ami_connector                │
└─────────────────────────────────────────────────────────────────────┘
```

**Dependency direction: CORRECT.** Services in upper layers do not import from lower-layer
consumer services or from connectors. All data flows are additive: connectors publish
canonical events/topology into the platform; no platform layer calls back into a connector.

### 2.2 Layer Boundary Compliance

| Boundary | Assessment | Finding |
|----------|------------|---------|
| Connectors → Platform | Data-only ingestion via canonical contracts | COMPLIANT |
| Operations → State | Operations consume state; do not write back outside `operational_state` | COMPLIANT |
| Intelligence → Operations | Advisory only — `IntelligenceAssessment` not actioned without operator decision | COMPLIANT |
| Operator API → Intelligence | Aggregation at `OperatorApi` facade; no direct service coupling | COMPLIANT |
| Connector → Identity service | Identity connectors independent of `identity-service` domain | COMPLIANT |
| P5 analytics (`fastapi/dms/`) | Pre-Phase 2 legacy path; isolated from `services/` | ATTENTION (see §2.5) |

### 2.3 Business Logic Separation

The connector-as-translator pattern (OA-069) is correctly implemented across all three
connectors. Business logic — fault detection, switching recommendations, contingency
analysis — lives exclusively in `adms_operational_intelligence` and `adms_operations`.
No routing decisions, restoration logic, or contingency rules are present in any connector.
This separation is a programme architecture strength.

### 2.4 Operator API Aggregation

`adms_operator_api` provides a `OperatorApi` facade with versioned envelopes (`v1`).
Authentication, HTTP handling, and domain models are cleanly separated into `auth`,
`http`, and `models` sub-packages. The operator service layer correctly aggregates from
intelligence and operations without reaching into lower topology or connector modules.

### 2.5 P5 Analytics Legacy Path

Tests in `tests/test_p5_state_estimation.py`, `tests/test_p5_powerflow.py`, and related
suites import from `fastapi/dms/` — the pre-Phase 2 legacy architecture. These 34 tests
pass (confirmed on baseline `e55b0b8`) but reference a path that pre-dates the `services/`
layer restructuring. **If EPIC-012 (Advanced Grid Analytics) is authorised, these P5
analytics capabilities must be re-architectured under the `services/` layer and integrated
with the existing `adms_operational_intelligence` foundation — they cannot simply be
promoted from `fastapi/dms/` as-is.**

---

## 3. External Integration Assessment

### 3.1 Connector Framework Consistency

All three connectors correctly inherit from `AbstractConnectorSession` and raise
`SCADAConnectorError` (or a typed subclass) on failure. The framework re-export chain is
implemented in all connectors:

| Symbol | scada_connector | gis_connector | ami_connector |
|--------|:--------------:|:-------------:|:-------------:|
| `AbstractConnectorSession` | ✓ (defines) | ✓ (re-exports) | ✓ (re-exports) |
| `SCADAConnectorError` | ✓ (defines) | ✓ (re-exports) | ✓ (re-exports) |
| `ConnectorConfig` | ✓ | ✓ | ✓ |
| `ConnectorHealth` | ✓ | ✓ | ✓ |
| `ConnectorLifecycle` | ✓ | ✓ | ✓ |
| `ConnectorRegistry` | ✓ | ✓ | ✓ |
| `TLSContext` | ✓ | ✓ | ✓ |
| `EventBuffer` / `DeadLetterQueue` | ✓ (defines) | **✗ not used** | **✗ not used** |
| `ExponentialBackoff` | ✓ (defines) | **✗ not used** | **✗ not used** |
| `ConnectorPipeline` | ✓ (defines) | **✗ not used** | **✗ not used** |

The reliability primitives gap is the most significant cross-connector consistency finding.

### 3.2 Canonical Contract Conformance

WP-011-01 canonical contracts (OA-070 v1.0) are correctly implemented:

- `OperationalEvent` with `event_types`: `breaker_operation` (SCADA), `alarm` (GIS/AMI),
  `telemetry` (SCADA/AMI) — all mapping paths verified by test suite.
- `MappedTopology` v1.0 — GIS-specific; not applicable to SCADA/AMI.
- Strict payload subset extraction enforced in AMI connector: only the canonical required
  key per event type (`available` for alarm, `energized` for telemetry) is forwarded;
  extra AMI fields are discarded at translation boundary. This is the correct behaviour
  (connector-as-translator, OA-069).

### 3.3 Identity Resolution

Progressive enhancement pattern observed — each successive connector added capability:

| Feature | SCADA `AssetIdentityMap` | GIS `GISAssetIdentityMap` | AMI `AMIMeterIdentityMap` |
|---------|:------------------------:|:-------------------------:|:------------------------:|
| `resolve(id)` | ✓ | ✓ | ✓ |
| `detect_ambiguities()` | ✗ | ✓ | ✓ |
| `detect_missing()` | ✗ | ✓ | ✓ |
| Fail-fast `known_asset_ids` validation | ✗ | ✗ | ✓ |

The SCADA `AssetIdentityMap` was designed for the simpler one-to-one SCADA use case where
asset IDs are authoritative by construction. The richer validation in GIS and AMI is
appropriate to the noisier identity environments those connectors operate in. This is a
considered design choice, not a defect. However, if SCADA is extended to multi-source or
multi-site scenarios in future, `detect_ambiguities()` and `detect_missing()` should be
added to maintain parity.

### 3.4 Reconciliation

The GIS connector produces reconciliation reports when topology mapping produces
unresolvable assets. RISK-010 (reconciliation report backlog accumulation) is open at LOW
severity with an advisory-only mitigation (operational governance process). No automated
backlog purge or staleness alerting is implemented. This is acceptable for current scope
but must be addressed before production deployment at scale.

### 3.5 Replay Capability

Both GIS and AMI connectors implement replay stubs (`GisStub` in
`scada_connector/harness/stubs.py`, `AmiStub` in `ami_connector/harness.py`). Both
implement `from_messages()`, `next_event()`, `exhausted`, and `remaining`. The placement
of `GisStub` inside `scada_connector/harness/` rather than `gis_connector/harness/` is a
minor module boundary inconsistency but does not affect runtime behaviour. SCADA uses
`SessionRecorder` and `SessionReplayer` for the same deterministic validation purpose.

### 3.6 Security Architecture

mTLS client certificates (OA-072), data diode OT/IT boundary, and environment-injected
secrets are specified in WP-011-01 and implemented via `TLSContext` in WP-011-02.
RISK-009 (data diode staging validation gap) remains open — this is correct; the gap
cannot be resolved by library-level code and requires a staging deployment environment
with an OT data diode to validate. No connector imports credentials or certificates at
module scope; all secret material is passed at `TLSContext` construction via
environment-resolved paths. This is the correct pattern.

**Diagnostics/Logging/Buffering/Retry gap:** As noted in §3.1, GIS and AMI connectors
have no retry logic, no event buffering, and no dead-letter queue. Network interruptions
result in silent event loss. This must be resolved before production operation.

---

## 4. Operational Readiness Assessment

### 4.1 Observability Maturity

| Component | Prometheus | Structured Logging | HTTP Health | Tracing |
|-----------|:----------:|:-----------------:|:-----------:|:-------:|
| `adms_topology_import` | ✓ `metrics.py` | ✓ `logging.py`, `observability.py` | ✓ scheduler/health | — |
| `adms_topology_services` | — | ✓ `tracing.py` | — | ✓ |
| `adms_operator_api` | — | ✓ | ✓ | — |
| `scada_connector` | ✗ | ✗ | ✗ (in-process only) | ✗ |
| `gis_connector` | ✗ | ✗ | ✗ (in-process only) | ✗ |
| `ami_connector` | ✗ | ✗ | ✗ (in-process only) | ✗ |
| `mdm` | ✓ | — | ✓ | — |
| `opcua` | ✓ | — | ✓ | — |

The connectors are the observability gap. `ConnectorHealth` is a dataclass with a
`healthy` property — it is read only by in-process test code, not exposed to any
operational monitoring system. An operator cannot determine whether a connector is active,
healthy, or in an error state without attaching to the process directly.

### 4.2 SLO / SLA Definition

No formal SLOs are defined for the current baseline. This is appropriate for a
pre-production platform but must be addressed before production deployment. The following
minimum SLO candidates should be defined in a deployment readiness WP:

- Connector event ingestion latency (p99 target)
- Topology import cycle time
- Operator API response time (p95 target)
- Operational state update propagation latency

### 4.3 Runbook Availability

No operational runbooks are present in the repository beyond `CUTOVER_PLAN_DRAFT.md`,
which is a planning document, not an operational runbook. Runbooks for connector startup,
connector failure recovery, topology import failure, and operator API degraded-mode
handling must be authored before production.

### 4.4 Backup / Recovery and Disaster Recovery

The host VM infrastructure has a documented write-ack/persistence gap across kafka,
redis, and timescaledb (RISK from prior incident). This is a host-level infrastructure
concern, not an application architecture concern. Application-level write guarantees depend
on the infrastructure layer being stable. This gap must be resolved and independently
verified before production data is persisted.

No application-level backup or DR procedures are currently documented.

### 4.5 Certificate Management

`TLSContext` accepts certificate paths via environment-injected configuration. The
certificate rotation process (how often, who rotates, what alerts on expiry) is not
specified. Certificate lifecycle management must be documented before production.

---

## 5. Deployment Readiness Assessment

### 5.1 Production Readiness Status

**PRODUCTION DEPLOYMENT IS DENIED.** `CUTOVER_PLAN_DRAFT.md` records:

```
MW2 = NO-GO
Production = DENIED
DO-NOT-GO-LIVE
```

This is the authoritative deployment status as of 2026-06-24. Nothing in this review
changes that status. The production deployment gate requires explicit, separate
programme authorisation.

### 5.2 Infrastructure Prerequisites

The following infrastructure prerequisites are open and unresolved:

| Prerequisite | Status |
|---|---|
| Host VM write-ack/persistence gap (kafka/redis/timescaledb) | OPEN — host-level |
| Registry credentials for Docker image push | OPEN |
| Staging VM provisioning | OPEN |
| DAST baseline (`.zap/rules.tsv`) | OPEN |
| Rollback drill completed | NOT STARTED |
| Connector deployment artefacts | NOT AUTHORED |
| Health endpoint implementation in connectors | NOT IMPLEMENTED |
| Reliability primitives in GIS/AMI connectors | NOT IMPLEMENTED |

### 5.3 Deployment Architecture

The current baseline produces Python library packages for all `services/` modules.
Connector deployment artefacts (Dockerfiles, compose configuration, systemd units, or
Kubernetes manifests) do not exist in the repository as production-ready assets. Release 2
Docker validation tests exist and are classified but explicitly skip on pull requests by
design — indicating the Docker build path has not been exercised in production-equivalent
conditions.

### 5.4 Monitoring Maturity

Prometheus integration exists in `adms_topology_import`, `mdm`, and `opcua`. It does not
exist in the three connectors or in the operator API layer. A unified monitoring
dashboard cannot be built until connector observability is implemented.

### 5.5 Deployment Procedures

No documented deployment procedure exists for the Phase 2 `services/` layer. The
`CUTOVER_PLAN_DRAFT.md` pre-dates the EPIC-011 connector work and references a
pre-Phase-2 architectural model. A new deployment procedure document must be authored as
part of any deployment readiness work package.

---

## 6. Strategic Roadmap Recommendation

### 6.1 Options Summary

The PAR-002 authorisation scope presented four strategic options:

| Option | Title | Description |
|--------|-------|-------------|
| A | OMS Historical Correlation | Extend EPIC-011 connectors to store and correlate historical operational events with OMS records |
| B | EPIC-012 Advanced Grid Analytics | State estimation, power flow analysis, Volt/VAR optimisation, advanced contingency ranking |
| C | EPIC-014 Digital Twin & Forecasting | Physics-based network model, predictive fault analytics, AI-assisted load forecasting |
| D | Deployment and Operational Rollout | Production-readiness work, connector reliability, observability, staging deployment, operational runbooks |

### 6.2 Option Assessment

**Option D — Deployment and Operational Rollout**

*Dependency status: HARD PREREQUISITE for all other options.*

Without a deployed, observable, and operationally managed platform, no analytics capability
delivers business value. The three material gaps identified in §1 (reliability primitives,
connector observability, production deployment denial) are all resolved by Option D.
Options A, B, and C all require live operational data flowing through deployed connectors
— none of which exists until Option D is executed.

Assessment: **HIGHEST PRIORITY — must precede all other options.**

**Option B — EPIC-012 Advanced Grid Analytics**

*Dependency status: Requires Option D completion (deployed platform with live data).*

The `adms_operational_intelligence` layer is the strongest technical argument for Option B:
`ContingencyAnalysisService`, `FaultLocationAssistanceService`,
`RestorationOptimisationService`, `ScenarioSimulationService`, and `DecisionExplanationService`
are all implemented and tested (291 analytical tests passing as of WP-010). P5 analytics
primitives exist in `tests/test_p5_state_estimation.py` and `tests/test_p5_powerflow.py`
(34 tests, all passing) — though these reference the pre-Phase-2 `fastapi/dms/` path and
cannot be promoted without re-architecturing under `services/`.

Option B is aligned with the PAR-001 approved roadmap sequence (EPIC-011 → EPIC-012) and
represents the highest-value near-term capability extension once the platform is deployed.

Assessment: **SECOND PRIORITY — authorise after Option D milestone completion.**

**Option A — OMS Historical Correlation**

*Dependency status: Requires Option D and a stable connector data pipeline.*

Option A extends the EPIC-011 connector framework to persist and correlate historical
events. It builds naturally on the existing canonical contract model (`OperationalEvent`
stores `observed_at` timestamps) and the `adms_operational_state` repository pattern.
However, it requires a reliable connector pipeline (Option D gap) and a time-series
persistence layer (TimescaleDB, whose host-level stability is currently flagged). This
should not be authorised until Option D is complete and the infrastructure stability gap
is independently verified.

Assessment: **THIRD PRIORITY — authorise after deployment is stable and RISK-009 is closed.**

**Option C — EPIC-014 Digital Twin & Forecasting**

*Dependency status: Requires live operational data for minimum 6–12 months; requires
Options A and B as analytical foundation.*

Digital twin and forecasting capabilities require a historical operational data corpus
to calibrate the physics model and train the forecasting layer. This corpus cannot exist
until the platform is live and stable. Option C is the correct long-term strategic
direction but is premature to authorise now.

Assessment: **LONG-TERM — do not authorise until platform has been live for at least
two operational seasons with confirmed data quality.**

### 6.3 Recommended Programme Sequence

```
[NOW]     PAO-026 → Option D: Deployment and Operational Rollout
            ├─ Connector reliability (EventBuffer/DLQ/ExponentialBackoff in GIS+AMI)
            ├─ Connector observability (Prometheus + HTTP health endpoints)
            ├─ Infrastructure stability verification (host VM gap)
            ├─ Staging deployment and DR drill
            ├─ Operational runbooks
            └─ Production deployment gate — formal sign-off required

[NEXT]    PAO-027 → Option B: EPIC-012 Advanced Grid Analytics
            ├─ Re-architect P5 state estimation under services/
            ├─ Power flow analysis service
            ├─ Volt/VAR optimisation service
            └─ Integration with adms_operational_intelligence analytics layer

[LATER]   PAO-028 → Option A: OMS Historical Correlation
            └─ Historical event correlation and OMS audit trail

[FUTURE]  Option C: EPIC-014 Digital Twin & Forecasting
            └─ Requires ≥12 months live operational data baseline
```

---

## 7. Risk Assessment

### 7.1 New Risks Identified by PAR-002

**RISK-PAR002-01 — Connector Reliability Gap (GIS and AMI)**

| Field | Value |
|-------|-------|
| Category | Architecture / Reliability |
| Description | `EventBuffer`, `DeadLetterQueue`, and `ExponentialBackoff` are implemented in `scada_connector/reliability.py` but are not used by `gis_connector` or `ami_connector`. Under network interruption or transient infrastructure failure, topology and metering events from these connectors are silently dropped with no retry and no dead-letter record. |
| Probability | 4 (Likely — network interruptions are routine in OT environments) |
| Impact | 4 (Major — silent data loss in a metering/topology platform is operationally critical) |
| **Risk Score** | **16 (HIGH)** |
| Owner | Connector Engineering Lead |
| Mitigation | Authorise connector reliability extension under Option D (PAO-026). Apply `ConnectorPipeline` wrapping `EventBuffer` and `DeadLetterQueue` to both GIS and AMI connector sessions. Extend reliability.py primitives to be connector-agnostic before GIS/AMI use. |
| Status | OPEN — identified by PAR-002 |

**RISK-PAR002-02 — Connector Observability Gap**

| Field | Value |
|-------|-------|
| Category | Operational |
| Description | All three connectors expose only an in-process `ConnectorHealth` dataclass with no Prometheus metrics, no HTTP health endpoint, and no structured operational logging. Operators cannot monitor connector state without direct process inspection. |
| Probability | 5 (Almost Certain — this is a confirmed architectural absence, not a probability) |
| Impact | 3 (Moderate — invisible failures lead to delayed incident response; direct process inspection is not operationally viable at scale) |
| **Risk Score** | **15 (HIGH)** |
| Owner | Platform Observability Lead |
| Mitigation | Authorise HTTP health endpoint implementation and Prometheus metric emission for all three connectors under Option D (PAO-026). Pattern from `adms_topology_import/metrics.py` and `mdm` should be reused. |
| Status | OPEN — identified by PAR-002 |

**RISK-PAR002-03 — P5 Analytics Legacy Path Promotion Risk**

| Field | Value |
|-------|-------|
| Category | Architecture |
| Description | P5 analytics (`test_p5_state_estimation.py`, `test_p5_powerflow.py`, etc.) import from `fastapi/dms/` — a pre-Phase-2 path that predates the `services/` architecture restructuring. If EPIC-012 is authorised without explicitly re-architecturing this code, P5 capabilities may be promoted from a path that is architecturally inconsistent with the current platform. |
| Probability | 3 (Possible — risk materialises only if EPIC-012 is authorised without explicit re-architecture scope) |
| Impact | 4 (Major — re-architecturing a live analytics service post-deployment is expensive) |
| **Risk Score** | **12 (HIGH)** |
| Owner | Platform Architect |
| Mitigation | EPIC-012 WP scope must explicitly include re-architecturing P5 analytics under `services/adms_grid_analytics/` (or equivalent), with integration into `adms_operational_intelligence`. The `fastapi/dms/` path must not be promoted. |
| Status | OPEN — identified by PAR-002 |

### 7.2 Existing Open Risks — Status

| Risk | Title | Score | Status | PAR-002 Note |
|------|-------|-------|--------|--------------|
| RISK-001 | Directory Structure Drift | 9 MEDIUM | OPEN | No change |
| RISK-002 | DLMS Test Environment Gap | 16 HIGH | OPEN | No change |
| RISK-003 | Sibling Branch Divergence | — | OPEN | No change; predates EPIC-011 |
| RISK-009 | Data Diode Staging Validation Gap | LOW | OPEN | Must close under Option D staging |
| RISK-010 | GIS Reconciliation Report Backlog | LOW | OPEN | No change; operational governance in place |

No existing risks are closed by this review. RISK-009 and RISK-010 must be addressed
under the Option D deployment readiness programme.

---

## 8. Governance Recommendation

### 8.1 EPIC-011 Formal Programme Closure

EPIC-011 — External Utility Integrations — is engineering-complete. All four authorised
work packages are merged and baseline-integrated:

| WP | Title | Status | Merge Commit |
|----|-------|--------|-------------|
| WP-011-01 | External Integration Architecture and Canonical Contracts | COMPLETED / MERGED | `135647d5b6e1da44d78e4d75c8df96c81ef1955f` |
| WP-011-02 | SCADA Integration Framework | COMPLETED / MERGED | `02bf256a911cb931ea764bc1c6bb9e495a4219c7` |
| WP-011-03 | GIS Topology Adapter | COMPLETED / MERGED | `2aabfdfca2463e7e6add46fb79d4774018b85476` |
| WP-011-04 | AMI Metering Connector | COMPLETED / MERGED | `848f717f65401c7f07801f6faaaf5d711568f6f5` |

**Recommendation:** EPIC-011 should be formally closed in the EECR. No further
engineering shall be authorised under EPIC-011 scope without a new Programme Architecture
Review and PAO. Future connector enhancements (reliability, observability) should be
scoped under Option D / PAO-026.

### 8.2 Baseline Freeze Recommendation

The current `develop/v1.1 @ e55b0b8` baseline is stable, validated, and suitable for
freeze as the Phase 2 engineering baseline. **Recommended action:** Update the EECR
baseline record to designate `e55b0b8` as the EPIC-011-COMPLETE baseline freeze point.
No further feature branches should be merged to `develop/v1.1` until PAO-026 Option D
work packages begin advancing through the governance gate.

### 8.3 Architecture Review Register — PAR-002 Entry

PAR-002 shall be recorded in the Architecture Review Register as a programme-level
review (not a WP-level AR). Recommend next sequential AR number after AR-068 be reserved
for PAR-002 (AR-069 if that slot is available, or the next available slot).

The following findings are formally registered:

| Finding ID | Severity | Description | Resolution |
|------------|----------|-------------|------------|
| F-PAR002-01 | HIGH | Connector reliability gap — no EventBuffer/DLQ/retry in GIS/AMI | Option D PAO-026 |
| F-PAR002-02 | HIGH | Connector observability gap — no Prometheus/HTTP health in connectors | Option D PAO-026 |
| F-PAR002-03 | HIGH | P5 analytics legacy `fastapi/dms/` path must not be promoted as-is | EPIC-012 scoping |
| F-PAR002-04 | MEDIUM | SCADA `AssetIdentityMap` lacks `detect_ambiguities()`/`detect_missing()` | Option B or future PAO |
| F-PAR002-05 | MEDIUM | GIS reconciliation backlog has no automated staleness alerting | Option D PAO-026 |
| F-PAR002-06 | LOW | `GisStub` placed in `scada_connector/harness/` instead of `gis_connector/` | Option B refactor |
| F-PAR002-07 | INFO | Certificate lifecycle management not documented | Option D PAO-026 |

---

## 9. Recommended Next Programme Authorisation Order

### PAO-026 — Option D: Deployment and Operational Rollout

**Recommended PAO Title:** PAO-026 — Connector Reliability, Observability, and
Deployment Readiness

**Recommended Authorising Authority:** Programme Engineering Manager

**Scope:**

PAO-026 shall authorise engineering work across three delivery tracks:

**Track 1 — Connector Reliability (highest priority)**
- Extend `EventBuffer`, `DeadLetterQueue`, and `ExponentialBackoff` from
  `scada_connector/reliability.py` to be connector-agnostic (move to framework or
  duplicate with shared interface)
- Apply `ConnectorPipeline` wrapping to `GISConnectorSession` and `AMIConnectorSession`
- Define configurable buffer depth, retry policy, and dead-letter log destination
- Add integration tests for connector failure and recovery paths

**Track 2 — Connector Observability (high priority)**
- Implement Prometheus metrics emission in all three connectors (events processed, events
  dropped, connection health, queue depth)
- Implement HTTP health endpoint (`/health`) per connector, returning `ConnectorHealth`
  as JSON
- Implement structured operational logging (startup, shutdown, event acceptance, rejection)
- Pattern from `adms_topology_import/metrics.py` and `mdm/health.py`

**Track 3 — Deployment Readiness (production gate)**
- Author production Dockerfiles for connector processes
- Author `docker-compose.production.yml` (or equivalent) for the full integrated platform
- Close infrastructure prerequisites: host VM stability verification, registry credentials,
  staging VM provisioning, DAST baseline
- Author operational runbooks for: connector startup/shutdown, connector failure recovery,
  topology import failure, operator API degraded mode
- Define minimum SLOs for production
- Complete rollback drill on staging environment
- Formally close RISK-009 (data diode staging validation — exercise the data diode path
  in staging)
- Obtain formal production deployment authorisation (NOT self-issued by AI; must be
  issued by Programme Engineering Manager after staging validation)

**What PAO-026 does NOT authorise:**
- New connector types (beyond existing SCADA/GIS/AMI)
- Analytics capabilities (EPIC-012 scope)
- Changes to canonical contracts (WP-011-01 scope — frozen)
- Modifications to the operational intelligence layer
- Any production deployment (production deployment requires explicit human-issued sign-off
  after staging validation completes)

**Recommended PAO-026 Quality Gates:**
- All three connectors: 0 ruff/black/isort/bandit findings
- Connector Prometheus metrics: verified in staging via Grafana
- Connector HTTP health endpoint: verified by automated health check in CI
- Staging deployment: full end-to-end connector event flow validated
- Rollback drill: completed and documented
- Full regression: ≥ 954 tests passing (existing baseline; must not regress)
- RISK-009: CLOSED

---

## Appendix A — Baseline Evidence Summary

| Evidence | Value |
|---------|-------|
| Baseline commit | `develop/v1.1 @ e55b0b8` |
| Non-infrastructure tests | 954 passed, 82 skipped |
| AMI connector tests | 78 passed |
| GIS connector tests | 78 passed |
| SCADA connector tests | 55 passed |
| P5 analytics tests (legacy path) | 34 passed |
| Operational intelligence tests | 48 passed (WP-010) |
| Operations tests | 45 passed (WP-009) |
| Quality gates | Ruff 0 / Black 0 / isort 0 / Bandit 0 |
| Open architecture reviews | None (AR-066 through AR-068 all closed) |
| Open HIGH risks | RISK-002 (DLMS), RISK-PAR002-01, RISK-PAR002-02, RISK-PAR002-03 |
| Production deployment status | DENIED (CUTOVER_PLAN_DRAFT.md) |

---

## Appendix B — Services Layer Inventory

| Service Package | Role | Layer |
|----------------|------|-------|
| `adms_operational_intelligence` | Contingency, fault location, restoration, simulation, rules, explanation | Intelligence |
| `adms_operational_state` | State engine, events, models, repository, validation | State |
| `adms_operations` | Advisory, audit, detection, isolation, restoration, switching | Operations |
| `adms_operator_api` | REST API facade, versioned envelopes, auth, models | Operator |
| `adms_operator_ui` | UI application, components, framework, workspaces | Operator |
| `adms_topology_import` | Observability stack, scheduler, worker, logging, metrics | Topology |
| `adms_topology_services` | Analysis, graph, outage, query, simulation, tracing | Topology |
| `ami_connector` | AMI metering event ingestion (EPIC-011 WP-011-04) | Integration |
| `gis_connector` | GIS topology import (EPIC-011 WP-011-03) | Integration |
| `scada_connector` | SCADA framework + connector (EPIC-011 WP-011-02) | Integration |
| `audit-service` | Audit trail microservice | Foundation |
| `cim` | CIM/IEC 61968 models and import/export | Foundation |
| `identity-service` | Identity management microservice | Foundation |
| `mdm` | Metering data management, Prometheus metrics | Foundation |
| `opcua` | OPC-UA integration, Prometheus metrics | Foundation |

---

*PAR-002 review conducted 2026-07-10. Baseline: `develop/v1.1 @ e55b0b8`.*
*Assessment only — no engineering, deployment, or architecture baseline changes are
authorised by this document. All findings and recommendations require a separately
issued Programme Authorisation Order before implementation may begin.*
