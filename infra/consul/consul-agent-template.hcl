# DAEP / RE-OS — Consul agent, client mode (Ansible-rendered template) (WP-003-10)
# This is the source-of-truth reference; the live Ansible template lives at
# infra/roles/consul-agent/templates/consul-agent.hcl.j2 (WP-003-07).

datacenter = "reos-{environment}"
data_dir   = "/var/lib/consul"
server     = false

bind_addr   = "{vm_private_ip}"
client_addr = "127.0.0.1"

retry_join = ["{consul_server_addr}"]

acl {
  enabled        = true
  default_policy = "deny"
  tokens {
    agent = "{consul_agent_token}"   # sourced from Vault once WP-003-13 exists (§25)
  }
}
