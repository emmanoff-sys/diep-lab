# EPIC-002 — Shared Platform Libraries

**DAEP / RE-OS** | Primary engineering reference for `libs/` | Version 0.1.0 (Release 1)

---

## 1. EPIC Overview

EPIC-002 delivers the reusable engineering foundation for every DAEP / RE-OS
service and app: configuration, logging, exception handling, and common
utilities — each in the three platform runtimes (Python backend, TypeScript
web, Dart mobile). Before this EPIC these were per-service pattern
descriptions in the LLD/DRDP; now they are shared, tested, versioned packages.

## 2. Purpose

- Eliminate per-service drift in config, logs, and error shapes across the
  ~30+ planned microservices and 4 client apps.
- Make security-critical patterns (tenant scoping, secret redaction, generic
  auth errors) structurally enforced, not remembered.
- Give EPIC-003+ real dependencies: services import these libraries from the
  internal artifact repository (WP-001-11) instead of copying code.

## 3. Scope

Eight Work Packages, two parallel tracks:

| Track | Config | Logging | Exceptions/Errors | Utilities |
|-------|--------|---------|-------------------|-----------|
| Backend (Python) | WP-002-01 | WP-002-03 | WP-002-05 | WP-002-07 |
| Frontend/Mobile (TS + Dart) | WP-002-02 | WP-002-04 | WP-002-06 | WP-002-08 |

Out of scope: Vault secrets retrieval (WP-003-13), log shipping
infrastructure, remote error-tracking backend selection (open decision),
auth token storage (future auth feature), 429/503 application handling
(infrastructure concern).

## 4. Architecture Overview & Dependency Graph

```
Backend (Python)                    Frontend/Mobile (TS ∥ Dart)

reos-config (WP-002-01)             @reos/config ∥ reos_config (WP-002-02)
     │                                   │
     ▼                                   ▼
reos-logging (WP-002-03)            @reos/logging ∥ reos_logging (WP-002-04)
     │                                   │
     ▼                                   ▼
reos-exceptions (WP-002-05) ──RFC 7807──▶ @reos/error-handling ∥ reos_error_handling (WP-002-06)
     │                                   │
     ▼                                   ▼
reos-common (WP-002-07)             @reos/utils ∥ reos_utils (WP-002-08)
```

No circular dependencies; each arrow is a one-way package dependency.
The horizontal arrow is a *wire contract* (RFC 7807 Problem Details), not a
package dependency.

## 5. Library Layout

```
libs/
├── README.md                  ← this file
├── reos-config/               Python  — ReosBaseSettings (WP-002-01)
├── reos-logging/              Python  — Structlog JSON framework (WP-002-03)
├── reos-exceptions/           Python  — REOSException + RFC 7807 (WP-002-05)
├── reos-common/               Python  — tenant scoping, pagination, datetime (WP-002-07)
├── reos-config-ts/            TS      — @reos/config (WP-002-02)
├── reos-logging-ts/           TS      — @reos/logging (WP-002-04)
├── reos-error-handling-ts/    TS      — @reos/error-handling (WP-002-06)
├── reos-utils-ts/             TS      — @reos/utils (WP-002-08)
├── reos_config/               Dart    — ReosConfig (WP-002-02)
├── reos_logging/              Dart    — ReosLogger (WP-002-04)
├── reos_error_handling/       Dart    — mapErrorToUiState + ReosErrorWidget (WP-002-06)
└── reos_utils/                Dart    — formatters, validators, ReosApiClient (WP-002-08)
```

Naming: Python/TS packages use kebab-case directories; Dart packages use
snake_case (pub convention). `reos-config` (Python) and `reos_config` (Dart)
are distinct packages.

## 6. Package Descriptions & Public APIs

| Package | Public API | One-liner |
|---------|-----------|-----------|
| `reos-config` | `ReosBaseSettings`, `Environment` | Env-driven settings base; fail-fast validation; DSN-masking repr |
| `reos-logging` | `configure_logging`, `get_logger`, `DEFAULT_REDACTED_FIELDS` | Structlog JSON chain with secret redaction; console in local |
| `reos-exceptions` | `REOSException` + 6 subclasses, `register_exception_handlers` | LLD §2.2 hierarchy; RFC 7807 responses; warning-level logging |
| `reos-common` | `tenant_scoped`, `Page`, `PageParams`, `encode_cursor`, `decode_cursor`, `utc_now`, `to_iso8601` | Mandatory tenant+soft-delete scoping; opaque cursors; UTC-safe time |
| `@reos/config` | `getConfig`, `ENVIRONMENTS`, `Environment`, `ReosConfig` | Zod-validated env config for Next.js |
| `@reos/logging` | `log`, `configureLogging`, `setTransport`, `Transport` | Structured client logging; pluggable transport; `stateTransition` |
| `@reos/error-handling` | `mapErrorToUiState`, `ReosErrorBoundary`, `ErrorUiState` | 9-code DRDP §21.3 mapping; no blank screens |
| `@reos/utils` | `ReosApiClient`, `ReosApiError`, formatters, validators | Governed fetch client; kWp/kWh/currency/date formatting |
| `reos_config` (Dart) | `ReosConfig`, `ReosEnvironment` | dotenv + --dart-define config for the 3 Flutter apps |
| `reos_logging` (Dart) | `log`, `ReosLogger`, `ReosLogTransport` | Structured client logging (Flutter) |
| `reos_error_handling` | `mapErrorToUiState`, `ReosErrorWidget`, `ErrorUiKind` | 9-code mapping + rendering widget (Flutter) |
| `reos_utils` (Dart) | `ReosApiClient`, `ReosApiException`, formatters, validators | Governed Dio client per DRDP §23.1 |

