# DIEP Release Notes — v1.0 (Pilot Release Baseline)

**Date:** 2026-06-13
**Status:** First official pilot release baseline. Documentation-only baseline snapshot —
no code or infrastructure changes were made to produce this document.

---

## 1. Major capabilities

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

---

## 2. DERMS functions

| Function | Endpoint | Status |
|---|---|---|
| Battery Dispatch | `POST /derms/battery_dispatch` | ✅ Verified end-to-end (ACKED, ~12ms) |
| Peak Shaving | `POST /derms/peak_shaving` | ✅ Verified end-to-end (ACKED, ~57ms), SOC-based safety gating (409 if SOC<25) |
| Demand Response | `POST /derms/demand_response` | ✅ Verified end-to-end (ACKED, ~92ms), Tier-1 battery / Tier-2 EV-curtailment fallback |
| Load Optimization | `POST /derms/load_optimization` | ✅ Verified end-to-end (ACKED, ~53ms) |
| Microgrid Setpoint/Island/Grid-connect | `POST /commands` (`microgrid`: `island`, `grid_connect`, `set_setpoint`) | ✅ Verified end-to-end (`set_setpoint` ACKED, ~108ms) |
| EV Charger Control | `POST /commands` (`ev_charger`: `start_charging`, `stop_charging`, `set_limit`) | ✅ Verified end-to-end (`start_charging` ACKED, ~80ms) |

All six functions are exercised by `DIEP_UAT_TEST_PLAN.md` with explicit pass/fail criteria.

---

## 3. Security features

| Feature | Status |
|---|---|
| API authentication (JWT + API keys) | ✅ Live, `DIEP_AUTH_ENFORCED=1` |
| RBAC (admin/operator/viewer/service) | ✅ Live, enforced per-route |
| MQTT mutual TLS (per-device certs, CA-issued) | ✅ Live, plaintext listeners retired (Phase 9J-S4) |
| Kafka SASL authentication | ✅ Live (SASL_PLAINTEXT; SASL_SSL recommended before WAN exposure) |
| Redis authentication (`requirepass`) | ✅ Live (Phase 15A) |
| Secret rotation | ✅ Core secrets rotated (Phase 15A) — 5 secondary secrets still default, must rotate before go-live |
| Audit trail (`audit_events`) | ✅ Live for command/DERMS actions; auth events not yet audited |
| TLS for Portal/Grafana/API | ⏳ Reverse-proxy seam exists (Caddy), not yet enabled |

---

## 4. Monitoring features

| Feature | Status |
|---|---|
| Prometheus metrics | ✅ FastAPI, node, cAdvisor, Postgres, Kafka exporters scraped (Phase 15B) |
| Grafana dashboards | ✅ Provisioned via `grafana/provisioning`, datasource = Prometheus |
| Alertmanager rules | ✅ 10 rules covering API/DB/Kafka/MQTT/Grafana/host CPU/memory and the monitoring pipeline itself |
| Alert notification receivers | ⏳ Not configured — alerts fire but produce no external notification |
| Container resource monitoring | ✅ cAdvisor + node-exporter |
| Backup job logging/observability | ✅ `backups/logs/*.log`, weekly verify-restore drill |

---

## 5. Known limitations

1. **RPO ≈ 24h** — nightly `pg_dump` only, no PITR/WAL archiving.
2. **Kafka is single-broker (RF=1), no failover** — a checkpoint-corruption issue was
   found and fixed during the Phase 15C DR drill; any future unclean shutdown could
   reintroduce a similar crash-loop.
3. **5 secondary secrets not yet rotated**: `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`,
   `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD` remain at
   `change-me-*` defaults.
4. **No TLS on operator-facing endpoints** (Portal :3002, Grafana :3001, API :8000).
5. **Alertmanager has no notification receiver configured**.
6. **Single-host deployment** — Postgres, Redis (primary), Kafka, MinIO, and MQTT are
   all single-instance SPOFs on one host.
7. **Orphaned InfluxDB container** — `diep-influxdb` runs but has no Grafana datasource
   and appears unused.
8. **Legacy plaintext MQTT port mappings** (1883/9001) remain in `docker-compose.yml`
   even though the corresponding listeners are commented out in `mosquitto.conf`.
9. **Backups are unencrypted** at rest in MinIO/local archive.
10. **Floating `latest`/`latest-pg16` image tags** in `docker-compose.yml` for 13 of 25
    services — see `DEPLOYMENT_BOM.md` for the digests pinned at this baseline; tags
    should be pinned to specific versions before broader rollout to avoid silent drift
    on rebuild.

None of these limitations block a controlled pilot with the mitigations in
`DIEP_INSTALLATION_GUIDE.md` §7 (pre-install checklist) applied, but items 1-5 should be
prioritized before the pilot is extended to production load or additional sites.

---

## 6. Production roadmap

| Priority | Item | Closes |
|---|---|---|
| 1 | **Postgres/TimescaleDB HA + PITR** (CloudNativePG or Patroni, WAL archiving) | RPO gap (24h → ≤5min); SPOF |
| 2 | **Kafka multi-broker** (Strimzi, RF=3, `min.insync.replicas=2`) | Restart-survival / crash-loop risk; SPOF |
| 3 | Redis Sentinel (replica already live-verified) | Redis SPOF / auto-failover |
| 4 | MinIO distributed + MQTT cluster (EMQX/HiveMQ or active/standby Mosquitto) | Object-store and MQTT SPOFs |
| 5 | Full Kubernetes cutover via `k8s/`/`helm/` manifests | Multi-AZ, rolling upgrades, anti-affinity |
| — | Enable TLS reverse proxy for Portal/Grafana/API; configure Alertmanager receivers; rotate remaining 5 secrets; remove orphaned InfluxDB and dead MQTT port mappings; pin floating image tags | Security/operability hygiene — recommended before pilot go-live |

---

## 7. Related documents

| Document | Purpose |
|---|---|
| [`SYSTEM_INVENTORY.md`](SYSTEM_INVENTORY.md) | Services, ports, containers, databases, brokers, certs, secrets |
| [`CONFIGURATION_BASELINE.md`](CONFIGURATION_BASELINE.md) | Compose files, env vars, backup schedules, monitoring config |
| [`DEPLOYMENT_BOM.md`](DEPLOYMENT_BOM.md) | Software/image/dependency versions, OS requirements |
| [`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md) | Pre/post-deployment and rollback checklists |
| [`DIEP_DEPLOYMENT_ARCHITECTURE.md`](DIEP_DEPLOYMENT_ARCHITECTURE.md) | Logical/physical/network/security architecture |
| [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md) | Hardware/VM/OS/Docker/network/certificate requirements |
| [`DIEP_OPERATIONS_MANUAL.md`](DIEP_OPERATIONS_MANUAL.md) | Startup/shutdown/backup/restore/DR/monitoring procedures |
| [`DIEP_UAT_TEST_PLAN.md`](DIEP_UAT_TEST_PLAN.md) | Customer acceptance tests for all 5 DERMS scenarios |
| [`DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md`](DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md) | Executive readiness summary |

---

## 8. Platform readiness score

**88 / 100** — see `DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md` for the full breakdown and
`PILOT_RELEASE_CHECKLIST.md` §5 for the scoring rationale at this baseline.
