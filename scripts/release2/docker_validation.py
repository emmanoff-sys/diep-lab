#!/usr/bin/env python3
"""Release 2 Docker validation substrate.

This helper records deterministic Docker runner evidence for the Release 2
validation framework. It does not alter application images or Dockerfiles.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPOSE_FILE = ROOT / "docker-compose.release2-db.yml"
DEFAULT_CONTEXT = ROOT / "fastapi"
DEFAULT_IMAGE_NAME = "reos-r2-fastapi"
MASK = "***"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def mask_text(text: str) -> str:
    masked = re.sub(r"://([^:/@\s]+):([^@\s]+)@", rf"://\1:{MASK}@", text)
    masked = re.sub(r"(POSTGRES_PASSWORD:\s*)[^\s]+", rf"\1{MASK}", masked)
    masked = re.sub(r"(DB_PASSWORD:\s*)[^\s]+", rf"\1{MASK}", masked)
    return masked


def emit(event: str, output: Path | None = None, **fields: object) -> None:
    record = {"event": event, **fields}
    line = json.dumps(record, sort_keys=True)
    print(line)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as fh:
            fh.write(f"{line}\n")


def run_command(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603 - governed validation helper runs fixed CLI commands.
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


def command_event_name(command: Sequence[str]) -> str:
    if command == ["docker", "info"]:
        return "docker_daemon"
    if command[:2] == ["docker", "compose"]:
        return "docker_compose"
    if command[:2] == ["docker", "buildx"]:
        return "docker_buildx"
    if command[:2] == ["docker", "--version"]:
        return "docker_client"
    return "docker_command"


def emit_command_result(result: CommandResult, output: Path | None = None) -> None:
    event = command_event_name(result.command)
    status = "pass" if result.returncode == 0 else "fail"
    emit(
        event,
        output,
        command=result.command,
        status=status,
        returncode=result.returncode,
        stdout=mask_text(result.stdout.strip()),
        stderr=mask_text(result.stderr.strip()),
    )


def run_preflight(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    commands = [
        ["docker", "--version"],
        ["docker", "compose", "version"],
        ["docker", "buildx", "version"],
        ["docker", "info"],
    ]
    failures = 0
    emit("docker_preflight_start", output, runner=os.getenv("RUNNER_OS", "local"))
    for command in commands:
        result = run_command(command)
        emit_command_result(result, output)
        if result.returncode != 0:
            failures += 1
    if failures:
        emit("docker_preflight_failed", output, failures=failures)
        return 1
    emit("docker_preflight_passed", output)
    return 0


def require_existing_path(path: Path, description: str) -> Path:
    resolved = path if path.is_absolute() else ROOT / path
    if not resolved.exists():
        raise SystemExit(f"{description} not found: {resolved}")
    return resolved


def display_path(path: Path) -> str:
    if path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix()
    return path.as_posix()


def run_compose_config(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    compose_file = require_existing_path(Path(args.compose_file), "compose file")
    config_output = Path(args.config_output) if args.config_output else None
    result = run_command(["docker", "compose", "-f", str(compose_file), "config"])
    if config_output is not None:
        config_output.parent.mkdir(parents=True, exist_ok=True)
        config_output.write_text(mask_text(result.stdout), encoding="utf-8")
    emit(
        "docker_compose_config",
        output,
        command=result.command,
        compose_file=display_path(compose_file),
        config_output=str(config_output) if config_output else None,
        status="pass" if result.returncode == 0 else "fail",
        returncode=result.returncode,
        stderr=mask_text(result.stderr.strip()),
    )
    return result.returncode


def run_build(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    context = require_existing_path(Path(args.context), "Docker build context")
    tag = args.tag
    dockerfile = context / "Dockerfile"
    require_existing_path(dockerfile, "Dockerfile")
    build_log = Path(args.build_log) if args.build_log else None

    emit(
        "docker_build_start",
        output,
        context=display_path(context),
        dockerfile=display_path(dockerfile),
        tag=tag,
    )
    result = run_command(["docker", "build", "-t", tag, str(context)])
    if build_log is not None:
        build_log.parent.mkdir(parents=True, exist_ok=True)
        build_log.write_text(mask_text(result.stdout + result.stderr), encoding="utf-8")
    if result.returncode != 0:
        emit(
            "docker_build_failed",
            output,
            command=result.command,
            tag=tag,
            returncode=result.returncode,
            stderr=mask_text(result.stderr.strip()),
            build_log=str(build_log) if build_log else None,
        )
        return result.returncode

    image_id = run_command(["docker", "image", "inspect", tag, "--format", "{{.Id}}"])
    emit(
        "docker_build_passed",
        output,
        command=result.command,
        tag=tag,
        returncode=result.returncode,
        build_log=str(build_log) if build_log else None,
    )
    if image_id.returncode == 0:
        emit("docker_image_metadata", output, tag=tag, image_id=image_id.stdout.strip())
        return 0
    emit(
        "docker_image_metadata_unavailable",
        output,
        tag=tag,
        returncode=image_id.returncode,
        stderr=mask_text(image_id.stderr.strip()),
    )
    return image_id.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--output")
    preflight.set_defaults(func=run_preflight)

    compose = subparsers.add_parser("compose-config")
    compose.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE.relative_to(ROOT)))
    compose.add_argument("--config-output")
    compose.add_argument("--output")
    compose.set_defaults(func=run_compose_config)

    build = subparsers.add_parser("build")
    build.add_argument("--context", default=str(DEFAULT_CONTEXT.relative_to(ROOT)))
    build.add_argument(
        "--tag",
        default=f"{DEFAULT_IMAGE_NAME}:{os.getenv('GITHUB_SHA', 'local-validation')}",
    )
    build.add_argument("--build-log")
    build.add_argument("--output")
    build.set_defaults(func=run_build)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
