#!/usr/bin/env bash
# DIEP Phase 15C — configuration backup: Docker Compose files, MQTT/mosquitto certs +
# config, Alertmanager config, Grafana provisioning (dashboards + datasources),
# Prometheus config, and device certs, archived to local + MinIO object storage.
#
# Does NOT include .env (secrets) — see PHASE15A_SECURITY_HARDENING_REPORT.md for
# why .env must never be committed or bundled into a shared archive. Operators
# restoring from this archive must restore .env separately from a secrets vault.
#
# Usage: scripts/backup-config.sh
# Env:   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD, DIEP_NET (autodetected from the
#        running diep-minio container if unset — Phase 21 fix for INSTALL-3,
#        see scripts/backup-db.sh for the full root-cause writeup),
#        CONFIG_BACKUP_BUCKET (default diep-config-backups),
#        BACKUP_RETENTION_DAYS (default 14).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-backup-alert.sh

TS=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="diep-config_${TS}.tar.gz"
DETECTED_NET=$(detect_diep_net || true)
NET="${DIEP_NET:-${DETECTED_NET:-diep-lab_diep-net}}"
BUCKET="${CONFIG_BACKUP_BUCKET:-diep-config-backups}"
MUSER="${MINIO_ROOT_USER:-admin}"
MPASS="${MINIO_ROOT_PASSWORD:-diep12345}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

trap 'rc=$?; if [ $rc -ne 0 ]; then alert_backup_failure "backup-config" "scripts/backup-config.sh exited $rc (see ${LOG_DIR:-backups/logs}/backup-config.log)"; fi' EXIT

mkdir -p backups/config

echo "[1/5] tar configuration tree -> backups/config/${ARCHIVE}"
tar -czf "backups/config/${ARCHIVE}" \
    --exclude='mosquitto/config/*.bak' \
    --exclude='*.pre-phase15a.bak' \
    docker-compose*.yml \
    mosquitto/config \
    alertmanager/alertmanager.yml \
    grafana/provisioning \
    prometheus/prometheus.yml \
    prometheus/alerts.yml \
    prometheus/postgres_exporter_queries.yaml \
    certs \
    .env.example
LOCAL_SIZE=$(stat -c%s "backups/config/${ARCHIVE}" 2>/dev/null || stat -f%z "backups/config/${ARCHIVE}")
echo "      size: $(du -h "backups/config/${ARCHIVE}" | cut -f1)"

echo "[2/5] checksum"
sha256sum "backups/config/${ARCHIVE}" | tee "backups/config/${ARCHIVE}.sha256"

echo "[3/5] verify archive contents (top-level entries)"
tar -tzf "backups/config/${ARCHIVE}" | awk -F/ '{print $1"/"$2}' | sort -u | head -20

echo "[4/5] upload to MinIO (s3://${BUCKET}/${ARCHIVE}) on network ${NET}"
docker run --rm --network "${NET}" -v "$PWD/backups/config:/backups" --entrypoint /bin/sh minio/mc -c "
  set -e
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null
  mc mb -p m/${BUCKET} >/dev/null 2>&1 || true
  mc cp /backups/${ARCHIVE} m/${BUCKET}/ >/dev/null
  mc cp /backups/${ARCHIVE}.sha256 m/${BUCKET}/ >/dev/null
"

echo "      positive upload confirmation (size match)"
REMOTE_SIZE=$(docker run --rm --network "${NET}" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null
  mc stat --json m/${BUCKET}/${ARCHIVE}
" | jq -r '.size' 2>/dev/null | head -1 || true)
if [ -z "${REMOTE_SIZE}" ] || [ "${REMOTE_SIZE}" = "null" ] || [ "${REMOTE_SIZE}" != "${LOCAL_SIZE}" ]; then
    echo "      FAIL: uploaded object size (${REMOTE_SIZE:-missing}) does not match local file (${LOCAL_SIZE})" >&2
    exit 1
fi
echo "      OK: s3://${BUCKET}/${ARCHIVE} confirmed (${REMOTE_SIZE} bytes)"

echo "[5/5] retention prune (local + MinIO, >${RETENTION_DAYS}d)"
find backups/config -maxdepth 1 -name 'diep-config_*.tar.gz*' -mtime "+${RETENTION_DAYS}" -print -delete || true
docker run --rm --network "${NET}" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null &&
  mc rm --force --older-than ${RETENTION_DAYS}d m/${BUCKET}/ || true
"

echo "Config backup complete: ${ARCHIVE}"
