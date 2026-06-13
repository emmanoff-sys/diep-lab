#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Starting DIEP Platform..."
docker compose up -d

echo ""
echo "Waiting for services to become available..."
echo "Initializing TimescaleDB schema and seed data..."
./init-db.sh

echo "Waiting for Node-RED to become available..."
python3 - <<'PY'
import time, urllib.request
for _ in range(60):
    try:
        urllib.request.urlopen('http://localhost:1880/')
        print('Node-RED is online.')
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit('Node-RED did not become ready in time.')
PY

echo "Deploying Node-RED flows..."
python3 nodered/rebuild_flows.py || true

echo ""
echo "Running Containers:"
docker compose ps

echo ""
echo "DIEP Services:"
echo "Grafana      : http://localhost:3001"
echo "Prometheus   : http://localhost:9090"
echo "Alertmanager : http://localhost:9093"
echo "cAdvisor     : http://localhost:8080"
echo "Node-RED     : http://localhost:1880"
echo "Kafka UI     : http://localhost:8081"
