#!/bin/sh
# K6 MinIO HA validation — WAL shipper pointing at the distributed cluster.
# Identical logic to pitr-validation/scripts/ship-wal.sh; only the endpoint
# changes to validate that the distributed MinIO is a drop-in replacement.
set -eu

ENDPOINT="${MINIO_HA_ENDPOINT:-http://minio-ha-0:9000}"
ALIAS="${MINIO_HA_ALIAS:-m-ha}"
USER="${MINIO_ROOT_USER:-minio-ha-val}"
PASS="${MINIO_ROOT_PASSWORD:-ha-val-minio-2026}"

mc alias set "${ALIAS}" "${ENDPOINT}" "${USER}" "${PASS}" >/dev/null
mc mb -p "${ALIAS}/diep-wal-archive-ha-test" >/dev/null 2>&1 || true
mc mb -p "${ALIAS}/diep-pg-basebackups-ha-test" >/dev/null 2>&1 || true

echo "ship-wal-ha started — mirroring /wal-archive -> ${ALIAS}/diep-wal-archive-ha-test every 5s"
while true; do
  mc mirror --quiet --overwrite /wal-archive "${ALIAS}/diep-wal-archive-ha-test" || true
  sleep 5
done
