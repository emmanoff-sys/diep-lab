#!/usr/bin/env bash
# DIEP Phase 9-Data / 15C — logical backup of the TimescaleDB database to local
# archive + MinIO object storage, with checksum verification and retention pruning.
# Usage: scripts/backup-db.sh
# Env:   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD (default admin/diep12345),
#        DIEP_NET (autodetected from the running diep-minio container if unset —
#        see Phase 21 fix for INSTALL-3 below), BACKUP_BUCKET (default diep-backups),
#        BACKUP_RETENTION_DAYS (default 14, applied to both local archive and MinIO).
#
# Phase 21 (INSTALL-3 fix): this script previously reported success even when
# the MinIO upload silently failed, for two compounding reasons fixed here:
#   1. DIEP_NET defaulted to a hardcoded "diep-lab_diep-net", which is wrong
#      for any clone whose directory/Compose project isn't exactly "diep-lab" —
#      now autodetected from the running diep-minio container instead.
#   2. The upload chain and the retention prune were one shell `-c "A && B || true"`
#      command; bash's left-associative &&/|| meant the trailing `|| true`
#      (meant only to tolerate "nothing to prune") actually swallowed a
#      failure ANYWHERE in the chain, including the upload itself. Upload and
#      prune are now separate `docker run` invocations, and a positive
#      `mc stat` check confirms the uploaded object's size matches the local
#      file before this script considers the backup complete.
#
# Production note: this logical (pg_dump) backup complements — does not replace —
# continuous WAL archiving + PITR, which is configured via the CloudNativePG operator
# in k8s/postgres-cnpg.yaml (point-in-time recovery, not just nightly snapshots).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-backup-alert.sh

TS=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="diep_${TS}.dump"
DETECTED_NET=$(detect_diep_net || true)
NET="${DIEP_NET:-${DETECTED_NET:-diep-lab_diep-net}}"
BUCKET="${BACKUP_BUCKET:-diep-backups}"
MUSER="${MINIO_ROOT_USER:-admin}"
MPASS="${MINIO_ROOT_PASSWORD:-diep12345}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

trap 'rc=$?; if [ $rc -ne 0 ]; then alert_backup_failure "backup-db" "scripts/backup-db.sh exited $rc (see ${LOG_DIR:-backups/logs}/backup-db.log)"; fi' EXIT

mkdir -p backups
echo "[1/5] pg_dump (custom format) -> backups/${DUMP}"
docker exec diep-timescaledb pg_dump -U diep -Fc -d diep > "backups/${DUMP}"
LOCAL_SIZE=$(stat -c%s "backups/${DUMP}" 2>/dev/null || stat -f%z "backups/${DUMP}")
echo "      size: $(du -h "backups/${DUMP}" | cut -f1)"

echo "[2/5] verify dump table-of-contents + checksum"
docker exec -i diep-timescaledb pg_restore --list < "backups/${DUMP}" \
    | grep -E "TABLE DATA public (telemetry|devices|commands|audit_events)" | head || true
sha256sum "backups/${DUMP}" | tee "backups/${DUMP}.sha256"

echo "[3/5] upload to MinIO (s3://${BUCKET}/${DUMP}) on network ${NET}"
docker run --rm --network "${NET}" -v "$PWD/backups:/backups" --entrypoint /bin/sh minio/mc -c "
  set -e
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null
  mc mb -p m/${BUCKET} >/dev/null 2>&1 || true
  mc cp /backups/${DUMP} m/${BUCKET}/ >/dev/null
  mc cp /backups/${DUMP}.sha256 m/${BUCKET}/ >/dev/null
"

echo "[4/5] positive upload confirmation (size match)"
REMOTE_SIZE=$(docker run --rm --network "${NET}" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null
  mc stat --json m/${BUCKET}/${DUMP}
" | jq -r '.size' 2>/dev/null | head -1 || true)
if [ -z "${REMOTE_SIZE}" ] || [ "${REMOTE_SIZE}" = "null" ] || [ "${REMOTE_SIZE}" != "${LOCAL_SIZE}" ]; then
    echo "      FAIL: uploaded object size (${REMOTE_SIZE:-missing}) does not match local file (${LOCAL_SIZE})" >&2
    exit 1
fi
echo "      OK: s3://${BUCKET}/${DUMP} confirmed (${REMOTE_SIZE} bytes)"

echo "[5/5] retention prune (local + MinIO, >${RETENTION_DAYS}d)"
find backups -maxdepth 1 -name 'diep_*.dump*' -mtime "+${RETENTION_DAYS}" -print -delete || true
docker run --rm --network "${NET}" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null &&
  mc rm --force --older-than ${RETENTION_DAYS}d m/${BUCKET}/ || true
"

echo "Backup complete: ${DUMP}"
