from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import ApprovalStatus, BookingStatus, FinancingStatus, PaymentStatus


class JointApplicantInput(BaseModel):
    customer_id: str | None = Field(default=None, max_length=36)
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    date_of_birth: date | None = None
    tax_identifier: str | None = Field(default=None, max_length=80)
    relationship_to_primary: str = Field(min_length=2, max_length=80)


class InstallmentInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    due_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class PaymentPlanInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    effective_from: date
    installments: list[InstallmentInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_schedule(self) -> "PaymentPlanInput":
        if any(item.due_date < self.effective_from for item in self.installments):
            raise ValueError("Installment due dates cannot precede the plan effective date")
        if [item.due_date for item in self.installments] != sorted(
            item.due_date for item in self.installments
        ):
            raise ValueError("Installments must be ordered by due date")
        return self


class FinancingInput(BaseModel):
    status: FinancingStatus = FinancingStatus.NOT_REQUIRED
    lender_name: str | None = Field(default=None, max_length=180)
    loan_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    application_number: str | None = Field(default=None, max_length=100)
    sanction_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_financing(self) -> "FinancingInput":
        if self.status != FinancingStatus.NOT_REQUIRED and not self.lender_name:
            raise ValueError("Lender name is required when financing is used")
        if self.status != FinancingStatus.NOT_REQUIRED and not self.loan_amount:
            raise ValueError("Loan amount is required when financing is used")
        return self


class BookingCreate(BaseModel):
    quotation_id: str = Field(min_length=1, max_length=36)
    unit_hold_id: str = Field(min_length=1, max_length=36)
    booking_number: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_/-]*$")
    salesperson_user_id: str | None = Field(default=None, max_length=36)
    channel_partner_id: str | None = Field(default=None, max_length=36)
    joint_applicants: list[JointApplicantInput] = Field(default_factory=list, max_length=10)
    financing: FinancingInput | None = None
    payment_plan: PaymentPlanInput

    @field_validator("booking_number", mode="before")
    @classmethod
    def uppercase_number(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class BookingApplicantView(BaseModel):
    id: str
    customer_id: str | None
    sequence: int
    is_primary: bool
    full_name: str
    email: str | None
    phone: str | None
    date_of_birth: date | None
    tax_identifier: str | None
    relationship_to_primary: str | None


class InstallmentView(BaseModel):
    id: str
    sequence: int
    name: str
    due_date: date
    amount: Decimal
    paid_amount: Decimal
    status: str


class PaymentPlanView(BaseModel):
    id: str
    name: str
    status: str
    currency: str
    total_amount: Decimal
    effective_from: date
    installments: list[InstallmentView]


class FinancingView(BaseModel):
    id: str
    status: FinancingStatus
    lender_name: str | None
    loan_amount: Decimal | None
    application_number: str | None
    sanction_reference: str | None
    notes: str | None


class BookingPaymentCreate(BaseModel):
    installment_id: str | None = Field(default=None, max_length=36)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: str = Field(min_length=2, max_length=40)
    reference_number: str | None = Field(default=None, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=100)
    paid_at: datetime | None = None


class BookingPaymentDecision(BaseModel):
    status: Literal["COMPLETED", "FAILED"]
    notes: str | None = Field(default=None, max_length=1000)


class BookingPaymentView(BaseModel):
    id: str
    installment_id: str | None
    verified_by_user_id: str | None
    verifier_name: str | None
    amount: Decimal
    currency: str
    method: str
    status: PaymentStatus
    reference_number: str | None
    idempotency_key: str
    paid_at: datetime | None
    verified_at: datetime | None
    created_at: datetime


class BookingApprovalRequest(BaseModel):
    approver_user_ids: list[str] = Field(min_length=1, max_length=10)
    comments: str | None = Field(default=None, max_length=2000)

    @field_validator("approver_user_ids")
    @classmethod
    def unique_approvers(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Approvers must be unique")
        return value


class BookingApprovalDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    comments: str = Field(min_length=2, max_length=2000)


class BookingApprovalView(BaseModel):
    id: str
    step_number: int
    requested_by_user_id: str
    requested_by_name: str | None
    approver_user_id: str
    approver_name: str | None
    status: ApprovalStatus
    comments: str | None
    decided_at: datetime | None
    created_at: datetime


class BookingDocumentSummary(BaseModel):
    id: str
    document_type: str
    version: int
    status: str
    file_name: str | None
    expiry_date: date | None


class BookingView(BaseModel):
    id: str
    booking_number: str
    status: BookingStatus
    customer_id: str
    customer_name: str
    lead_id: str | None
    quotation_id: str | None
    quotation_number: str | None
    unit_hold_id: str | None
    unit_id: str
    unit_number: str
    project_id: str
    project_name: str
    salesperson_user_id: str | None
    salesperson_name: str | None
    channel_partner_id: str | None
    broker_name: str | None
    booked_by_user_id: str
    booked_by_name: str
    agreed_price: Decimal | None
    discount_amount: Decimal
    booking_amount: Decimal
    currency: str
    paid_amount: Decimal
    applicants: list[BookingApplicantView]
    payment_plan: PaymentPlanView | None
    payments: list[BookingPaymentView]
    documents: list[BookingDocumentSummary]
    financing: FinancingView | None
    approvals: list[BookingApprovalView]
    submitted_at: datetime | None
    verification_completed_at: datetime | None
    approval_requested_at: datetime | None
    booked_at: datetime | None
    rejected_at: datetime | None
    cancelled_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class BookingAdvance(BaseModel):
    status: Literal["DOCUMENTATION_PENDING", "PAYMENT_PENDING", "VERIFICATION"]


class BookingCancel(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class BookingStats(BaseModel):
    total: int
    documentation_pending: int
    payment_pending: int
    verification: int
    approval: int
    confirmed: int
    rejected: int
    cancelled: int


class BookingOption(BaseModel):
    id: str
    label: str


class EligibleQuotationOption(BaseModel):
    id: str
    quotation_number: str
    version: int
    customer_id: str
    customer_name: str
    unit_id: str
    unit_number: str
    agreed_price: Decimal
    discount_amount: Decimal
    booking_amount: Decimal
    currency: str
    hold_id: str


class BookingOptions(BaseModel):
    quotations: list[EligibleQuotationOption]
    salespeople: list[BookingOption]
    brokers: list[BookingOption]
    approvers: list[BookingOption]
