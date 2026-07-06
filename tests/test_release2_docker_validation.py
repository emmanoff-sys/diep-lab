from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/release2/docker_validation.py"
SPEC = importlib.util.spec_from_file_location("docker_validation", MODULE_PATH)
assert SPEC is not None
docker_validation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = docker_validation
SPEC.loader.exec_module(docker_validation)


def load_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_preflight_fails_when_daemon_is_unavailable(monkeypatch, tmp_path):
    def fake_run(command):
        if command == ["docker", "info"]:
            return docker_validation.CommandResult(command, 1, "", "cannot connect to daemon")
        return docker_validation.CommandResult(command, 0, "ok", "")

    monkeypatch.setattr(docker_validation, "run_command", fake_run)
    output = tmp_path / "preflight.jsonl"
    parser = docker_validation.build_parser()
    args = parser.parse_args(["preflight", "--output", str(output)])

    assert docker_validation.run_preflight(args) == 1
    events = load_events(output)

    assert events[-1] == {"event": "docker_preflight_failed", "failures": 1}
    assert any(event["event"] == "docker_daemon" and event["status"] == "fail" for event in events)


def test_compose_config_writes_masked_config(monkeypatch, tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    def fake_run(command):
        assert command[:4] == ["docker", "compose", "-f", str(compose_file)]
        stdout = "DB_DSN: postgresql://diep:diep123@localhost:5432/diep\n"
        stdout += "POSTGRES_PASSWORD: diep123\n"
        return docker_validation.CommandResult(command, 0, stdout, "")

    monkeypatch.setattr(docker_validation, "run_command", fake_run)
    output = tmp_path / "compose.jsonl"
    config_output = tmp_path / "compose.rendered.yml"
    parser = docker_validation.build_parser()
    args = parser.parse_args(
        [
            "compose-config",
            "--compose-file",
            str(compose_file),
            "--config-output",
            str(config_output),
            "--output",
            str(output),
        ]
    )

    assert docker_validation.run_compose_config(args) == 0
    rendered = config_output.read_text(encoding="utf-8")

    assert "diep123" not in rendered
    assert "postgresql://diep:***@localhost:5432/diep" in rendered
    assert load_events(output)[0]["status"] == "pass"


def test_build_records_image_metadata(monkeypatch, tmp_path):
    context = tmp_path / "fastapi"
    context.mkdir()
    (context / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command):
        commands.append(list(command))
        if command[:3] == ["docker", "image", "inspect"]:
            return docker_validation.CommandResult(command, 0, "sha256:abc123\n", "")
        return docker_validation.CommandResult(command, 0, "build ok\n", "")

    monkeypatch.setattr(docker_validation, "run_command", fake_run)
    output = tmp_path / "build.jsonl"
    build_log = tmp_path / "build.log"
    parser = docker_validation.build_parser()
    args = parser.parse_args(
        [
            "build",
            "--context",
            str(context),
            "--tag",
            "reos-r2-fastapi:test",
            "--build-log",
            str(build_log),
            "--output",
            str(output),
        ]
    )

    assert docker_validation.run_build(args) == 0
    events = load_events(output)

    assert ["docker", "build", "-t", "reos-r2-fastapi:test", str(context)] in commands
    assert build_log.read_text(encoding="utf-8") == "build ok\n"
    assert events[-1] == {
        "event": "docker_image_metadata",
        "image_id": "sha256:abc123",
        "tag": "reos-r2-fastapi:test",
    }
