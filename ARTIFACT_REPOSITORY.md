# Artifact Repository — DAEP / RE-OS

## Authority
- Roadmap v1.0 §11.1 Stage 7 ("Push to Registry" — pattern applied to Python packages and npm packages)
- LLD v2.0 §2.1.2 (`pyproject.toml` build system feeds this WP's publish step)
- WP-001-11 Engineering Package

---

## 1. Purpose

The DAEP / RE-OS artifact repository hosts versioned Python wheels produced by the build framework (WP-001-09). It enables shared libraries built in EPIC-002 (`libs/`) to be declared as real package dependencies by services, rather than consumed via in-tree source copying.

This addresses the supply-chain control requirement: all internal packages pass through the artifact repository and its associated CVE gate (WP-001-08) before any service may depend on them.

---

## 2. Scope — Release 1

For Release 1, the internal package index runs as a Docker Compose service (`infra/artifact-repo/docker-compose.yml`) suitable for local developer use and CI execution. This is explicitly a Release 1 constraint. The index will be promoted to a production-durable VM-hosted instance in a follow-on work package after EPIC-003 establishes the VM and Ansible provisioning infrastructure (WP-003-05/06/07).

| Package Type | Release 1 Host | Post-EPIC-003 Host |
|-------------|---------------|-------------------|
| Python wheels | pypiserver on Docker Compose (local / CI) | VM-hosted pypiserver (Ansible-provisioned) |
| npm packages | Internal registry — scoped to a future WP | VM-hosted Verdaccio |
| Flutter / Dart packages | Monorepo path imports (no registry needed) | No change planned |
| Docker images | Out of scope — EPIC-003 / WP-003-03 | ECR or Docker Hub |

---

## 3. Package Index — pypiserver

The Python package index is [pypiserver](https://pypi.org/project/pypiserver/), a minimal, standards-compliant PyPI-compatible server exposing:
- **PEP 503 Simple Repository API** — consumed by `pip install --index-url`
- **Upload API** — used by `twine upload`

### 3.1 Starting the Local Index

```bash
# From the repository root:
cd infra/artifact-repo

# Create the package storage directory.
mkdir -p packages

# Create the .htpasswd credentials file.
# This file is gitignored — it must be created manually on each environment.
htpasswd -scB .htpasswd publisher
# Enter a password when prompted.
# Store credentials in ~/.netrc (see §3.5).

# Start the index.
docker compose up -d

# Verify the index is reachable.
curl -s http://localhost:8080/simple/ | head -5
```

### 3.2 Publish a Wheel

```bash
# Install twine.
pip install twine

# Build the wheel from the service or library root.
python -m build --wheel

# Publish to the local index.
twine upload \
  --repository-url http://localhost:8080 \
  --username publisher \
  --password <your-password> \
  dist/*.whl
```

After publishing, pip-audit must have returned zero CVE findings on the wheel's `requirements.txt` before the publish step.

### 3.3 Consume from the Index

```bash
# Install a package from the local index.
# Falls back to PyPI for packages not hosted internally.
pip install \
  --index-url http://localhost:8080/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  your-library-name==1.0.0

# Configure permanently for a service via pyproject.toml (when using uv or pip config):
# [tool.uv]
# [[tool.uv.index]]
# url = "http://localhost:8080/simple/"
# name = "internal"
# priority = "primary"
```

### 3.4 Publish Verification

After uploading, confirm the package is listed:

```bash
# List packages on the index.
curl -s http://localhost:8080/simple/ | grep your-library-name

# Install the exact version just published.
pip install \
  --no-deps \
  --index-url http://localhost:8080/simple/ \
  your-library-name==<version>
```

### 3.5 Authentication — Release 1

Release 1 uses HTTP Basic Authentication via a `.htpasswd` file (bcrypt hashed, created by `htpasswd`). Credentials are stored in `~/.netrc`:

```
machine localhost
login publisher
password <your-password>
```

Protect the netrc file: `chmod 600 ~/.netrc`. With `.netrc` in place, `twine upload` reads credentials automatically without command-line flags.

A production-grade credential solution — Vault secrets injection for CI (WP-003-13) or GitHub Actions secrets — will replace the `.netrc` pattern when the index is promoted to a VM instance after EPIC-003.

---

## 4. Access Logs and Audit

pypiserver writes access logs to stdout. Capture them:

```bash
# Follow logs in real time.
docker compose logs -f pypiserver

# Dump a snapshot.
docker compose logs pypiserver > /tmp/pypiserver-access.log
```

For production deployments (post-EPIC-003), logs must be forwarded to the log aggregation stack (WP-002-07) and retained per the platform's log retention policy.

---

## 5. Stopping and Data Management

```bash
cd infra/artifact-repo

# Stop the index (preserves stored packages in packages/).
docker compose down

# Stop and remove all containers, networks, and volumes.
docker compose down --volumes

# Remove stored packages (DESTRUCTIVE — confirm intent before running).
rm -rf packages/
```

Package data is stored in `infra/artifact-repo/packages/` (gitignored). Removing this directory removes all published packages permanently unless separately backed up. For CI pipelines, packages are re-published from source on each release workflow run.

---

## 6. CI Bootstrap Pattern (Release 1 — Pre-Promotion)

Until pypiserver is promoted to a VM-hosted instance (§7), the Stage 3 dependency-scan job in `service-ci-cd.yml` uses a **CI bootstrap pattern** to make internal packages available to `pip-audit`:

```yaml
# 1. Build wheels from monorepo source
pip install build
for lib in libs/reos-config libs/reos-logging libs/reos-exceptions libs/reos-common; do
  python -m build --wheel "$lib" --outdir /tmp/reos-wheels/
done

# 2. Start pypiserver serving the wheels (loopback only, no auth)
python -m pypiserver run --port 8080 --interface 127.0.0.1 /tmp/reos-wheels &

# 3. Configure pip's resolver
PIP_EXTRA_INDEX_URL=http://localhost:8080/simple/ pip-audit --strict -r requirements.txt
```

This pattern is authorised under ARTIFACT_REPOSITORY.md §2 ("suitable for local developer use and CI execution"). It is explicitly temporary and must be replaced when:

1. The pypiserver VM instance is live (§7)
2. GitHub Actions can authenticate to it via a `PYPI_INTERNAL_URL` secret

When that happens: remove the wheel-build and pypiserver-start steps, add a secret-driven `PIP_EXTRA_INDEX_URL` env var, and record the transition in an EECR change entry.

**ECR reference:** ECR-005-CI-01 (WP-005-04 Audit Service — shared library package resolution failure in CI).

---

## 7. Promotion to Production (Post-EPIC-003)

After WP-003-05 (VM base image), WP-003-06 (systemd service management), and WP-003-07 (Ansible provisioning) are complete:

1. Convert the `docker-compose.yml` configuration into an Ansible role.
2. Provision pypiserver as a systemd service on the designated artifact VM.
3. Update `ARTIFACT_REPOSITORY.md` with the production URL (e.g., `http://artifacts.internal:8080/simple/`).
4. Update `pip install --index-url` references in all service README files.
5. Migrate `.htpasswd` credentials to Vault (WP-003-13).
6. Record a new EECR change entry for this promotion.

---

## 7. npm Registry (Future)

An internal npm registry ([Verdaccio](https://verdaccio.org)) is scoped for a future work package. When provisioned it will follow the same publish-and-consume pattern documented in this file. All internal JavaScript / TypeScript packages must be published to the internal registry before any service may declare them as dependencies.

---

## 8. Traceability

| Artefact | Reference |
|----------|-----------|
| Roadmap v1.0 §11.1 Stage 7 | Registry push pattern (applied here to Python packages, not Docker images) |
| LLD v2.0 §2.1.2 | `pyproject.toml` build system — feeds the publish step |
| WP-001-08 | Dependency Policy — CVE scan must pass before publishing |
| WP-001-09 | Build Framework — produces the wheel this WP distributes |
| WP-001-10 | Versioning Policy — wheels are published with version-tagged names |
| WP-001-11 | This document |
| WP-002-07 | Log Aggregation — pypiserver access logs forwarded post-EPIC-003 |
| WP-003-05/06/07 | VM base image, systemd, Ansible — production promotion target |
| WP-003-13 | Vault secrets management — replaces Release 1 .htpasswd / .netrc |
