from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
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
from app.models.enums import (
    PossessionStatus,
    PostBookingStage,
    ProgressStatus,
    RecordStatus,
    SnagStatus,
    WorkflowStatus,
)


class PostBookingCase(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "post_booking_cases"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        tenant_fk(__tablename__, "final_demand_letter_id", "demand_letters"),
        UniqueConstraint("organization_id", "booking_id", name="uq_post_booking_cases_booking"),
        Index("ix_post_booking_cases_status", "organization_id", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    final_demand_letter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[PostBookingStage] = mapped_column(
        status_enum(PostBookingStage, "post_booking_stage"),
        default=PostBookingStage.AGREEMENT_PENDING,
        nullable=False,
    )
    readiness_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    agreement_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    construction_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_demand_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_payment_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    no_dues_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snagging_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    possession_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handover_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
        tenant_fk(__tablename__, "post_booking_case_id", "post_booking_cases"),
        tenant_fk(__tablename__, "readiness_override_id", "possession_override_requests"),
        tenant_fk(__tablename__, "offered_by_user_id", "users"),
        tenant_fk(__tablename__, "scheduled_by_user_id", "users"),
        tenant_fk(__tablename__, "completed_by_user_id", "users"),
        UniqueConstraint("organization_id", "booking_id", name="uq_possessions_tenant_booking"),
        Index("ix_possessions_tenant_status", "organization_id", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    post_booking_case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    readiness_override_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    offered_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scheduled_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    completed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[PossessionStatus] = mapped_column(
        status_enum(PossessionStatus, "possession_status"),
        default=PossessionStatus.PENDING,
        nullable=False,
    )
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Handover(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "handovers"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "possession_id", "possessions"),
        tenant_fk(__tablename__, "handed_over_by_user_id", "users"),
        tenant_fk(__tablename__, "acknowledged_by_user_id", "users"),
        UniqueConstraint("organization_id", "possession_id", name="uq_handovers_tenant_possession"),
    )

    possession_id: Mapped[str] = mapped_column(String(36), nullable=False)
    handed_over_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    acknowledged_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "handover_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    handover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    customer_acknowledgement_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_acknowledgement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NoDuesCertificate(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "no_dues_certificates"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "post_booking_case_id", "post_booking_cases", ondelete="CASCADE"),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "issued_by_user_id", "users"),
        UniqueConstraint("organization_id", "booking_id", name="uq_no_dues_booking"),
        UniqueConstraint("organization_id", "certificate_number", name="uq_no_dues_number"),
    )

    post_booking_case_id: Mapped[str] = mapped_column(String(36), nullable=False)
    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    issued_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    certificate_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        status_enum(RecordStatus, "no_dues_status"), default=RecordStatus.ACTIVE, nullable=False
    )
    financial_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)


class SnagItem(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "snag_items"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "post_booking_case_id", "post_booking_cases", ondelete="CASCADE"),
        tenant_fk(__tablename__, "reported_by_user_id", "users"),
        tenant_fk(__tablename__, "resolved_by_user_id", "users"),
        Index("ix_snag_items_case_status", "organization_id", "post_booking_case_id", "status"),
    )

    post_booking_case_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reported_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[SnagStatus] = mapped_column(
        status_enum(SnagStatus, "snag_status"), default=SnagStatus.OPEN, nullable=False
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PossessionOverrideRequest(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "possession_override_requests"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "post_booking_case_id", "post_booking_cases", ondelete="CASCADE"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "decided_by_user_id", "users"),
        Index("ix_possession_overrides_status", "organization_id", "status"),
    )

    post_booking_case_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "possession_override_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    missing_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandoverDocument(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "handover_documents"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "handover_id", "handovers", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "handover_id", "document_type", name="uq_handover_document_type"
        ),
    )

    handover_id: Mapped[str] = mapped_column(String(36), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
