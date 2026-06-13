#!/usr/bin/env bash
# DIEP Phase 15C — non-destructive disaster-recovery drill.
#
# For each of TimescaleDB, MQTT, Kafka, Grafana, and FastAPI: restart the container
# (data volumes are untouched — this simulates a process/pod crash + restart, not
# data loss) and measure the time until the service is healthy again (RTO proxy).
#
# Usage: scripts/dr-test.sh [service ...]   (default: all five)
set -uo pipefail
cd "$(dirname "$0")/.."

SERVICES="${*:-timescaledb mqtt kafka grafana fastapi}"

wait_for() {
    local desc="$1"; local cmd="$2"; local timeout="${3:-60}"
    local start=$(date +%s.%N)
    local elapsed
    until eval "${cmd}" >/dev/null 2>&1; do
        elapsed=$(echo "$(date +%s.%N) - ${start}" | bc)
        if (( $(echo "${elapsed} > ${timeout}" | bc -l) )); then
            echo "      TIMEOUT after ${timeout}s waiting for: ${desc}"
            return 1
        fi
        sleep 0.5
    done
    elapsed=$(echo "$(date +%s.%N) - ${start}" | bc)
    printf "      recovered in %.1fs\n" "${elapsed}"
}

echo "=== DIEP Phase 15C DR drill: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

for svc in ${SERVICES}; do
    case "${svc}" in
        timescaledb)
            CONTAINER=diep-timescaledb
            HEALTHCHECK='docker exec diep-timescaledb pg_isready -U diep'
            ;;
        mqtt)
            CONTAINER=diep-mqtt
            # Phase 9J-S4 retired the plaintext 1883 listener; mTLS-only on 8883.
            # No client cert is mounted in the broker container, so probe with a
            # plain TCP connect to confirm the listener is accepting connections.
            HEALTHCHECK='docker exec diep-mqtt nc -z -w2 localhost 8883'
            ;;
        kafka)
            CONTAINER=diep-kafka
            HEALTHCHECK='docker exec diep-kafka /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092'
            ;;
        grafana)
            CONTAINER=diep-grafana
            HEALTHCHECK='curl -sf http://localhost:3001/api/health'
            ;;
        fastapi)
            CONTAINER=diep-fastapi
            HEALTHCHECK='curl -sf http://localhost:8000/healthz'
            ;;
        *)
            echo "unknown service: ${svc}" >&2
            continue
            ;;
    esac

    echo
    echo "--- ${svc} (${CONTAINER}) ---"
    echo "[1/2] restarting container..."
    RESTART_START=$(date +%s.%N)
    docker restart "${CONTAINER}" >/dev/null
    echo "[2/2] waiting for health check: ${HEALTHCHECK}"
    wait_for "${svc}" "${HEALTHCHECK}" 90
    RESTART_END=$(date +%s.%N)
    printf "      total wall time (restart issued -> healthy): %.1fs\n" "$(echo "${RESTART_END} - ${RESTART_START}" | bc)"
done

echo
echo "=== DR drill complete ==="
