# Python Service Scaffold — DAEP / RE-OS
### LLD v2.0 §2.1.2 Reference Implementation | WP-001-05

This scaffold is the canonical starting point for every new Python/FastAPI service in the DAEP / RE-OS
programme. Copy it, rename it, and begin implementation from a known-good baseline that already passes
the full static-analysis and formatting toolchain.

---

## Instantiation Steps

1. **Copy** this directory into `services/{your-service-name}/`
2. **Rename** the Python package: `mv src/service_name src/{your_service_name}`
3. **Update** `pyproject.toml`: change `name = "service-name"` to your service name
4. **Find/replace** `service_name` (Python import path) → `your_service_name` across all files
5. **Replace** `ExampleModel`, `ExampleRepository`, `ExampleService`, `ExampleCreated` with your domain entities
6. **Update** `main.py` title and description fields
7. **Create** your first Alembic migration: `alembic revision --autogenerate -m "initial schema"`

---

## Quick Start (Docker Compose — Local Dev)

Brings up the scaffold plus Postgres, Redis, and Kafka in one command
(Roadmap v1.0 §11.2 "Local Dev" row — WP-003-02):

```bash
cp .env.example .env
docker compose up
```

`GET http://localhost:8000/health` should respond within ~2 minutes of all
services reaching healthy. Reset everything (fresh seed data, clean volumes):

```bash
docker compose down -v
```

## Running Locally (without Docker Compose)

```bash
# Install dependencies
pip install -e ".[dev]"

# Copy and populate the env file
cp .env.example .env

# Start the service (from the service root)
PYTHONPATH=src uvicorn service_name.main:app --reload --host 0.0.0.0 --port 8000
```

`GET /health` should return `{"status": "ok"}`.

---

## Running Tests

```bash
# Unit tests (no external dependencies)
PYTHONPATH=src pytest tests/unit/ -v

# Integration tests (requires Docker for testcontainers)
PYTHONPATH=src pytest tests/integration/ -v
```

---

## Static Analysis

All checks must pass before a PR is raised (enforced by pre-commit and CI):

```bash
# Type checking
mypy --strict src/

# Linting
ruff check src/ tests/

# Formatting
black --check src/ tests/
isort --check-only src/ tests/

# Security scanning
bandit -r src/ -c pyproject.toml
```

---

## Architecture References

| Document | Section | Content |
|----------|---------|---------|
| LLD v2.0 | §2.1 | Python toolchain — tool versions, enforcement points |
| LLD v2.0 | §2.1.1 | Type annotation rules — mandatory examples |
| LLD v2.0 | §2.1.2 | Service module structure — authoritative directory tree |
| STANDARDS.md | §2 | Distilled binding rules |

---

## Known Placeholders

| File | Status | Replaced By |
|------|--------|------------|
| `core/logging.py` | Local stub | Shared logging library (WP-002-03) |
| `core/exceptions.py` | Local base class | Shared exception library (WP-002-05) |
| `core/kafka.py` | Protocol interface only | Real aiokafka wiring (WP-002-04) |
| `core/security.py` | JWT decode stub | Full IAM integration (EPIC-005) |
