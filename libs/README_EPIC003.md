# EPIC-003 — Core Platform Framework

### DAEP / RE-OS | Official Engineering Guide | Version 0.1.0 (Release 1)

---

## 1. EPIC Overview

EPIC-003 establishes the reusable runtime platform used by every DAEP / RE-OS
backend service: how services are containerized, locally tested, stored in a
registry, security-scanned, hardened on a VM, supervised by systemd, provisioned
by Ansible, cloud-provisioned by Terraform, load-balanced, discovered via Consul,
access-controlled via branch protection, organized as GitOps, and issued secrets
via Vault.

Every EPIC-004 CI stage and every EPIC-005+ application service builds directly
on the artifacts produced here.

---

## 2. Purpose

Replace the per-service, undocumented, and unjustifiably varied infrastructure
decisions that would otherwise appear across the ~30+ planned microservices, with:

1. **One container build pattern** (DOCKER_STANDARDS.md) — `python:3.12-slim`,
   builder→production, non-root, HEALTHCHECK, <200MB.
2. **One local dev entry point** (`docker compose up` in `templates/python-service/`).
3. **One registry** with a documented tagging convention.
4. **One security scan gate** (Trivy, CRITICAL = block).
5. **One hardened VM baseline** (Ubuntu 22.04 LTS, UFW, SSH key-only, zero
   Kubernetes artifacts — the ECR-001 operationalization check).
