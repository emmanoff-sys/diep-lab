# DIEP Installation Guide (Phase 16, Task 2)

**Date:** 2026-06-13
**Audience:** Customer/pilot-site operations and IT staff installing the DIEP platform.
**Scope:** Hardware, VM, OS, Docker, network, and certificate requirements to stand up the
DIEP stack as deployed in this lab (`~/projects/diep-lab`, single-host `docker compose`,
25 containers). This guide documents requirements only — no installation steps were
executed against any new environment as part of producing it.

See also: [`DIEP_DEPLOYMENT_ARCHITECTURE.md`](DIEP_DEPLOYMENT_ARCHITECTURE.md) for the
architecture this installation produces, and [`DIEP_OPERATIONS_MANUAL.md`](DIEP_OPERATIONS_MANUAL.md)
for day-2 procedures.

---

## 1. Hardware requirements

The lab host currently runs 25 containers at the following live-measured footprint:

| Resource | Lab host total | Lab steady-state usage |
|---|---|---|
| CPU | 4 vCPU | ~25-35% aggregate |
| Memory | 7.2 GiB | ~4.8 GiB used |
| Disk | 48 GB | 26 GB used / 21 GB free |

### 1.1 Recommended pilot sizing

| Tier | Minimum (pilot, ≤10 devices) | Recommended (pilot, 10-50 devices, headroom for compression/retention) |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| Memory | 8 GiB | 16 GiB |
| Disk (root/data volume) | 100 GB SSD | 250 GB SSD (TimescaleDB grows with telemetry retention — 90-day default, see Phase 9 schema report) |
| Network | 1 Gbps NIC | 1 Gbps NIC, static IP, DNS entry for the pilot hostname |

**Disk growth driver:** TimescaleDB `telemetry` hypertable with a 90-day retention policy
and compression after 7 days (per `DIEP_PHASE9SCHEMA_REPORT.md`/`FINAL_DIEP_READINESS_REPORT.md`).
Plan for ~1-5 GB/month per actively-reporting device at typical 5-30s sample intervals,
before compression.

### 1.2 Edge gateway hardware (if deploying physical field devices)

See [`DIEP_EDGE_GATEWAY_ARCHITECTURE.md`](DIEP_EDGE_GATEWAY_ARCHITECTURE.md) §3 for a full
comparison (Raspberry Pi 5, industrial PC, Jetson, Siemens IOT2050, Advantech). For a
pilot, an industrial PC or Siemens IOT2050-class device per site is recommended for
multi-protocol (Modbus/SunSpec/OCPP/CAN) support and mTLS egress only.

---

## 2. VM requirements

| Item | Requirement |
|---|---|
| Virtualization | Any hypervisor (VMware, Hyper-V, KVM, or cloud VM — AWS/Azure/GCP) supporting nested container workloads |
| vCPU/RAM/Disk | Per §1.1 sizing table |
| Network adapter | Bridged or routed adapter with a static IP reachable from both the operator network and (if applicable) the site/edge gateway network |
| Swap | ≥ 2 GB swap recommended (lab host runs with 3.8 GiB swap configured) |
| Snapshots | Take a VM-level snapshot before initial install and before major version upgrades — complements the application-level backup/restore procedures in `DIEP_OPERATIONS_MANUAL.md` |

---

## 3. OS requirements

| Item | Requirement |
|---|---|
| OS | Ubuntu 22.04 LTS or 24.04 LTS (lab runs `Linux 7.0.0-22-generic`, Ubuntu-based) |
| Kernel | Recent LTS kernel with cgroup v2 enabled (default on Ubuntu 22.04+) — required for cAdvisor and container resource accounting |
| Filesystem | ext4 or xfs for the Docker data root and named-volume mount path |
| Users | A non-root user with passwordless `sudo` and membership in the `docker` group, for running `docker compose` and the backup/cron scripts |
| Timezone/NTP | NTP-synced clock (`chronyd`/`systemd-timesyncd`) — required for correct TimescaleDB hypertable chunking, Prometheus alert timing, and audit-event timestamps |
| Host packages | `git`, `curl`, `jq`, `bc`, `openssl`, `cron`, `tar`, `python3` (used by `start-all-diep.sh`, `dr-test.sh`, `backup-*.sh`, `init-db.sh`) |

---

## 4. Docker requirements

