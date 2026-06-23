# DIEP Phase 24 — Production Cutover Checklist (MW2)

A printable checklist for an MW2 production cutover. Items map to Phase 24
automation where one exists; the rest are operator attestations recorded via the
`checklist` field on `POST /deployment/cutover/start`.

Legend: **[auto]** verified by the framework · **[attest]** operator confirms.

---

## A. T-24h — readiness

- [ ] **[auto]** MW2 readiness assessment is PASS (`scripts/run_mw2_readiness_check.py`).
- [ ] **[attest]** Change ticket approved; window scheduled and communicated.
- [ ] **[attest]** Rollback plan reviewed ([PHASE24_ROLLBACK_PROCEDURE.md](PHASE24_ROLLBACK_PROCEDURE.md)).
- [ ] **[attest]** On-call + NOC notified of the window.

## B. T-1h — pre-cutover gate (`GET /deployment/status?live=true`)

- [ ] **[auto]** `mw2_readiness_certification` — PASS.
- [ ] **[auto]** `critical_containers_healthy` — all critical containers up.
- [ ] **[auto]** `database_backups_present` — recent backup artifact exists.
- [ ] **[auto]** `minio_archive_accessible` — MinIO archive reachable.
- [ ] **[auto]** `kafka_health` — Kafka broker/exporter healthy.
- [ ] **[auto]** `redis_health` — Redis reachable.
- [ ] **[attest]** Maintenance mode / customer comms in place (if applicable).

> Pre-cutover gate must be **PASS** before starting.

## C. T-0 — start (`POST /deployment/cutover/start`)

- [ ] **[auto]** Deployment ID + timestamp generated.
- [ ] **[auto]** Baseline snapshot captured.
- [ ] **[attest]** Checklist items A/B submitted in the `checklist` field.
- [ ] **[attest]** Execute the change via the standard change procedure.

## D. T+0..n — execution (operator, outside the framework)

- [ ] **[attest]** New release deployed (image tags / migrations applied).
- [ ] **[attest]** Smoke test of the primary user journey.

## E. Post-cutover gate (`POST /deployment/cutover/validate`)

- [ ] **[auto]** `fastapi_readyz` — `/readyz` 200.
- [ ] **[auto]** `portal_login` — portal reachable.
- [ ] **[auto]** `redis_connectivity` — Redis healthy.
- [ ] **[auto]** `kafka_metrics` — Kafka metrics present.
- [ ] **[auto]** `prometheus_targets` — targets up.
- [ ] **[auto]** `grafana_availability` — Grafana healthy.
- [ ] **[auto]** Gate = **GO** (`deployment_status`), score ≥ threshold.

> NO-GO → [rollback](PHASE24_ROLLBACK_PROCEDURE.md).

## F. Close-out

- [ ] **[auto]** Evidence + audit trail persisted (`GET /deployment/status`).
- [ ] **[attest]** Maintenance mode lifted; customers notified of completion.
- [ ] **[attest]** Change ticket updated with the `deployment_id` and outcome.
- [ ] **[attest]** Monitoring confirmed stable for the post-cutover observation window.
