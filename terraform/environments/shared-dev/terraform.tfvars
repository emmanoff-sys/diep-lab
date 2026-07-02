# DAEP / RE-OS — shared-dev Terraform variables (WP-003-14)
#
# PROVISIONING STATUS: STRUCTURALLY READY — requires real subnet/sg/kms
# values from the networking module (WP-003-08 §9 dependency) before
# `terraform apply` can run. See ENVIRONMENT_STRATEGY.md.

environment    = "shared_dev"
instance_count = 1
instance_type  = "t3.small"
disk_size_gb   = 20

# Replace these with real values from the AWS networking module once provisioned:
subnet_ids         = ["AWAITING-networking-module-subnet-id"]
security_group_id  = "AWAITING-networking-module-sg-id"
vault_addr         = "https://vault.shared-dev.reos.internal:8200"
kms_key_id         = "AWAITING-kms-key-id"
