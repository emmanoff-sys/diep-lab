#!/bin/sh
# DIEP Phase 22 K1 — production WAL shipper sidecar.
#
# Ships WAL segments staged by diep-timescaledb's archive_command from the
# shared /wal-archive volume to MinIO, then PRUNES the local copy — but only
# after positively confirming the upload to MinIO succeeded.
#
# Incident MW1-PITR-WAL-LEAK (2026-06-18): the previous version used
# `mc mirror` and never pruned local staging, so /wal-archive grew unbounded
# (~1 GB/hour at archive_timeout=60) until the root filesystem filled and
# PostgreSQL crash-looped. K1_PITR_IMPLEMENTATION_PLAN.md §3.1 required
# "pruning shipped segments locally once confirmed" — this is that fix.
#
# Verification uses mc's own EXIT CODES (no text parsing): the minio/mc image
# is minimal and has no grep/awk/sed. `mc cp` returns 0 only after a
# checksum-verified transfer; `mc stat` returns 0 only if the object exists.
#
# Safety contract (matches the recovery rule): a local segment is deleted ONLY
# after (a) `mc cp` succeeds, (b) `mc stat` confirms the object exists in
# MinIO, and (c) the local file did not change during upload (guards against
# pruning a half-written segment while archive_command's cp is still in
# flight). Any failure KEEPS the local copy for the next cycle — an
# unconfirmed segment is never deleted. (Verified live during the recovery:
# when verification could not run, every segment was kept, zero data loss.)
set -u

ALIAS=m
BUCKET=diep-wal-archive
STAGE=/wal-archive
KEY="${MINIO_KMS_KEY_NAME:-diep-backup-key}"
INTERVAL="${SHIP_INTERVAL:-15}"
# Retention safeguard: warn loudly if local staging exceeds this many bytes
# (default 2 GiB) — early-warning that uploads are failing (e.g. MinIO
# unreachable) BEFORE the disk fills, so the leak can never silently recur.
# We never auto-delete unconfirmed segments to satisfy a threshold.
WARN_BYTES="${STAGE_WARN_BYTES:-2147483648}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] wal-shipper: $*"; }

mc alias set $ALIAS http://diep-minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
mc mb -p $ALIAS/$BUCKET >/dev/null 2>&1 || true
mc mb -p $ALIAS/diep-pg-basebackups >/dev/null 2>&1 || true
mc encrypt set sse-kms "$KEY" $ALIAS/$BUCKET >/dev/null 2>&1 || true
mc encrypt set sse-kms "$KEY" $ALIAS/diep-pg-basebackups >/dev/null 2>&1 || true

log "started; upload-verify-prune loop every ${INTERVAL}s (bucket=$BUCKET, warn>${WARN_BYTES}B)"
while true; do
  shipped=0; pruned=0; kept=0
  for f in "$STAGE"/*; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    case "$name" in *.tmp|*.partial) continue ;; esac

    size_before=$(stat -c%s "$f" 2>/dev/null || echo 0)

    # (a) upload — mc cp exits 0 only after a checksum-verified transfer
    if ! mc cp --quiet "$f" "$ALIAS/$BUCKET/$name" >/dev/null 2>&1; then
      log "WARN upload failed: $name (retry next cycle)"; kept=$((kept+1)); continue
    fi
    shipped=$((shipped+1))

    # (b) confirm the object now exists in MinIO (exit-code only, no parsing)
    if ! mc stat "$ALIAS/$BUCKET/$name" >/dev/null 2>&1; then
      log "WARN post-upload stat missing: $name (keep)"; kept=$((kept+1)); continue
    fi

    # (c) confirm the local file did not change during upload
    size_after=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [ "$size_before" != "$size_after" ]; then
      log "WARN size changed during upload: $name ($size_before->$size_after) (keep)"; kept=$((kept+1)); continue
    fi

    rm -f "$f" && pruned=$((pruned+1))
  done

  [ "$pruned" -gt 0 ] || [ "$kept" -gt 0 ] && log "cycle: shipped=$shipped pruned=$pruned kept=$kept"

  # Phase 22 MON-5 — freshness metric for the WalArchiveStalled Prometheus
  # alert. Written every cycle (not just on shipped>0) so the timestamp
  # reflects "the loop is alive", not "there was WAL to ship".
  cat > /textfile_collector/diep_wal_shipper.prom.tmp <<METRICS
# HELP diep_wal_last_cycle_timestamp_seconds Unix time of the last completed wal-shipper upload-verify-prune cycle.
# TYPE diep_wal_last_cycle_timestamp_seconds gauge
diep_wal_last_cycle_timestamp_seconds $(date -u +%s)
METRICS
  mv /textfile_collector/diep_wal_shipper.prom.tmp /textfile_collector/diep_wal_shipper.prom

  # retention safeguard / early-warning before any disk-fill recurrence
  used=$(du -sb "$STAGE" 2>/dev/null | cut -f1)
  if [ -n "${used:-}" ] && [ "$used" -gt "$WARN_BYTES" ] 2>/dev/null; then
    log "ALERT staging at ${used}B > ${WARN_BYTES}B threshold — uploads likely failing; investigate before disk fills"
  fi

  sleep "$INTERVAL"
done
