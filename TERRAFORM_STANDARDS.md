# Terraform Standards — DAEP / RE-OS

**Authority:** WP-003-08 | LLD v2.0 §17.3 (direct, literal source)

## 1. Module

`terraform/modules/vm/` — a reusable cloud VM module:

| Variable | Default | Notes |
|----------|---------|-------|
| `service_name` | — (required) | Resource naming/tagging |
| `instance_count` | `2` | HA default, per LLD §17.2's 2-backend Nginx upstream examples |
| `instance_type` | `t3.medium` | |
| `disk_size_gb` | `30` | |
| `environment` | — (required) | Validated against Roadmap v1.0 §11.2's environment names |
| `subnet_ids` | — (required) | Pre-existing — see §2 |
| `security_group_id` | — (required) | Pre-existing — see §2 |
| `vault_addr` | — (required) | Rendered into `cloud-init.yml.tftpl` (WP-003-05) |
| `kms_key_id` | — (required) | Root volume encryption |

```hcl
module "identity_service_vm" {
  source             = "../../modules/vm"
  service_name       = "identity-service"
  environment        = "shared_dev"
  subnet_ids         = data.terraform_remote_state.network.outputs.private_subnet_ids
  security_group_id  = data.terraform_remote_state.network.outputs.service_sg_id
  vault_addr         = "https://vault.internal:8200"
  kms_key_id         = data.aws_kms_key.reos.id
}
```

## 2. Networking Dependency (flagged, not assumed pre-built)

LLD v2.0 §17.3 references `var.subnet_ids` and `aws_security_group.service.id`
as pre-existing inputs — implying a separate networking module (VPC,
subnets, security groups). **This WP does not build that module.** It is a
documented dependency to be defined alongside this one, not silently assumed
to already exist (§9).

## 3. Security

- Root volume: `gp3`, `encrypted = true`, KMS-backed.
- `metadata_options`: IMDSv2-only (`http_tokens = "required"`,
  `http_put_response_hop_limit = 1`) — hardens against SSRF-based credential
  theft.
- State file encrypted at rest (S3 backend, see §5).

## 4. Tagging

Every instance: `Name`, `Service`, `Environment`, `ManagedBy = "terraform"`
— cost allocation and auditability.

## 5. Remote State Backend — Flagged Architectural Addition

**This Work Package introduces a design decision not explicitly shown in
the captured LLD v2.0 §17.3 excerpt: S3 + DynamoDB remote state with
locking** (`terraform/backend.tf`). This is standard Terraform practice and
reasonably implied by the LLD's multi-environment, multi-engineer usage
pattern (remote state locking is itself a stated release-exit-criterion
requirement), but it has **not been confirmed by the Project Owner** as the
intended backend versus alternatives (e.g., Terraform Cloud).

**Action required:** confirm S3+DynamoDB (vs. an alternative) with the
Project Owner before this becomes load-bearing in a later release (§35,
§39). The bucket name and region in `backend.tf` are explicit placeholders
pending that confirmation — not real infrastructure identifiers.

## 6. State Locking

DynamoDB lock table prevents concurrent-apply corruption. `terraform destroy`
cleanly tears down provisioned resources; already-running services on
already-provisioned VMs are unaffected by Terraform state operations (VM
runtime doesn't depend on Terraform being reachable).

## 7. Verification — NOT EXECUTED

```bash
terraform init
terraform validate
terraform plan -var-file=... # test variable values
# Full apply/destroy cycle against a sandboxed (non-production) AWS account
```

**This implementation did NOT run `terraform init`/`plan`/`apply`/`destroy`
against any AWS account, sandboxed or otherwise.** Terraform is not
installed in the implementation environment, and — independent of tooling —
provisioning real, billable cloud infrastructure is a hard-to-reverse,
shared-system action requiring explicit human authorization and real AWS
credentials, neither of which this implementation has or should
autonomously assume. **Runtime PASS Deferred — requires human execution**
with real credentials in a sandboxed AWS account, plus the backend
confirmation from §5 first.

## 8. CI Integration

`terraform plan` runs as a required check on `infra/*` branches per
WP-003-11/WP-001-04's branch protection rules (also not live-configured by
this implementation — see WP-003-11's report).

## 9. Traceability

| Requirement | Source |
|-------------|--------|
| Module structure, resource attributes | LLD v2.0 §17.3 (literal) |
| `cloud-init.yml.tftpl` source | WP-003-05 |
| Environment names | Roadmap v1.0 §11.2 |
