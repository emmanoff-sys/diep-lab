# Vault Standards — DAEP / RE-OS

**Authority:** WP-003-13 | HLD v2.0 ADR-008 (Accepted — "Vault for all secrets management. No secrets stored in environment variables or [...] without Vault integration") | LLD v2.0 §17.1 `vault-agent` role

## 1. Purpose

Every service's secrets are fetched dynamically from Vault at boot instead of
stored in `.env` files — a leaked config file or compromised VM never exposes
long-lived credentials.

## 2. AppRole Auth Rationale

HLD v2.0's technology table lists "Kubernetes integration" as a Vault
capability — **this capability is explicitly NOT used** (ECR-001 rules
out Kubernetes entirely). AppRole is the auth method chosen for VM-deployed
services (a standard, non-Kubernetes Vault auth method), delivering the
same ADR-008 "no static secrets" principle on VMs rather than Kubernetes
pod service accounts.

## 3. Secret Delivery Flow

```
Vault Agent on service VM
    ↓ AppRole login (role-id / secret-id)
    ↓ read database/creds/{service}-role
    ↓ render env.ctmpl → /run/reos/{service}.env (tmpfs, 0600, owner reos)
    ↓
systemd EnvironmentFile=/run/reos/{service}.env (WP-003-06)
    ↓
docker run --env-file /run/reos/{service}.env   (reos-service@.service)
    ↓
ReosBaseSettings (WP-002-01) reads DATABASE_URL, REDIS_URL, etc.
```

## 4. Dynamic Postgres Credential

Vault's `database` secrets engine issues short-lived, per-service Postgres
credentials via the `reos-scaffold-role` Vault database role. TTL: 1 hour
(documented default); Vault Agent renews before TTL expires — no service
restart required on renewal (§29 acceptance criterion).

## 5. AppRole secret-id Delivery

The AppRole `role-id` is non-secret and can be committed to Ansible inventory.
The `secret-id` is Vault-controlled and is delivered securely at VM
provisioning time via Terraform `user_data`/cloud-init (WP-003-05/WP-003-08)
— never committed to this repository.

## 6. Unseal Governance (Platform Lead / Project Owner action — technical enforcement not possible here)

Vault must be unsealed via Shamir's Secret Sharing after every restart.
Key-holder governance (who holds key shares, quorum required) is an
organizational decision that this Work Package can flag but cannot
technically enforce. **Action required from the Project Owner:** identify
key-holders before WP-003-13 is considered operationally (not just
technically) Done (§39).

## 7. Audit Logging

Vault audit logging must be enabled after server initialization:

```bash
vault audit enable file file_path=/var/log/vault/audit.log
```

Every secret access is logged — a compliance control given BRS v1.0's
"Internal — Confidential" classification.

## 8. Scope Exclusions (explicit, not silently assumed)

- **PKI (certificate issuance)** — named in HLD ADR-008's technology row;
  not built in Release 1 (no service yet needs machine certs from an internal
  CA — flagged as a later-release follow-on, not silently included).
- **Encryption as a service (transit engine)** — same: HLD-listed capability,
  out of Release 1 scope.
- **Kubernetes auth method** — explicitly excluded per ECR-001.

## 9. Production Upgrade Path (§35 — explicit)

Release 1's single-node, filesystem-backend Vault is:

- **Not HA** — a Vault restart (or the single node failing) requires manual
  unseal and blocks new credential issuance and renewal.
- **Not auto-unsealing** — requires key-holders to be available.

Production path: Raft integrated storage, 3+ node cluster, auto-unseal
via cloud KMS (AWS KMS `seal "awskms"` block in `vault-server.hcl`).
The operational grace window if Vault goes down: already-issued credentials
continue working until their TTL expires (1 hour default) — test and
document this behavior explicitly before Production (§36).

## 10. Verification (Runtime — requires a running Vault server + service VM)

```bash
# Initialize and unseal
vault operator init
vault operator unseal <key-1>
vault operator unseal <key-2>
vault operator unseal <key-3>

# Enable database secrets engine and register Postgres
vault secrets enable database
vault write database/config/reos-scaffold \
  plugin_name=postgresql-database-plugin \
  connection_url="postgresql://vault-admin:{{username}}:{{password}}@db.internal:5432/reos_scaffold" \
  ...

# Run Vault Agent on a service VM and verify:
systemctl start vault-agent
test -f /run/reos/scaffold.env && echo PASS || echo FAIL
grep DATABASE_URL /run/reos/scaffold.env | grep -v PLACEHOLDER && echo PASS || echo FAIL

# Verify credential rotation (WP-003-13 §29 AC):
vault lease revoke database/creds/reos-scaffold-role/<lease-id>  # force expire
sleep 5
# confirm Vault Agent renewed: DATABASE_URL in /run/reos/scaffold.env has different credentials
# confirm service still running (no restart required)
```

**Status in this repository:** Vault binary is not installed in the
implementation environment, and no Vault server or Postgres instance
exists to test against — **Runtime PASS Deferred** for all items above.
Structural PASS: all YAML parses cleanly (yaml.safe_load verified).

## 11. Traceability

| Requirement | Source |
|-------------|--------|
| Vault decision | HLD v2.0 ADR-008 |
| `vault-agent` role | LLD v2.0 §17.1 |
| Dynamic secrets capability | HLD v2.0 technology table (Vault row) |
| Kubernetes integration explicitly excluded | ECR-001, HLD v2.0 ADR-008 (noted exclusion) |
