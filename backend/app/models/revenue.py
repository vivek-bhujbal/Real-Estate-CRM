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
    AgreementStatus,
    InstallmentStatus,
    LedgerEntryType,
    PaymentStatus,
    RecordStatus,
    WorkflowStatus,
)


class Agreement(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agreements"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        UniqueConstraint("organization_id", "booking_id", name="uq_agreements_tenant_booking"),
        UniqueConstraint("organization_id", "agreement_number", name="uq_agreements_tenant_number"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agreement_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[AgreementStatus] = mapped_column(
        status_enum(AgreementStatus, "agreement_status"),
        default=AgreementStatus.DRAFT,
        nullable=False,
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PaymentPlan(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_plans"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        UniqueConstraint(
            "organization_id", "booking_id", "name", name="uq_payment_plans_tenant_booking_name"
        ),
        CheckConstraint("total_amount >= 0", name="total_amount_nonnegative"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        status_enum(RecordStatus, "payment_plan_status"),
        default=RecordStatus.DRAFT,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class Installment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "installments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "payment_plan_id", "payment_plans", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id",
            "payment_plan_id",
            "sequence",
            name="uq_installments_tenant_plan_sequence",
        ),
        CheckConstraint("amount >= 0 AND paid_amount >= 0", name="amounts_nonnegative"),
        Index("ix_installments_tenant_due_status", "organization_id", "due_date", "status"),
    )

    payment_plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    status: Mapped[InstallmentStatus] = mapped_column(
        status_enum(InstallmentStatus, "installment_status"),
        default=InstallmentStatus.SCHEDULED,
        nullable=False,
    )


class DemandLetter(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demand_letters"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "installment_id", "installments"),
        UniqueConstraint(
            "organization_id", "demand_number", name="uq_demand_letters_tenant_number"
        ),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        Index("ix_demand_letters_tenant_due_status", "organization_id", "due_date", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    installment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    demand_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        status_enum(RecordStatus, "demand_letter_status"),
        default=RecordStatus.DRAFT,
        nullable=False,
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Payment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "installment_id", "installments"),
        tenant_fk(__tablename__, "verified_by_user_id", "users"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_payments_tenant_idempotency_key"
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_tenant_customer_paid", "organization_id", "customer_id", "paid_at"),
        Index("ix_payments_tenant_status", "organization_id", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    installment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        status_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Receipt(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "receipts"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "payment_id", "payments"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        UniqueConstraint("organization_id", "payment_id", name="uq_receipts_tenant_payment"),
        UniqueConstraint("organization_id", "receipt_number", name="uq_receipts_tenant_number"),
    )

    payment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    receipt_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        status_enum(RecordStatus, "receipt_status"), default=RecordStatus.ACTIVE, nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class CustomerLedger(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_ledger_entries"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "payment_id", "payments"),
        tenant_fk(__tablename__, "receipt_id", "receipts"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_customer_ledger_tenant_idempotency_key"
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index(
            "ix_customer_ledger_tenant_customer_posted",
            "organization_id",
            "customer_id",
            "posted_at",
        ),
    )

    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    receipt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        status_enum(LedgerEntryType, "ledger_entry_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Cancellation(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cancellations"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        UniqueConstraint("organization_id", "booking_id", name="uq_cancellations_tenant_booking"),
        Index("ix_cancellations_tenant_status", "organization_id", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "cancellation_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Refund(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "cancellation_id", "cancellations"),
        tenant_fk(__tablename__, "payment_id", "payments"),
        tenant_fk(__tablename__, "customer_id", "customers"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_refunds_tenant_status", "organization_id", "status"),
    )

    cancellation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        status_enum(PaymentStatus, "refund_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UnitTransfer(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "unit_transfers"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "booking_id", "bookings"),
        tenant_fk(__tablename__, "from_unit_id", "units"),
        tenant_fk(__tablename__, "to_unit_id", "units"),
        tenant_fk(__tablename__, "requested_by_user_id", "users"),
        tenant_fk(__tablename__, "approved_by_user_id", "users"),
        CheckConstraint("from_unit_id <> to_unit_id", name="units_different"),
        Index("ix_unit_transfers_tenant_booking_status", "organization_id", "booking_id", "status"),
    )

    booking_id: Mapped[str] = mapped_column(String(36), nullable=False)
    from_unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        status_enum(WorkflowStatus, "unit_transfer_status"),
        default=WorkflowStatus.REQUESTED,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
