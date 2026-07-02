# DORA Metrics — DAEP / RE-OS

**Authority:** WP-004-14 | Roadmap v1.0 §Delivery Metrics (DORA)

This document closes every "feeds the DORA dashboard" forward reference
in EPIC-004 (and several in EPIC-001/003).

## Four Standard DORA Metrics

| Metric | Definition | Data Source | Calculation |
|--------|-----------|-------------|-------------|
| Deployment Frequency | How often code ships to Production | GitHub Actions `deploy-production` run history | Successful runs / weeks in window |
| Lead Time for Changes | How fast committed code reaches Production | Same run history | Median of (`updated_at - created_at`) per successful production run |
| Change Failure Rate | % of deployments causing a failure | Same run history | Failed + cancelled runs / total runs |
| MTTR (Mean Time to Recovery) | How fast from incident to recovery | WP-004-13 timed rollback drills | Measured manually; future: auto-compute from rollback run pairs |

## Generation

```bash
# On demand:
python3 scripts/dora-metrics.py --days 30

# Write to file:
python3 scripts/dora-metrics.py --days 30 --output reports/dora/$(date +%Y-%m-%d).md
```

Requires `GITHUB_TOKEN` env var (read-only scope) and the `gh` CLI authenticated.

The `dora-report.yml` workflow generates a fresh report every Monday at 3am
UTC, committing it to `reports/dora/`.

## Release 1 Note (§35)

The first DORA numbers from this pipeline describe this package's own
infrastructure-foundation delivery — not a representative production workload.
The values only become meaningful once a real business feature ships in a later
release with real customer traffic.

**MTTR data point:** the WP-004-13 rollback drill's timed result is the first
real MTTR measurement. Record it in the initial report generated after WP-004-13
closes.

## Auditability

Each calculation method is documented in `DORA_METRICS.md` and the script
source (`scripts/dora-metrics.py`) so the numbers are reproducible and
auditable — not a black box.

## Traceability

| Metric | Source |
|--------|--------|
| All four DORA metrics | Roadmap v1.0 §Delivery Metrics |
| "rollback within 15 minutes" (MTTR target) | Roadmap Production Stability success metric |
| Release 1 representativeness note | WP-004-14 §35 |
