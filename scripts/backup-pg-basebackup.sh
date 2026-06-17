#!/usr/bin/env bash
# DIEP Phase 22 K1 PITR — weekly physical base backup, uploaded to MinIO.
# Complements (does not replace) the existing nightly logical pg_dump
# (scripts/backup-db.sh) and the continuous WAL archive (wal-shipper sidecar):
# base backup + WAL archive together form the physical PITR restore chain
# (K1_PITR_IMPLEMENTATION_PLAN.md §3.3/§3.5).
# Usage: scripts/backup-pg-basebackup.sh
# Env:   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD, DIEP_NET (autodetected),
#        BASEBACKUP_BUCKET (default diep-pg-basebackups),
#        BASEBACKUP_RETENTION_DAYS (default 28, i.e. 4 weeks).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-backup-alert.sh

TS=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="diep_basebackup_${TS}.tar.gz"
DETECTED_NET=$(detect_diep_net || true)
NET="${DIEP_NET:-${DETECTED_NET:-diep-lab_diep-net}}"
BUCKET="${BASEBACKUP_BUCKET:-diep-pg-basebackups}"
MUSER="${MINIO_ROOT_USER:-admin}"
MPASS="${MINIO_ROOT_PASSWORD:-diep12345}"
RETENTION_DAYS="${BASEBACKUP_RETENTION_DAYS:-28}"

trap 'rc=$?; if [ $rc -ne 0 ]; then alert_backup_failure "backup-pg-basebackup" "scripts/backup-pg-basebackup.sh exited $rc (see ${LOG_DIR:-backups/logs}/backup-pg-basebackup.log)"; fi' EXIT

mkdir -p backups
echo "[1/4] pg_basebackup (tar, gzip, fast checkpoint) -> backups/${ARCHIVE}"
# -Xfetch (not -Xs/--wal-method=stream): streaming WAL into the same tar
# written to stdout (-D -) is rejected by pg_basebackup ("cannot stream
# write-ahead logs in tar mode to stdout") -- fetch is the stdout-compatible
# equivalent, and is sufficient here since continuous WAL archiving already
# covers the gap between base backups (wal-shipper sidecar).
docker exec diep-timescaledb pg_basebackup -D - -Ft -z -Xfetch -c fast -U diep > "backups/${ARCHIVE}"
LOCAL_SIZE=$(stat -c%s "backups/${ARCHIVE}" 2>/dev/null || stat -f%z "backups/${ARCHIVE}")
echo "      size: $(du -h "backups/${ARCHIVE}" | cut -f1)"

echo "[2/4] upload to MinIO (s3://${BUCKET}/${ARCHIVE}) on network ${NET}"
docker run --rm --network "${NET}" -v "$PWD/backups:/backups" --entrypoint /bin/sh minio/mc -c "
  set -e
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null
  mc mb -p m/${BUCKET} >/dev/null 2>&1 || true
  mc cp /backups/${ARCHIVE} m/${BUCKET}/ >/dev/null
"

echo "[3/4] positive upload confirmation (size match)"
REMOTE_SIZE=$(docker run --rm --network "${NET}" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null
  mc stat --json m/${BUCKET}/${ARCHIVE}
" | jq -r '.size' 2>/dev/null | head -1 || true)
if [ -z "${REMOTE_SIZE}" ] || [ "${REMOTE_SIZE}" = "null" ] || [ "${REMOTE_SIZE}" != "${LOCAL_SIZE}" ]; then
    echo "      FAIL: uploaded object size (${REMOTE_SIZE:-missing}) does not match local file (${LOCAL_SIZE})" >&2
    exit 1
fi
echo "      OK: s3://${BUCKET}/${ARCHIVE} confirmed (${REMOTE_SIZE} bytes)"

echo "[4/4] retention prune (local + MinIO, >${RETENTION_DAYS}d)"
find backups -maxdepth 1 -name 'diep_basebackup_*.tar.gz' -mtime "+${RETENTION_DAYS}" -print -delete || true
docker run --rm --network "${NET}" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null &&
  mc rm --force --older-than ${RETENTION_DAYS}d m/${BUCKET}/ || true
"

echo "Base backup complete: ${ARCHIVE}"
