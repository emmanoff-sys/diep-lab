# systemd Standards — DAEP / RE-OS

**Authority:** WP-003-06 | LLD v2.0 Ch. 17 introduction ("Docker packages services; systemd manages them") | LLD v2.0 §17.1 `reos-service` role

## 1. Template Unit

`infra/systemd/reos-service@.service` is a systemd **template unit** — the
`@` allows instantiation per service name:

```bash
systemctl enable --now reos-service@identity.service
systemctl status reos-service@identity.service
systemctl restart reos-service@identity.service
```

## 2. Directive Rationale

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `After=`/`Requires=docker.service` | — | Container can't start before the Docker daemon is up |
| `EnvironmentFile=/run/reos/%i.env` | tmpfs-backed | Rendered by Vault Agent (WP-003-13); secrets never touch persistent disk (HLD ADR-008) |
| `ExecStartPre=docker pull` | — | Always pulls the tag named in the env file — image version lives in Ansible inventory, not this template |
| `Restart=on-failure`, `RestartSec=5` | — | Automatic supervision — the "systemd manages them" half of LLD Ch. 17's core claim |
| `MemoryMax=512M`, `CPUQuota=100%` | documented default | Scaffold benchmark; per-service override via a templated drop-in (WP-003-07), not edits to this file |
| `StandardOutput/Error=journal` | — | Feeds the `log-forwarder` (Promtail) role, LLD v2.0 §17.1 |
| `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome` | — | systemd-level sandboxing of the supervising process, independent of Docker's own isolation |

## 3. Instantiating for a New Service

1. Ansible's `reos-service` role (WP-003-07) renders
   `/run/reos/{service}.env` (via Vault Agent) and, if needed, a resource
   drop-in at `/etc/systemd/system/reos-service@{service}.service.d/resources.conf`.
2. `systemctl enable --now reos-service@{service}.service`.
3. No edit to `reos-service@.service` itself is required — it is
   Docker-image-version-agnostic by design (§39).

## 4. Verification (Runtime — requires a provisioned VM with Docker + systemd)

```bash
systemctl start reos-service@scaffold.service
systemctl status reos-service@scaffold.service   # expect "active (running)"

# Restart-on-failure test:
docker kill reos-scaffold
sleep 6
systemctl status reos-service@scaffold.service   # expect restarted, uptime < RestartSec + a few seconds

# Resource-limit test:
systemctl show reos-service@scaffold.service --property=MemoryMax,CPUQuotaPerSecUSec
```

**Status in this repository:** no real VM exists in the implementation
environment to instantiate this unit against — start/restart/resource-limit
verification is **Runtime PASS Deferred**.

## 5. Traceability

| Requirement | Source |
|-------------|--------|
| systemd supervision decision | LLD v2.0 Ch. 17 introduction |
| `reos-service` role reference | LLD v2.0 §17.1 |
| `EnvironmentFile` tmpfs requirement | WP-003-06 §25, HLD v2.0 ADR-008 (adapted per ECR-001) |
