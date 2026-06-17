#!/bin/sh
# DIEP Phase 22 INFRA-2 / K4 — production Sentinel entrypoint.
# Sentinel rewrites its config file at runtime (discovered replicas/other
# sentinels), so each instance needs its own writable copy seeded from the
# read-only template — same pattern as redis-sentinel-validation/scripts/.
set -eu

CONF=/data/sentinel.conf

if [ ! -f "$CONF" ]; then
  sed -e "s/__REDIS_PASSWORD__/${REDIS_PASSWORD}/" \
    /etc/redis-sentinel/sentinel.conf.template > "$CONF"
fi

exec redis-sentinel "$CONF"