6. **One supervision unit** (`reos-service@.service` — systemd template).
7. **One provisioning playbook** (`provision-vm.yml` — Ansible, 7 roles).
8. **One cloud VM module** (`terraform/modules/vm/` — Terraform, IMDSv2, KMS).
9. **One load-balancing stack** (Nginx HTTP + HAProxy TCP + Keepalived VRRP).
10. **One service registry** (Consul, LLD-literal registration schema).
11. **One infra/* change control** (ansible-lint + terraform-plan + tfsec workflow).
12. **One GitOps tree** (8 environments structured, no role/module duplication).
13. **One secrets store** (Vault, AppRole → dynamic Postgres credentials, no static secrets).
14. **One environment-status record** (`ENVIRONMENT_STRATEGY.md` — never guess what's live).

---

## 3. Scope

14 Work Packages across four features:

| Feature | WPs |
|---------|-----|
| Docker Foundation | WP-003-01 to WP-003-04 |
| VM/Systemd Foundation | WP-003-05 to WP-003-10 |
| GitOps Foundation | WP-003-11 to WP-003-14 |

---

## 4. Architecture Overview

```
Developer machine                   VM-hosted services
──────────────────                  ────────────────────────────────────────
docker compose up                   systemd → reos-service@{name}.service
 (WP-003-02)                              │
     │                                    └─▶ docker run ... ← Vault Agent
     │                                              (WP-003-06/13)
     ▼
Dockerfile builder→production       Ubuntu 22.04 LTS (WP-003-05 hardened)
 (WP-003-01)                              │
     │                                    └─▶ Consul agent registers service
     ▼                                         (WP-003-10)
Trivy scan (WP-003-04)
     │                              Nginx (HTTP/443) ─┐
     ▼                              HAProxy (TCP)     ├─ Keepalived VIP
Container Registry (WP-003-03)      (WP-003-09)       │
     │                              ──────────────────┘
     ▼
Ansible provision-vm.yml (WP-003-07)
     │
     └─▶ Terraform modules/vm (WP-003-08)
               │
               └─▶ cloud-init.yml.tftpl (WP-003-05)
```

---

## 5. Component Hierarchy

```
EPIC-003 artifacts (repo root and infra/)
├── DOCKER_STANDARDS.md                       WP-003-01
├── CONTAINER_REGISTRY.md                     WP-003-03
├── CONTAINER_SECURITY.md                     WP-003-04
├── LOAD_BALANCING.md                         WP-003-09
├── CONSUL_STANDARDS.md                       WP-003-10
├── ANSIBLE_STANDARDS.md                      WP-003-07
├── SYSTEMD_STANDARDS.md                      WP-003-06
├── VAULT_STANDARDS.md                        WP-003-13
├── TERRAFORM_STANDARDS.md                    WP-003-08
├── GITOPS_STRUCTURE.md                       WP-003-12
├── ENVIRONMENT_STRATEGY.md                   WP-003-14 ← read this first
├── .trivyignore                              WP-003-04
├── templates/python-service/
│   ├── Dockerfile                            WP-003-01 (rewrote from stub)
│   ├── docker-compose.yml                    WP-003-02
│   ├── scripts/seed-local-dev.py             WP-003-02
│   └── requirements.in / requirements.txt   WP-003-01 (closed EPIC-002 drift)
├── infra/
│   ├── container-registry/docker-compose.yml WP-003-03
│   ├── vm-base/{HARDENING_STANDARD,ufw-rules,cloud-init.yml.tftpl}  WP-003-05
│   ├── systemd/reos-service@.service          WP-003-06
│   ├── playbooks/provision-vm.yml             WP-003-07
│   ├── roles/{common,docker,vault-agent,consul-agent,prometheus-node,reos-service,log-forwarder}/  WP-003-07/13
│   ├── loadbalancer/{nginx.conf,keepalived.conf,keepalived-backup.conf,haproxy.cfg}  WP-003-09
│   ├── consul/{consul-server.hcl,consul-agent-template.hcl,scaffold-service-registration.json}  WP-003-10
│   ├── vault/{vault-server.hcl,postgres-dynamic-secrets-policy.hcl}  WP-003-13
│   └── environments/{local-dev,shared-dev,integration,qa,uat,staging,production,dr}/  WP-003-12/14
├── terraform/
│   ├── backend.tf                             WP-003-08
│   ├── modules/vm/{main,variables,outputs}.tf WP-003-08
│   └── environments/{7 envs}/terraform.tfvars WP-003-12/14
└── .github/workflows/infra-checks.yml        WP-003-11
```

---

## 6. Dependency Graph

```
WP-003-01 (Docker std)
    ├── WP-003-02 (Compose local dev)
    ├── WP-003-03 (Registry)
    │       └── WP-003-04 (Trivy scanning)
    │                   └── WP-003-05 (VM hardening)
    │                               └── WP-003-06 (systemd unit)
    │                                           └── WP-003-07 (Ansible) ──── WP-003-09 (LB)
    │                                                       └── WP-003-08 (Terraform)
    │                                                                   └── WP-003-10 (Consul)
    │                                                                               └── WP-003-11 (infra/* checks)
    │                                                                                           └── WP-003-12 (GitOps)
    │                                                                                                       └── WP-003-13 (Vault) ──▶ completes WP-003-07 vault-agent stub
    │                                                                                                                   └── WP-003-14 (Env strategy)
```

---

## 7. Key Configuration

All runtime configuration flows through `ReosBaseSettings` (EPIC-002,
WP-002-01) via environment variables — never baked into Docker images
or committed to configuration files as credentials.

Secrets delivery chain (WP-003-13):

```
Vault database secrets engine → Vault Agent (AppRole auth) → /run/reos/{svc}.env (tmpfs) → systemd EnvironmentFile → ReosBaseSettings
```

---

## 8. Build Instructions

```bash
# Container build (WP-003-01)
cd templates/python-service
docker build -t reos/scaffold:local .

# Local dev (WP-003-02)
cp .env.example .env && docker compose up

# Registry push (WP-003-03)
docker tag reos/scaffold:local registry.internal:5000/reos/scaffold:$(git rev-parse --short HEAD)
docker push registry.internal:5000/reos/scaffold:$(git rev-parse --short HEAD)

# Security scan (WP-003-04)
trivy image --severity CRITICAL --exit-code 1 reos/scaffold:local

# Provision a VM (WP-003-07)
ansible-playbook infra/playbooks/provision-vm.yml \
  -i infra/environments/shared-dev/inventory.yml \
  -e target_group=application -e service_name=scaffold -e service_port=8000

# Provision cloud VM (WP-003-08 — NOT executed; see TERRAFORM_STANDARDS.md §7)
cd terraform/environments/shared-dev && terraform apply -var-file=terraform.tfvars
```

---

## 9. Test Strategy

All tests in EPIC-003 are runtime-deferred (WP-003-01 through WP-003-14
are infrastructure artifacts, not Python/TS/Dart packages with executable
unit tests). Structural verification was performed in this session:

| WP | Structural Verification Performed |
|----|----------------------------------|
| WP-003-04 | Trivy CLI not installed; `.trivyignore` syntax reviewed |
| WP-003-06 | `systemd-analyze verify` ran — exit 0 (genuine unit file syntax check) |
| WP-003-07 | `yaml.safe_load` on all 12 Ansible YAML files |
| WP-003-10 | `json.load` on Consul registration JSON |
| WP-003-11 | `yaml.safe_load` on infra-checks workflow |
| WP-003-12 | All 7 `inventory.yml` parse; structure lint (no missing files); heuristic secret scan (no hits) |
| WP-003-13 | `yaml.safe_load` on all vault-agent YAML files |
| WP-003-14 | `yaml.safe_load` on shared-dev/integration inventories |

Everything else: **Runtime PASS Deferred** — requires Docker daemon,
Ansible/Terraform/Trivy/Vault/Consul/nginx binaries, and/or a real VM.

---

## 10. Security Considerations

| Control | WP | Enforcement |
|---------|-----|-------------|
| Multi-stage Docker (no build tools in prod image) | WP-003-01 | Dockerfile structure |
| Non-root container user (`reos`) | WP-003-01 | Dockerfile `USER reos` |
| CRITICAL CVE gate | WP-003-04 | Trivy `--exit-code 1` |
| VM default-deny UFW, SSH key-only | WP-003-05 | `common` Ansible role |
| Zero Kubernetes artifacts (ECR-001) | WP-003-05/07 | Negative check in `common` role and `cloud-init.yml.tftpl` |
| No static secrets | WP-003-13 | Vault AppRole + dynamic creds → tmpfs |
| Secrets in tmpfs only | WP-003-06/13 | systemd `EnvironmentFile=/run/reos/` |
| IMDSv2-only cloud metadata | WP-003-08 | Terraform `http_tokens = "required"` |
| TLS 1.3, security headers | WP-003-09 | nginx.conf |
| Rate limiting (429, per DRDP §21.3) | WP-003-09 | nginx.conf `limit_req` |
| No secrets in GitOps files | WP-003-12 | Structure lint (heuristic scan), Vault runtime delivery |
| infra/* change control (tfsec, ansible-lint, terraform-plan) | WP-003-11 | Required checks (NOT yet live-registered — Platform Lead action) |

---

## 11. ECRs Raised

| ECR | Status | Summary |
|-----|--------|---------|
| ECR-003-02-01 | **Resolved at scope** — WP-003-02's `docker-compose.yml`/README Quick Start were scoped to `templates/python-service/` rather than the repo root to avoid overwriting the live platform's 760-line production `docker-compose.yml` (+ 30+ overlay files) and substantial root `README.md`. Enterprise Architect confirmation requested at Architecture Review. | Scope conflict |

---

## 12. Work Package Summary

| WP | Title | SP | Commit |
|----|----|----|----|
| WP-003-01 | Base Docker Images & Multi-Stage Build Standards | 5 | `3b59e71` |
| WP-003-02 | Docker Compose Local Dev Environment | 5 | `cd3b2b4` |
| WP-003-03 | Container Registry | 5 | `ff8abd3` |
| WP-003-04 | Container Security Scanning (Trivy) Foundation | 3 | `b930c5a` |
| WP-003-05 | Ubuntu 22.04 LTS VM Base Image & Hardening Standard | 8 | `47b01e2` |
| WP-003-06 | systemd Service Unit Framework | 5 | `0de96da` |
| WP-003-07 | Ansible Playbook Foundation | 8 | `ad495c0` |
| WP-003-08 | Terraform Cloud VM Lifecycle Foundation | 8 | `9516feb` |
| WP-003-09 | Nginx + HAProxy + Keepalived Load Balancing Foundation | 8 | `d2e3c64` |
| WP-003-10 | Consul Service Discovery Foundation | 5 | `421ce21` |
| WP-003-11 | Git Branching Strategy & Branch Protection (infra/*) | 3 | `478e245` |
| WP-003-12 | GitOps Repository Structure | 5 | `9a9d0fc` |
| WP-003-13 | Secrets Management Foundation (Vault) | 8 | `bcd4352` |
| WP-003-14 | Environment Strategy Implementation | 5 | `7e1e99c` |

---

## 13. Version History

| Version | Date | Change |
|---------|------|--------|
| 0.1.0 | 2026-07-02 | Initial EPIC-003 delivery — all 14 WPs across 3 features |

---

## 14. Open Actions (Human Required Before EPIC-003 Goes Live)

| # | Action | Owner |
|---|--------|-------|
| 1 | AR-020 through AR-033: Architecture Reviews for WP-003-01 through WP-003-14 | Enterprise Architect |
| 2 | Confirm ECR-003-02-01 scope resolution (Compose files at scaffold level vs repo root) | Enterprise Architect |
| 3 | Confirm remote-state-backend choice: S3+DynamoDB vs Terraform Cloud (TERRAFORM_STANDARDS.md §5) | Project Owner |
| 4 | Build AWS networking module (VPC/subnets/security groups) — blocker for Shared Dev / Integration provisioning | Platform Lead |
| 5 | Provision first Vault and Consul server VMs | DevOps Lead |
| 6 | Vault unseal key-holder governance decision | Project Owner |
| 7 | Register infra/* required-status-checks in GitHub branch protection | Platform Lead |
| 8 | Run docker build + Trivy scan + docker compose smoke tests against scaffold | Tech Lead |
| 9 | Run ansible-lint + terraform validate against playbook/module | Tech Lead |
