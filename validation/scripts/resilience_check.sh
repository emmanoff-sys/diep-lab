#!/bin/bash
# SIT Deliverable 4 — resilience: graceful docker compose restart per service,
# verifying no crash loop and recovery. Run from repo root.
set -uo pipefail

SERVICE="$1"
CONTAINER="diep-$SERVICE"

echo "=== Resilience check: $SERVICE ($CONTAINER) ==="
echo "--- baseline ---"
docker ps --filter "name=$CONTAINER" --format '{{.Names}}: {{.Status}}'

echo "--- restarting ---"
# -p diep-lab: this worktree's directory basename differs from the main
# checkout's, so compose's auto-inferred project name wouldn't match the
# live containers (started from the main checkout) without this.
docker compose -p diep-lab restart "$SERVICE" 2>&1

echo "--- waiting for container to report Up ---"
for i in $(seq 1 30); do
  status=$(docker ps --filter "name=$CONTAINER" --format '{{.Status}}')
  if [[ "$status" == Up* ]]; then
    echo "Up after ${i}x2s: $status"
    break
  fi
  sleep 2
done

echo "--- post-restart status ---"
docker ps --filter "name=$CONTAINER" --format '{{.Names}}: {{.Status}}'
echo "--- restart count ---"
docker inspect "$CONTAINER" --format 'RestartCount: {{.RestartCount}}'
