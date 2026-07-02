# reos-logging — Shared Structured Logging Framework (Backend)

**Authority:** WP-002-03 | LLD v2.0 §2.3 (Structured Logging Standard) | LLD v2.0 §2.2 (structured-log call pattern)

Pre-configured Structlog for every DAEP / RE-OS Python service: identical JSON
log shape platform-wide, no per-service logging boilerplate.

## Usage

```python
from reos_config import ReosBaseSettings
from reos_logging import configure_logging, get_logger

settings = Settings()            # your ReosBaseSettings subclass (WP-002-01)
configure_logging(settings)      # once, at service startup (lifespan)

log = get_logger(__name__)
log.info("topology.import_started", version_id=42)
log.warning("request.error", code="NOT_FOUND", status=404, path="/api/v1/x", detail="...")
```

## Processor chain

| Order | Processor | Purpose |
|-------|-----------|---------|
| 1 | `merge_contextvars` | Request-ID / per-request context correlation |
| 2 | redaction | Masks sensitive fields (see below) |
| 3 | `TimeStamper(fmt="iso")` | ISO-8601 UTC timestamps |
| 4 | `add_log_level` | `level` key |
| 5 | `JSONRenderer` / `ConsoleRenderer` | JSON everywhere except `environment == "local"` (developer-readable console) |

## Redaction

Default masked field names (case-insensitive): `password`, `token`, `secret`,
`authorization`. Values are replaced with `***REDACTED***`.

Extend per service — the list is a parameter, not hardcoded (WP-002-03 §35):

```python
configure_logging(settings, extra_redacted_fields=["api_key", "meter_psk"])
```

**Limitation:** redaction matches event-dict *keys* only. Never interpolate
secrets into the event string itself.

## Log levels

`REOSException`s are logged at `warning` by the shared handler (WP-002-05,
matching LLD v2.0 §2.2). Reserve `error`/`critical` for unhandled failures.

## Request-ID binding

```python
# FastAPI middleware in the consuming service:
structlog.contextvars.bind_contextvars(request_id=request_id)
```

Groundwork for distributed tracing correlation; full OpenTelemetry is out of
scope for Release 1 (WP-002-03 §28).

## Example output

JSON (non-local): `{"service_name": "my-service", "environment": "staging", "timestamp": "2026-07-02T10:00:00Z", "level": "info", "event": "topology.import_started", "version_id": 42}`

Console (local): `2026-07-02T10:00:00Z [info] topology.import_started service_name=my-service version_id=42`

## Design constraints

Dependency-light by design (Structlog only + reos-config) — no log-shipping
backend coupling; aggregation infrastructure is a later EPIC-003 follow-on
(WP-002-03 §9, §39).
