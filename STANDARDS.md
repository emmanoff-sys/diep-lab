# RE-OS Engineering Standards
### LLD v2.0 Chapter 2 — Binding Reference | WP-001-02 | v1.0 | 2026-07-02

> This document is a distillation of LLD v2.0 Chapter 2. Every rule cites the authoritative
> LLD section. For long-form rationale, read the LLD. For enforcement tooling, see `.pre-commit-config.yaml`.

---

## Document Control

| Field | Value |
|-------|-------|
| Document | STANDARDS.md |
| Authority | LLD v2.0 Chapter 2 |
| Version | 1.0 |
| WP | WP-001-02 |
| Classification | Internal — Confidential |
| Owner | Platform Lead |
| Last Updated | 2026-07-02 |

---

## 1. Scope and Authority

These standards are **binding** on every RE-OS engineer, AI agent, reviewer, and automated
pipeline. Non-compliant code is rejected by pre-commit hooks and CI/CD pipelines before
it reaches `develop` or `main`.

Standards apply to all code in the RE-OS monorepo across services, libraries, applications,
and infrastructure configurations regardless of language or platform.

**Any deviation requires a formal ADR** recorded in `engineering/governance/EECR/decision-log.md`
before implementation — not after.

---

## 2. Python / FastAPI Standards *(LLD v2.0 §2.1)*

### 2.1 Toolchain *(LLD v2.0 §2.1)*

| Tool | Role | Minimum Version |
|------|------|----------------|
| Black | Formatter | 24.0 |
| isort | Import sorter | 5.13 (profile: `black`) |
| Ruff | Linter | 0.4 |
| Mypy | Type checker | 1.10 (strict mode) |
| pytest | Test runner | 8.0 |

