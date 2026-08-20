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
from app.models.enums import (
    ApprovalStatus,
    BookingStatus,
    DocumentStatus,
    QuotationStatus,
    VisitStatus,
)


class SiteVisit(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site_visits"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "project_id", "projects"),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "assigned_user_id", "users"),
        CheckConstraint(
            "lead_id IS NOT NULL OR customer_id IS NOT NULL", name="lead_or_customer_required"
        ),
        Index("ix_site_visits_tenant_scheduled", "organization_id", "scheduled_at"),
        Index("ix_site_visits_tenant_status", "organization_id", "status"),
    )

    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[VisitStatus] = mapped_column(
        status_enum(VisitStatus, "site_visit_status"),
        default=VisitStatus.SCHEDULED,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Quotation(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quotations"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "project_id", "projects"),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        UniqueConstraint(
            "organization_id",
            "quotation_number",
            "version",
            name="uq_quotations_tenant_number_version",
        ),
        CheckConstraint(
            "lead_id IS NOT NULL OR customer_id IS NOT NULL", name="lead_or_customer_required"
        ),
        CheckConstraint("subtotal >= 0 AND total >= 0", name="totals_nonnegative"),
        Index("ix_quotations_tenant_status", "organization_id", "status"),
    )

    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quotation_number: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[QuotationStatus] = mapped_column(
        status_enum(QuotationStatus, "quotation_status"),
        default=QuotationStatus.DRAFT,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)


class QuotationItem(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quotation_items"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "quotation_id", "quotations", ondelete="CASCADE"),
        tenant_fk(__tablename__, "unit_id", "units"),
        UniqueConstraint(
            "organization_id",
            "quotation_id",
            "sequence",
            name="uq_quotation_items_tenant_quote_sequence",
        ),
        CheckConstraint("quantity > 0 AND unit_price >= 0 AND total >= 0", name="amounts_valid"),
    )

    quotation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sequence: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class Booking(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "quotation_id", "quotations"),
        tenant_fk(__tablename__, "booked_by_user_id", "users"),
        UniqueConstraint("organization_id", "booking_number", name="uq_bookings_tenant_number"),
        UniqueConstraint(
            "organization_id", "active_unit_key", name="uq_bookings_tenant_active_unit"
        ),
        CheckConstraint("booking_amount >= 0", name="booking_amount_nonnegative"),
        Index("ix_bookings_tenant_status", "organization_id", "status"),
        Index("ix_bookings_tenant_customer", "organization_id", "customer_id"),
    )

    unit_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quotation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booked_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    booking_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        status_enum(BookingStatus, "booking_status"),
        default=BookingStatus.DRAFT,
        nullable=False,
    )
    booking_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    active_unit_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BookingDocument(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_documents"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "storage_key", name="uq_booking_documents_tenant_storage_key"
        ),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        status_enum(DocumentStatus, "booking_document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )


class BookingApproval(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_approvals"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings", ondelete="CASCADE"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "approver_user_id", "users"),
        UniqueConstraint(
            "organization_id",
            "booking_id",
            "step_number",
            name="uq_booking_approvals_tenant_booking_step",
        ),
        Index(
            "ix_booking_approvals_tenant_approver_status",
            "organization_id",
            "approver_user_id",
            "status",
        ),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approver_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        status_enum(ApprovalStatus, "booking_approval_status"),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
