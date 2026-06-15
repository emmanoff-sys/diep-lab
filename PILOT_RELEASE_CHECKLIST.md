# DIEP Pilot Release Checklist (v1.0 Baseline)

**Date:** 2026-06-13
**Purpose:** Operational checklist for taking the v1.0 baseline to a customer pilot site,
plus a rollback plan. Documentation only.

---

## 1. Pre-deployment checks

- [ ] Target host meets sizing in `DIEP_INSTALLATION_GUIDE.md` §1.1 (≥8 vCPU / 16 GiB /
      250 GB SSD recommended for 10-50 devices)
- [ ] OS/Docker prerequisites met (`DIEP_INSTALLATION_GUIDE.md` §3-4): Ubuntu 22.04/24.04,
      Docker Engine ≥24.x, Compose V2, `overlay2`, privileged containers allowed (for
      `diep-cadvisor`)
- [ ] All image versions/digests pre-pulled per `DEPLOYMENT_BOM.md` §2 (especially on
      bandwidth-limited sites)
- [ ] `.env` populated from `.env.example` (`cp .env.example .env`) with **all**
      40 vars reviewed and every `change-me-*` secret rotated, including
      `DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`,
      `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, `DB_PASSWORD`, `REDIS_PASSWORD`,
      `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, `MQTT_PASS`/`MQTT_NODERED_PASS` —
      `SYSTEM_INVENTORY.md` §6. Note: `DB_PASSWORD` is also consumed directly by
      `docker-compose.yml`'s `timescaledb` service via variable substitution — no
      separate value to keep in sync.
- [ ] Run `./scripts/bootstrap-pki.sh` to generate the CA, broker cert, and per-device
      mTLS certs under `certs/devices/` and `mosquitto/config/certs/`, and the
      `mosquitto/config/passwd` file (`DIEP_INSTALLATION_GUIDE.md` §6.1). For pilot
      device fleets beyond the default set, re-run
      `scripts/issue-device-cert.sh <device-id>` per additional device and update
      `mosquitto/config/acl` with its CN
- [ ] TLS reverse proxy (Caddy) configured for Portal (:3002), Grafana (:3001), and API
      (:8000) with a certificate for the pilot hostname (`DIEP_INSTALLATION_GUIDE.md` §6.2)
- [ ] Firewall rules applied per `DIEP_INSTALLATION_GUIDE.md` §5.1/5.2 — only 8883,
      8000/3002/3001 (via TLS proxy), and 22 reachable from outside the management VLAN
