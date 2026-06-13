#!/usr/bin/env bash
# DIEP Phase 9-Data / 15C — logical backup of the TimescaleDB database to local
# archive + MinIO object storage, with checksum verification and retention pruning.
# Usage: scripts/backup-db.sh
# Env:   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD (default admin/diep12345),
#        DIEP_NET (default diep-lab_diep-net), BACKUP_BUCKET (default diep-backups),
#        BACKUP_RETENTION_DAYS (default 14, applied to both local archive and MinIO).
#
# Production note: this logical (pg_dump) backup complements — does not replace —
# continuous WAL archiving + PITR, which is configured via the CloudNativePG operator
# in k8s/postgres-cnpg.yaml (point-in-time recovery, not just nightly snapshots).
set -euo pipefail
cd "$(dirname "$0")/.."

TS=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="diep_${TS}.dump"
NET="${DIEP_NET:-diep-lab_diep-net}"
BUCKET="${BACKUP_BUCKET:-diep-backups}"
MUSER="${MINIO_ROOT_USER:-admin}"
MPASS="${MINIO_ROOT_PASSWORD:-diep12345}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p backups
echo "[1/4] pg_dump (custom format) -> backups/${DUMP}"
docker exec diep-timescaledb pg_dump -U diep -Fc -d diep > "backups/${DUMP}"
echo "      size: $(du -h "backups/${DUMP}" | cut -f1)"

echo "[2/4] verify dump table-of-contents + checksum"
docker exec -i diep-timescaledb pg_restore --list < "backups/${DUMP}" \
    | grep -E "TABLE DATA public (telemetry|devices|commands|audit_events)" | head || true
sha256sum "backups/${DUMP}" | tee "backups/${DUMP}.sha256"

echo "[3/4] upload to MinIO (s3://${BUCKET}/${DUMP}) + retention prune"
docker run --rm --network "${NET}" -v "$PWD/backups:/backups" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null &&
  ( mc mb -p m/${BUCKET} >/dev/null 2>&1 || true ) &&
  mc cp /backups/${DUMP} m/${BUCKET}/ >/dev/null &&
  mc cp /backups/${DUMP}.sha256 m/${BUCKET}/ >/dev/null &&
  echo '      objects in bucket:' &&
  mc ls m/${BUCKET}/ | tail -5 &&
  echo '      pruning objects older than ${RETENTION_DAYS}d:' &&
  mc rm --force --older-than ${RETENTION_DAYS}d m/${BUCKET}/ || true
"

echo "[4/4] local retention prune (>${RETENTION_DAYS}d)"
find backups -maxdepth 1 -name 'diep_*.dump*' -mtime "+${RETENTION_DAYS}" -print -delete || true

echo "Backup complete: ${DUMP}"
