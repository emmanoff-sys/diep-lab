# OA-098 — Staging Deployment Procedure

## Status

APPROVED (PAO-026)

## Scope

End-to-end staging validation procedure for the PAO-026 connector operational
hardening deliverables (OA-096, OA-097). This procedure validates the reliable
connector runtime and observability layer before any further programme authorisation.

Production deployment is not authorised. This procedure is for staging environments
only. MW2 remains NO-GO per CUTOVER_PLAN_DRAFT.md.

## Prerequisites

| Gate | Required Evidence |
| --- | --- |
| Quality gates | ruff, black, bandit, isort all clean on branch HEAD |
| Regression suite | `python3 -m pytest tests/` — PAO-026 scope passes; pre-existing failures unchanged |
| Governance | Feature branch `feature/wp-026-deployment-hardening` reviewed and approved |
| Environment | Staging environment with working TimescaleDB, Redis, Kafka, ingestion API |
| Credentials | Connector endpoint credentials, TLS certificates, identity maps available |

## Procedure

### Step 1 — Confirm deployment candidate

1. Record the deployment commit SHA.
2. Confirm the commit is on `feature/wp-026-deployment-hardening` or a successor
   branch that has been governance-reviewed.
3. Confirm that all quality gates have been executed against this exact commit.

### Step 2 — Confirm staging environment baseline

1. Confirm core platform health: database, Redis, Kafka, ingestion API `/readyz`.
2. Confirm no active topology import or governance-restricted operation is running.
3. Record the staging environment baseline state.

### Step 3 — Execute Connector Startup Runbook

Follow `docs/deployment/runbooks/connector-startup.md` in full.

Acceptance gate: All three connectors report `status: UP` within 120 seconds.

### Step 4 — Validate OA-096 reliability

For each connector:

1. Inject a synthetic invalid event or batch (unknown identity, malformed payload).
2. Confirm the event is dead-lettered: DLQ count = 1.
3. Confirm a valid event is processed successfully after the invalid one: no backlog.
4. Confirm buffer overflow handling: if feasible, saturate the buffer and confirm
   oldest-drop behaviour.

Acceptance gate: DLQ accumulates on invalid events only; valid events are unaffected.

### Step 5 — Validate OA-097 observability

For each connector:

1. `GET /health` → 200, JSON body with `connector_id`, `healthy`, event counts.
2. `GET /ready` → 200 when connected, 503 when idle or degraded.
3. `GET /live` → 200 always (including when degraded).
4. `GET /metrics` → 200 with Prometheus text if prometheus_client available,
   or 503 with JSON error body if absent. Either outcome is accepted.
5. `GET /unknown-path` → 404.

Acceptance gate: All five endpoint behaviours confirmed for all three connectors.

### Step 6 — Run PAO-026 regression suite

```
python3 -m pytest tests/test_ami_connector_reliability.py \
    tests/test_gis_connector_reliability.py \
    tests/test_connector_metrics.py \
    tests/test_connector_observability.py -v
```

Acceptance gate: 45/45 tests pass.

### Step 7 — Run full regression suite

```
python3 -m pytest tests/ -q
```

Acceptance gate: No new failures versus the pre-PAO-026 baseline. Pre-existing
failures (`test_cim_api.py`, `test_mdm_pipeline.py`, `test_opcua_*.py`, and
`test_fastapi_telemetry_auth.py` DB errors) are excluded from this gate as they
pre-date the PAO-026 branch.

### Step 8 — Record staging validation evidence

| Field | Value |
| --- | --- |
| Operator / automation identity | |
| Environment | |
| Deployment commit SHA | |
| Startup runbook outcome | |
| OA-096 reliability validation outcome | |
| OA-097 observability validation outcome | |
| PAO-026 test suite result (45 tests) | |
| Full regression suite result | |
| Overall staging outcome | PASS / FAIL / CONDITIONAL |
| Exceptions or follow-up actions | |
| Validation timestamp | |

### Step 9 — Accept or reject

- **PASS**: All gates met. Record as OA-098 staging validation complete.
  Proceed to OA-099 operational readiness validation.
- **FAIL**: Identify root cause. Execute Rollback Procedure if the environment must
  be restored. Record in EECR change log.
- **CONDITIONAL**: Document conditional with specific exceptions and a governed
  resolution plan. Do not proceed to OA-099 without resolving conditional.
