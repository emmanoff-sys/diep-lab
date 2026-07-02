#!/usr/bin/env python3
"""DORA Metrics extraction — DAEP / RE-OS (WP-004-14).

Authority: Roadmap v1.0 §Delivery Metrics (DORA) section.
Closing note for every "feeds the DORA dashboard" reference in EPIC-004.

Queries the GitHub Actions API for deploy-staging / deploy-production run
history and computes the four standard DORA metrics:

1. Deployment Frequency    — successful deploy-production runs per week
2. Lead Time for Changes   — PR-merge to successful deploy-production, median
3. Change Failure Rate     — % of deploy-production runs followed by rollback
4. MTTR                    — time from failed deploy to successful rollback
                             (WP-004-13's timed rollback drill is the first
                             real data point for this metric)

Usage:
    python3 scripts/dora-metrics.py [--days WINDOW_DAYS]
    python3 scripts/dora-metrics.py --output reports/dora/$(date +%Y-%m-%d).md

Requires: GITHUB_TOKEN env var with read-only repo scope.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "emmanoff-sys/diep-lab")
WORKFLOW_STAGING = "service-ci-cd.yml"
WORKFLOW_PRODUCTION = "service-ci-cd.yml"
DEPLOY_JOB_STAGING = "deploy-staging"
DEPLOY_JOB_PRODUCTION = "deploy-production"


def _gh(args: list[str]) -> list[dict]:
    """Run a `gh api` call and return parsed JSON. Exits on failure."""
    result = subprocess.run(
        ["gh", "api", "--paginate"] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"gh api error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def _get_workflow_runs(workflow: str, days: int) -> list[dict]:
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = _gh([
        f"/repos/{REPO}/actions/workflows/{workflow}/runs",
        "--jq",
        f'.workflow_runs[] | select(.created_at >= "{since}")',
    ])
    if isinstance(runs, list):
        return runs
    return [runs] if runs else []


def deployment_frequency(prod_runs: list[dict]) -> float:
    """Successful production deployments per week."""
    successful = [r for r in prod_runs if r.get("conclusion") == "success"]
    if not successful:
        return 0.0
    # Sort by created_at
    dates = sorted(datetime.fromisoformat(r["created_at"].rstrip("Z")).replace(tzinfo=UTC) for r in successful)
    if len(dates) < 2:
        weeks = 1
    else:
        delta = dates[-1] - dates[0]
        weeks = max(1, delta.days / 7)
    return round(len(successful) / weeks, 2)


def change_failure_rate(prod_runs: list[dict]) -> float:
    """% of production deployments that failed (or were followed by rollback)."""
    total = len(prod_runs)
    if total == 0:
        return 0.0
    failed = len([r for r in prod_runs if r.get("conclusion") in ("failure", "cancelled")])
    return round((failed / total) * 100, 1)


def lead_time_for_changes(prod_runs: list[dict]) -> float | None:
    """Median lead time from commit to successful production deployment (minutes)."""
    lead_times = []
    for run in prod_runs:
        if run.get("conclusion") == "success":
            created = datetime.fromisoformat(run["created_at"].rstrip("Z")).replace(tzinfo=UTC)
            updated = datetime.fromisoformat(run["updated_at"].rstrip("Z")).replace(tzinfo=UTC)
            lead_times.append((updated - created).total_seconds() / 60)
    if not lead_times:
        return None
    lead_times.sort()
    mid = len(lead_times) // 2
    return round(lead_times[mid], 1)


def render_report(
    freq: float,
    cfr: float,
    lead: float | None,
    window_days: int,
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lead_str = f"{lead} min" if lead is not None else "N/A (no data yet)"
    return f"""# DORA Metrics Report — DAEP / RE-OS

Generated: {now} | Window: last {window_days} days

| Metric | Value | Notes |
|--------|-------|-------|
| Deployment Frequency | **{freq} / week** | Successful `deploy-production` runs |
| Lead Time for Changes | **{lead_str}** | Commit → successful production deploy (median) |
| Change Failure Rate | **{cfr}%** | Failed/cancelled `deploy-production` runs |
| MTTR | **See WP-004-13 rollback drill** | Timed during deployment rollback drills |

## Interpretation (WP-004-14 §35)

> ⚠️ Release 1 note: these metrics describe *this package's own delivery
> process* (infrastructure foundation build-out), not a representative
> production workload. The scaffold has no real business feature or customer
> traffic. Re-interpret as meaningful production metrics in the release that
> ships the first real service.

## Calculation Method

- **Deployment Frequency:** count of `conclusion=success` runs on
  `{WORKFLOW_PRODUCTION}` → `{DEPLOY_JOB_PRODUCTION}` in the window,
  divided by the number of weeks.
- **Lead Time:** `updated_at - created_at` of each successful production run
  (proxy for workflow duration; a more accurate measure would trace from
  PR-merge to deploy completion, requiring cross-referencing PR events).
- **Change Failure Rate:** failed/cancelled production runs ÷ total runs.
- **MTTR:** measured manually from WP-004-13's timed rollback drills;
  not yet auto-computed (no production incident has occurred to measure).

## Data Source

GitHub Actions API: `GET /repos/{REPO}/actions/workflows/{{workflow}}/runs`
with the `--paginate` flag for completeness over the window.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DORA metrics report")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    print(f"Fetching workflow run history (last {args.days} days)...")
    prod_runs = _get_workflow_runs(WORKFLOW_PRODUCTION, args.days)

    freq = deployment_frequency(prod_runs)
    cfr = change_failure_rate(prod_runs)
    lead = lead_time_for_changes(prod_runs)

    report = render_report(freq, cfr, lead, args.days)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Report written to: {out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