| Item | Requirement |
|---|---|
| Docker Engine | ≥ 24.x (Compose V2 `docker compose` subcommand, used throughout `docker-compose*.yml` and all helper scripts) |
| Docker Compose | V2 (bundled with Docker Engine ≥ 20.10.13 via the `docker compose` plugin) |
| Storage driver | `overlay2` (default) |
| Privileged containers | `diep-cadvisor` runs `privileged: true` with host mounts (`/`, `/var/run`, `/sys`, `/var/lib/docker`) and device access (`/dev/kmsg`) — ensure the host allows privileged containers (relevant for hardened Docker daemons / rootless Docker, which is **not** compatible with this cAdvisor configuration as-is) |
| Networks | One bridge network `diep-net` (created automatically by `docker compose up`) |
| Volumes | Seven named volumes created automatically: `timescale-data`, `kafka-data`, `redis-data`, `minio-data`, `grafana-data`, `prometheus-data`, `influxdb-data` — ensure the Docker data root has sufficient free space per §1.1 |
| Images pulled | `timescale/timescaledb:latest-pg16`, `redis:7-alpine`, `apache/kafka:latest`, `provectuslabs/kafka-ui:latest`, `eclipse-mosquitto`, `minio/minio`, `python:3.12`, `node:20`, `nodered/node-red`, `influxdb:1.8`, `grafana/grafana`, `prom/prometheus`, `prom/alertmanager`, `gcr.io/cadvisor/cadvisor:latest`, `prom/node-exporter`, `quay.io/prometheuscommunity/postgres-exporter`, `danielqsj/kafka-exporter` — pre-pull these on a site with limited bandwidth |

---

## 5. Network requirements

### 5.1 Inbound (from operator / site networks to the pilot host)

| Port | Protocol | Purpose | Source |
|---|---|---|---|
| 8883/tcp | mTLS | MQTT broker — telemetry/command/ack | Site edge gateways |
| 8000/tcp | HTTPS (via reverse proxy) | FastAPI REST API | Operators, mobile app, portal |
| 3002/tcp | HTTPS (via reverse proxy) | Operator Portal | Operators |
| 3001/tcp | HTTPS (via reverse proxy) | Grafana dashboards | Operators / ops team |
| 9090, 9093, 9100, 9187, 9308, 8080/tcp | HTTP | Prometheus/Alertmanager/exporters | Ops/management VLAN only |
| 22/tcp | SSH | Host administration | Ops/management VLAN only |

Internal-only ports (5432, 6379, 9000/9002, 9092/9094, 8081, 1880, 8086) must **not** be
exposed beyond `127.0.0.1`/`diep-net` — see [`DIEP_DEPLOYMENT_ARCHITECTURE.md`](DIEP_DEPLOYMENT_ARCHITECTURE.md) §3.

### 5.2 Outbound (from the pilot host)

| Destination | Purpose |
|---|---|
| Docker Hub / GHCR / Quay (`registry-1.docker.io`, `ghcr.io`, `quay.io`) | Image pulls during install/upgrade |
| NTP servers | Time sync |
| (Optional) External MinIO/S3, SMTP/Slack/webhook endpoints | Off-host backup copies, Alertmanager notification receivers (not yet configured — see Task 5 report §"Known limitations") |

### 5.3 DNS

- Assign a stable hostname for the pilot host (e.g. `diep-pilot.<customer-domain>`),
  used for TLS certificates on Portal/Grafana/API.
- Edge gateways should resolve the MQTT broker hostname (or use a pinned IP) for the
  mTLS connection on 8883.

---

## 6. Certificate requirements

DIEP uses a private CA for MQTT mutual TLS (Phase 9J-S4) and (recommended) a public/internal
CA for the operator-facing TLS endpoints.

### 6.1 MQTT mTLS (mandatory — generated by `scripts/bootstrap-pki.sh`)

None of the artifacts below are checked into git (see `.gitignore`). On a fresh clone,
before the first `./start-all-diep.sh`, run:

```bash
./scripts/bootstrap-pki.sh
```

This generates a fresh platform CA, a broker (server) cert for the 8883 mTLS listener,
the per-device/service client certs, and `mosquitto/config/passwd` (used by the legacy
password-auth identities in `mosquitto/config/acl`, with credentials taken from `.env`'s
`MQTT_USER`/`MQTT_PASS`/`MQTT_NODERED_PASS`). It is idempotent — re-running it skips any
artifact that already exists, so it is safe to re-run after adding new device IDs.

