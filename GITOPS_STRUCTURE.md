# GitOps Repository Structure — DAEP / RE-OS

**Authority:** WP-003-12 | Roadmap v1.0 §11.2 (8-environment strategy) | LLD v2.0 §17.1/§17.3 (roles/modules organized by this structure)

Git-as-source-of-truth for infrastructure state, reconciled via
Ansible/Terraform rather than a Kubernetes controller — the VM-only
interpretation of a GitOps pattern (ECR-001).

## 1. Structure

```
infra/environments/
├── local-dev/README.md          # Docker Compose only — no inventory (WP-003-02)
├── shared-dev/inventory.yml
├── integration/inventory.yml
├── qa/inventory.yml
├── uat/inventory.yml
├── staging/inventory.yml
├── production/inventory.yml
└── dr/inventory.yml

terraform/environments/
├── shared-dev/terraform.tfvars
├── integration/terraform.tfvars
├── qa/terraform.tfvars
├── uat/terraform.tfvars
├── staging/terraform.tfvars
├── production/terraform.tfvars
└── dr/terraform.tfvars
```

**Note on file count:** WP-003-12's own §17 text ("seven inventory.yml
files, six populated") is inconsistent with its own §15 tree diagram and
with the Roadmap's 8-environment strategy referenced throughout this WP and
WP-003-14 (both consistently list 7 non-local-dev environments: shared-dev,
integration, qa, uat, staging, production, dr). This implementation follows
the more specific §15 tree diagram and the 8-environment strategy — 7
`inventory.yml` + 7 `terraform.tfvars` files, plus `local-dev/README.md` —
rather than the inconsistent count in §17's prose. Flagged for Architecture
Review confirmation, not a blocking ambiguity (both readings agree on
*which* environments exist; only the summary count in one paragraph was off
by one).

## 2. No Duplication Principle

Shared roles (`infra/roles/`, WP-003-07) and modules (`terraform/modules/vm/`,
WP-003-08) are environment-agnostic and referenced, never duplicated. Every
`inventory.yml`/`terraform.tfvars` supplies only variable values — this is
the core GitOps discipline this structure enforces.

## 3. Provisioning Status (Release 1)

| Environment | Structure | Real Provisioning |
|-------------|-----------|-------------------|
| Local Dev | N/A (Compose only) | **LIVE** — WP-003-02 |
| Shared Dev | This WP | WP-003-14 (populates this WP's placeholders) |
| Integration | This WP | WP-003-14 (populates this WP's placeholders) |
| QA, UAT, Staging, Production, DR | This WP | **Deferred** — no business feature yet needs them (Release 1 is infrastructure-only) |

Every non-local-dev file created by this WP contains explicit
`PROVISIONING STATUS: NOT YET PROVISIONED` placeholder markers — a future
contributor must not mistake this structural scaffolding for a live
environment (§35). `ENVIRONMENT_STRATEGY.md` (WP-003-14) is the single
source of truth for what's actually live.

## 4. Adding a New Environment

1. Copy `infra/environments/{template}/inventory.yml` and
   `terraform/environments/{template}/terraform.tfvars`.
2. Adjust variable values only — never add role/module logic here.
3. No shared role or module needs modification.

## 5. Security

No environment-specific credential or secret value is ever committed to any
file in this structure — secrets come from Vault at runtime (WP-003-13),
never from `inventory.yml`/`terraform.tfvars`. Structure-lint (heuristic
secret-value scan) is a candidate for WP-003-11's `security-scan` job.

## 6. Verification

```bash
# Confirm every non-local-dev environment has both files:
for env in shared-dev integration qa uat staging production dr; do
  test -f infra/environments/$env/inventory.yml || echo "MISSING: $env inventory.yml"
  test -f terraform/environments/$env/terraform.tfvars || echo "MISSING: $env terraform.tfvars"
done
```

**Status in this repository:** all 7 environments have both files present
(Structural PASS — verified via the loop above and via `yaml.safe_load`
parsing every `inventory.yml`); heuristic secret-value scan found zero
matches.

## 7. Traceability

| Requirement | Source |
|-------------|--------|
| Environment names/purposes | Roadmap v1.0 §11.2 (8-environment table) |
| Roles/modules organized | LLD v2.0 §17.1 (`infra/roles/`), §17.3 (`terraform/modules/`) |
