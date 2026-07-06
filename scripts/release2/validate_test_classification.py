#!/usr/bin/env python3
"""Validate and query the Release 2 test classification manifest.

This is release-engineering support, not application functionality. It keeps
R2-RISK-017 closure auditable by ensuring every existing test file is assigned
to at least one governed validation profile.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT / "engineering" / "governance" / "EECR" / "release-2" / "RELEASE-2-TEST-CLASSIFICATION.csv"
)
TEST_ROOTS = (ROOT / "tests", ROOT / "libs", ROOT / "services")


def isolation_group(test_path: str) -> str:
    """Return the pytest isolation root for a classified test path."""
    parts = Path(test_path).parts
    if len(parts) >= 2 and parts[0] in {"libs", "services"}:
        return "/".join(parts[:2])
    return parts[0]


def discover_test_files() -> set[str]:
    files: set[str] = set()
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("test*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "__pycache__" not in rel:
                files.add(rel)
    return files


def load_manifest() -> list[dict[str, str]]:
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    required = {
        "test_path",
        "classification",
        "validation_profiles",
        "environment_contract",
        "required_services",
        "ci_job",
        "notes",
    }
    if not rows:
        raise SystemExit("classification manifest is empty")
    missing_columns = required - set(rows[0])
    if missing_columns:
        raise SystemExit(f"classification manifest missing columns: {sorted(missing_columns)}")
    return rows


def validate_manifest(rows: list[dict[str, str]]) -> None:
    discovered = discover_test_files()
    classified = {row["test_path"] for row in rows}
    missing = sorted(discovered - classified)
    stale = sorted(classified - discovered)
    duplicates = sorted(
        path for path in classified if sum(1 for row in rows if row["test_path"] == path) > 1
    )
    if missing or stale or duplicates:
        if missing:
            print("Missing classifications:")
            for path in missing:
                print(f"  {path}")
        if stale:
            print("Stale classifications:")
            for path in stale:
                print(f"  {path}")
        if duplicates:
            print("Duplicate classifications:")
            for path in duplicates:
                print(f"  {path}")
        raise SystemExit(1)


def profiles(row: dict[str, str]) -> set[str]:
    return {item.strip() for item in row["validation_profiles"].split(";") if item.strip()}


def profile_rows(rows: list[dict[str, str]], profile: str) -> list[dict[str, str]]:
    return [row for row in rows if profile in profiles(row)]


def grouped_paths(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        groups[isolation_group(row["test_path"])].append(row["test_path"])
    return dict(sorted(groups.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="print test files assigned to this validation profile")
    parser.add_argument("--print-files", action="store_true", help="print matching files only")
    parser.add_argument(
        "--print-groups",
        action="store_true",
        help="print one pytest-safe isolated file group per line",
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="print isolation group names and test counts for this profile",
    )
    args = parser.parse_args()

    rows = load_manifest()
    validate_manifest(rows)

    if args.profile:
        matched_rows = profile_rows(rows, args.profile)
        matched = [row["test_path"] for row in matched_rows]
        groups = grouped_paths(matched_rows)
        if args.print_files:
            for path in matched:
                print(path)
        elif args.print_groups:
            for paths in groups.values():
                print(" ".join(paths))
        elif args.list_groups:
            for group, paths in groups.items():
                print(f"{group}: {len(paths)} files")
        else:
            print(f"{args.profile}: {len(matched)} files")
        return 0

    print(f"Release 2 test classification valid: {len(rows)} files classified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
