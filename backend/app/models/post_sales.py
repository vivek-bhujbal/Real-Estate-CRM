from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
from app.models.enums import PossessionStatus, ProgressStatus, WorkflowStatus


class ConstructionUpdate(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "construction_updates"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "project_id", "projects", ondelete="CASCADE"),
        tenant_fk(__tablename__, "tower_id", "towers"),
        tenant_fk(__tablename__, "published_by_user_id", "users"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100", name="progress_percent_valid"
        ),
        Index(
            "ix_construction_updates_tenant_project_date",
            "organization_id",
            "project_id",
            "update_date",
        ),
    )

    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tower_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    published_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    progress_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[ProgressStatus] = mapped_column(
        status_enum(ProgressStatus, "construction_update_status"),
        default=ProgressStatus.DRAFT,
        nullable=False,
    )
    update_date: Mapped[date] = mapped_column(Date, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Possession(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "possessions"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "unit_id", "units"),
        UniqueConstraint("organization_id", "booking_id", name="uq_possessions_tenant_booking"),
        Index("ix_possessions_tenant_status", "organization_id", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[PossessionStatus] = mapped_column(
        status_enum(PossessionStatus, "possession_status"),
        default=PossessionStatus.PENDING,
        nullable=False,
    )
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Handover(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "handovers"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "possession_id", "possessions"),
        tenant_fk(__tablename__, "handed_over_by_user_id", "users"),
        UniqueConstraint("organization_id", "possession_id", name="uq_handovers_tenant_possession"),
    )

    possession_id: Mapped[str] = mapped_column(String(36), nullable=False)
    handed_over_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "handover_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    handover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
