from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, status_enum, tenant_fk, tenant_unique
from app.models.enums import HoldStatus, ProjectStatus, RecordStatus, UnitStatus


class Project(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "code", name="uq_projects_organization_id_code"),
        Index("ix_projects_tenant_status", "organization_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        status_enum(ProjectStatus, "project_status"),
        default=ProjectStatus.PLANNING,
        nullable=False,
    )


class Tower(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "towers"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "project_id", "projects", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "project_id", "code", name="uq_towers_tenant_project_code"
        ),
    )

    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Floor(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "floors"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "tower_id", "towers", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id",
            "tower_id",
            "floor_number",
            name="uq_floors_tenant_tower_number",
        ),
    )

    tower_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    floor_number: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Unit(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "units"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "project_id", "projects", ondelete="CASCADE"),
        tenant_fk(__tablename__, "tower_id", "towers"),
        tenant_fk(__tablename__, "floor_id", "floors"),
        UniqueConstraint(
            "organization_id", "project_id", "unit_number", name="uq_units_tenant_project_number"
        ),
        CheckConstraint("base_price IS NULL OR base_price >= 0", name="base_price_nonnegative"),
        CheckConstraint("area_sqft IS NULL OR area_sqft > 0", name="area_sqft_positive"),
        Index("ix_units_tenant_status", "organization_id", "status"),
        Index("ix_units_tenant_tower_floor", "organization_id", "tower_id", "floor_id"),
    )

    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tower_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    floor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    area_sqft: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[UnitStatus] = mapped_column(
        status_enum(UnitStatus, "unit_status"), default=UnitStatus.AVAILABLE, nullable=False
    )
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)


class UnitHold(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "unit_holds"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "held_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "active_unit_key", name="uq_unit_holds_tenant_active_unit"
        ),
        Index("ix_unit_holds_tenant_expiry", "organization_id", "status", "expires_at"),
    )

    unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    held_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[HoldStatus] = mapped_column(
        status_enum(HoldStatus, "unit_hold_status"), default=HoldStatus.ACTIVE, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_unit_key: Mapped[str | None] = mapped_column(String(36), nullable=True)


class PriceList(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_lists"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "project_id", "projects", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "code", "version", name="uq_price_lists_tenant_code_version"
        ),
        Index("ix_price_lists_tenant_project_status", "organization_id", "project_id", "status"),
    )

    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        status_enum(RecordStatus, "price_list_status"), default=RecordStatus.DRAFT, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    pricing_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
