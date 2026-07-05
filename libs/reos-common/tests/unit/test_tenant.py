"""Unit tests for tenant_scoped — WP-002-07 §29, §33.

Demonstrably prevents cross-tenant data leakage against a real (in-memory
SQLite) database, and raises AuthorizationError when tenant context is
missing.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from reos_common import tenant_scoped
from reos_exceptions import AuthorizationError
from sqlalchemy import Boolean, String, Uuid, create_engine, literal, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str] = mapped_column(String(50))


class NoTenantModel(Base):
    __tablename__ = "no_tenant"

    id: Mapped[int] = mapped_column(primary_key=True)


TENANT_A = uuid4()
TENANT_B = uuid4()


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                Customer(tenant_id=TENANT_A, name="a-live"),
                Customer(tenant_id=TENANT_A, name="a-deleted", is_deleted=True),
                Customer(tenant_id=TENANT_B, name="b-live"),
            ]
        )
        s.commit()
        yield s


class TestTenantIsolation:
    def test_only_own_tenant_rows_returned(self, session: Session) -> None:
        rows = session.scalars(tenant_scoped(select(Customer), TENANT_A)).all()
        assert [c.name for c in rows] == ["a-live"]

    def test_cross_tenant_leakage_prevented(self, session: Session) -> None:
        rows = session.scalars(tenant_scoped(select(Customer), TENANT_B)).all()
        names = {c.name for c in rows}
        assert "a-live" not in names
        assert "a-deleted" not in names
        assert names == {"b-live"}

    def test_soft_deleted_rows_excluded(self, session: Session) -> None:
        rows = session.scalars(tenant_scoped(select(Customer), TENANT_A)).all()
        assert all(not c.is_deleted for c in rows)


class TestMissingTenantContext:
    def test_none_tenant_raises_authorization_error(self) -> None:
        with pytest.raises(AuthorizationError) as excinfo:
            tenant_scoped(select(Customer), None)
        assert excinfo.value.http_status == 403
        assert excinfo.value.metadata == {"reason": "missing_tenant_context"}

    def test_missing_context_logs_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        # get_logger works unconfigured (structlog defaults); the warning
        # must be emitted for development-time misuse detection (§26).
        with pytest.raises(AuthorizationError):
            tenant_scoped(select(Customer), None)
        assert "tenant.missing_context" in capsys.readouterr().out


class TestSchemaConvention:
    def test_model_without_tenant_columns_rejected(self) -> None:
        with pytest.raises(TypeError, match="tenant_id"):
            tenant_scoped(select(NoTenantModel), uuid4())

    def test_entity_less_select_rejected(self) -> None:
        with pytest.raises(TypeError):
            tenant_scoped(select(literal(1)), uuid4())

    def test_empty_select_rejected(self) -> None:
        with pytest.raises(TypeError):
            tenant_scoped(select(), uuid4())

    def test_column_select_still_scoped(self, session: Session) -> None:
        # Selecting a column keeps the mapped entity — scoping still applies.
        names = session.scalars(tenant_scoped(select(Customer.name), TENANT_A)).all()
        assert names == ["a-live"]
