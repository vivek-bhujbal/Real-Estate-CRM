from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, status_enum, tenant_fk, tenant_unique
from app.models.enums import ActivityType, CustomerStatus, DocumentStatus, LeadStatus


class LeadSource(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_sources"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "code", name="uq_lead_sources_organization_id_code"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Lead(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "source_id", "lead_sources"),
        tenant_fk(__tablename__, "owner_user_id", "users"),
        tenant_fk(__tablename__, "branch_id", "branches"),
        tenant_fk(__tablename__, "lost_reason_id", "lost_lead_reasons"),
        tenant_fk(__tablename__, "import_batch_id", "lead_import_batches"),
        tenant_fk(__tablename__, "duplicate_of_lead_id", "leads"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="budget_range",
        ),
        Index("ix_leads_tenant_status", "organization_id", "status"),
        Index("ix_leads_tenant_phone", "organization_id", "phone"),
        Index("ix_leads_tenant_email", "organization_id", "email"),
        Index("ix_leads_tenant_normalized_phone", "organization_id", "normalized_phone"),
        Index("ix_leads_tenant_normalized_email", "organization_id", "normalized_email"),
        Index("ix_leads_tenant_owner_status", "organization_id", "owner_user_id", "status"),
        Index("ix_leads_tenant_follow_up", "organization_id", "next_follow_up_at"),
    )

    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    lost_reason_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    duplicate_of_lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        status_enum(LeadStatus, "lead_status"), default=LeadStatus.NEW, nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    qualification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lost_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class LostLeadReason(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lost_lead_reasons"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint(
            "organization_id", "code", name="uq_lost_lead_reasons_organization_id_code"
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class LeadImportBatch(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_import_batches"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        Index("ix_lead_import_batches_tenant_created", "organization_id", "created_at"),
    )

    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mapping_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    errors_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadScoreRule(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_score_rules"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "name", name="uq_lead_score_rules_tenant_name"),
        CheckConstraint("points >= -100 AND points <= 100", name="points_range"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), nullable=False)
    comparison_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class LeadAssignment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_assignments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lead_id", "leads", ondelete="CASCADE"),
        tenant_fk(__tablename__, "assigned_user_id", "users"),
        tenant_fk(__tablename__, "assigned_by_user_id", "users"),
        UniqueConstraint(
            "organization_id",
            "active_lead_key",
            name="uq_lead_assignments_tenant_active_lead",
        ),
        Index(
            "ix_lead_assignments_tenant_user_active",
            "organization_id",
            "assigned_user_id",
            "is_active",
        ),
    )

    lead_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assigned_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    active_lead_key: Mapped[str | None] = mapped_column(String(36), nullable=True)


class LeadActivity(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_activities"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lead_id", "leads", ondelete="CASCADE"),
        tenant_fk(__tablename__, "performed_by_user_id", "users"),
        Index(
            "ix_lead_activities_tenant_lead_occurred", "organization_id", "lead_id", "occurred_at"
        ),
    )

    lead_id: Mapped[str] = mapped_column(String(36), nullable=False)
    performed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activity_type: Mapped[ActivityType] = mapped_column(
        status_enum(ActivityType, "lead_activity_type"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_completed: Mapped[bool] = mapped_column(default=False, nullable=False)


class LeadNote(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_notes"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lead_id", "leads", ondelete="CASCADE"),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        Index("ix_lead_notes_tenant_lead_created", "organization_id", "lead_id", "created_at"),
    )

    lead_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(default=False, nullable=False)


class Customer(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "converted_from_lead_id", "leads"),
        tenant_fk(__tablename__, "owner_user_id", "users"),
        tenant_fk(__tablename__, "branch_id", "branches"),
        UniqueConstraint(
            "organization_id",
            "converted_from_lead_id",
            name="uq_customers_tenant_converted_lead",
        ),
        Index("ix_customers_tenant_phone", "organization_id", "phone"),
        Index("ix_customers_tenant_email", "organization_id", "email"),
        Index("ix_customers_tenant_normalized_phone", "organization_id", "normalized_phone"),
        Index("ix_customers_tenant_normalized_email", "organization_id", "normalized_email"),
        Index("ix_customers_tenant_owner_status", "organization_id", "owner_user_id", "status"),
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="budget_range",
        ),
    )

    converted_from_lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(30), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    communication_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[CustomerStatus] = mapped_column(
        status_enum(CustomerStatus, "customer_status"),
        default=CustomerStatus.PROSPECT,
        nullable=False,
    )


class CustomerActivity(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_activities"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers", ondelete="CASCADE"),
        tenant_fk(__tablename__, "performed_by_user_id", "users"),
        Index(
            "ix_customer_activities_tenant_customer_occurred",
            "organization_id",
            "customer_id",
            "occurred_at",
        ),
    )

    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    performed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activity_type: Mapped[ActivityType] = mapped_column(
        status_enum(ActivityType, "customer_activity_type"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CustomerDocument(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_documents"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers", ondelete="CASCADE"),
        tenant_fk(__tablename__, "booking_id", "bookings", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        tenant_fk(__tablename__, "reviewed_by_user_id", "users"),
        tenant_fk(__tablename__, "supersedes_document_id", "customer_documents"),
        UniqueConstraint(
            "organization_id", "storage_key", name="uq_customer_documents_tenant_storage_key"
        ),
        UniqueConstraint(
            "organization_id",
            "document_set_id",
            "version",
            name="uq_customer_documents_tenant_set_version",
        ),
        UniqueConstraint(
            "organization_id",
            "current_version_key",
            name="uq_customer_documents_tenant_current_version",
        ),
        Index("ix_customer_documents_tenant_customer", "organization_id", "customer_id"),
        Index("ix_customer_documents_tenant_booking", "organization_id", "booking_id"),
        Index("ix_customer_documents_tenant_status", "organization_id", "status"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_nonnegative"),
    )

    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_set_id: Mapped[str] = mapped_column(String(36), nullable=False)
    supersedes_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_version_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(default=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        status_enum(DocumentStatus, "customer_document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
