# reos-common — Common Backend Utilities

**Authority:** WP-002-07 | LLD v2.0 §2.1.1 (tenant-scoping + soft-delete pattern — direct source) | DRDP v1.0 §21 (cursor-pagination convention)

Tenant scoping, cursor pagination, and UTC-safe datetime helpers. The
tenant-scoping helper is **the primary data-isolation security control in
Release 1** (WP-002-07 §39) — changes to `tenant.py` require heightened
review scrutiny permanently.

## Tenant scoping — MANDATORY convention

LLD v2.0 §2.1.1 mandates: `.where(Customer.tenant_id == current_tenant_id)
# ALWAYS tenant-scoped` plus the `is_deleted` soft-delete filter. This helper
enforces it structurally:

```python
from reos_common import tenant_scoped

query = tenant_scoped(select(Customer), current_tenant_id)
# ≡ select(Customer).where(Customer.tenant_id == tid).where(Customer.is_deleted == False)
```

- `tenant_id=None` → raises `AuthorizationError` (403) and logs
  `tenant.missing_context` at warning — an unscoped query never reaches the DB.
- Model without `tenant_id`/`is_deleted` columns → `TypeError` at call time.

**Required schema convention (Release 2+):** every multi-tenant table defines
`tenant_id` and `is_deleted` columns. Design new schemas accordingly (§22, §35).

## Cursor pagination

```python
from reos_common import Page, PageParams

params = PageParams(cursor=request.query_params.get("cursor"), limit=50)
rows = (await session.scalars(
    query.offset(params.offset).limit(params.limit + 1)   # fetch limit+1
)).all()
page = Page.build(list(rows), params)
# → {"items": [...], "next_cursor": "b2Zmc2V0OjUw"}
```

Cursors are opaque URL-safe tokens (`decode_cursor` raises
`ValidationError`/422 on tampering). `limit` is clamped to 200.

## Datetime

```python
from reos_common import utc_now, to_iso8601

created_at = utc_now()          # always timezone-aware UTC
to_iso8601(created_at)          # "2026-07-02T12:30:45+00:00"
to_iso8601(datetime(2026, 1, 1))  # ValueError — naive datetimes refused
```

## Traceability

| Helper | Source |
|--------|--------|
| `tenant_scoped` | LLD v2.0 §2.1.1 worked example (tenant + soft-delete filters) |
| `Page` / `PageParams` | DRDP v1.0 §21 cursor pattern (`GET /users?tenant_id&cursor&status`) |
| `AuthorizationError` on misuse | reos-exceptions (WP-002-05) |
| Misuse warning log | reos-logging (WP-002-03) |
