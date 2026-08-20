from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint
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
        Index("ix_leads_tenant_status", "organization_id", "status"),
        Index("ix_leads_tenant_phone", "organization_id", "phone"),
        Index("ix_leads_tenant_email", "organization_id", "email"),
    )

    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        status_enum(LeadStatus, "lead_status"), default=LeadStatus.NEW, nullable=False
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


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


class Customer(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "converted_from_lead_id", "leads"),
        UniqueConstraint(
            "organization_id",
            "converted_from_lead_id",
            name="uq_customers_tenant_converted_lead",
        ),
        Index("ix_customers_tenant_phone", "organization_id", "phone"),
        Index("ix_customers_tenant_email", "organization_id", "email"),
    )

    converted_from_lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[CustomerStatus] = mapped_column(
        status_enum(CustomerStatus, "customer_status"),
        default=CustomerStatus.PROSPECT,
        nullable=False,
    )


class CustomerDocument(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_documents"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "storage_key", name="uq_customer_documents_tenant_storage_key"
        ),
        Index("ix_customer_documents_tenant_customer", "organization_id", "customer_id"),
    )

    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        status_enum(DocumentStatus, "customer_document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
