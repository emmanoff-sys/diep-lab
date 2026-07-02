# DAEP / RE-OS — shared-dev Terraform variables (WP-003-12 structure; population per WP-003-14 scope)
#
# PROVISIONING STATUS: NOT YET PROVISIONED — structural placeholder only.
# Values below are explicitly non-real (WP-003-12 §39). See
# ENVIRONMENT_STRATEGY.md (WP-003-14) for live-vs-deferred status.

environment    = "shared_dev"
instance_count = 2
instance_type  = "t3.medium"
disk_size_gb   = 30

# PLACEHOLDER — real subnet/security-group/KMS/Vault values require the
# networking module (WP-003-08 §9 dependency, not yet built) and a live
# Vault server (WP-003-13).
subnet_ids         = ["PLACEHOLDER-subnet-not-yet-provisioned"]
security_group_id  = "PLACEHOLDER-sg-not-yet-provisioned"
vault_addr         = "https://vault.internal:8200"
kms_key_id         = "PLACEHOLDER-kms-not-yet-provisioned"
