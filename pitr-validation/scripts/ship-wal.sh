#!/bin/sh
# K1 PITR validation — WAL shipper sidecar.
# Mirrors staged WAL segments from the shared /wal-archive volume to MinIO,
# and bootstraps the validation buckets.
set -eu

mc alias set m http://diep-minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
mc mb -p m/diep-wal-archive >/dev/null 2>&1 || true
mc mb -p m/diep-pg-basebackups >/dev/null 2>&1 || true

echo "wal-shipper started, mirroring /wal-archive -> m/diep-wal-archive every 5s"
while true; do
  mc mirror --quiet --overwrite /wal-archive m/diep-wal-archive || true
  sleep 5
done
