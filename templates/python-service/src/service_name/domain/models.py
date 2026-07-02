from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "ExampleModel"]


class Base(DeclarativeBase):
    pass


class ExampleModel(Base):
    """Replace with the domain entity for this service."""

    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
