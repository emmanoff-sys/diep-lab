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
# Env:   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD, DIEP_NET (default diep-lab_diep-net),
#        CONFIG_BACKUP_BUCKET (default diep-config-backups),
#        BACKUP_RETENTION_DAYS (default 14).
set -euo pipefail
cd "$(dirname "$0")/.."

TS=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="diep-config_${TS}.tar.gz"
NET="${DIEP_NET:-diep-lab_diep-net}"
BUCKET="${CONFIG_BACKUP_BUCKET:-diep-config-backups}"
MUSER="${MINIO_ROOT_USER:-admin}"
MPASS="${MINIO_ROOT_PASSWORD:-diep12345}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p backups/config

echo "[1/4] tar configuration tree -> backups/config/${ARCHIVE}"
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
echo "      size: $(du -h "backups/config/${ARCHIVE}" | cut -f1)"

echo "[2/4] checksum"
sha256sum "backups/config/${ARCHIVE}" | tee "backups/config/${ARCHIVE}.sha256"

echo "[3/4] verify archive contents (top-level entries)"
tar -tzf "backups/config/${ARCHIVE}" | awk -F/ '{print $1"/"$2}' | sort -u | head -20

echo "[4/4] upload to MinIO (s3://${BUCKET}/${ARCHIVE}) + retention prune"
docker run --rm --network "${NET}" -v "$PWD/backups/config:/backups" --entrypoint /bin/sh minio/mc -c "
  mc alias set m http://diep-minio:9000 ${MUSER} ${MPASS} >/dev/null &&
  ( mc mb -p m/${BUCKET} >/dev/null 2>&1 || true ) &&
  mc cp /backups/${ARCHIVE} m/${BUCKET}/ >/dev/null &&
  mc cp /backups/${ARCHIVE}.sha256 m/${BUCKET}/ >/dev/null &&
  echo '      objects in bucket:' &&
  mc ls m/${BUCKET}/ | tail -5 &&
  echo '      pruning objects older than ${RETENTION_DAYS}d:' &&
  mc rm --force --older-than ${RETENTION_DAYS}d m/${BUCKET}/ || true
"

find backups/config -maxdepth 1 -name 'diep-config_*.tar.gz*' -mtime "+${RETENTION_DAYS}" -print -delete || true

echo "Config backup complete: ${ARCHIVE}"
