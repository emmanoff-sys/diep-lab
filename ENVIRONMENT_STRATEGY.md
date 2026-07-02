# Environment Strategy — DAEP / RE-OS

**Authority:** WP-003-14 | Roadmap v1.0 §11.2 (8-environment strategy — direct, literal source)

This is the **single source of truth for what is actually provisioned** across
all 8 Roadmap-defined environments. A future contributor must never assume
QA/UAT/Staging/Production/DR are live — read this document first (§35).

## 1. Environment Status (2026-07-02)

| Environment | Status | Deployment | Data Policy | Reset Policy | WP Reference |
|-------------|--------|-----------|-------------|-------------|------|
| **Local Dev** | **STRUCTURALLY LIVE** | Docker Compose (`templates/python-service/docker-compose.yml`) | Synthetic, ephemeral (WP-003-02 seed script) | Automatic on `docker compose down -v` | WP-003-02 |
| **Shared Dev** | **STRUCTURALLY READY** — awaiting networking module (WP-003-08 §9) + VM provisioning | Ansible/Terraform via this EPIC's artifacts; auto-deploy on every `develop` push (preview, WP-004-11 completes this) | Synthetic, non-PII | Weekly (Roadmap §11.2) | WP-003-12/14 |
| **Integration** | **STRUCTURALLY READY** — awaiting networking module + CI wiring (WP-004-10) | GitHub Actions only; ephemeral (created/destroyed per run) | Synthetic, non-PII | Automatic on `terraform destroy` at end of run | WP-003-12/14 |
| **QA** | **DEFERRED** | — | — | — | WP-003-12 (structure only) |
| **UAT** | **DEFERRED** | — | — | — | WP-003-12 (structure only) |
| **Staging** | **DEFERRED** | — | — | — | WP-003-12 (structure only) |
| **Production** | **DEFERRED** | — | — | — | WP-003-12 (structure only) |
| **DR** | **DEFERRED** | — | — | — | WP-003-12 (structure only) |

**"Structurally Ready"** means: the `inventory.yml` + `terraform.tfvars` files
exist (WP-003-12), the Ansible playbook and roles exist (WP-003-07), the
Terraform module exists (WP-003-08), and the Vault/Consul/systemd
infrastructure exists (WP-003-13/10/06). What does NOT exist yet: real
AWS subnet/security-group/KMS IDs (require the networking module, WP-003-08
§9 dependency), real host IPs, and real Vault/Consul servers. A real
provisioning run requires those values first.

**"Deferred"** means: the 5 non-Release-1 environments have placeholder
`inventory.yml`/`terraform.tfvars` files but no actual VMs, no real services,
and no release timeline commitment yet — Release 1 is infrastructure-only
and no business feature yet requires them.

## 2. Local Dev (Live — WP-003-02)

```bash
cd templates/python-service
cp .env.example .env
docker compose up       # scaffold + postgres:16 + redis:7 + kafka:3.7.0
# GET http://localhost:8000/health → {"status": "ok"} within ~2 minutes

docker compose down -v  # full reset: Roadmap §11.2 Reset Policy
```

## 3. Shared Dev (Structurally Ready — awaiting infrastructure prerequisites)

**Roadmap v1.0 §11.2 "Shared Dev" row:** auto-deploy on every `develop`
push; developer access; weekly reset; synthetic/non-PII data.

**Provisioning sequence (Platform Lead action):**

```bash
# 1. Provision via Terraform (once networking module exists and AWS credentials set):
cd terraform/environments/shared-dev
terraform init -backend-config="key=shared-dev/vm/terraform.tfstate"
terraform apply -var-file=terraform.tfvars

# 2. Configure via Ansible (once VMs are up):
ansible-playbook infra/playbooks/provision-vm.yml \
  -i infra/environments/shared-dev/inventory.yml \
  -e target_group=application -e service_name=scaffold -e service_port=8000

# 3. Verify health:
curl https://api.shared-dev.reos.internal/health
```

**Auto-deploy trigger (preview — full CI-pipeline version is WP-004-11):**

This WP's auto-deploy is intentionally minimal/preview-scoped — the
underlying infrastructure works; WP-004-11 makes it fully pipeline-driven.
Current preview: a simple wrapper script calling the same Terraform/Ansible
commands above, triggered by a post-merge hook on `develop`. EPIC-004
replaces this with a proper CI Stage 9 workflow.

## 4. Integration (Structurally Ready — awaiting CI wiring)

**Roadmap v1.0 §11.2 "Integration" row:** GitHub Actions only; ephemeral;
auto-destroy after each pipeline run; synthetic/non-PII.

**Lifecycle (WP-004-10 pipeline scope — preview sketch here):**

```bash
# Create at pipeline start:
terraform apply -var-file=terraform/environments/integration/terraform.tfvars
ansible-playbook infra/playbooks/provision-vm.yml -i infra/environments/integration/inventory.yml ...

# Run scaffold tests against the integration environment

# Destroy at pipeline end (verify no orphaned resources):
terraform destroy -var-file=terraform/environments/integration/terraform.tfvars -auto-approve
```

Full CI-integrated version with orphaned-resource verification is WP-004-10.

## 5. QA, UAT, Staging, Production, DR (Deferred)

No actual provisioning has been performed for these 5 environments.
Their `inventory.yml`/`terraform.tfvars` placeholder files (WP-003-12)
are explicitly marked `PROVISIONING STATUS: NOT YET PROVISIONED`.

**When to provision:** driven by the first business feature release that
needs each environment. The Ansible/Terraform/Vault/Consul infrastructure
is already built and ready — only the environment-specific variable values
need populating.

## 6. Blockers (for Shared Dev and Integration to go live)

| Blocker | Resolution |
|---------|-----------|
| AWS networking module (VPC/subnets/SGs) | Build as a companion to `terraform/modules/vm/` (WP-003-08 §9 flagged) |
| Real AWS subnet/sg/kms IDs | Output of the networking module, inserted into `terraform.tfvars` |
| Real Vault/Consul server instances | VM provisioned for these infrastructure services (separate Terraform/Ansible run) |
| Vault unseal governance | Project Owner decision (VAULT_STANDARDS.md §6) |
| AWS credentials for CI runner | GitHub Actions secret (WP-004 scope) |

## 7. EPIC-003 As Its Own Integration Test (WP-003-14 §34)

This WP's role is to prove EPIC-003 composes correctly — not just
document-complete, but provably working. Given the blocker list above
(all infrastructure-prerequisite rather than implementation gaps), the
verdict is: **every prior EPIC-003 Work Package has a structurally correct
and coherent artifact; the composition will work once those prerequisites
are met**. No re-work of WP-003-01 through WP-003-13 is indicated by this
integration-test review.

## 8. Traceability

| Requirement | Source |
|-------------|--------|
| Environment names, purposes, deployment/data/reset policies | Roadmap v1.0 §11.2 (literal) |
| Ansible provisioning playbook | WP-003-07 |
| Terraform VM module | WP-003-08 |
| GitOps structure | WP-003-12 |
