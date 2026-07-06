# Release 2 Docker Runner Readiness
### DAEP / RE-OS | R2-PLAT-004 | Revision 1.0 | 2026-07-06

## 1. Purpose

R2-PLAT-004 establishes the governed Docker execution model required by the Release 2 validation
framework. It is a release-engineering substrate only and does not change application functionality,
Dockerfile contents, EPIC-006 scope, WP-006-03B authorization, or Release 1.

## 2. Root Cause

The Docker validation profile previously invoked `docker build` directly. When the runner exposed a
Docker client without a reachable daemon, validation failed with no structured evidence about daemon
availability, BuildKit readiness, Compose rendering, or image metadata. The underlying cause is
runner/substrate readiness, not application code.

## 3. Execution Model

| Context | Required Model |
|---------|----------------|
| Local developer machine | Docker CLI, compose plugin, buildx plugin, and reachable Docker daemon are required for operational Docker evidence. If the daemon is unavailable, only implementation/static evidence is valid. |
| GitHub Actions | `ubuntu-22.04`, `actions/setup-python@v5`, `docker/setup-buildx-action@v3`, reachable Docker daemon, and artifact upload. |
| Docker Compose | `docker-compose.release2-db.yml` must render with `docker compose -f ... config`; evidence must mask secrets. |
| Image build | `fastapi/Dockerfile` must build as `reos-r2-fastapi:<sha>` and image metadata must be captured. |
| Container scan prerequisites | Docker build must produce a scanner-ready image reference and image ID. Vulnerability scan policy remains governed by the security validation profile and DevSecOps policy. |

## 4. Commands

```bash
python scripts/release2/docker_validation.py preflight --output release2-docker-preflight.jsonl
python scripts/release2/docker_validation.py compose-config \
  --compose-file docker-compose.release2-db.yml \
  --config-output release2-docker-compose-config.yml \
  --output release2-docker-compose.jsonl
python scripts/release2/docker_validation.py build \
  --context fastapi \
  --tag reos-r2-fastapi:<sha> \
  --build-log release2-docker-build.log \
  --output release2-docker-build.jsonl
```

## 5. Evidence Requirements

| Evidence | Pass Criteria |
|----------|---------------|
| `release2-docker-preflight.jsonl` | `docker_preflight_passed`; Docker client, compose, buildx, and daemon all pass |
| `release2-docker-compose.jsonl` | `docker_compose_config` status is `pass` |
| `release2-docker-compose-config.yml` | Rendered compose contract exists and secrets are masked |
| `release2-docker-build.jsonl` | `docker_build_passed` and `docker_image_metadata` exist |
| `release2-docker-build.log` | Build log exists for audit and failure triage |

## 6. Exit Criteria

R2-PLAT-004 is operationally complete when the governed Docker validation profile passes on a
Docker-enabled runner and uploads all evidence artifacts. If local execution cannot reach a Docker
daemon, the implementation may be complete, but operational validation remains pending.
