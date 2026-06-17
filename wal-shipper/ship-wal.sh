#!/bin/sh
# DIEP Phase 22 K1 — production WAL shipper sidecar.
# Mirrors staged WAL segments from the shared /wal-archive volume (written by
# diep-timescaledb's archive_command) to MinIO, and bootstraps the buckets.
# Mirrors the validated design in pitr-validation/scripts/ship-wal.sh.
set -eu

mc alias set m http://diep-minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
mc mb -p m/diep-wal-archive >/dev/null 2>&1 || true
mc mb -p m/diep-pg-basebackups >/dev/null 2>&1 || true
mc encrypt set sse-kms "${MINIO_KMS_KEY_NAME:-diep-backup-key}" m/diep-wal-archive >/dev/null 2>&1 || true
mc encrypt set sse-kms "${MINIO_KMS_KEY_NAME:-diep-backup-key}" m/diep-pg-basebackups >/dev/null 2>&1 || true

echo "wal-shipper started, mirroring /wal-archive -> m/diep-wal-archive every 15s"
while true; do
  mc mirror --quiet --overwrite /wal-archive m/diep-wal-archive || true
  sleep 15
done
