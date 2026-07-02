# Ansible Standards — DAEP / RE-OS

**Authority:** WP-003-07 | LLD v2.0 §17.1 (direct, literal source — playbook structure, variable validation, role sequence)

## 1. Playbook

`infra/playbooks/provision-vm.yml` targets `hosts: '{{ target_group }}'`,
`become: true`, validates `service_name` and `service_port > 1024` in
`pre_tasks`, then applies the role sequence in order:

```
common → docker → vault-agent → consul-agent → prometheus-node → reos-service → log-forwarder
```

```bash
ansible-playbook infra/playbooks/provision-vm.yml \
  -i infra/environments/{env}/inventory.yml \
  -e target_group=web -e service_name=identity -e service_port=8001
```

## 2. Role Sequence & Responsibilities

| Order | Role | Responsibility | Status |
|-------|------|----------------|--------|
| 1 | `common` | OS hardening per `HARDENING_STANDARD.md` (WP-003-05), UFW, non-root `reos` user, zero-Kubernetes check | Complete |
| 2 | `docker` | Docker CE install, no swarm mode (explicit negative, ECR-001) | Complete |
| 3 | `vault-agent` | Fetch secrets → `/run/reos/{service}.env` | **STUB** — see §3 |
| 4 | `consul-agent` | Register service + health checks per WP-003-10's schema | Complete (agent + registration file; full cluster is WP-003-10's scope) |
| 5 | `prometheus-node` | Node Exporter install | Complete |
| 6 | `reos-service` | Install + instantiate the WP-003-06 systemd template unit | Complete |
| 7 | `log-forwarder` | Promtail → Loki | **STUB** — see §4 |

## 3. `vault-agent` Stub Status

No Vault server, AppRole credentials, or database secrets engine exist
until WP-003-13 builds them. This role therefore renders a **structurally
correct** `/run/reos/{service}.env` (satisfying WP-003-06's systemd
`EnvironmentFile` contract with placeholder values) rather than performing
a real Vault Agent fetch. **Do not deploy any real service against this
stub.** WP-003-13 replaces this task file's content entirely — tracked
explicitly in that Work Package's "Files to Modify" list, not silently
assumed complete here.

## 4. `log-forwarder` Stub Status (Release 1 — explicit, out of scope)

The Loki/Promtail log-aggregation **backend** does not exist in Release 1's
scope — it belongs to a later observability epic. This role performs no
action and documents exactly what completing it requires (a running Loki
instance, Promtail scraping journald for `reos-service@*.service` units,
a supervised Promtail systemd unit). **A future contributor must not mistake
this stub for live log forwarding** — this note is deliberately prominent
for that reason.

## 5. Idempotency

Every task uses Ansible's built-in idempotent modules (`apt`, `user`,
`copy`, `systemd`, `community.general.ufw`, `community.docker.docker_network`)
— no raw `shell`/`command` tasks except the two explicit verification checks
(`common`'s zero-Kubernetes grep, `docker`'s Swarm-inactive confirmation),
both of which are read-only and `changed_when: false`.

## 6. Verification (Runtime — requires `ansible-lint` and a target VM)

```bash
ansible-lint infra/playbooks/ infra/roles/
ansible-playbook infra/playbooks/provision-vm.yml -i <inventory> --check   # dry run
ansible-playbook infra/playbooks/provision-vm.yml -i <inventory>           # first run
ansible-playbook infra/playbooks/provision-vm.yml -i <inventory>           # second run — expect 0 changed
```

**Status in this repository:** `ansible-lint` and `ansible-playbook` are not
installed in the implementation environment, and no target VM exists —
lint and idempotency verification are **Runtime PASS Deferred**. YAML
structure was hand-verified against LLD v2.0 §17.1's literal role sequence
and variable-validation pattern (Structural PASS).

## 7. Traceability

| Requirement | Source |
|-------------|--------|
| Playbook structure, variable validation, role sequence | LLD v2.0 §17.1 (literal) |
| `common` role content | WP-003-05 `HARDENING_STANDARD.md` |
| `reos-service` role content | WP-003-06 `reos-service@.service` |
| Consul registration schema | WP-003-10 (worked LLD JSON example) |
