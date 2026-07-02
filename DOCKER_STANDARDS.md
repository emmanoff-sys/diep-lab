# Docker Build Standards — DAEP / RE-OS

**Authority:** WP-003-01 | LLD v2.0 §2.1.2 (`Dockerfile` — "Multi-stage: builder → production") | LLD v2.0 Ch. 17 introduction ("Docker packages services; systemd manages them")

Every DAEP / RE-OS Python service Dockerfile follows the pattern below.
Docker is retained under the VM-only architecture (ADR-LLD-001 / ECR-001) —
it packages the service; systemd (WP-003-06) supervises the running container.

## 1. Two-Stage Pattern

| Stage | Base Image | Purpose |
|-------|-----------|---------|
| `builder` | `python:3.12-slim` | Installs build deps, `pip install`s the exact-pinned `requirements.txt` (WP-001-08), builds the wheel (hatchling, WP-001-09) |
| `production` | `python:3.12-slim` | Copies only the built wheel + its installed dependencies; no compilers, no pip cache, no source tree |

Rationale for `python:3.12-slim` over `python:3.12` (full) or `-alpine`: `slim`
has the smallest attack surface that still ships glibc-compatible wheels
without requiring a musl rebuild of every dependency (asyncpg, cryptography
in particular have flaky Alpine wheel availability) — confirmed against the
Python 3.10+ requirement in LLD v2.0 §2.1.1 (3.12 satisfies 3.11+ project floor).

## 2. Layer Ordering (BuildKit Cache Discipline)

`COPY` instructions are ordered dependency-manifest-first:

1. `COPY requirements.txt pyproject.toml ./`
2. `RUN pip install ...` (cached unless the manifest changes)
3. `COPY src/ ./src/` (source changes don't invalidate the dependency layer)

This is required so CI Stage 5 (WP-004-05, Docker BuildKit, <8-minute budget
per Roadmap v1.0 §11.1) gets cache hits on every build that only touches
application code.

## 3. Security Checklist (every Dockerfile must satisfy)

- [ ] Multi-stage — no build tools (`gcc`, `pip` cache, `.git`) in the final image
- [ ] Non-root `USER reos` in the production stage (never `root`)
- [ ] `HEALTHCHECK` calling the service's `/health` endpoint
- [ ] No secrets `ARG`/`ENV`-baked into any layer — configuration is
      env-var-only at container *run* time via `ReosBaseSettings` (WP-002-01)
- [ ] Base image pinned by tag (`python:3.12-slim`), never `:latest`

## 4. Size Budget

**Under 200MB** for the scaffold — a benchmark other services should target,
not a hard platform-wide cap (some services with heavier native deps may
reasonably exceed it; document the reason if so).

## 5. Logging (12-Factor)

Containers log to stdout/stderr only — no in-container log files. Consumed
by the `log-forwarder` role (LLD v2.0 §17.1, Promtail → Loki), stubbed until
WP-003-07 (§9 scope note) and completed by a later observability epic.

## 6. Build Verification (Runtime — requires a reachable Docker daemon)

```bash
docker build -t reos/scaffold:local .
docker images reos/scaffold:local --format '{{.Size}}'   # confirm < 200MB
docker inspect reos/scaffold:local --format '{{.Config.User}}'   # confirm "reos", not root/empty
docker run -d --name scaffold-test -p 8000:8000 reos/scaffold:local
docker inspect --format='{{.State.Health.Status}}' scaffold-test  # confirm "healthy"
```

**Status in this repository:** the Dockerfile below implements every item on
the checklist above. Docker daemon was not reachable in the implementation
environment (CLI present, no daemon socket) — build/size/healthcheck/non-root
verification is **Runtime PASS Deferred**, to be executed in a real dev/CI
environment before this WP is closed to APPROVED.

## 7. Rebuild Cadence

`python:3.12-slim` receives upstream security patches on its own schedule —
rebuild and re-scan (WP-003-04) periodically even without an application code
change. This is an operational process note for later releases, not solved
by this WP alone (§35).

## 8. Traceability

| Requirement | Source |
|-------------|--------|
| Multi-stage `builder → production` | LLD v2.0 §2.1.2 |
| Docker's retained role | LLD v2.0 Ch. 17 introduction, ADR-LLD-001 |
| Exact-pinned `requirements.txt` input | WP-001-08 `DEPENDENCY_POLICY.md` |
| Wheel build via hatchling | WP-001-09 `BUILD.md` |
| `/health` endpoint | scaffold `api/v1/endpoints/health.py` |
