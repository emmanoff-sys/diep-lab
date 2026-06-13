# DIEP Phase 10 (Group B) — Production Operations

> **Status:** Production artifacts delivered; key pieces live-validated with Docker +
> containerized tooling. Date: 2026-06-06. The single host can't run a real multi-node
> cluster, so (like 9K) the cluster-deploy steps ship as validated manifests/pipelines.
> Running stack stayed intact (5/5 verticals PRODUCTION_READY).

---

## 10A — IaC & orchestration

### Production API image (`fastapi/Dockerfile` + `requirements.txt`) — ✅ built & run-validated
- Multi-stage, **non-root** (uid 10001), slim, **pinned deps** (InfluxDB removed), with a
  container HEALTHCHECK. Replaces the lab's pip-install-at-runtime container.
- **Validated live:** `docker build` → `diep/api:1.0.0` (260 MB); ran it on the network →
  `Up (healthy)`, `/healthz` 200, `/readyz` `{ready:true, db+redis ok}`, `/assets` 200,
  `POST /commands` no-token → **401** (auth enforced in the image), `id` → uid 10001.

### Helm chart (`helm/diep/`) — ✅ render-validated
- Templated **Deployment + Service + HPA + PDB + Ingress** with rolling-update
  (`maxUnavailable:0`), topology spread, `readOnlyRootFilesystem`, drop-ALL caps,
  secret-sourced env. Per-env `values-dev.yaml` / `values-prod.yaml`.
- **Validated:** rendered via containerized helm → prod = 5 resources (Deploy/Svc/HPA/PDB/
  Ingress), dev = 3 (HPA/PDB conditionally off). Output parses as valid k8s YAML.

### Terraform (`terraform/main.tf`) — skeleton
- Cluster + `diep` namespace + operator installs (CNPG, Strimzi, Redis, cert-manager,
  external-secrets) + remote state; cloud-agnostic (swap the cluster module for EKS/GKE/AKS).

---

## 10B — CI/CD (`.github/workflows/ci.yml`)

Pipeline: **lint** (hadolint, helm lint/template, ruff) → **test** (the 5 driver selftests) →
**build → Trivy scan → Syft SBOM → push → cosign sign** → **deploy** (`helm upgrade --atomic`,
auto-rollback) → DB-migration Job.

**Validated locally (containerized tools):**
- **Trivy** scan of `diep/api:1.0.0` → surfaced **9 CVEs (7 HIGH, 2 CRITICAL)** in the
  debian base packages (mostly `fix_deferred`). The CI gate uses `ignore-unfixed` + would
  fail on fixable HIGH/CRITICAL. Action item: distroless/Chainguard base (see runbook 10D).
- **Syft** SBOM → **SPDX-2.3, 119 packages**, including all DIEP python deps.
- The **test stage** runs the dependency-free driver selftests (all green throughout 9C–9G).

---

## 10C / 10D / 10E — Observability, Security-ops, DR (`DIEP_PHASE10_RUNBOOK.md`)

### 10C Observability — ✅ alerts live-validated
- Rewrote `prometheus/alerts.yml`: removed stale alerts for **decommissioned** services
  (InfluxDB retired, Node-RED stopped), added a **`diep-slo`** group: `DiepApiDown`,
  `HighCommandFailureRate`, `CommandsRejected`, `HighCommandDispatchLatency`, `SlowCommandAck`.
- **Validated:** `promtool check rules` → SUCCESS (9 rules); Prometheus reloaded → groups
  `[diep-infra, diep-slo]`, all 5 SLO rules loaded. SLO targets + Loki/OTel plan in the runbook.

### 10D Security-ops
- CI security gates (Trivy/Syft/cosign) in place; secret rotation + Vault PKI (CRL/OCSP),
  quarterly RBAC/ACL review, audit-log→SIEM, annual pentest — in the runbook.

### 10E Disaster recovery
- **RPO ≤ 5 min / RTO ≤ 30 min**; PITR via CNPG WAL archiving + nightly logical backup
  (`k8s/backup-cronjob.yaml`, `scripts/backup-db.sh`) with a **verified restore**
  (`scripts/restore-db.sh`). Failover/backup/chaos drill cadence in the runbook.

---

## What's live-validated vs delivered-as-artifact

| Item | Status |
|------|--------|
| Production API image builds + runs (healthy, non-root, auth) | ✅ live |
| Helm chart renders (prod/dev) to valid k8s | ✅ live |
| Trivy scan + Syft SBOM | ✅ live (containerized) |
| Prometheus SLO alerts load + validate | ✅ live |
| Full CI/CD run, k8s cluster deploy, CNPG/Strimzi HA | ⏳ artifact (needs a cluster — Group B/10A-cluster) |

---

## Result & next

The "lab → deployable system" gap is closed at the artifact level: a real container image,
a Helm chart, a CI/CD pipeline with supply-chain security, production SLO alerts, and a
DR/security runbook — the things needed to run DIEP on a real cluster. **Group A (security,
HA, schema, data) + Group B (IaC, CI/CD, observability, security-ops, DR) are now complete
as code + validated patterns.**

**Next on the roadmap:** **Group C** — field/certification (9I real security+failover tests
now that mTLS+HA exist, edge-gateway productization, remaining drivers, 9L pilot) — and
**Group D** — the mobile app (the API is now HTTPS + JWT + versionable, so the PWA/native
track can start on a stable contract).