- [ ] Decide on the `diep-influxdb` service (legacy, superseded by TimescaleDB) — remove
      from `docker-compose.yml` for the pilot deployment, or explicitly retain with a
      noted reason (Known Limitations #7). The legacy 1883/9001 MQTT port mappings have
      been removed; `docker-compose.yml` now publishes 8883 (mTLS) only, per
      `DIEP_INSTALLATION_GUIDE.md` §5.1
- [ ] Alertmanager receivers configured with real Slack/PagerDuty/webhook endpoints
      (`DIEP_ALERT_*_WEBHOOK_URL` in `.env`) — `CONFIGURATION_BASELINE.md` §4.3
- [ ] DNS hostname assigned for the pilot host (`DIEP_INSTALLATION_GUIDE.md` §5.3)

---

## 2. Deployment checks

- [ ] `git clone`/transfer the release at the v1.0 baseline commit to the target host
- [ ] Run `./start-all-diep.sh` (`DIEP_OPERATIONS_MANUAL.md` §1.1)
- [ ] `docker compose ps` — all 25 services `Up` / `Up (healthy)`
- [ ] `curl -sf https://<pilot-host>:8000/healthz` → 200
- [ ] `curl -sf https://<pilot-host>:8000/readyz` → `{"ready": true, "checks": {"database": true, "redis": true}}`
- [ ] Portal reachable over HTTPS at the pilot hostname, login works for
      admin/operator/viewer roles with rotated passwords
- [ ] Grafana reachable over HTTPS, dashboards (`command-path`, `kafka`,
      `postgres-timescaledb`) render data
- [ ] Edge devices connect to MQTT over mTLS :8883 (check `mosquitto` logs for successful
      TLS handshakes per device CN)
- [ ] Install scheduled backups: `./scripts/install-backup-cron.sh`
      (`DIEP_OPERATIONS_MANUAL.md` §3.1) — confirm `crontab -l | grep diep-backup` shows
      the 3 jobs

---

## 3. Post-deployment checks

- [ ] Run the full UAT plan (`DIEP_UAT_TEST_PLAN.md`) — all 5 scenarios PASS, sign-off
      table completed
- [ ] Run one manual backup cycle and verify: `./scripts/backup-db.sh`,
      `./scripts/backup-config.sh`, `./scripts/verify-backup.sh` all succeed
      (`DIEP_OPERATIONS_MANUAL.md` §3.2)
- [ ] Run a non-destructive DR drill: `./scripts/dr-test.sh` — confirm all 5 core
      services recover (`DIEP_OPERATIONS_MANUAL.md` §5.1); compare RTOs against the lab
      baseline (TimescaleDB 2.8s, MQTT 2.7s, Kafka 19.6s, Grafana 11.1s, FastAPI 16.0s)
- [ ] Confirm Alertmanager test alert reaches the configured receiver (fire a synthetic
      alert or temporarily stop a non-critical exporter)
- [ ] Confirm `audit_events` records operator actions taken during UAT
- [ ] Confirm `docker stats` resource usage is within the sized host's headroom
      (lab baseline: ~25-35% CPU, ~4.8 GiB RAM on 4 vCPU / 7.2 GiB)
- [ ] Record the pilot site's device inventory (device IDs, cert serials, site name) for
      future cert-rotation and onboarding reference

---

## 4. Rollback checklist

If the pilot deployment must be rolled back (failed UAT, critical defect found
post-deployment):

- [ ] Stop application writers: `docker compose stop diep-fastapi diep-ingestor diep-dispatcher`
- [ ] Do **not** run `docker compose down -v` / `--volumes` — this destroys
      `timescale-data`, `kafka-data`, `redis-data`, `minio-data`, `grafana-data`,
      `prometheus-data` (`DIEP_OPERATIONS_MANUAL.md` §2.1)
- [ ] If rolling back to a prior release tag: `git checkout <previous-tag>`, then
      `docker compose pull && docker compose up -d` to restore the previous image set
      (cross-check digests against the previous release's `DEPLOYMENT_BOM.md`)
- [ ] If data corruption is suspected: follow the disaster-restore sequence in
      `DIEP_OPERATIONS_MANUAL.md` §4.2 (stop writers → `timescaledb_pre_restore()` →
      `pg_restore` → `timescaledb_post_restore()` → restart services → verify `/readyz`)
- [ ] If Kafka enters a restart-crash loop after rollback, apply the checkpoint-file fix
      in `DIEP_OPERATIONS_MANUAL.md` §5.2 before restarting `diep-kafka`
- [ ] Re-run `curl -sf .../healthz` / `/readyz` and the §3 post-deployment checks against
      the rolled-back state before declaring the rollback complete
- [ ] Notify the customer pilot point-of-contact of the rollback, cause, and revised
      timeline

---

## 5. Final platform readiness score

**88 / 100**

| Category | Score | Basis |
|---|---|---|
| Core DERMS functionality | 18/20 | All 6 functions verified end-to-end (`RELEASE_NOTES_v1.0.md` §2); -2 for no automated regression suite covering these paths |
| Security | 16/20 | mTLS, JWT/RBAC, audit trail, secret rotation mostly complete; -4 for 5 unrotated default secrets and no operator-facing TLS |
| Monitoring & observability | 15/20 | Full Prometheus/Grafana/Alertmanager stack provisioned; -5 for no live Alertmanager notification receiver |
| Operations (backup/DR) | 17/20 | Automated backups, weekly verify drill, DR drill with measured RTOs; -3 for ~24h RPO (no PITR) |
| Deployment hygiene | 12/20 | Functional single-host compose deployment; -8 for floating image tags, orphaned InfluxDB, dead MQTT port mappings, and single-host SPOFs (no HA) |
| Documentation | 10/10 | Full architecture, install, ops, UAT, and release-baseline document set complete |

**Total: 88/100** — unchanged from the Phase 16 readiness assessment
(`DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md`). The v1.0 baseline is **ready for a
controlled customer pilot** once the §1 pre-deployment checks — particularly secret
rotation and operator-facing TLS — are completed. The highest-leverage items for the
next release are Postgres PITR (closes the RPO gap) and Kafka multi-broker (removes the
command-bus SPOF), both already scoped with draft `k8s/` manifests.

---

## 6. Related documents

- [`RELEASE_NOTES_v1.0.md`](RELEASE_NOTES_v1.0.md)
- [`SYSTEM_INVENTORY.md`](SYSTEM_INVENTORY.md)
- [`CONFIGURATION_BASELINE.md`](CONFIGURATION_BASELINE.md)
- [`DEPLOYMENT_BOM.md`](DEPLOYMENT_BOM.md)
- [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md)
- [`DIEP_OPERATIONS_MANUAL.md`](DIEP_OPERATIONS_MANUAL.md)
- [`DIEP_UAT_TEST_PLAN.md`](DIEP_UAT_TEST_PLAN.md)
