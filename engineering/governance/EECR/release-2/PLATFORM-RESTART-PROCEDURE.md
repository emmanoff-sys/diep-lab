# Platform Restart Procedure
### RE-OS Development Platform

---

## Purpose

Step-by-step procedure for starting or restarting the RE-OS development platform
stack after a VM reboot, power cycle, or hypervisor snapshot restoration.

---

## Prerequisites

- VM is running and SSH accessible
- Docker daemon is active (`systemctl status docker`)
- Working directory: `/home/emmanoff_lab/projects/diep-lab`

---

## Full Stack Start Procedure

### Step 1 — Confirm environment

```bash
cd /home/emmanoff_lab/projects/diep-lab
git status
git log -1 --oneline
docker ps -a | wc -l
```

Confirm on the expected branch and commit. Confirm no unexpected containers in error state.

### Step 2 — Start all services

```bash
./start-all-diep.sh
```

This script starts all Docker Compose services in dependency order. Wait for output to confirm
all containers are started.

### Step 3 — Verify container health (wait ~60 seconds for startup)

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

Expected: all 25 containers `Up` (with healthy label where applicable).
Acceptable transient: `kafka-exporter` may restart 2–10 times while Kafka warms up — normal.

### Step 4 — Verify core services

```bash
# FastAPI
curl -s http://localhost:8000/healthz

# TimescaleDB
docker exec diep-timescaledb psql -U diep -d diep -c "SELECT NOW(), version();"

# Kafka
docker exec diep-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group diep-command-dispatcher

# Redis
RPASS=$(grep REDIS_PASSWORD .env | cut -d= -f2)
docker exec diep-redis redis-cli -a "$RPASS" ping
docker exec diep-redis redis-cli -a "$RPASS" info replication | grep role

# WAL shipping
docker logs diep-wal-shipper --tail 5
```

### Step 5 — Start Prometheus if not auto-started

Prometheus has no restart policy and may need manual start if it was stopped:

```bash
docker ps -a --filter name=diep-prometheus --format '{{.Names}} {{.Status}}'
# If Exited:
docker start diep-prometheus
sleep 5
docker ps --filter name=diep-prometheus
```

### Step 6 — Verify Prometheus and Grafana

```bash
PROM_IP=$(docker inspect diep-prometheus \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec diep-alertmanager wget -qO- "http://${PROM_IP}:9090/-/healthy"
# Expected: "Prometheus Server is Healthy."
# Grafana: http://localhost:3001 (default port)
```

### Step 7 — Confirm WAL archive reachable

```bash
MINIO_IP=$(docker inspect diep-minio \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec diep-wal-shipper mc alias set diep-minio \
  "http://${MINIO_IP}:9000" diepadmin "$(grep MINIO_ROOT_PASSWORD .env | cut -d= -f2)"
docker exec diep-wal-shipper mc ls diep-minio/diep-wal-archive | tail -5
```

Expected: WAL segments appearing every ~60 seconds.

---

## Recovery from Unexpected Container Failure

If a specific container is in error state:

```bash
docker logs <container-name> --tail 50
docker restart <container-name>
```

For TimescaleDB specifically, check logs carefully before restart — an unclean shutdown
may require recovery. Do not force-remove the container if data loss is a concern.

---

## Known Startup Behaviours

| Container | Behaviour | Action |
|-----------|-----------|--------|
| diep-kafka-exporter | 5–15 restarts while Kafka warms up | Wait; resolves automatically |
| diep-wal-shipper | Initial connection refused to MinIO | Wait ~30s; resolves automatically |
| diep-prometheus | Does not auto-restart after clean stop | Manual `docker start diep-prometheus` |
| diep-dispatcher | May restart once at startup | Normal; stable after ~60s |

---

## Stop Procedure

To gracefully stop the platform (e.g., before taking a VM snapshot):

```bash
docker compose down
# or to stop without removing:
docker compose stop
```

TimescaleDB will checkpoint on shutdown. Redis will save RDB. Kafka will flush logs.
Allow at least 30 seconds for graceful shutdown before forcing.

---

*Last updated: 2026-07-11T02:10:00Z*
