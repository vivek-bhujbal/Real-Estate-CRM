from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, status_enum, tenant_fk, tenant_unique
from app.models.enums import InvoiceStatus, LeaseStatus, PaymentStatus, TenantStatus


class Tenant(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        tenant_unique(__tablename__),
        Index("ix_tenants_tenant_phone", "organization_id", "phone"),
        Index("ix_tenants_tenant_email", "organization_id", "email"),
    )

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[TenantStatus] = mapped_column(
        status_enum(TenantStatus, "tenant_status"), default=TenantStatus.ACTIVE, nullable=False
    )


class Lease(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leases"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "unit_id", "units"),
        UniqueConstraint("organization_id", "lease_number", name="uq_leases_tenant_number"),
        UniqueConstraint("organization_id", "active_unit_key", name="uq_leases_tenant_active_unit"),
        CheckConstraint("monthly_rent >= 0 AND security_deposit >= 0", name="amounts_nonnegative"),
        CheckConstraint("end_date >= start_date", name="date_range_valid"),
        Index("ix_leases_tenant_status", "organization_id", "status"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
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


class RentalInvoice(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rental_invoices"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "lease_id", "leases"),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
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


class RentPayment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rent_payments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "rental_invoice_id", "rental_invoices"),
        tenant_fk(__tablename__, "lease_id", "leases"),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "verified_by_user_id", "users"),
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
