"""Unit tests for ``tenant_filter.apply_tenant_filter()``."""

from __future__ import annotations

import pytest

from copilot.helpers.tenant_filter import apply_tenant_filter


class TestApplyTenantFilter:
    """Tests for the apply_tenant_filter function."""

    def test_no_tenant_returns_query_unmodified(self) -> None:
        query = "SELECT * FROM devices d WHERE d.device_id = %s"
        result = apply_tenant_filter(query, tenant=None)
        assert result == query

    def test_empty_tenant_returns_query_unmodified(self) -> None:
        query = "SELECT * FROM devices d"
        result = apply_tenant_filter(query, tenant=None)
        assert result == query

    def test_adds_where_when_no_where_clause(self) -> None:
        query = "SELECT * FROM devices d"
        result = apply_tenant_filter(query, tenant="acme")
        assert result == "SELECT * FROM devices d WHERE d.tenant_id = %s"

    def test_appends_and_when_where_exists(self) -> None:
        query = "SELECT * FROM devices d WHERE d.device_id = %s"
        result = apply_tenant_filter(query, tenant="acme")
        assert result == "SELECT * FROM devices d WHERE d.device_id = %s AND d.tenant_id = %s"

    def test_count_query_without_where(self) -> None:
        query = "SELECT COUNT(*) FROM devices d"
        result = apply_tenant_filter(query, tenant="acme")
        assert result == "SELECT COUNT(*) FROM devices d WHERE d.tenant_id = %s"

    def test_join_query_with_where(self) -> None:
        query = """
            SELECT a.id, a.device_id, a.alarm_type, a.severity
            FROM alarms a
            JOIN devices d ON a.device_id = d.device_id
            WHERE a.id = %s
        """
        result = apply_tenant_filter(query, tenant="acme", alias="d")
        assert "AND d.tenant_id = %s" in result
        assert result.count("%s") == 2  # original %s + tenant %s

    def test_group_by_query(self) -> None:
        query = """
            SELECT d.device_type, d.status, COUNT(*) AS count
            FROM devices d
            GROUP BY d.device_type, d.status
        """
        result = apply_tenant_filter(query, tenant="globex")
        assert "WHERE d.tenant_id = %s" in result
        assert result.index("WHERE") < result.index("GROUP BY")

    def test_custom_alias(self) -> None:
        query = "SELECT * FROM devices dev WHERE dev.device_id = %s"
        result = apply_tenant_filter(query, tenant="acme", alias="dev")
        assert result == "SELECT * FROM devices dev WHERE dev.device_id = %s AND dev.tenant_id = %s"

    def test_raises_on_empty_query(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            apply_tenant_filter("", tenant="acme")

    def test_raises_on_whitespace_only_query(self) -> None:
        with pytest.raises(ValueError):
            apply_tenant_filter("   ", tenant="acme")

    def test_subquery_with_where_outer(self) -> None:
        """Tenant filter should append to the outermost query, not inside subqueries."""
        query = """
            SELECT d.device_id
            FROM devices d
            WHERE d.id IN (SELECT device_id FROM telemetry WHERE time > now() - interval '1h')
        """
        result = apply_tenant_filter(query, tenant="acme")
        # The WHERE clause is detected and we append AND
        assert "AND d.tenant_id = %s" in result
        # The subquery's WHERE should remain unchanged
        assert "WHERE time > now() - interval '1h')" in result

    def test_uppercase_query(self) -> None:
        query = "SELECT * FROM DEVICES D WHERE D.DEVICE_ID = %s"
        result = apply_tenant_filter(query, tenant="acme", alias="D")
        assert result == "SELECT * FROM DEVICES D WHERE D.DEVICE_ID = %s AND D.tenant_id = %s"