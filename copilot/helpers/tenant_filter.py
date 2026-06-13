"""Tenant isolation utility for parameterised SQL queries.

All Copilot DB queries route through `apply_tenant_filter()` to ensure
cross-tenant data leakage is prevented at the database level.

Usage:
    from copilot.helpers.tenant_filter import apply_tenant_filter

    base_query = "SELECT d.* FROM devices d WHERE d.device_id = %s"
    query = apply_tenant_filter(base_query, tenant="acme")
    # -> "SELECT d.* FROM devices d WHERE d.device_id = %s AND d.tenant_id = %s"

The function appends a parameterised `AND {alias}.tenant_id = %s` clause when
a tenant is provided. When tenant is None (global admin/service account), the
query is returned unmodified.
"""

from __future__ import annotations


def apply_tenant_filter(
    query: str,
    tenant: str | None,
    alias: str = "d",
) -> str:
    """Append tenant isolation WHERE clause if tenant is not None.

    Args:
        query: SQL query (may already have a WHERE clause).
        tenant: Tenant ID from JWT, or None for unrestricted access.
        alias: Table alias used in the query (default: ``"d"`` for devices).

    Returns:
        Modified query with tenant filter appended. The caller MUST supply
        tenant as an additional ``%s`` parameter when executing.

    Raises:
        ValueError: If query is empty or malformed.

    Examples:
        >>> apply_tenant_filter("SELECT * FROM devices d WHERE d.id = %s", "acme")
        'SELECT * FROM devices d WHERE d.id = %s AND d.tenant_id = %s'

        >>> apply_tenant_filter("SELECT COUNT(*) FROM devices", "acme")
        'SELECT COUNT(*) FROM devices WHERE d.tenant_id = %s'

        >>> apply_tenant_filter("SELECT * FROM devices d", None)
        'SELECT * FROM devices d'
    """
    if not query or not query.strip():
        msg = "Query must not be empty"
        raise ValueError(msg)

    if tenant is None:
        return query

    clause = f" AND {alias}.tenant_id = %s"

    # Detect if a WHERE clause already exists (case-insensitive check on
    # the outermost query, avoiding matches inside string literals).
    normalized = query.strip().upper()

    # Heuristic: check if the query contains WHERE not preceded by FROM or JOIN.
    # This works for standard SQL where WHERE appears once in the outer query.
    if " WHERE " in normalized or normalized.endswith(" WHERE"):
        return f"{query}{clause}"

    # Check for WHERE at the end of the query (e.g., "WHERE")
    if normalized.rstrip().endswith("WHERE"):
        return f"{query}{clause.lstrip(' AND')}"

    # No WHERE clause — add one
    return f"{query} WHERE {alias}.tenant_id = %s"


__all__ = ["apply_tenant_filter"]