| Artifact | Location | Purpose |
|---|---|---|
| CA certificate/key | `mosquitto/config/certs/ca.{crt,key}` | Trust root for the Mosquitto broker and all device/service client certs |
| Broker cert/key | `mosquitto/config/certs/server.{crt,key}` | Server identity (CN=`diep-mqtt`) for the 8883 mTLS listener |
| Per-device client certs | `certs/devices/<DEVICE_ID>.{crt,key}` + `certs/devices/ca.crt` (`BAT001`, `EV001`, `INV001`, `MG001`, `METER001`, plus `ingestor`, `dispatcher`, `csms`) | Client identity (CN) used by `mosquitto.conf`'s `use_identity_as_username` for ACL binding |
| Mosquitto password file | `mosquitto/config/passwd` | Legacy password-auth users (`diep-device`, `diep-nodered`) referenced by `mosquitto/config/acl` |

Without this step, `diep-mqtt`, `diep-ingestor`, `diep-dispatcher`, and `diep-ev-charger`
fail to start (missing cert/passwd files referenced by `mosquitto.conf` and the
container `MQTT_CLIENT_CERT`/`MQTT_CLIENT_KEY` bind-mounts).

For a customer pilot:
1. Run `scripts/bootstrap-pki.sh` once to provision the pilot's own CA and core fleet —
   **do not reuse a lab-generated CA/keys for a pilot or production deployment.**
2. For each additional device beyond the default fleet, run
   `scripts/issue-device-cert.sh <device-id>` and add a matching block to
   `mosquitto/config/acl` scoping the CN to its own topic namespace
   (`diep/<domain>/<DEVICE_ID>/#`).
3. Distribute device certs to edge gateways via a secure out-of-band channel (not MQTT).
4. Certificate rotation: plan an expiry/rotation cadence (e.g. 1 year) and a documented
   re-issuance procedure — not currently automated.

### 6.2 Operator-facing TLS (Portal / Grafana / API)

Not yet enabled in the lab (HTTP only). For a customer pilot:
1. Obtain a TLS certificate for the pilot hostname — either a public CA (Let's Encrypt,
   if the host is internet-reachable) or the customer's internal CA.
2. Terminate TLS at the Caddy reverse proxy (`caddy/Caddyfile`, Phase 9J-S6 seam) in front
   of Portal (3002), Grafana (3001), and FastAPI (8000).
3. Configure automatic renewal (Caddy's `auto_https` handles Let's Encrypt automatically
   if enabled; for an internal CA, script renewal via cron).

### 6.3 Kafka

Kafka currently uses SASL_PLAINTEXT (Phase 9J-S5) — no TLS. For a customer pilot where
Kafka traffic crosses any network boundary (it currently does not — `diep-net` only),
upgrade to SASL_SSL with broker certs from the same/parallel CA.

---

## 7. Pre-install checklist

- [ ] Host provisioned per §1.1/§2/§3
- [ ] Docker Engine + Compose V2 installed, user in `docker` group
- [ ] Firewall rules per §5.1/§5.2 applied
- [ ] DNS hostname assigned (§5.3)
- [ ] `cp .env.example .env`, then review **all 40 variables** and rotate every
      `change-me-*` default (see
      [`PHASE15A_SECURITY_HARDENING_REPORT.md`](PHASE15A_SECURITY_HARDENING_REPORT.md)).
      This includes `DB_PASSWORD`, `REDIS_PASSWORD`, `MINIO_ROOT_USER`/
      `MINIO_ROOT_PASSWORD`, `MQTT_PASS`/`MQTT_NODERED_PASS`, and the API/JWT secrets and
      operator logins (`DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`,
      `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`). `DB_PASSWORD`
      is consumed directly by `docker-compose.yml`'s `timescaledb` service via variable
      substitution — set it once in `.env`, no separate place to keep in sync.
- [ ] Run `./scripts/bootstrap-pki.sh` to generate the CA, broker cert, per-device mTLS
      certs (placed under `certs/devices/`), and `mosquitto/config/passwd` (§6.1)
- [ ] For any devices beyond the default fleet, update `mosquitto/config/acl`
- [ ] TLS reverse proxy configured for Portal/Grafana/API (§6.2)
- [ ] Run `./start-all-diep.sh` per [`DIEP_OPERATIONS_MANUAL.md`](DIEP_OPERATIONS_MANUAL.md) §1
- [ ] Verify `curl -sf http://localhost:8000/readyz` returns
      `{"ready": true, "checks": {"database": true, "redis": true}}`
      (`DIEP_OPERATIONS_MANUAL.md` §1.3)
- [ ] Install scheduled backups: `./scripts/install-backup-cron.sh` (per
      [`PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`](PHASE15C_PRODUCTION_OPERATIONS_REPORT.md) §1)
- [ ] Run the UAT plan ([`DIEP_UAT_TEST_PLAN.md`](DIEP_UAT_TEST_PLAN.md)) before customer hand-off
