#!/usr/bin/env bash
# DIEP Phase 15C — backup verification: checksum + restore-into-scratch-DB.
# Usage: scripts/verify-backup.sh [dump-file-in-backups/]
#        (defaults to the most recent backups/diep_*.dump)
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP="${1:-}"
if [ -z "${DUMP}" ]; then
    DUMP=$(ls -1t backups/diep_*.dump 2>/dev/null | head -1 | xargs -n1 basename || true)
fi
[ -n "${DUMP}" ] && [ -f "backups/${DUMP}" ] || { echo "no dump found in backups/"; exit 1; }

START=$(date +%s)
echo "=== Verifying ${DUMP} ==="

echo "[1/2] checksum"
if [ -f "backups/${DUMP}.sha256" ]; then
    sha256sum -c "backups/${DUMP}.sha256"
else
    echo "      (no .sha256 sidecar — recording current hash)"
    sha256sum "backups/${DUMP}" | tee "backups/${DUMP}.sha256"
fi

echo "[2/2] restore-verify into scratch database"
./scripts/restore-db.sh "${DUMP}"

END=$(date +%s)
echo "=== PASS: ${DUMP} verified in $((END-START))s ==="
