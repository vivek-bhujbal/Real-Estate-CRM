from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, status_enum, tenant_fk, tenant_unique
from app.models.enums import CommissionStatus, PartnerStatus, PaymentStatus, WorkflowStatus


class ChannelPartner(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_partners"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "code", name="uq_channel_partners_tenant_code"),
        Index("ix_channel_partners_tenant_status", "organization_id", "status"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tax_identifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[PartnerStatus] = mapped_column(
        status_enum(PartnerStatus, "channel_partner_status"),
        default=PartnerStatus.PENDING,
        nullable=False,
    )


class PartnerLead(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_leads"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "lead_id", "leads"),
        UniqueConstraint(
            "organization_id",
            "channel_partner_id",
            "lead_id",
            name="uq_partner_leads_tenant_partner_lead",
        ),
        Index("ix_partner_leads_tenant_protection", "organization_id", "protected_until"),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "partner_lead_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    protected_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class CommissionPayout(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_payouts"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "payout_number", name="uq_commission_payouts_tenant_number"
        ),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        Index("ix_commission_payouts_tenant_status", "organization_id", "status"),
    )

    channel_partner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payout_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        status_enum(PaymentStatus, "commission_payout_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Commission(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commissions"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "channel_partner_id", "channel_partners"),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "commission_payout_id", "commission_payouts"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
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
    status: Mapped[CommissionStatus] = mapped_column(
        status_enum(CommissionStatus, "commission_status"),
        default=CommissionStatus.PENDING,
        nullable=False,
    )
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
