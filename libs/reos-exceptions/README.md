# reos-exceptions — Shared Exception Hierarchy & RFC 7807 Handler (Backend)

**Authority:** WP-002-05 | LLD v2.0 §2.2 (Error Handling Standard — direct source) | DRDP v1.0 §21.3 (frontend contract)

The platform's error-response contract: every service raises the same
exception types and returns identically shaped RFC 7807 Problem Details JSON.

## Exception types

| Exception | HTTP | Code | Usage |
|-----------|------|------|-------|
| `ValidationError(detail, metadata?)` | 422 | `VALIDATION_ERROR` | Domain validation failure |
| `AuthenticationError(metadata?)` | 401 | `AUTHENTICATION_REQUIRED` | Identity not established |
| `AuthorizationError(metadata?)` | 403 | `AUTHORIZATION_DENIED` | Permission denied |
| `NotFoundError(resource, id, metadata?)` | 404 | `RESOURCE_NOT_FOUND` | Missing / soft-deleted resource |
| `ConflictError(detail, metadata?)` | 409 | `RESOURCE_CONFLICT` | State conflict |
| `ExternalServiceError(service, detail?, metadata?)` | 502 | `EXTERNAL_SERVICE_ERROR` | Upstream dependency failure |

## Usage

```python
from fastapi import FastAPI
from reos_exceptions import NotFoundError, register_exception_handlers

app = FastAPI()
register_exception_handlers(app)   # once, in create_app()

@app.get("/customers/{customer_id}")
async def get_customer(customer_id: int) -> Customer:
    customer = await repo.get_by_id(customer_id)
    if customer is None:
        raise NotFoundError("Customer", customer_id)
    return customer
```

Response (`404`, `application/problem+json`):

```json
{
  "type": "https://errors.re-os.dev/resource_not_found",
  "title": "Customer was not found.",
  "status": 404,
  "detail": "Customer with id '7' was not found.",
  "instance": "/customers/7",
  "code": "RESOURCE_NOT_FOUND"
}
```

`metadata` entries are merged as RFC 7807 extension members.

## Logging levels

Every `REOSException` is logged by the handler at **`warning`** via
`reos-logging` (exact LLD v2.0 §2.2 call pattern):
`log.warning('request.error', code=..., status=..., path=..., detail=...)`.
Reserve `error`/`critical` for unhandled, non-`REOSException` failures —
those indicate a bug, not a domain outcome.

## Security

`AuthenticationError` / `AuthorizationError` default messages are generic by
design (WP-002-05 §25) — never put credential-check internals, stack traces,
or role structure into `detail` or `metadata`.

## Not Covered by This Library

**429 (Too Many Requests)** and **503 (Service Unavailable)** are raised by
infrastructure — the rate limiter and load balancer (HAProxy, WP-003-09) —
not by application code. The frontend error mapping (WP-002-06) still handles
them; do not add application exceptions for them here. (WP-002-05 §9, §35.)

## Rollback

Pre-Release-2 revert is safe (no production endpoint depends on this yet).
Once any real endpoint ships, this library defines the wire contract —
reverting requires a coordinated frontend rollback (WP-002-06 consumes the
shape). Revert plan: pin consumers to the prior minor version via the
internal index (`ARTIFACT_REPOSITORY.md`), never a partial in-place edit.
