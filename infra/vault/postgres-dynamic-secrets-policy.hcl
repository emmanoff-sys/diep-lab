# DAEP / RE-OS — Vault policy: Postgres dynamic credentials (WP-003-13)
# Authority: HLD v2.0 ADR-008 ("Dynamic secrets" capability — direct source)
#
# Applied to the AppRole that each service VM's Vault Agent authenticates
# with. Allows the agent to read a short-lived Postgres credential from the
# database secrets engine.
#
# Apply: vault policy write reos-service-db infra/vault/postgres-dynamic-secrets-policy.hcl

# Read a dynamic Postgres credential for the given service role.
# The path `database/creds/{service}-role` is parameterized per service —
# each service gets its own Vault database role (REOS_VAULT_DB_ROLE in the
# EnvironmentFile, sourced from the AppRole's own env vars).
path "database/creds/reos-scaffold-role" {
  capabilities = ["read"]
}

# Allow token renewal — Vault Agent renews the credential before TTL expires
# without service restart (§29 acceptance criterion).
path "auth/token/renew-self" {
  capabilities = ["update"]
}
