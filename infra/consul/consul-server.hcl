# DAEP / RE-OS — Consul server, single-node (Release 1 scope) (WP-003-10)
# Authority: LLD v2.0 §17.1 (`consul-agent` role reference)
#
# Runs as a systemd-managed process (WP-003-06 supervision pattern applied
# to Consul as infrastructure, matching Vault's treatment in WP-003-13).
# Single-node for Release 1 — documented multi-node upgrade path below.

datacenter = "reos-shared-dev"   # one per environment; see CONSUL_STANDARDS.md
data_dir   = "/var/lib/consul"
server     = true
bootstrap_expect = 1             # single-node Release 1; see §"Multi-Node Upgrade Path"

bind_addr   = "0.0.0.0"
client_addr = "127.0.0.1"        # HTTP API never public-internet-exposed (§25)

ui_config {
  enabled = true
}

acl {
  enabled        = true
  default_policy = "deny"
  tokens {
    initial_management = "PLACEHOLDER-pending-WP-003-13-vault-integration"
  }
}

# Prometheus-compatible metrics endpoint (WP-003-10 §27) — consumed by
# prometheus-node once fully wired (WP-003-07 follow-on).
telemetry {
  prometheus_retention_time = "60s"
  disable_hostname          = true
}

# Multi-Node Upgrade Path (Production, standard Consul HA practice):
#   bootstrap_expect = 3   # or 5, for a proper quorum
#   retry_join = ["consul-1.internal", "consul-2.internal", "consul-3.internal"]
