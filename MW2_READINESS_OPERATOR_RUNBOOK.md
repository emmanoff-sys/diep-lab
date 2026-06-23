# MW2 Readiness Operator Runbook

## Purpose

This runbook covers the automated MW2 readiness verification framework added after
the 2026-06-23 Redis/Kafka recovery. It gives operators a repeatable way to:

- run the readiness assessment from the Docker host
- persist scored results into the TimescaleDB production database
- review the latest result via the FastAPI control surface
- confirm the 24-hour stability observation period before authorizing MW2

The framework is additive only. It writes new rows to `platform_readiness_reports`
and does not modify any existing production application tables.

## What It Checks

The runner evaluates nine checks for a total score of 100:

1. FastAPI `/readyz`
2. PostgreSQL connectivity
3. Redis connectivity and authentication
4. Kafka broker health
5. Kafka exporter metrics availability
6. Docker container restart deltas
7. Disk utilization threshold
8. Memory utilization threshold
9. Critical service uptime threshold

Default MW2 policy:

- pass threshold: `90`
- minimum uptime: `86400` seconds (24 hours)
- maximum restart delta: `0`
- disk maximum used: `85%`
- memory maximum used: `85%`

These defaults are configurable through the `READINESS_*` values in
`.env.example`.

## Prerequisites

1. Apply the new schema migration:

```bash
./init-db.sh
```

This picks up `sql/022_platform_readiness.sql`.

2. Ensure the host Python environment has the FastAPI dependency set:

```bash
python3 -m pip install -r fastapi/requirements.txt
```

3. Confirm `.env` contains the `READINESS_*` values appropriate for the host.

## Run the Assessment

From the Docker host:

```bash
python3 scripts/run_mw2_readiness_check.py --json
```

Behavior:

- reads `.env` by default
- inspects Docker container state from the host
- verifies the live services
- persists a row to `platform_readiness_reports`
- prints a JSON report
- exits `0` on PASS, `1` on FAIL

To dry-run without writing a DB row:

```bash
python3 scripts/run_mw2_readiness_check.py --json --no-persist
```

## Review the Result

Latest result:

```bash
curl -H "Authorization: Bearer $DIEP_ADMIN_KEY" \
  http://127.0.0.1:8000/controls/readiness
```

History:

```bash
curl -H "Authorization: Bearer $DIEP_ADMIN_KEY" \
  "http://127.0.0.1:8000/controls/readiness/history?since_hours=48&limit=20"
```

Access is intentionally restricted to `engineer`, `admin`, and `service`
principals because the response includes infrastructure-sensitive details such as
restart counts and host resource usage.

## Prometheus Metrics

The FastAPI `/metrics` endpoint now publishes:

- `diep_readiness_score`
- `diep_readiness_pass`
- `diep_readiness_last_run_timestamp_seconds`
- `diep_readiness_check_status{check_name=...}`

These metrics reflect the latest persisted readiness run.

## Recommended Automation

Use cron or a systemd timer on the Docker host during the MW2 observation period.
Example crontab entry:

```cron
*/5 * * * * cd /home/emmanoff_lab/projects/diep-lab && /usr/bin/python3 scripts/run_mw2_readiness_check.py >> /var/log/diep-mw2-readiness.log 2>&1
```

Five-minute cadence is usually enough for the 24-hour soak.

## PASS / FAIL Interpretation

PASS means:

- no check is in `FAIL`
- score is at or above the configured pass threshold

FAIL means MW2 stays blocked. Common causes:

- `/readyz` is not fully green
- PostgreSQL, Redis, or Kafka is unreachable
- Kafka exporter metrics are missing
- a critical container restarted since the prior persisted run
- disk or memory usage exceeds threshold
- any critical service has less than 24 hours of continuous uptime

## Sample Reports

- `docs/readiness/mw2_readiness_fail_sample.json`
- `docs/readiness/mw2_readiness_pass_sample.json`

## Rollback / Removal

This feature is low-risk and additive:

- stop running `scripts/run_mw2_readiness_check.py`
- keep or ignore the historical rows in `platform_readiness_reports`
- the API and metrics remain read-only against those rows

No existing operational data is touched.

