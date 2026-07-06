#!/usr/bin/env python3
"""Audit Release 2 legacy DB hostname and test classification rules.

This is release-engineering support for R2-PLAT-005. It records where legacy
Docker-network database hostnames are referenced and verifies that DB-dependent
tests are not routed through non-DB validation profiles.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "engineering/governance/EECR/release-2/RELEASE-2-TEST-CLASSIFICATION.csv"
SCAN_ROOTS = (
    ROOT / "tests",
    ROOT / "fastapi",
    ROOT / "services/cim",
    ROOT / "docker-compose.yml",
    ROOT / "docker-compose-timescale.yml",
    ROOT / "docker-compose-mdm.yml",
    ROOT / "docker-compose-cim.yml",
)
LEGACY_HOSTNAMES = ("diep-timescaledb",)
DB_SERVICE_MARKERS = ("PostgreSQL", "TimescaleDB", "running FastAPI stack")


@dataclass(frozen=True)
class HostnameReference:
    path: str
    line: int
    hostname: str
    reference_type: str
    release2_action: str


def load_manifest() -> dict[str, dict[str, str]]:
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {row["test_path"]: row for row in rows}


def profiles(row: dict[str, str]) -> set[str]:
    return {item.strip() for item in row["validation_profiles"].split(";") if item.strip()}


def is_db_dependent(row: dict[str, str]) -> bool:
    return any(marker in row["required_services"] for marker in DB_SERVICE_MARKERS) or row[
        "environment_contract"
    ] in {"database-integration", "release-gate"}


def iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix in {".py", ".yml", ".yaml"}
            )
    return sorted(files)


def classify_reference(path: str) -> tuple[str, str]:
    if path.startswith("docker-compose"):
        return "docker-only-assumption", "valid only inside Docker Compose network"
    if path in {"fastapi/common.py", "fastapi/auth.py", "services/cim/config.py"}:
        return "environment-derived-legacy-default", "Release 2 must provide DB_HOST from DB_DSN"
    if path == "tests/test_deployment_unit.py":
        return "fixture-container-name", "unit test validates deployment container inventory only"
    if path.startswith("tests/"):
        return "test-hostname-reference", "test must be classified as DB or release-gate profile"
    return "legacy-compatibility", "document and override through Release 2 environment contract"


def hostname_references() -> list[HostnameReference]:
    references: list[HostnameReference] = []
    for path in iter_scan_files():
        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for hostname in LEGACY_HOSTNAMES:
                if hostname in line:
                    reference_type, action = classify_reference(rel)
                    references.append(
                        HostnameReference(
                            path=rel,
                            line=line_no,
                            hostname=hostname,
                            reference_type=reference_type,
                            release2_action=action,
                        )
                    )
    return references


def validate_classification(rows: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for path, row in sorted(rows.items()):
        row_profiles = profiles(row)
        if is_db_dependent(row):
            is_mixed_environment_file = (
                row["classification"] == "Environment-dependent"
                and "database-integration" in row_profiles
                and "unit-tests" in row_profiles
            )
            if "legacy-platform" in row_profiles or (
                "unit-tests" in row_profiles and not is_mixed_environment_file
            ):
                errors.append(f"{path}: DB-dependent test routed to non-DB profile")
            if not ({"database-integration", "service-integration", "release-gate"} & row_profiles):
                errors.append(f"{path}: DB-dependent test lacks governed DB-capable profile")
        if "legacy-platform" in row_profiles and row["required_services"] not in {"none"}:
            errors.append(f"{path}: legacy-platform row declares external services")
    return errors


def emit_jsonl(references: list[HostnameReference], errors: list[str], output: Path | None) -> None:
    lines: list[str] = []
    for ref in references:
        lines.append(json.dumps({"event": "hostname_reference", **ref.__dict__}, sort_keys=True))
    lines.append(
        json.dumps(
            {
                "event": "classification_audit",
                "status": "pass" if not errors else "fail",
                "errors": errors,
                "reference_count": len(references),
            },
            sort_keys=True,
        )
    )
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="write JSONL audit evidence")
    args = parser.parse_args()

    rows = load_manifest()
    references = hostname_references()
    errors = validate_classification(rows)
    emit_jsonl(references, errors, Path(args.output) if args.output else None)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