- **Line length: 100 characters** (LLD v2.0 §2.1 explicit requirement — not Black's default of 88).
  Black, isort, and Ruff are all configured with `line-length = 100` in `pyproject.toml`.
  This override is intentional: the 100-char limit accommodates the longer identifier names
  typical in energy-domain code (`network_model_version_id`, `telemetry_timestamp_utc`) without
  forcing mid-expression line breaks that reduce readability.
- **isort profile:** `black` — eliminates any formatting conflict between isort and Black output.
- **Minimum Python version:** 3.11.
- All tool versions are pinned in `pyproject.toml` (root and per-service) for CI reproducibility.

### 2.1.1 Type Annotations *(LLD v2.0 §2.1.1)*

- All public function signatures must carry parameter and return type annotations.
- Use `X | None` syntax (PEP 604); `Optional[X]` is prohibited.
- Declare `from __future__ import annotations` at the top of every Python module.
- Pydantic v2 `BaseModel` is the required type for all API request and response schemas.
- SQLAlchemy 2.x `Mapped[T]` column annotations are required for all ORM model definitions.
- Prefer `TypeVar`, `Protocol`, and `NewType` over `Any`. Any use of `Any` requires an inline
  `# type: ignore[...]` comment citing the specific mypy code and reason.

### 2.1.2 Module Structure *(LLD v2.0 §2.1.2)*

Import block order (enforced by isort):
1. `from __future__ import annotations`
2. Standard library
3. Third-party packages (alphabetical within group)
4. Local application imports (alphabetical within group)

Blank lines between import groups; no blank lines within a group.

`__all__` is required in every module that exposes a public surface.

One class per file for service, repository, and router classes. Utility functions may be
grouped by domain within a single file.

**Standard service directory layout** *(LLD v2.0 §2.1.2 — canonical):*
```
templates/python-service/           ← copy this scaffold for every new service
├── pyproject.toml                  # project metadata + tool config (black, isort, ruff, mypy)
├── Dockerfile                      # multi-stage build
├── .env.example                    # environment variable template
├── alembic.ini                     # database migration configuration
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
└── src/{service_name}/
    ├── main.py                     # FastAPI application factory + lifespan handlers
    ├── config.py                   # Pydantic BaseSettings configuration
    ├── dependencies.py             # FastAPI dependency injection providers
    ├── api/v1/
    │   ├── endpoints/              # APIRouter modules — one file per resource
    │   └── schemas/                # Pydantic v2 request/response models
    ├── domain/
    │   ├── models.py               # SQLAlchemy ORM models (Mapped[T] columns)
    │   ├── repositories.py         # Database access layer (one class per aggregate root)
    │   ├── services.py             # Business logic layer
    │   └── events.py               # Domain events (dataclasses, frozen=True)
    ├── core/
    │   ├── security.py             # JWT decode / RBAC stubs → replaced by EPIC-005
    │   ├── exceptions.py           # Local exception hierarchy → replaced by libs/ in EPIC-002
    │   ├── logging.py              # Structlog setup stub → replaced by libs/ in EPIC-002
    │   └── kafka.py                # Event producer/consumer Protocol → wired in EPIC-002
    └── tests/
        ├── conftest.py
        ├── unit/
        └── integration/            # testcontainers — requires Docker
```

**Use the scaffold:** `cp -r templates/python-service services/{your-service}` then rename
`service_name` → `{your_service_name}` throughout. See `templates/python-service/README.md`.

---

## 3. Error Handling *(LLD v2.0 §2.2)*

- All application exceptions must inherit from `REOSBaseException` or a domain-scoped
  subclass defined in `libs/exceptions/`.
- Bare `except:` and bare `except Exception:` without re-raise are prohibited.
- Log the full exception context (`exc_info=True`) before re-raising.
- FastAPI HTTP error responses must conform to the standard error envelope:

  ```json
  {
    "error_code": "RESOURCE_NOT_FOUND",
    "message": "Asset id=42 was not found.",
    "request_id": "a1b2c3d4-e5f6-..."
  }
  ```

- `error_code` values must be defined in `libs/error-codes/`; no ad-hoc error code strings.
- Do not swallow `HTTPException` — let FastAPI's default exception handler propagate it.
- Credential or PII values must never appear in exception messages or log payloads.

---

## 4. Logging *(LLD v2.0 §2.3)*

- Use `structlog` for structured JSON logging in all Python services.
- `logging.basicConfig` and bare `print` statements are prohibited in production code paths.
- Every log entry must include: `service`, `request_id`, `timestamp` (ISO 8601 UTC), `level`.
- Approved log levels:

  | Level | When to use |
  |-------|------------|
  | `DEBUG` | Development tracing — must not appear in production deployments |
  | `INFO` | Operational events: request received, state transition, scheduled task started |
  | `WARNING` | Recoverable anomalies: retry attempt, degraded-mode activation, unexpected-but-handled state |
  | `ERROR` | Failures requiring operator attention; service is still running |
  | `CRITICAL` | Service-stopping failures; immediate operator response required |

- Never log PII, credentials, secrets, or sensitive configuration values at any level.
- Log state transitions ("asset status OFFLINE → ONLINE"), not intermediate computation steps.
- `structlog.get_logger()` is bound at module level; do not create loggers inside functions.

---

## 5. Naming Conventions *(LLD v2.0 §2.5)*

### 5.1 Database — PostgreSQL / TimescaleDB *(LLD v2.0 §2.5)*

| Object | Convention | Example |
|--------|-----------|---------|
| Schema (domain) | `snake_case` singular noun | `metering`, `topology`, `iam`, `audit`, `network`, `dispatch` |
| Table | `snake_case` plural noun; no abbreviations | `energy_readings`, `network_assets`, `audit_events` |
| Column | `snake_case`; suffix units where applicable | `reading_value_kwh`, `timestamp_utc`, `duration_seconds` |
| Primary key | Always `id` — `BIGINT GENERATED ALWAYS AS IDENTITY` | `id` |
| Foreign key column | `{ref_table_singular}_id` | `asset_id`, `user_id`, `site_id` |
| Foreign key constraint | `fk_{table}_{ref_table}_{col}` | `fk_readings_assets_asset_id` |
| Check constraint | `ck_{table}_{rule}` | `ck_readings_positive_value`, `ck_users_email_format` |
| Index | `ix_{table}_{col}` | `ix_readings_timestamp_utc`, `ix_assets_site_id` |
| Unique constraint | `uq_{table}_{col}` | `uq_users_email`, `uq_assets_serial_number` |
| Sequence (explicit) | `sq_{table}_{col}` | `sq_audit_events_id` |
| TimescaleDB hypertable | Same table name — no suffix | `energy_readings` (partitioned on `timestamp_utc`) |

No abbreviations in object names unless the abbreviation is an established domain term
(`kwh`, `utc`, `ip`, `iam`). Spell out all other terms.

Schema domain nouns define service ownership boundaries. A table belongs to exactly one
schema. Cross-schema reads use fully qualified names; cross-schema writes are prohibited —
services must call the owning service's API instead.

### 5.2 Python *(LLD v2.0 §2.5)*

| Construct | Convention | Example |
|-----------|-----------|---------|
| Module file | `snake_case.py` | `asset_repository.py` |
| Class | `PascalCase` | `AssetRepository`, `ReadingSchema` |
| Function / method | `snake_case` | `get_asset_by_id`, `create_reading` |
| Constant (module-level) | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT`, `DEFAULT_PAGE_SIZE` |
| Private member | `_single_leading_underscore` | `_session_factory`, `_retry_limit` |
| Type alias | `PascalCase` | `AssetId = NewType("AssetId", int)` |
| Enum class | `PascalCase` members | `class AssetStatus(str, Enum): ONLINE = "online"` |

### 5.3 TypeScript / Next.js *(LLD v2.0 §2.5)*

| Construct | Convention | Example |
|-----------|-----------|---------|
| Variable / function | `camelCase` | `fetchAssetList`, `currentPageSize` |
| React component | `PascalCase` | `AssetListView`, `LoginForm` |
| Type / Interface | `PascalCase` | `AssetSchema`, `ApiErrorResponse` |
| Enum | `PascalCase` members | `enum AssetStatus { Online = "online" }` |
| Constant | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_SIZE`, `API_BASE_URL` |
| Component file | `PascalCase.tsx` | `AssetListView.tsx` |
| Utility / hook file | `camelCase.ts` | `useAssetList.ts`, `fetchAssetList.ts` |

### 5.4 Flutter / Dart *(LLD v2.0 §2.5)*

| Construct | Convention | Example |
|-----------|-----------|---------|
| Class / Widget | `PascalCase` | `AssetDetailScreen`, `ReadingTileWidget` |
| Method / variable | `camelCase` | `loadAssets`, `currentReading` |
| Constant | `camelCase` (Dart convention) | `defaultPageSize`, `apiTimeout` |
| Source file | `snake_case.dart` | `asset_detail_screen.dart` |
| Widget naming | Suffix with widget type | `AssetListView`, `LoginScreen`, `ReadingCard` |

### 5.5 Terraform / Ansible *(LLD v2.0 §2.5)*

| Construct | Convention | Example |
|-----------|-----------|---------|
| Terraform resource | `snake_case` | `resource "vm_instance" "app_server"` |
| Terraform variable | `snake_case` | `variable "db_port"` |
| Terraform output | `snake_case` | `output "app_server_ip"` |
| Terraform files | Standard names only | `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf` |
| Ansible role | `snake_case` | `roles/postgres_setup/` |
| Ansible task `name:` | Sentence case | `"Configure PostgreSQL client authentication"` |
| Ansible variable | `snake_case` with role prefix | `postgres_setup_port`, `mosquitto_bind_address` |

### 5.6 File and Directory Naming *(LLD v2.0 §2.5)*

| Artifact | Convention | Notes |
|----------|-----------|-------|
| Directories | `kebab-case` | No underscores; no spaces |
| Python source | `snake_case.py` | |
| Configuration | `kebab-case.yaml`, `kebab-case.json` | |
| Shell scripts | `kebab-case.sh` with `#!/usr/bin/env bash` shebang | |
| Markdown docs | `kebab-case.md` | Exceptions: `README.md`, `STANDARDS.md`, `CODEOWNERS`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` |
| Migration files | `{seq:04d}_{description}.py` | e.g., `0001_create_metering_schema.py` |

---

## 6. Git Branching Strategy *(LLD v2.0 §2.6)*

### 6.1 Branch Types

| Branch | Purpose | Direct commit | Merges from |
|--------|---------|:---:|------------|
| `main` | Production-ready state | **Prohibited** | `release/*`, `hotfix/*` |
| `develop` | Integration and staging | **Prohibited** | `feature/*`, `fix/*`, `docs/*` |
| `feature/{name}` | New functionality | Yes | — |
| `fix/{name}` | Non-urgent bug fixes | Yes | — |
| `hotfix/{version}-{desc}` | Urgent production fix | Yes | — |
| `release/{version}` | Release preparation and freeze | Yes | — |
| `docs/{name}` | Documentation-only changes | Yes | — |

Branch naming rules *(LLD v2.0 §2.6)*:

- Lowercase only; hyphens as word separators; no underscores, no capital letters.
- WP-implementing branches must embed the WP ID: `feature/wp-{nnn}-{nn}-{short-description}`.
  Example: `feature/wp-003-01-fastapi-service-template`.
- Maximum 72 characters total.
- No branch may reference internal system names, credentials, or ticket IDs beyond the WP ID.

### 6.2 Commit Message Standard *(LLD v2.0 §2.6)*

All commits must follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body — wrap at 72 characters]
[blank line before body]

[optional footer(s)]
```

**Types:**

| Type | Use |
|------|-----|
| `feat` | New feature or user-facing capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting; no logic change |
| `refactor` | Code restructure; no feature or fix |
| `test` | Test additions or corrections |
| `chore` | Tooling, build, dependency, or housekeeping updates |
| `ci` | CI/CD pipeline changes |
| `perf` | Performance improvement |
| `build` | Build system or compilation changes |

**Scope:** WP ID, service name, or affected subsystem.
Examples: `(wp-003-01)`, `(metering-svc)`, `(eecr)`, `(iam)`.

**Subject rules:**
- Imperative mood: "add feature" not "added feature".
- Lowercase first character; no trailing period.
- Maximum 72 characters total on the first line (type + scope + colon + space + subject).

**Breaking changes:** include `BREAKING CHANGE: <description>` in the commit footer.

**Examples:**
```
feat(wp-003-01): add FastAPI service template with health endpoint

docs(wp-001-02): add STANDARDS.md and pre-commit skeleton

fix(metering-svc): correct timestamp parsing for DST boundary reads
```

### 6.3 Pull Request Rules *(LLD v2.0 §2.6)*

- Every `feature/*`, `fix/*`, and `hotfix/*` branch must be merged via an approved PR.
  Direct pushes to `develop` and `main` are blocked (enforced in WP-001-04).
- PR title must reference the WP ID: `feat(wp-003-01): FastAPI service template`.
- **Minimum required approvals before merge:** 1 architecture review (DoD-06) + 1 code review (DoD-06).
- PR must pass all required status checks before merge button is enabled (enforced in WP-004-01+).
- AI engineering agents may open PRs and implement WP code. They must not merge PRs (GOV-002).
- PR descriptions must complete the PR template defined in `.github/` (added in WP-001-04).

---

## 7. Testing Standards *(LLD v2.0 §2.7)*

| Requirement | Standard |
|-------------|----------|
| Unit test coverage | ≥ 80% line coverage per service module |
| Integration tests | Required for every API endpoint and database operation |
| Test file naming | `test_{module}.py` |
| Test directory | `tests/` mirroring source; `unit/` and `integration/` sub-directories |
| Determinism | All tests must be deterministic; no flaky tests permitted to merge |
| Isolation | Each test cleans up its own state; no test may depend on execution order |
| PII / credential policy | No production credentials, real PII, or real IP addresses in any test fixture or seed data |
| Performance baseline | P95 response time < 200 ms for all API endpoints (measured in integration tests; tracked in WP-004-02) |

**Test data:**

- Use factories (e.g., `factory_boy`) for entity generation; do not hand-craft fixture JSON
  with real-looking identifiers or values.
- Integration tests must use a real database instance — mocking the database layer is
  prohibited for integration tests. (Rationale: prior program incident where mock/prod
  divergence masked a broken migration. See program risk register RISK-004.)
- Test seeds must use obviously synthetic values: `user@example-test.invalid`,
  `serial-number: TEST-00000001`, `ip: 192.0.2.1` (TEST-NET-1 per RFC 5737).

---

## 8. Enforcement

The `.pre-commit-config.yaml` at the repository root defines the automated enforcement
layer. Install on a fresh clone:

```bash
pip install pre-commit
pre-commit install
```

Run all hooks manually against all files:

```bash
pre-commit run --all-files
```

**Hook delivery schedule:**

| WP | Hooks Added |
|----|------------|
| WP-001-02 (this WP) | Framework skeleton — no live hooks; `pre-commit install` succeeds |
| WP-001-06 | Python: Black formatter, isort, Ruff linter, Mypy type-checker |
| WP-001-07 | Terraform: `terraform fmt --check`, `tflint`; Ansible: `ansible-lint` |
| WP-001-08 | Secrets detection (`detect-secrets`), dependency audit (`pip-audit`), licence check |

Until WP-001-06 is merged, format and lint enforcement is applied manually in code review.

---

## 9. Document Revision History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0 | 2026-07-02 | Platform Lead (AI-assisted: claude-sonnet-4-6) | Initial publication — WP-001-02 |
