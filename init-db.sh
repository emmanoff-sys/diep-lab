#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Waiting for TimescaleDB container..."
until docker exec diep-timescaledb pg_isready -U diep >/dev/null 2>&1; do
  sleep 2
  echo "Waiting for TimescaleDB..."
done

echo "Applying DIEP schema and seed SQL..."
cat sql/000_schema.sql sql/001_commands.sql sql/002_seed_battery_solar.sql sql/003_seed_microgrid.sql sql/004_seed_smartmeter.sql sql/005_derms.sql sql/006_analytics.sql sql/007_onboarding.sql sql/008_security.sql sql/009_schema_extension.sql sql/010_data_lifecycle.sql sql/011_tenancy.sql sql/012_users_rbac.sql | docker exec -i diep-timescaledb psql -U diep -d diep

echo "Database initialization complete."
