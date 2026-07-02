# DAEP / RE-OS — Vault server configuration (WP-003-13)
# Authority: HLD v2.0 ADR-008 (Accepted: "Vault for all secrets management.
# No secrets stored in environment variables or [...] without Vault integration")
#
# Runs as a systemd-managed process (WP-003-06 supervision pattern applied
# to Vault as infrastructure — matching Consul's treatment in WP-003-10).
#
# Release 1 scope: filesystem storage backend (single-node, not HA).
# Production upgrade path documented below (§35).

storage "file" {
  path = "/var/lib/vault/data"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/etc/vault/tls/vault.crt"
  tls_key_file  = "/etc/vault/tls/vault.key"
  # Self-signed certificate for Release 1 scope — replace with a real cert
  # once PKI infrastructure exists (flagged, not silently assumed solved).
}

# Vault HTTP API must not be publicly internet-exposed (§25) — restrict via
# UFW rule in the infra/vm-base/ufw-rules.md rule set (port 8200,
# localhost-scoped where possible, internal network for Vault Agents on
# service VMs).

api_addr = "https://vault.internal:8200"
ui       = false  # no web UI in Release 1 — CLI + API only

# Audit logging — every secret access logged (HLD ADR-008 compliance,
# BRS v1.0 "Internal — Confidential" classification).
# Configured via `vault audit enable file file_path=/var/log/vault/audit.log`
# after server initialization (run-time, not declarative — Vault's audit
# configuration is not part of the HCL config file).

# Note on Vault's "Kubernetes integration" capability (HLD v2.0 technology
# table): this capability is explicitly NOT used — ECR-001 rules out
# Kubernetes entirely. AppRole is the auth method chosen here (non-Kubernetes,
# standard Vault practice for VM-deployed services) — documented in
# VAULT_STANDARDS.md.

# Production upgrade path (§35 — explicit, not silently presented as
# production-ready):
#   storage "raft" { path = "/var/lib/vault/data" }   # Raft integrated storage
#   cluster_addr = "https://vault-X.internal:8201"
#   auto_unseal via cloud KMS (AWS KMS / GCP CKMS)
#   bootstrap_expect equivalent: raft peer join, not this file
