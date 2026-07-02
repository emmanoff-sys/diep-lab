# DAEP / RE-OS — integration Terraform variables (WP-003-14)
# Ephemeral — `terraform destroy` is run at end of each pipeline run (WP-004-10).

environment    = "integration"
instance_count = 1
instance_type  = "t3.micro"
disk_size_gb   = 20

subnet_ids         = ["AWAITING-networking-module-subnet-id"]
security_group_id  = "AWAITING-networking-module-sg-id"
vault_addr         = "https://vault.integration.reos.internal:8200"
kms_key_id         = "AWAITING-kms-key-id"
