from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/release2/security_dependency_audit.py"
SPEC = importlib.util.spec_from_file_location("security_dependency_audit", MODULE_PATH)
assert SPEC is not None
security_dependency_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = security_dependency_audit
SPEC.loader.exec_module(security_dependency_audit)


def test_materialization_excludes_internal_reos_packages(tmp_path: Path) -> None:
    output_dir = tmp_path / "audit"
    surface = security_dependency_audit.select_surfaces(["release2-audit-service-runtime"])[0]

    record = security_dependency_audit.materialize_surface(surface, output_dir)

    audit_file = security_dependency_audit.ROOT / record["audit_file"]
    generated = audit_file.read_text(encoding="utf-8")
    assert record["status"] == "materialized"
    assert "reos-config" in record["internal_dependencies_excluded"]
    assert "reos-common" in record["internal_dependencies_excluded"]
    assert "reos-config==" not in generated
    assert "fastapi==" in generated


def test_metadata_only_surfaces_are_classified_without_audit_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "audit"
    surface = security_dependency_audit.select_surfaces(["development-tooling"])[0]

    record = security_dependency_audit.materialize_surface(surface, output_dir)

    assert record["status"] == "classified"
    assert record["audit_required"] is False
    assert record["audit_file"] is None


def test_run_audit_invokes_pip_audit_once_per_selected_runtime_surface(
    monkeypatch: Any, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: Sequence[str]) -> object:
        commands.append(list(command))
        output = Path(command[-1])
        output.write_text('{"dependencies": []}\n', encoding="utf-8")
        return security_dependency_audit.CommandResult(command, 0, "ok", "")

    monkeypatch.setattr(security_dependency_audit, "run_command", fake_run)
    parser = security_dependency_audit.build_parser()
    summary = tmp_path / "summary.json"
    output_dir = tmp_path / "audit"
    args = parser.parse_args(
        [
            "--surface",
            "release2-template-runtime",
            "--surface",
            "release2-shared-library-runtime",
            "--output-dir",
            str(output_dir),
            "--summary",
            str(summary),
            "--pip-audit",
            "pip-audit",
        ]
    )

    assert security_dependency_audit.run_audit(args) == 0
    summary_json = json.loads(summary.read_text(encoding="utf-8"))

    assert len(commands) == 1
    assert commands[0][:3] == ["pip-audit", "--strict", "-r"]
    assert summary_json["overall_status"] == "pass"
    assert summary_json["surfaces"][1]["status"] == "classified"


def test_run_audit_passes_governed_advisory_acceptances(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """EECR-CHG-093: every ACCEPTED_VULNERABILITIES entry must be passed to
    pip-audit as an --ignore-vuln flag so the acceptance is visible in the
    recorded audit command evidence."""
    commands: list[list[str]] = []

    def fake_run(command: Sequence[str]) -> object:
        commands.append(list(command))
        output = Path(command[-1])
        output.write_text('{"dependencies": []}\n', encoding="utf-8")
        return security_dependency_audit.CommandResult(command, 0, "ok", "")

    monkeypatch.setattr(security_dependency_audit, "run_command", fake_run)
    parser = security_dependency_audit.build_parser()
    args = parser.parse_args(
        [
            "--surface",
            "release2-template-runtime",
            "--output-dir",
            str(tmp_path / "audit"),
            "--summary",
            str(tmp_path / "summary.json"),
            "--pip-audit",
            "pip-audit",
        ]
    )

    assert security_dependency_audit.run_audit(args) == 0
    assert len(commands) == 1
    for vuln_id in security_dependency_audit.ACCEPTED_VULNERABILITIES:
        idx = commands[0].index("--ignore-vuln")
        assert vuln_id in commands[0], f"{vuln_id} missing from pip-audit command"
        assert commands[0][idx + 1] in security_dependency_audit.ACCEPTED_VULNERABILITIES
    # accepted advisories must never displace the output path (evidence file)
    assert commands[0][-2] == "--output"


def test_run_audit_fails_on_mandatory_surface_audit_failure(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def fake_run(command: Sequence[str]) -> object:
        return security_dependency_audit.CommandResult(command, 1, "", "resolver failure")

    monkeypatch.setattr(security_dependency_audit, "run_command", fake_run)
    parser = security_dependency_audit.build_parser()
    summary = tmp_path / "summary.json"
    args = parser.parse_args(
        [
            "--surface",
            "legacy-diep-runtime",
            "--output-dir",
            str(tmp_path / "audit"),
            "--summary",
            str(summary),
        ]
    )

    assert security_dependency_audit.run_audit(args) == 1
    summary_json = json.loads(summary.read_text(encoding="utf-8"))
    assert summary_json["overall_status"] == "fail"
    assert summary_json["audit_results"][0]["stderr"] == "resolver failure"
