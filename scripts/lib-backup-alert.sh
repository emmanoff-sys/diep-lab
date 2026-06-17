#!/usr/bin/env bash
# DIEP Phase 21 — shared helpers for scripts/backup-db.sh and
# scripts/backup-config.sh.
#
# detect_diep_net(): replaces the old hardcoded "diep-lab_diep-net" default
# (INSTALL-3 root cause #1 — wrong for any clone whose directory/Compose
# project isn't literally named diep-lab) by reading the network the running
# diep-minio container is actually attached to.
#
# alert_backup_failure(): pushes a critical-severity alert into the
# Alertmanager instance that's already part of this stack (no new
# notification path), so a failed backup is visible the same way any other
# platform alert is, instead of only living in a cron log nobody is tailing.
detect_diep_net() {
    docker inspect diep-minio \
        --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null
}

alert_backup_failure() {
    local job="$1" reason="$2"
    local am="${ALERTMANAGER_URL:-http://localhost:9093}"
    local now
    now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    if ! curl -sf -X POST "${am}/api/v2/alerts" -H 'Content-Type: application/json' -d "[{
        \"labels\": {\"alertname\": \"BackupFailed\", \"severity\": \"critical\", \"job\": \"${job}\"},
        \"annotations\": {\"summary\": \"${job} failed\", \"description\": \"${reason}\"},
        \"startsAt\": \"${now}\"
    }]" >/dev/null 2>&1; then
        echo "      WARNING: could not reach Alertmanager (${am}) to raise BackupFailed alert" >&2
    fi
}
