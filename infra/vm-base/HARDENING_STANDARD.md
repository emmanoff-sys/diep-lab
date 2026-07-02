# Ubuntu 22.04 LTS VM Hardening Standard — DAEP / RE-OS

**Authority:** WP-003-05 | LLD v2.0 ADR-LLD-001 (Accepted — "All RE-OS services run on Ubuntu 22.04 LTS VMs. Docker packages services; systemd manages them.") | LLD v2.0 §17.1 `common` role ("OS hardening, packages, users, UFW firewall")

This is the target-state specification every RE-OS VM — on-premises or
cloud — must satisfy. It is defined before the Ansible `common` role
(WP-003-07) automates its application, so that role can be written directly
from this document without further architectural decisions.

**This Work Package directly operationalizes ECR-001's resolution
(VM-only, no Kubernetes, confirmed 2026-07-01).** Its highest-value review
point is the explicit zero-Kubernetes-artifacts check in §5.

## 1. Base Image

Ubuntu 22.04 LTS (Jammy Jellyfish), minimal server install (`ubuntu-22.04-minimal`
cloud image or equivalent ISO profile — no desktop packages, no snapd
bloat beyond what's required for `unattended-upgrades`).

## 2. Firewall (UFW)

Default-deny incoming, default-allow outgoing. Explicit allow rules only:

| Port | Protocol | Purpose | Scope |
|------|----------|---------|-------|
| 22 | TCP | SSH (key-only) | Admin network / bastion only, never `0.0.0.0/0` |
| `{service_port}` | TCP | Application traffic | Per-service, from LB tier only where applicable |
| 8500 | TCP | Consul agent (WP-003-10) | Localhost-scoped where possible |
| 8200 | TCP | Vault agent (WP-003-13) | Localhost-scoped where possible |

See `ufw-rules.md` for the reviewed rule-change process — this is not an
ad hoc, per-incident firewall edit process.

## 3. SSH Hardening

```
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

Key-only authentication. No root login over SSH — administrative access is
via a non-root user with `sudo`, itself governed by the same key-only policy.

## 4. Patch Management

`unattended-upgrades` enabled for security patches. `python:3.12-slim`-style
periodic-rebuild discipline (WP-003-01 §35) applies analogously at the VM
layer — base image drift is expected and handled by this automatic patching,
not by treating a provisioned VM as permanently frozen.

## 5. Zero Kubernetes Confirmation (ECR-001 operationalization)

**Explicit negative check — no Kubernetes packages, `kubelet`, `kube-proxy`,
`containerd` (beyond what Docker itself requires), or any
container-orchestration agent may be present on the image.**

```bash
# Verification command (run against a provisioned VM):
dpkg -l | grep -iE 'kube|k3s|k0s' && echo "FAIL: Kubernetes artifact found" || echo "PASS: zero Kubernetes artifacts"
systemctl list-unit-files | grep -iE 'kube|k3s|k0s' && echo "FAIL" || echo "PASS"
```

This check should be re-run at every review of this Work Package and its
Ansible automation (WP-003-07) — the single highest-value verification
point in EPIC-003 for catching any accidental regression toward the
superseded HLD v2.0 ADR-001 (§39).

## 6. Non-Root Service User

A dedicated `reos` system user (no login shell, `useradd --system --shell
/usr/sbin/nologin`) runs the Docker containers themselves — separate from
the SSH-accessible admin user. Matches the container-level non-root policy
established in WP-003-01 `DOCKER_STANDARDS.md` §3.

## 7. Kernel Hardening (CIS-Benchmark-Aligned)

- Disable unused network protocols: `dccp`, `sctp`, `rds`, `tipc` (via
  `/etc/modprobe.d/reos-hardening.conf` blacklist entries).
- Restrict core dumps: `fs.suid_dumpable = 0` (`sysctl`).
- `net.ipv4.conf.all.rp_filter = 1` (reverse-path filtering, anti-spoofing).

## 8. Audit Logging

`auditd` enabled for security event logging (CIS-baseline standard
practice). Forwarded via the `log-forwarder` role (LLD v2.0 §17.1) once
WP-003-07 automates it — this WP documents the requirement, automation is a
follow-on (consistent with the `log-forwarder` stub noted in WP-003-07 §9).

## 9. Metrics

VM-level metrics via the `prometheus-node` role (LLD v2.0 §17.1, Node
Exporter) — this WP documents the requirement, WP-003-07 automates
installation.

## 10. Verification (Runtime — requires a provisioned VM)

```bash
lynis audit system   # CIS-benchmark-style hardening scan
# documented acceptable threshold: hardening index ≥ 70 (Lynis default
# "good" baseline for a freshly hardened server; revisit once a real
# threshold is agreed with the Security Review Checklist owner)
```

**Status in this repository:** no real VM (cloud or on-prem) exists in the
implementation environment to scan — hardening-scan and zero-Kubernetes
verification are **Runtime PASS Deferred** to WP-003-07/08's actual
provisioning.

## 11. UFW Rule-Change Process

See `ufw-rules.md` — any new port requirement goes through documented
review, never an ad hoc production firewall edit (§35 risk mitigation).

## 12. Traceability

| Requirement | Source |
|-------------|--------|
| VM-only decision | LLD v2.0 ADR-LLD-001, ECR-001 |
| `common` role scope | LLD v2.0 §17.1 |
| Ubuntu 22.04 LTS | LLD v2.0 ADR-LLD-001, Ch. 17 introduction |
