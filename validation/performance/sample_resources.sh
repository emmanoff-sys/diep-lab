#!/usr/bin/env bash
# Samples `docker stats` for a container once per second into a CSV, for use
# alongside load_test.py: run this in the background on the host (it needs
# the docker socket, which the load generator container deliberately doesn't
# have) while load_test.py runs, then correlate samples against each tier's
# tier_start_utc/tier_end_utc (printed by load_test.py) to get CPU/memory per
# tier. Stops on SIGTERM/SIGINT or after $3 seconds, whichever first.
#
# Usage: sample_resources.sh <container_name> <output_csv> <max_duration_s>
set -euo pipefail

container="${1:?container name required}"
out="${2:?output csv path required}"
max_duration="${3:-600}"

echo "timestamp_utc,cpu_perc,mem_usage,mem_perc" > "$out"
end=$((SECONDS + max_duration))
while [ "$SECONDS" -lt "$end" ]; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)
  stats=$(docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}' "$container" 2>/dev/null || echo "NA,NA,NA")
  echo "${ts},${stats}" >> "$out"
  sleep 1
done
