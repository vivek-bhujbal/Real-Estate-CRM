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
    DocumentStatus,
    InvoiceStatus,
    LeaseStatus,
    PaymentStatus,
    RentalPropertyStatus,
    RentScheduleStatus,
    TenantStatus,
    WorkflowStatus,
)


class RentalProperty(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rental_properties"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "manager_user_id", "users"),
        UniqueConstraint("organization_id", "code", name="uq_rental_properties_code"),
        CheckConstraint(
            "default_monthly_rent >= 0 AND default_security_deposit >= 0",
            name="rental_default_amounts_nonnegative",
        ),
        Index("ix_rental_properties_status", "organization_id", "status"),
    )

    manager_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    property_type: Mapped[str] = mapped_column(String(80), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    bedrooms: Mapped[int | None] = mapped_column(nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(nullable=True)
    area_sqft: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    amenities: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    default_monthly_rent: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    default_security_deposit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[RentalPropertyStatus] = mapped_column(
        status_enum(RentalPropertyStatus, "rental_property_status"),
        default=RentalPropertyStatus.AVAILABLE,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Tenant(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "user_id", "users"),
        UniqueConstraint("organization_id", "user_id", name="uq_tenants_user"),
        Index("ix_tenants_tenant_phone", "organization_id", "phone"),
        Index("ix_tenants_tenant_email", "organization_id", "email"),
    )

    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    identity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    identity_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[TenantStatus] = mapped_column(
        status_enum(TenantStatus, "tenant_status"), default=TenantStatus.ACTIVE, nullable=False
    )


class Lease(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leases"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "property_id", "rental_properties"),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        UniqueConstraint("organization_id", "lease_number", name="uq_leases_tenant_number"),
        UniqueConstraint(
            "organization_id", "active_property_key", name="uq_leases_active_rental_property"
        ),
        CheckConstraint("monthly_rent >= 0 AND security_deposit >= 0", name="amounts_nonnegative"),
        CheckConstraint("end_date >= start_date", name="date_range_valid"),
        CheckConstraint(
            "NOT (unit_id IS NOT NULL AND property_id IS NOT NULL)",
            name="sales_rental_reference_exclusive",
        ),
        Index("ix_leases_tenant_status", "organization_id", "status"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    property_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[LeaseStatus] = mapped_column(
        status_enum(LeaseStatus, "lease_status"), default=LeaseStatus.DRAFT, nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    security_deposit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    active_unit_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_property_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rent_due_day: Mapped[int] = mapped_column(default=1, nullable=False)
    notice_period_days: Mapped[int] = mapped_column(default=30, nullable=False)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeaseDocument(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lease_documents"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lease_id", "leases", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        tenant_fk(__tablename__, "reviewed_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "lease_id", "document_type", "version", name="uq_lease_doc_version"
        ),
        Index("ix_lease_documents_status", "organization_id", "lease_id", "status"),
    )

    lease_id: Mapped[str] = mapped_column(String(36), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        status_enum(DocumentStatus, "lease_document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RentScheduleItem(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rent_schedule_items"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lease_id", "leases", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "lease_id", "sequence", name="uq_rent_schedule_sequence"
        ),
        CheckConstraint("amount >= 0", name="rent_schedule_amount_nonnegative"),
        Index("ix_rent_schedule_due_status", "organization_id", "due_date", "status"),
    )

    lease_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[RentScheduleStatus] = mapped_column(
        status_enum(RentScheduleStatus, "rent_schedule_status"),
        default=RentScheduleStatus.SCHEDULED,
        nullable=False,
    )


class RentalInvoice(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rental_invoices"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lease_id", "leases"),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "rent_schedule_item_id", "rent_schedule_items"),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "invoice_number", name="uq_rental_invoices_tenant_number"
        ),
        UniqueConstraint(
            "organization_id",
            "lease_id",
            "period_start",
            "period_end",
            name="uq_rental_invoices_tenant_lease_period",
        ),
        CheckConstraint("period_end >= period_start", name="period_valid"),
        CheckConstraint(
            "amount >= 0 AND tax_amount >= 0 AND total >= 0", name="amounts_nonnegative"
        ),
        Index("ix_rental_invoices_tenant_due_status", "organization_id", "due_date", "status"),
    )

    lease_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rent_schedule_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        status_enum(InvoiceStatus, "rental_invoice_status"),
        default=InvoiceStatus.DRAFT,
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RentPayment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rent_payments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "rental_invoice_id", "rental_invoices"),
        tenant_fk(__tablename__, "lease_id", "leases"),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "verified_by_user_id", "users"),
        tenant_fk(__tablename__, "submitted_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_rent_payments_tenant_idempotency_key"
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_rent_payments_tenant_paid", "organization_id", "tenant_id", "paid_at"),
    )

    rental_invoice_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        status_enum(PaymentStatus, "rent_payment_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class LeaseRenewal(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lease_renewals"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lease_id", "leases", ondelete="CASCADE"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "decided_by_user_id", "users"),
        Index("ix_lease_renewals_status", "organization_id", "status"),
    )

    lease_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "lease_renewal_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    previous_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    proposed_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    previous_monthly_rent: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    proposed_monthly_rent: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeaseMove(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lease_moves"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lease_id", "leases", ondelete="CASCADE"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        tenant_fk(__tablename__, "completed_by_user_id", "users"),
        Index("ix_lease_moves_status", "organization_id", "move_type", "status"),
    )

    lease_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    completed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    move_type: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "lease_move_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checklist: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    meter_readings: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