Full field/function documentation: each package's own `README.md`.

## 7. Cross-Cutting Contracts

- **Environment enum** (`local`, `shared_dev`, `ci`, `staging`, `production`):
  synchronized across Python/TS/Dart — single-source-of-truth comment blocks
  in each config module. Change all three in one commit or none.
- **Event naming** `noun.verb` (`request.error`, `error.mapped`,
  `ui.state_transition`) across backend and client logging.
- **RFC 7807 shape** `{type, title, status, detail, instance, code, **metadata}`
  produced by `reos-exceptions`, consumed by both error-handling packages.
- **Log levels**: `REOSException` → `warning`; unhandled failures → `error`/`critical`.

## 8. Coding Standards

All packages follow `STANDARDS.md` (WP-001-05). Python: 3.11+, mypy
`--strict`, Ruff (E/F/W/C90/N/UP/B/S), Black (line 100), Bandit; full typing
per LLD v2.0 §2.1.1; hatchling build backend per `BUILD.md` (WP-001-09).
TypeScript: `strict` + `noUncheckedIndexedAccess`. Dart: `flutter_lints`.
Dependency injection throughout (settings/transports/fetch/Dio are injectable).

## 9. Build Instructions

Per `BUILD.md` (WP-001-09):

```bash
# Python (each libs/reos-*/ directory)
python -m build --wheel          # → dist/*.whl
twine upload --repository-url http://localhost:8080 dist/*.whl   # ARTIFACT_REPOSITORY.md

# TypeScript
npm ci && npm run build          # → dist/

# Dart — consumed via path imports; no publish step in Release 1
flutter pub get
```

## 10. Testing Instructions

```bash
# Python
pip install -e ".[dev]" && pytest --cov

# TypeScript
npm ci && npm test               # jest

# Dart
flutter pub get && flutter test
```

## 11. Usage Example (end-to-end, backend)

```python
from fastapi import FastAPI
from reos_config import ReosBaseSettings
from reos_logging import configure_logging, get_logger
from reos_exceptions import NotFoundError, register_exception_handlers
from reos_common import Page, PageParams, tenant_scoped

class Settings(ReosBaseSettings): ...

settings = Settings()
configure_logging(settings)
log = get_logger(__name__)

app = FastAPI()
register_exception_handlers(app)

@app.get("/api/v1/customers")
async def list_customers(tenant_id: UUID, params: PageParams = Depends()):
    query = tenant_scoped(select(Customer), tenant_id)      # ALWAYS tenant-scoped
    rows = await session.scalars(query.offset(params.offset).limit(params.limit + 1))
    return Page.build(list(rows), params)
```

The scaffold `templates/python-service/` demonstrates the full composition.

## 12. Traceability

| Library | EAS/BRS/SRS | HLD/LLD | DRDP / UI-UX |
|---------|------------|---------|--------------|
| reos-config | SRS Vol. 1 | LLD §2.1.1, §2.1.2 | — |
| reos-logging | — | LLD §2.2, §2.3 | — |
| reos-exceptions | — | LLD §2.2 (literal source) | DRDP §21.3 (contract) |
| reos-common | — | LLD §2.1.1 (literal source) | DRDP §21 (pagination) |
| config-ts / reos_config | — | — | DRDP §23.1, §23.2 |
| logging-ts / reos_logging | — | — | DRDP §22, §23.1, §23.2 |
| error-handling (both) | — | LLD §2.2 (consumed shape) | DRDP §21.3, §22 (literal source) |
| utils (both) | — | — | DRDP §23.1, §23.2; UI/UX Spec (units) |

## 13. Work Package Summary

| WP | Title | SP | Deliverable |
|----|-------|-----|------------|
| WP-002-01 | Configuration Framework (Backend) | 5 | `reos-config` |
| WP-002-02 | Configuration Framework (Frontend/Mobile) | 5 | `@reos/config`, `reos_config` |
| WP-002-03 | Logging Framework (Backend) | 5 | `reos-logging` |
| WP-002-04 | Logging Framework (Frontend/Mobile) | 5 | `@reos/logging`, `reos_logging` |
| WP-002-05 | Exception Framework (Backend) | 8 | `reos-exceptions` |
| WP-002-06 | Exception Framework (Frontend/Mobile) | 5 | `@reos/error-handling`, `reos_error_handling` |
| WP-002-07 | Common Utilities (Backend) | 5 | `reos-common` |
| WP-002-08 | Common Utilities (Frontend/Mobile) | 5 | `@reos/utils`, `reos_utils` |

## 14. Open Items

- **ECR-002-06-01** — DRDP v1.0 §21.3 approved user-message copy is external;
  all client-facing strings are `[PLACEHOLDER]`-prefixed until resolved.
- **Remote error-tracking backend** — open Project Owner decision (WP-002-04).
- **Auth token storage** — `TODO(auth-feature)` hooks in both API clients.
- **Environment enum codegen** (YAML → 3 languages) — later-release candidate.

## 15. Version History

| Version | Date | Change |
|---------|------|--------|
| 0.1.0 | 2026-07-02 | Initial EPIC-002 delivery — all 12 packages across 8 WPs |

## 16. Future Extension Guidance

- New shared backend concerns: add a `libs/reos-<name>/` package following the
  reos-common template; depend only on lower layers (config → logging →
  exceptions → common) — never sideways or upward.
- New client-side concerns: mirror TS and Dart packages together; keep the
  public shapes aligned (`Transport`, `ErrorUiState` precedent).
- Any change to `reos-common/tenant.py` is security-critical — heightened
  review scrutiny permanently (WP-002-07 §39).
- Do not edit `[PLACEHOLDER]` copy or the environment enum without the
  cross-language synchronization rules above.
