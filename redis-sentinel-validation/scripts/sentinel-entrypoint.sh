#!/bin/sh
# K4 Redis Sentinel validation — entrypoint for each sentinel-val-* container.
# Sentinel rewrites its config file at runtime (discovered replicas/sentinels),
# so each instance needs its own writable copy seeded from the read-only template.
set -eu

CONF=/data/sentinel.conf

if [ ! -f "$CONF" ]; then
  # Resolve the primary's current container IP once at first startup.
  # Sentinel (with default resolve-hostnames=no) needs an IP in the
  # "sentinel monitor" line; once monitoring begins it tracks the primary
  # (and any newly promoted primary) by IP regardless of hostname.
  PRIMARY_IP=""
  while [ -z "$PRIMARY_IP" ]; do
    PRIMARY_IP=$(getent hosts diep-redis-val-primary | awk '{print $1}')
    [ -z "$PRIMARY_IP" ] && sleep 1
  done
  sed -e "s/__REDIS_VAL_PASSWORD__/${REDIS_VAL_PASSWORD}/" \
      -e "s/__PRIMARY_IP__/${PRIMARY_IP}/" \
    /etc/redis-sentinel/sentinel.conf.template > "$CONF"
fi

exec redis-sentinel "$CONF"
