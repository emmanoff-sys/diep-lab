#!/usr/bin/env python3
"""Host-side MW2 readiness verification runner.

This script is intentionally designed for the Docker Compose host rather than
the FastAPI container, so it can inspect container restart counts and service
uptime without widening the API container's privileges.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = REPO_ROOT / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import readiness  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and persist the MW2 readiness assessment")
    parser.add_argument(
        "--env-file",
        default=str(REPO_ROOT / ".env"),
        help="Optional .env file to preload before running checks",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Compute the readiness assessment but do not write it to TimescaleDB",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full readiness report as JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    readiness.load_env_defaults(args.env_file)
    config = readiness.load_runner_config()
    previous_run = None
    try:
        previous_run = readiness.fetch_latest_readiness_run()
    except Exception:
        previous_run = None

    report = readiness.run_readiness_assessment(config, previous_run=previous_run)
    if not args.no_persist:
        readiness.persist_readiness_run(report, config)

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"[{report.status}] score={report.score}/{report.pass_threshold} run_id={report.run_id}")
        print(report.recommendation)
        for check in report.checks:
            print(f" - {check.check_name}: {check.status} ({check.score}/{check.weight}) {check.message}")

    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

