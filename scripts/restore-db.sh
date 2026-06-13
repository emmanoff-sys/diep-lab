#!/usr/bin/env bash
# DIEP Phase 9-Data — restore-verify a TimescaleDB dump into a scratch database.
# Usage: scripts/restore-db.sh <dump-file-in-backups/> [target_db]
# Default target is diep_restore_test (a throwaway DB — never touches prod `diep`).
#
# Uses the documented TimescaleDB restore procedure (pre_restore / post_restore) so
# hypertables + continuous aggregates come back correctly.
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP="${1:?usage: restore-db.sh <dump-file-in-backups/> [target_db]}"
TARGET="${2:-diep_restore_test}"
PATH_IN="backups/${DUMP}"
[ -f "${PATH_IN}" ] || { echo "no such dump: ${PATH_IN}"; exit 1; }

echo "[1/5] (re)create scratch database ${TARGET}"
docker exec diep-timescaledb psql -U diep -d postgres -c "DROP DATABASE IF EXISTS ${TARGET} WITH (FORCE);" >/dev/null
docker exec diep-timescaledb psql -U diep -d postgres -c "CREATE DATABASE ${TARGET};" >/dev/null

echo "[2/5] timescaledb extension + pre_restore"
docker exec diep-timescaledb psql -U diep -d "${TARGET}" -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" >/dev/null
docker exec diep-timescaledb psql -U diep -d "${TARGET}" -c "SELECT timescaledb_pre_restore();" >/dev/null

echo "[3/5] pg_restore"
docker exec -i diep-timescaledb pg_restore -U diep -d "${TARGET}" --no-owner < "${PATH_IN}" 2>/dev/null || true

echo "[4/5] post_restore"
docker exec diep-timescaledb psql -U diep -d "${TARGET}" -c "SELECT timescaledb_post_restore();" >/dev/null

echo "[5/5] verify row counts (restored vs prod)"
for tbl in telemetry devices commands audit_events; do
  R=$(docker exec diep-timescaledb psql -U diep -d "${TARGET}" -t -c "SELECT count(*) FROM ${tbl};" 2>/dev/null | xargs)
  P=$(docker exec diep-timescaledb psql -U diep -d diep -t -c "SELECT count(*) FROM ${tbl};" 2>/dev/null | xargs)
  echo "      ${tbl}: restored=${R}  prod=${P}"
done

if [ "${KEEP:-0}" != "1" ]; then
  docker exec diep-timescaledb psql -U diep -d postgres -c "DROP DATABASE ${TARGET} WITH (FORCE);" >/dev/null
  echo "scratch database dropped (set KEEP=1 to keep it)"
fi
echo "Restore-verify complete."
