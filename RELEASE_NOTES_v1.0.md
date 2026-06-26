# DIEP Release Notes — v1.0 (Release Candidate, Qualification Baseline)

**Date:** 2026-06-26
**Status:** [VERDICT_PLACEHOLDER] — see `QUALIFICATION_REPORT.md` for full evidence.
**Supersedes:** the 2026-06-13 pilot baseline below this line and the 2026-06-17
`GO_LIVE_AUTHORIZATION_PACKAGE.md` NO-GO — both predate the AMI Contract, MDM,
OPC UA, CIM/IEC 61968, and the HA/performance/security work this qualification
covers.

This document is a documentation-and-testing snapshot: it reflects what was
verified live against the running system on 2026-06-26, not a new code
release.

---

## 1. What's new since the 2026-06-13 baseline

- **AMI Contract** (`contracts/`): pinned `TelemetryEnvelope` MQTT/Kafka
  schema all drivers/services now share.
- **DLMS/COSEM AMI driver** (`drivers/dlms/`): hand-rolled (stdlib) wire
  profile — spec-shaped, **not yet validated against real hardware**.
- **MDM** (`services/mdm/`): quality/enrichment pipeline, now the actual
  production path (`AMI → MDM → ingestor → FastAPI → TimescaleDB`, not the
  raw path the 06-13 baseline described).
- **OPC UA connector** (`services/opcua/`): connect/subscribe/reconnect/
  security against `asyncua`'s documented surface — **re-validate against a
  real OPC UA server with `asyncua` actually installed before connecting to
  real OT hardware.**
- **CIM/IEC 61968 adapter** (`services/cim/`): read-only REST translation
  layer, 12 CIM classes, own Bearer-token auth with verified tenant
  isolation. Mappings are spec-shaped, **not independently verified against
  official UML/RDF/XSD artifacts.**
- **Redis Sentinel HA** is now actually deployed (3-node quorum, not just
  validated in isolation) — confirmed via a real failover drill (~5s
  recovery), see `QUALIFICATION_REPORT.md` §3.
- **TLS termination** (Caddy, Phase 22 SEC-3) now live for API/Portal/
  Grafana — additive, not yet enforced (legacy plaintext ports still work).
- **Ingestor redesigned** (queue + worker pool): fixed the silent NaN-loss
  and MQTT-keepalive-loss bugs found in this branch's own SIT; zero
  permanent loss confirmed at burst rates up to ~750 msg/s actually achieved.

## 2. DERMS functions

Unchanged from the 06-13 baseline — not in this qualification's scope (no
functional/architectural changes were made). See that section of the
original baseline (preserved in git history) or `END_TO_END_TEST_SCENARIOS.md`.

## 3. Performance (newly characterized this qualification)

- **Throughput ceiling: ~15 msg/s sustained**, bottlenecked at TimescaleDB's
  single-row insert path. Confirmed twice (2026-06-25 and 2026-06-26, no
  regression).
- **Steady-state latency at 12 msg/s:** p50=0.66s, p95=5.34s, p99=5.72s,
  708/708 delivered, 0 lost.
- **Zero permanent message loss** confirmed at burst rates up to ~750 msg/s
  actually achieved (received==persisted after full drain).
- Full detail and tuning recommendations: `QUALIFICATION_REPORT.md` §1,
  `DEPLOYMENT_GUIDE.md`.

## 4. High Availability (re-characterized this qualification)

Only **Redis (Sentinel) and PITR/backups are deployed as HA**. Kafka,
TimescaleDB, MQTT, and MinIO are single-instance with restart-based recovery
(5-15s, confirmed clean) — the K2/K3/K5/K6 multi-node designs exist only in
isolated, never-merged validation compose files. See
`QUALIFICATION_REPORT.md` §3 for the full HA drill results, including two
new findings on Docker's `unless-stopped` restart policy and Sentinel's
"tilt mode."

## 5. Security (re-characterized this qualification)

