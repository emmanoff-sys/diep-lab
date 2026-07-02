# UFW Rule Set & Change Process — DAEP / RE-OS

**Authority:** WP-003-05 | `HARDENING_STANDARD.md` §2

## Current Rule Set (baseline, per `common` role)

```bash
ufw default deny incoming
ufw default allow outgoing

ufw allow from <admin-network-cidr> to any port 22 proto tcp comment 'SSH — admin network only'
ufw allow <service_port>/tcp comment 'Application traffic'
ufw allow from 127.0.0.1 to any port 8500 proto tcp comment 'Consul agent — localhost'
ufw allow from 127.0.0.1 to any port 8200 proto tcp comment 'Vault agent — localhost'

ufw enable
```

`<admin-network-cidr>` and `<service_port>` are Ansible inventory variables
(WP-003-07/WP-003-12), never hardcoded per-VM.

## Rule-Change Process

A new port requirement (e.g., a service needing an additional inbound rule)
is a **reviewed change**, not an ad hoc production edit:

1. Open a PR modifying the relevant `infra/environments/{env}/inventory.yml`
   UFW variable (WP-003-12).
2. PR goes through `infra/*` branch protection (2 approvals, Ansible lint —
   WP-003-11).
3. Applied via a normal `provision-vm.yml` re-run (WP-003-07), never a
   manual `ufw allow` on a live VM outside of Ansible's control.

This process exists specifically to prevent the hardening baseline from
being silently loosened over time (WP-003-05 §35 risk).
