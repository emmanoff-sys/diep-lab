#!/bin/sh
# Renders alertmanager.yml from alertmanager.yml.template by substituting
# SMTP credentials from environment variables (sourced from .env via
# docker-compose env_file), then starts Alertmanager. The rendered file
# (containing the SMTP password) lives only in the container's storage
# volume, never in the bind-mounted repo directory.
set -e

RENDERED=/alertmanager/alertmanager.yml

sed \
  -e "s|__ALERT_SMTP_HOST__|${ALERT_SMTP_HOST}|g" \
  -e "s|__ALERT_SMTP_PORT__|${ALERT_SMTP_PORT}|g" \
  -e "s|__ALERT_SMTP_USER__|${ALERT_SMTP_USER}|g" \
  -e "s|__ALERT_SMTP_PASSWORD__|${ALERT_SMTP_PASSWORD}|g" \
  -e "s|__ALERT_RECEIVER_EMAIL__|${ALERT_RECEIVER_EMAIL}|g" \
  /etc/alertmanager-template/alertmanager.yml.template > "$RENDERED"

exec /bin/alertmanager --config.file="$RENDERED" --storage.path=/alertmanager
