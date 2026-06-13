#!/usr/bin/env bash
# DIEP Phase 15C — install scheduled backup jobs into the current user's crontab.
# Idempotent: removes any prior DIEP backup lines (marked with the "# diep-backup"
# tag) before re-adding, so re-running this script is safe.
#
# Schedule:
#   02:00 daily  - database backup (scripts/backup-db.sh)
#   02:30 daily  - configuration backup (scripts/backup-config.sh)
#   03:00 Sunday - backup verification / restore drill (scripts/verify-backup.sh)
#
# Usage: scripts/install-backup-cron.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
ENV_FILE="${ROOT}/.env"
LOG_DIR="${ROOT}/backups/logs"
mkdir -p "${LOG_DIR}"

TAG="# diep-backup"
NEW_CRON=$(cat <<EOF
${TAG}
0 2 * * *  cd ${ROOT} && set -a && . ${ENV_FILE} && set +a && ./scripts/backup-db.sh >> ${LOG_DIR}/backup-db.log 2>&1 ${TAG}
30 2 * * * cd ${ROOT} && set -a && . ${ENV_FILE} && set +a && ./scripts/backup-config.sh >> ${LOG_DIR}/backup-config.log 2>&1 ${TAG}
0 3 * * 0  cd ${ROOT} && set -a && . ${ENV_FILE} && set +a && ./scripts/verify-backup.sh >> ${LOG_DIR}/verify-backup.log 2>&1 ${TAG}
EOF
)

( crontab -l 2>/dev/null | { grep -v "${TAG}" || true; } ; printf '%s\n' "${NEW_CRON}" ) | crontab -
echo "Installed crontab entries:"
crontab -l | grep "${TAG}"
