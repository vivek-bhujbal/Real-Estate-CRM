from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    FinancialChargeStatus,
    FinancialChargeType,
    InstallmentStatus,
    PaymentStatus,
    ReconciliationStatus,
    RecordStatus,
)


class FinanceSummary(BaseModel):
    total_receivable: Decimal
    received: Decimal
    outstanding: Decimal
    overdue: Decimal
    unapplied_payments: Decimal
    pending_reconciliation: int
    pending_refunds: int


class CollectionAccount(BaseModel):
    booking_id: str
    booking_number: str
    booking_status: str
    customer_id: str
    customer_name: str
    project_name: str
    unit_number: str
    currency: str
    total_value: Decimal
    received: Decimal
    outstanding: Decimal
    overdue: Decimal
    next_due_date: date | None


class FinanceInstallment(BaseModel):
    id: str
    sequence: int
    name: str
    due_date: date
    amount: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    status: InstallmentStatus


class FinanceDemand(BaseModel):
    id: str
    installment_id: str | None
    demand_number: str
    status: RecordStatus
    issue_date: date
    due_date: date
    amount: Decimal
    currency: str


class FinanceAllocation(BaseModel):
    id: str
    payment_id: str
    installment_id: str | None
    demand_letter_id: str | None
    amount: Decimal
    allocated_at: datetime
    reversed_at: datetime | None


class FinancePayment(BaseModel):
    id: str
    amount: Decimal
    allocated_amount: Decimal
    unallocated_amount: Decimal
    currency: str
    method: str
    status: PaymentStatus
    reference_number: str | None
    paid_at: datetime | None
    verified_at: datetime | None
    receipt_number: str | None
    created_at: datetime


class FinanceReconciliation(BaseModel):
    id: str
    payment_id: str
    status: ReconciliationStatus
    expected_amount: Decimal
    received_amount: Decimal
    difference_amount: Decimal
    external_reference: str | None
    notes: str | None
    reconciled_at: datetime


class FinanceCharge(BaseModel):
    id: str
    installment_id: str
    charge_type: FinancialChargeType
    status: FinancialChargeStatus
    principal_amount: Decimal
    rate_percent: Decimal
    days_calculated: int
    amount: Decimal
    paid_amount: Decimal
    currency: str
    calculation_date: date
    reason: str
    waived_reason: str | None


class FinanceRefund(BaseModel):
    id: str
    payment_id: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    reference_number: str | None
    reason: str | None
    decision_notes: str | None
    requested_by_user_id: str | None
    approved_by_user_id: str | None
    requested_at: datetime
    processed_at: datetime | None


class LedgerEntryView(BaseModel):
    id: str
    entry_type: str
    amount: Decimal
    currency: str
    description: str
    posted_at: datetime


class CollectionAccountDetail(BaseModel):
    account: CollectionAccount
    plan_name: str | None
    installments: list[FinanceInstallment]
    demands: list[FinanceDemand]
    payments: list[FinancePayment]
    allocations: list[FinanceAllocation]
    reconciliations: list[FinanceReconciliation]
    charges: list[FinanceCharge]
    refunds: list[FinanceRefund]
    ledger: list[LedgerEntryView]


class DemandCreate(BaseModel):
    installment_id: str
    demand_number: str = Field(min_length=2, max_length=60, pattern=r"^[A-Z0-9][A-Z0-9_/-]*$")
    issue_date: date
    due_date: date

    @model_validator(mode="after")
    def dates_valid(self) -> "DemandCreate":
        if self.due_date < self.issue_date:
            raise ValueError("Demand due date cannot precede issue date")
        return self


class CollectionPaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: str = Field(min_length=2, max_length=40)
    reference_number: str | None = Field(default=None, max_length=100)
    paid_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class ReconciliationCreate(BaseModel):
    received_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    external_reference: str | None = Field(default=None, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class PaymentAllocationRequest(BaseModel):
    installment_ids: list[str] = Field(default_factory=list, max_length=100)
    allow_unallocated_credit: bool = False
    manual_reconciliation_reason: str | None = Field(default=None, min_length=5, max_length=1000)


class ChargeCreate(BaseModel):
    charge_type: FinancialChargeType
    calculation_date: date
    annual_rate_percent: Decimal | None = Field(default=None, ge=0, le=1000)
    fixed_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=100)

    @model_validator(mode="after")
    def calculation_mode(self) -> "ChargeCreate":
        if self.charge_type == FinancialChargeType.INTEREST and self.annual_rate_percent is None:
            raise ValueError("Annual rate is required for interest")
        if self.charge_type == FinancialChargeType.PENALTY and self.fixed_amount is None:
            raise ValueError("Fixed amount is required for a penalty")
        return self


class ChargeWaive(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RefundCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reason: str = Field(min_length=3, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=100)


class RefundDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(min_length=3, max_length=2000)


class RefundProcess(BaseModel):
    reference_number: str = Field(min_length=2, max_length=100)