| Feature | Status |
|---|---|
| API authentication (JWT + API keys) | ✅ Live, enforced per-route — **except** `GET /telemetry/latest`, confirmed open with no auth at all |
| RBAC (viewer/operator/engineer/admin/service) | ✅ Live |
| MQTT mutual TLS | ✅ Live |
| Kafka SASL | ✅ Live, credentials from `.env`, no hardcoded literal |
| Redis auth | ✅ Live, enforced across Sentinel failover |
| Admin bootstrap credentials | ✅ `DIEP_ADMIN_KEY`/`DIEP_ADMIN_PASSWORD` rotated to strong values; `DIEP_ADMIN_USER` still the literal default |
| TLS for Portal/Grafana/API | ✅ Live (Phase 22 SEC-3) — ⚠️ additive, legacy plaintext ports still reachable |
| Monitoring/admin surfaces (Prometheus/Alertmanager/kafka-ui/cAdvisor/Node-RED) | ❌ Unauthenticated on all interfaces — confirmed live |
| CIM tenant isolation | ✅ Verified (cross-tenant request → 404, not a leak) |

Full detail: `SECURITY_GUIDE.md`, `QUALIFICATION_REPORT.md` §5.

## 6. Known limitations

See `KNOWN_LIMITATIONS.md` for the consolidated, current list. Several
items from the 06-13 baseline's list are now resolved (Redis Sentinel is
live; secrets are mostly rotated; TLS exists) — others are unchanged or
newly found. Don't rely on the 06-13 list below this line; it's preserved
for history, not as current status.

## 7. Final verdict

[VERDICT_PLACEHOLDER — see `QUALIFICATION_REPORT.md` §8 for the full
evidence-based reasoning]

---

## Appendix: 2026-06-13 baseline (historical, superseded — preserved for reference)

**Date:** 2026-06-13
**Status:** First official pilot release baseline. Documentation-only baseline snapshot —
no code or infrastructure changes were made to produce this document.

### Major capabilities (as of 2026-06-13)

DIEP (Distributed Intelligent Energy Platform) v1.0 is an end-to-end DERMS stack providing:

- **Telemetry ingestion**: field devices → MQTT (mutual TLS, port 8883) → Kafka →
  TimescaleDB, with continuous aggregates (`telemetry_1m`, `telemetry_1h`) for
  dashboards/analytics.
- **Command & control**: full lifecycle tracking (`PENDING → SENT → ACKED`) over
  Kafka → MQTT, sub-150ms measured round-trip latency.
- **Multi-protocol edge adapters**: Modbus, SunSpec, OCPP, CAN/BMS, and
  IEC-104/61850-style microgrid RTU via the `drivers/` SDK and edge gateway pattern.
- **Operator portal** (Next.js 14): fleet overview, DERMS request console, alarms,
  reports, digital twins, and AI-operations views — all routes verified 200 OK.
- **REST API** (FastAPI): JWT + API-key auth, RBAC (admin/operator/viewer/service),
  ~35 documented endpoints covering assets, devices, telemetry, commands, DERMS
  actions, analytics, onboarding, and reporting.
- **Analytics**: anomaly detection, forecasting, predictive maintenance, and
  recommendations endpoints (`/analytics/*`, `/recommendations`).
- **Multi-tenant data model**: `tenants` / `sites` / `devices` hierarchy with
  foreign-key integrity (38 constraints verified).
- **Mobile app integration** (Phase 11) and commercial/billing features (Phase 12-14).

### Known limitations (as of 2026-06-13 — see §6 above for current status)

1. RPO ≈ 24h — nightly `pg_dump` only, no PITR/WAL archiving. **(superseded: PITR now exists, see `K1_PITR_VALIDATION_REPORT.md` and this qualification's backup findings.)**
2. Kafka is single-broker (RF=1), no failover. **(still true — confirmed by this qualification.)**
3. 5 secondary secrets not yet rotated. **(mostly superseded — admin key/password rotated; see §5 above.)**
4. No TLS on operator-facing endpoints. **(superseded — TLS now live, additive not enforced; see §5 above.)**
5. Alertmanager has no notification receiver configured. **(not re-verified this qualification.)**
6. Single-host deployment, multiple SPOFs. **(still true except Redis — see §4 above.)**
7. Orphaned InfluxDB container. **(not re-verified this qualification.)**
8. Legacy plaintext MQTT port mappings remain. **(not re-verified this qualification — TLS finding in §5 above covers Portal/Grafana/API specifically, not MQTT.)**
9. Backups unencrypted at rest. **(not re-verified this qualification.)**
10. Floating image tags. **(not re-verified this qualification.)**

### Platform readiness score (as of 2026-06-13)

88/100 — see `DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md`. **Superseded by this
qualification's evidence-based verdict in §7 above — that score predates the
AMI/MDM/OPC UA/CIM work and this qualification's performance/HA/security
findings entirely.**
