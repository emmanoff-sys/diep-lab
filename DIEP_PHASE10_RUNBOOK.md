# DIEP Production Ops Runbook (Phase 10C/10D/10E)

> Observability, security-ops, and disaster-recovery procedures for the production
> deployment. Companion to the Helm chart (`helm/`), k8s manifests (`k8s/`), and CI
> (`.github/workflows/ci.yml`).

---

## 10C — Observability / SRE

### Metrics & alerting (in place)
- **Prometheus** scrapes the API (`/metrics`), node-exporter, cAdvisor. Rules in
  `prometheus/alerts.yml`, validated with `promtool check rules`, fired via Alertmanager.
- **DIEP SLO alerts** (loaded + verified): `DiepApiDown`, `HighCommandFailureRate`
  (>20% FAILED acks/10m), `CommandsRejected`, `HighCommandDispatchLatency` (p95 > 1s),
  `SlowCommandAck` (p95 cmd→ack > 30s).
- **Grafana** dashboards: command throughput/latency, ack latency histograms, per-device
  telemetry, DERMS activity, fleet health. (Provision as ConfigMaps via the kube-prometheus
  stack in prod.)

### SLOs (targets)
| SLO | Target | Source metric |
|-----|--------|---------------|
| API availability | 99.9% | `up{job="diep-fastapi"}` |
| Command dispatch p95 | < 1 s | `diep_command_dispatch_seconds` |
| Command→ack p95 | < 30 s | `diep_command_ack_latency_seconds` |
| Command success | > 99% | `diep_commands_acked_total{result}` |

### Logging & tracing (to add in prod)
- **Logs:** Loki + Promtail (or Fluent Bit) → centralized, label-indexed; 30–90 d retention.
- **Traces:** OpenTelemetry SDK in the API + an OTel Collector → Tempo/Jaeger; trace the
  command path (API → Kafka → dispatcher → MQTT → ack).
- **Dashboards-as-code** + alert routing (PagerDuty/Opsgenie) with on-call rotations.

---

## 10D — Security operations

- **CI gates (in place):** Trivy image scan (fail on HIGH/CRITICAL, ignore-unfixed), Syft
  SPDX SBOM per build, cosign image signing, hadolint, helm lint. (Demonstrated locally:
  Trivy found base-image CVEs; Syft produced a 119-package SBOM.)
- **Base image:** move from `python:3.12-slim` (debian) to **distroless / Chainguard** to
  cut the OS-package CVE surface flagged by Trivy.
- **Secrets:** Vault KV + PKI (9J-S7); External Secrets Operator syncs to k8s; **rotate**
  JWT secret, API keys, DB/MQTT creds on a schedule; short-lived device certs via Vault PKI
  with **CRL/OCSP** for revocation.
- **AuthZ review:** quarterly RBAC review of the `viewer/operator/admin/service` roles and
  the per-device MQTT ACLs; audit-log (`audit_events`) shipped to SIEM with ≥1 y retention.
- **Cadence:** dependency scanning on every PR; **annual penetration test**; SBOM retained
  per release; container runtime policy (read-only rootfs, drop ALL caps, non-root — already
  in the Helm `securityContext`).

---

## 10E — Disaster recovery

### Targets
- **RPO ≤ 5 min** (continuous WAL archiving → PITR). **RTO ≤ 30 min** (restore + cutover).

### Backups (in place / automated)
- **PITR:** CloudNativePG continuous WAL archive to object storage (`k8s/postgres-cnpg.yaml`).
- **Logical:** nightly `pg_dump` → object storage — `scripts/backup-db.sh` (lab) /
  `k8s/backup-cronjob.yaml` (prod). **Verified restore** via `scripts/restore-db.sh` into a
  scratch DB (row counts matched).

### Restore procedure
1. Provision a fresh CNPG cluster (or `Cluster.spec.bootstrap.recovery` from the WAL archive).
2. PITR to the target timestamp, **or** `restore-db.sh <dump>` for a logical restore.
3. Verify row counts + run smoke tests (`/readyz`, a telemetry write, a command round-trip).
4. Repoint the `diep-pg-rw` Service / app; redeploy the API (`helm upgrade --atomic`).

### Resilience drills (cadence)
- **Backup-restore drill:** monthly (restore into scratch, verify).
- **Failover drill:** kill the primary Postgres pod → confirm CNPG promotes a standby
  (RTO measured). API pod kill → confirm LB/HPA recovery (verified in 9K).
- **Chaos:** periodic pod/AZ kill (e.g. via a chaos tool) against staging.
- **Multi-AZ:** spread stateful sets across ≥3 AZs (anti-affinity in the manifests).

---

## Quick reference

| Need | Where |
|------|-------|
| Deploy API | `helm upgrade --install diep helm/diep -f helm/diep/values-prod.yaml` |
| Build/scan/sign/deploy | `.github/workflows/ci.yml` |
| DB HA + PITR | `k8s/postgres-cnpg.yaml` |
| Nightly backup | `k8s/backup-cronjob.yaml` · `scripts/backup-db.sh` |
| Restore-verify | `scripts/restore-db.sh <dump>` |
| Alerts/SLOs | `prometheus/alerts.yml` |
| Secrets/PKI | Vault (`docker-compose-vault.yml`) → External Secrets |
