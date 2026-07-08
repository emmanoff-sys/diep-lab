#!/usr/bin/env python3
"""Run segmented Release 2 dependency security audits.

This helper is release-engineering control code for R2-PLAT-007. It separates
dependency surfaces before invoking pip-audit so independent product/runtime
locks do not get merged into a single resolver input.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERNAL_PREFIXES = ("reos-",)

# Governed advisory acceptances (EECR-CHG-093). Every entry must cite the
# advisory ID, the acceptance rationale, and the governance record; an entry
# must be removed as soon as an upstream fix version exists. These are passed
# to pip-audit as --ignore-vuln flags, so the acceptance is visible in the
# recorded audit command evidence.
ACCEPTED_VULNERABILITIES: dict[str, str] = {
    # ecdsa (transitive dependency of python-jose). Minerva timing attack on
    # P-256 (CVE-2024-23342 / GHSA-wj6h-64fc-37mp). No fixed release exists —
    # upstream states side-channel resistance is out of scope. The vulnerable
    # surface (ecdsa signing / key generation / ECDH) is not exercised in this
    # repository: services sign RS256 only via python-jose's cryptography
    # backend, and signature verification is unaffected per the advisory.
    "PYSEC-2026-1325": (
        "ecdsa Minerva timing attack; no fix upstream; "
        "ECDSA signing path unused (EECR-CHG-093)"
    ),
}


@dataclass(frozen=True)
class DependencySurface:
    surface_id: str
    title: str
    category: str
    source_paths: tuple[Path, ...]
    audit_required: bool
    gate_required: bool
    rationale: str


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


SURFACES: tuple[DependencySurface, ...] = (
    DependencySurface(
        surface_id="release2-template-runtime",
        title="Release 2 Python service template runtime dependencies",
        category="release2-application-dependencies",
        source_paths=(ROOT / "templates/python-service/requirements.txt",),
        audit_required=True,
        gate_required=True,
        rationale="Pinned public runtime dependency lock for new Release 2 service scaffolds.",
    ),
    DependencySurface(
        surface_id="release2-audit-service-runtime",
        title="Release 2 audit service runtime dependencies",
        category="release2-application-dependencies",
        source_paths=(ROOT / "services/audit-service/requirements.txt",),
        audit_required=True,
        gate_required=True,
        rationale="Pinned public runtime dependency lock for the WP-005-04 audit service.",
    ),
    DependencySurface(
        surface_id="release2-shared-library-runtime",
        title="Release 2 shared library runtime dependencies",
        category="shared-library-dependencies",
        source_paths=(
            ROOT / "libs/reos-config/pyproject.toml",
            ROOT / "libs/reos-logging/pyproject.toml",
            ROOT / "libs/reos-exceptions/pyproject.toml",
            ROOT / "libs/reos-common/pyproject.toml",
        ),
        audit_required=False,
        gate_required=True,
        rationale=(
            "First-party shared libraries are not resolved from the public advisory index; "
            "their public transitive dependencies are audited through the pinned consuming "
            "application/template locks until a dedicated shared-library lock is approved."
        ),
    ),
    DependencySurface(
        surface_id="legacy-diep-runtime",
        title="Legacy DIEP runtime dependencies",
        category="legacy-diep-dependencies",
        source_paths=(ROOT / "fastapi/requirements.txt",),
        audit_required=True,
        gate_required=True,
        rationale="Pinned runtime dependency lock for the legacy platform validation surface.",
    ),
    DependencySurface(
        surface_id="development-tooling",
        title="Development-only tooling dependencies",
        category="development-only-tooling",
        source_paths=(
            ROOT / "pyproject.toml",
            ROOT / "services/audit-service/pyproject.toml",
            ROOT / "libs/reos-config/pyproject.toml",
            ROOT / "libs/reos-logging/pyproject.toml",
            ROOT / "libs/reos-exceptions/pyproject.toml",
            ROOT / "libs/reos-common/pyproject.toml",
        ),
        audit_required=False,
        gate_required=False,
        rationale=(
            "Development extras are outside the Release 2 runtime gate unless a governed "
            "tooling lock is introduced; they remain classified to prevent leakage into the "
            "runtime audit."
        ),
    ),
    DependencySurface(
        surface_id="optional-dependencies",
        title="Optional dependency extras",
        category="optional-dependencies",
        source_paths=(
            ROOT / "services/audit-service/pyproject.toml",
            ROOT / "fastapi/requirements.txt",
        ),
        audit_required=False,
        gate_required=True,
        rationale=(
            "Optional extras are audited when they are materialized in pinned runtime locks; "
            "unmaterialized optional extras are classified but not independently resolved."
        ),
    ),
)


def display_path(path: Path) -> str:
    if path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix()
    return path.as_posix()


def requirement_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "-", "--")):
        return None
    if line[:1].isspace() and stripped.startswith("#"):
        return None
    match = re.match(r"([A-Za-z0-9_.-]+)(?:\[.*?\])?\s*(?:[<>=!~]|@|$)", stripped)
    if match is None:
        return None
    return match.group(1).replace("_", "-").lower()


def is_internal_requirement(name: str | None) -> bool:
    return name is not None and name.startswith(INTERNAL_PREFIXES)


def filtered_requirement_lines(source: Path) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    skipped: list[str] = []
    skip_internal_comment = False
    for line in source.read_text(encoding="utf-8").splitlines():
        name = requirement_name(line)
        if is_internal_requirement(name):
            assert name is not None
            skipped.append(name)
            skip_internal_comment = True
            continue
        stripped = line.strip()
        if skip_internal_comment and line[:1].isspace() and stripped.startswith("#"):
            continue
        if stripped:
            skip_internal_comment = False
        lines.append(line)
    return lines, skipped


def dependency_names(lines: Sequence[str]) -> list[str]:
    names = {name for line in lines if (name := requirement_name(line)) is not None}
    return sorted(names)


def select_surfaces(surface_ids: Sequence[str] | None = None) -> list[DependencySurface]:
    if not surface_ids:
        return list(SURFACES)
    by_id = {surface.surface_id: surface for surface in SURFACES}
    unknown = sorted(set(surface_ids) - set(by_id))
    if unknown:
        raise SystemExit(f"Unknown dependency surface(s): {', '.join(unknown)}")
    return [by_id[surface_id] for surface_id in surface_ids]


def materialize_surface(surface: DependencySurface, output_dir: Path) -> dict[str, object]:
    record: dict[str, object] = {
        "surface_id": surface.surface_id,
        "title": surface.title,
        "category": surface.category,
        "audit_required": surface.audit_required,
        "gate_required": surface.gate_required,
        "source_paths": [display_path(path) for path in surface.source_paths],
        "rationale": surface.rationale,
    }
    if not surface.audit_required:
        record["status"] = "classified"
        record["audit_file"] = None
        return record

    source = surface.source_paths[0]
    if not source.exists():
        record["status"] = "failed"
        record["error"] = f"source file missing: {display_path(source)}"
        return record

    lines, skipped = filtered_requirement_lines(source)
    audit_file = output_dir / f"{surface.surface_id}.requirements.txt"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    record.update(
        {
            "status": "materialized",
            "audit_file": display_path(audit_file),
            "dependency_count": len(dependency_names(lines)),
            "internal_dependencies_excluded": sorted(set(skipped)),
        }
    )
    return record


def run_command(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603 - fixed validation command with explicit arguments.
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_pip_audit(
    surface: DependencySurface,
    audit_file: Path,
    output_dir: Path,
    pip_audit: str,
) -> dict[str, object]:
    audit_output = output_dir / f"{surface.surface_id}.pip-audit.json"
    command = [
        pip_audit,
        "--strict",
        "-r",
        str(audit_file),
    ]
    for vuln_id in sorted(ACCEPTED_VULNERABILITIES):
        command += ["--ignore-vuln", vuln_id]
    command += [
        "--format",
        "json",
        "--output",
        str(audit_output),
    ]
    result = run_command(command)
    return {
        "surface_id": surface.surface_id,
        "event": "pip_audit",
        "status": "pass" if result.returncode == 0 else "fail",
        "returncode": result.returncode,
        "command": result.command,
        "audit_output": display_path(audit_output),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def write_summary(path: Path, summary: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_audit(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    summary_path = Path(args.summary)
    if not summary_path.is_absolute():
        summary_path = ROOT / summary_path
    surfaces = select_surfaces(args.surface)

    materialized = [materialize_surface(surface, output_dir) for surface in surfaces]
    audit_results: list[dict[str, object]] = []
    if not args.dry_run:
        for surface, record in zip(surfaces, materialized, strict=True):
            if not surface.audit_required or record.get("status") != "materialized":
                continue
            audit_file_value = record["audit_file"]
            if not isinstance(audit_file_value, str):
                continue
            audit_results.append(
                run_pip_audit(surface, ROOT / audit_file_value, output_dir, args.pip_audit)
            )

    failed_materialization = [row for row in materialized if row.get("status") == "failed"]
    failed_audits = [row for row in audit_results if row.get("returncode") != 0]
    summary = {
        "work_package": "R2-PLAT-007",
        "risk": "R2-RISK-017",
        "adr": "ADR-R2-07",
        "overall_status": "fail" if failed_materialization or failed_audits else "pass",
        "dry_run": args.dry_run,
        "surfaces": materialized,
        "audit_results": audit_results,
    }
    write_summary(summary_path, summary)
    print(json.dumps(summary, sort_keys=True))
    return 1 if failed_materialization or failed_audits else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="release2-pip-audit",
        help="directory for generated requirements and pip-audit artifacts",
    )
    parser.add_argument(
        "--summary",
        default="release2-pip-audit-summary.json",
        help="write segmented audit summary JSON",
    )
    parser.add_argument("--pip-audit", default="pip-audit", help="pip-audit executable")
    parser.add_argument("--surface", action="append", help="limit execution to a surface id")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="materialize and classify surfaces without invoking pip-audit",
    )
    return parser


def main() -> int:
    parser = build_parser()
    return run_audit(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
