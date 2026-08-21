from datetime import date, datetime
from decimal import Decimal

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
from app.models.enums import (
    ApprovalStatus,
    BookingStatus,
    CostSheetStatus,
    DocumentStatus,
    FinancingStatus,
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
        tenant_fk(__tablename__, "created_by_user_id", "users"),
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
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[VisitStatus] = mapped_column(
        status_enum(VisitStatus, "site_visit_status"),
        default=VisitStatus.SCHEDULED,
        nullable=False,
    )
    attendees: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SiteVisitUnit(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site_visit_units"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "site_visit_id", "site_visits", ondelete="CASCADE"),
        tenant_fk(__tablename__, "unit_id", "units"),
        UniqueConstraint(
            "organization_id",
            "site_visit_id",
            "unit_id",
            name="uq_site_visit_units_tenant_visit_unit",
        ),
    )

    site_visit_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    unit_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(nullable=False)


class CostSheet(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_sheets"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "price_list_id", "price_lists"),
        tenant_fk(__tablename__, "created_by_user_id", "users"),
        CheckConstraint("gross_value >= 0", name="gross_value_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="discount_amount_nonnegative"),
        CheckConstraint("tax_amount >= 0", name="tax_amount_nonnegative"),
        CheckConstraint("final_agreed_value >= 0", name="final_value_nonnegative"),
        CheckConstraint("booking_amount >= 0", name="booking_amount_nonnegative"),
        Index("ix_cost_sheets_tenant_status", "organization_id", "status"),
        Index("ix_cost_sheets_tenant_customer", "organization_id", "customer_id"),
    )

    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    unit_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    price_list_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[CostSheetStatus] = mapped_column(
        status_enum(CostSheetStatus, "cost_sheet_status"),
        default=CostSheetStatus.DRAFT,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    final_agreed_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    booking_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pricing_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class CostSheetItem(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_sheet_items"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "cost_sheet_id", "cost_sheets", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id",
            "cost_sheet_id",
            "sequence",
            name="uq_cost_sheet_items_tenant_sheet_sequence",
        ),
    )

    cost_sheet_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    taxable: Mapped[bool] = mapped_column(default=False, nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class DiscountApproval(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "discount_approvals"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "cost_sheet_id", "cost_sheets", ondelete="CASCADE"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "approver_user_id", "users"),
        UniqueConstraint(
            "organization_id",
            "cost_sheet_id",
            name="uq_discount_approvals_tenant_cost_sheet",
        ),
        Index(
            "ix_discount_approvals_tenant_status",
            "organization_id",
            "status",
        ),
    )

    cost_sheet_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approver_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        status_enum(ApprovalStatus, "discount_approval_status"),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )
    requested_discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    requested_discount_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    self_approval_limit_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    approval_level_name: Mapped[str] = mapped_column(String(120), nullable=False)
    required_approver_user_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_approver_role_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    previous_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    final_approved_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    request_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Quotation(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quotations"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "project_id", "projects"),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "cost_sheet_id", "cost_sheets"),
        tenant_fk(__tablename__, "parent_quotation_id", "quotations"),
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
    unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cost_sheet_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    parent_quotation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    final_agreed_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    booking_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    pricing_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
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
        tenant_fk(__tablename__, "unit_hold_id", "unit_holds"),
        tenant_fk(__tablename__, "booked_by_user_id", "users"),
        tenant_fk(__tablename__, "salesperson_user_id", "users"),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "verified_by_user_id", "users"),
        tenant_fk(__tablename__, "confirmed_by_user_id", "users"),
        UniqueConstraint("organization_id", "booking_number", name="uq_bookings_tenant_number"),
        UniqueConstraint(
            "organization_id", "active_unit_key", name="uq_bookings_tenant_active_unit"
        ),
        CheckConstraint("booking_amount >= 0", name="booking_amount_nonnegative"),
        CheckConstraint(
            "agreed_price IS NULL OR agreed_price >= 0", name="agreed_price_nonnegative"
        ),
        CheckConstraint("discount_amount >= 0", name="discount_amount_nonnegative"),
        Index("ix_bookings_tenant_status", "organization_id", "status"),
        Index("ix_bookings_tenant_customer", "organization_id", "customer_id"),
    )

    unit_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quotation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    unit_hold_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booked_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    salesperson_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel_partner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booking_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        status_enum(BookingStatus, "booking_status"),
        default=BookingStatus.DRAFT,
        nullable=False,
    )
    booking_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    agreed_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    active_unit_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BookingApplicant(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_applicants"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings", ondelete="CASCADE"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        UniqueConstraint(
            "organization_id", "booking_id", "sequence", name="uq_booking_applicants_sequence"
        ),
        UniqueConstraint(
            "organization_id", "primary_booking_key", name="uq_booking_applicants_primary"
        ),
        CheckConstraint("sequence > 0", name="sequence_positive"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sequence: Mapped[int] = mapped_column(nullable=False)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    primary_booking_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    tax_identifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    relationship_to_primary: Mapped[str | None] = mapped_column(String(80), nullable=True)


class BookingFinancing(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "booking_financing"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings", ondelete="CASCADE"),
        UniqueConstraint("organization_id", "booking_id", name="uq_booking_financing_booking"),
        CheckConstraint("loan_amount IS NULL OR loan_amount >= 0", name="loan_amount_nonnegative"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[FinancingStatus] = mapped_column(
        status_enum(FinancingStatus, "booking_financing_status"),
        default=FinancingStatus.NOT_REQUIRED,
        nullable=False,
    )
    lender_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    loan_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    application_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sanction_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


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
