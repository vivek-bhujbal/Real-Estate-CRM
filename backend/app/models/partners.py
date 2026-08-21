from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
    AgreementStatus,
    CommissionStatus,
    DocumentStatus,
    PartnerStatus,
    PaymentStatus,
    WorkflowStatus,
)


class ChannelPartner(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_partners"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "applied_by_user_id", "users"),
        tenant_fk(__tablename__, "manager_user_id", "users"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        tenant_fk(__tablename__, "activated_by_user_id", "users"),
        UniqueConstraint("organization_id", "code", name="uq_channel_partners_tenant_code"),
        UniqueConstraint(
            "organization_id", "registration_number", name="uq_channel_partners_registration"
        ),
        Index("ix_channel_partners_tenant_status", "organization_id", "status"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    applied_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    partner_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tax_identifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tax_registration_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_account_holder: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(String(160), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_account_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    bank_account_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activated_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    default_commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    lead_protection_days: Mapped[int] = mapped_column(default=30, nullable=False)
    application_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PartnerStatus] = mapped_column(
        status_enum(PartnerStatus, "channel_partner_status"),
        default=PartnerStatus.APPLICATION,
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    documents_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agreement_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PartnerContact(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_contacts"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "channel_partner_id", "email", name="uq_partner_contacts_email"
        ),
        Index("ix_partner_contacts_partner", "organization_id", "channel_partner_id"),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PartnerTerritory(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_territories"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners", ondelete="CASCADE"),
        tenant_fk(__tablename__, "territory_id", "territories", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "channel_partner_id", "territory_id", name="uq_partner_territory"
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    territory_id: Mapped[str] = mapped_column(String(36), nullable=False)


class PartnerProject(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_projects"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners", ondelete="CASCADE"),
        tenant_fk(__tablename__, "project_id", "projects", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "channel_partner_id", "project_id", name="uq_partner_project"
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)


class PartnerDocument(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_documents"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        tenant_fk(__tablename__, "reviewed_by_user_id", "users"),
        UniqueConstraint("organization_id", "storage_key", name="uq_partner_document_storage"),
        Index(
            "ix_partner_documents_partner_status", "organization_id", "channel_partner_id", "status"
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        status_enum(DocumentStatus, "partner_document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PartnerAgreement(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_agreements"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners", ondelete="CASCADE"),
        tenant_fk(__tablename__, "verified_by_user_id", "users"),
        UniqueConstraint("organization_id", "agreement_number", name="uq_partner_agreement_number"),
        CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 100", name="commission_percent_valid"
        ),
        Index(
            "ix_partner_agreements_partner_status",
            "organization_id",
            "channel_partner_id",
            "status",
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agreement_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[AgreementStatus] = mapped_column(
        status_enum(AgreementStatus, "partner_agreement_status"),
        default=AgreementStatus.DRAFT,
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    commission_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    terms_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommissionStructure(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_structures"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners", ondelete="CASCADE"),
        tenant_fk(__tablename__, "project_id", "projects", ondelete="CASCADE"),
        CheckConstraint("rate_percent >= 0 AND rate_percent <= 100", name="rate_percent_valid"),
        UniqueConstraint(
            "organization_id", "active_scope_key", name="uq_commission_structure_active_scope"
        ),
        Index(
            "ix_commission_structures_partner", "organization_id", "channel_partner_id", "is_active"
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    calculation_basis: Mapped[str] = mapped_column(
        String(40), default="AGREED_VALUE", nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_scope_key: Mapped[str | None] = mapped_column(String(100), nullable=True)


class PartnerLead(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_leads"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "lead_id", "leads"),
        tenant_fk(__tablename__, "registered_by_user_id", "users"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        UniqueConstraint(
            "organization_id",
            "channel_partner_id",
            "lead_id",
            name="uq_partner_leads_tenant_partner_lead",
        ),
        Index("ix_partner_leads_tenant_protection", "organization_id", "protected_until"),
        UniqueConstraint(
            "organization_id", "active_email_key", name="uq_partner_lead_active_email"
        ),
        UniqueConstraint(
            "organization_id", "active_phone_key", name="uq_partner_lead_active_phone"
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(36), nullable=False)
    registered_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "partner_lead_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    protected_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    active_email_key: Mapped[str | None] = mapped_column(String(254), nullable=True)
    active_phone_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    registration_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommissionPayout(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_payouts"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "payout_number", name="uq_commission_payouts_tenant_number"
        ),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        Index("ix_commission_payouts_tenant_status", "organization_id", "status"),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payout_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        status_enum(PaymentStatus, "commission_payout_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Commission(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commissions"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "commission_payout_id", "commission_payouts"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        tenant_fk(__tablename__, "commission_structure_id", "commission_structures"),
        UniqueConstraint(
            "organization_id",
            "channel_partner_id",
            "booking_id",
            name="uq_commissions_tenant_partner_booking",
        ),
        CheckConstraint(
            "rate_percent >= 0 AND rate_percent <= 100 AND amount >= 0",
            name="rate_and_amount_valid",
        ),
        Index(
            "ix_commissions_tenant_partner_status",
            "organization_id",
            "channel_partner_id",
            "status",
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    commission_payout_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    commission_structure_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[CommissionStatus] = mapped_column(
        status_enum(CommissionStatus, "commission_status"),
        default=CommissionStatus.PENDING,
        nullable=False,
    )
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class PartnerDispute(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_disputes"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "partner_lead_id", "partner_leads"),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "commission_id", "commissions"),
        tenant_fk(__tablename__, "commission_payout_id", "commission_payouts"),
        tenant_fk(__tablename__, "raised_by_user_id", "users"),
        tenant_fk(__tablename__, "assigned_to_user_id", "users"),
        tenant_fk(__tablename__, "resolved_by_user_id", "users"),
        UniqueConstraint("organization_id", "dispute_number", name="uq_partner_dispute_number"),
        Index(
            "ix_partner_disputes_partner_status", "organization_id", "channel_partner_id", "status"
        ),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    partner_lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    commission_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    commission_payout_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    raised_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    dispute_number: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "partner_dispute_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
