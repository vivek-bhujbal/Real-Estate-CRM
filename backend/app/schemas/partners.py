from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import (
    AgreementStatus,
    CommissionStatus,
    DocumentStatus,
    PartnerStatus,
    PaymentStatus,
    WorkflowStatus,
)


class PartnerApplicationCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    name: str = Field(min_length=2, max_length=180)
    legal_name: str = Field(min_length=2, max_length=200)
    partner_type: str = Field(min_length=2, max_length=80)
    registration_number: str = Field(min_length=2, max_length=100)
    registration_date: date | None = None
    contact_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=32)
    website: str | None = Field(default=None, max_length=255)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(min_length=2, max_length=100)
    manager_user_id: str | None = Field(default=None, max_length=36)
    application_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("code", mode="before")
    @classmethod
    def uppercase_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class PartnerProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    legal_name: str | None = Field(default=None, min_length=2, max_length=200)
    partner_type: str | None = Field(default=None, min_length=2, max_length=80)
    registration_number: str | None = Field(default=None, min_length=2, max_length=100)
    registration_date: date | None = None
    contact_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    website: str | None = Field(default=None, max_length=255)
    address_line1: str | None = Field(default=None, min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    country: str | None = Field(default=None, min_length=2, max_length=100)
    manager_user_id: str | None = Field(default=None, max_length=36)
    application_notes: str | None = Field(default=None, max_length=2000)


class PartnerComplianceUpdate(BaseModel):
    tax_identifier: str = Field(min_length=3, max_length=80)
    gst_number: str | None = Field(default=None, max_length=40)
    tax_registration_name: str = Field(min_length=2, max_length=200)
    bank_account_holder: str = Field(min_length=2, max_length=200)
    bank_name: str = Field(min_length=2, max_length=160)
    bank_branch: str | None = Field(default=None, max_length=160)
    bank_ifsc: str = Field(min_length=4, max_length=30)
    bank_account_last4: str = Field(pattern=r"^[0-9]{4}$")
    bank_account_reference: str = Field(min_length=8, max_length=255)
    lead_protection_days: int = Field(ge=1, le=365)


class PartnerAssignmentsUpdate(BaseModel):
    territory_ids: list[str] = Field(default_factory=list, max_length=100)
    project_ids: list[str] = Field(default_factory=list, max_length=100)


class PartnerContactCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    designation: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    is_primary: bool = False

    @model_validator(mode="after")
    def contact_required(self) -> "PartnerContactCreate":
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        return self


class PartnerContactView(BaseModel):
    id: str
    full_name: str
    designation: str | None
    email: str | None
    phone: str | None
    is_primary: bool
    is_active: bool


class PartnerDocumentRequest(BaseModel):
    document_type: str = Field(min_length=2, max_length=80)
    expiry_date: date | None = None


class PartnerDocumentDecision(BaseModel):
    status: Literal["VERIFIED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)
    rejection_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def rejection_required(self) -> "PartnerDocumentDecision":
        if self.status == "REJECTED" and not (self.rejection_reason or "").strip():
            raise ValueError("Rejection reason is required")
        return self


class PartnerDocumentView(BaseModel):
    id: str
    document_type: str
    status: DocumentStatus
    file_name: str | None
    content_type: str | None
    size_bytes: int | None
    expiry_date: date | None
    rejection_reason: str | None
    review_notes: str | None
    uploaded_at: datetime | None
    reviewed_at: datetime | None


class PartnerAgreementCreate(BaseModel):
    agreement_number: str = Field(min_length=2, max_length=80)
    effective_from: date
    effective_until: date | None = None
    commission_percent: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)
    terms_summary: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def valid_dates(self) -> "PartnerAgreementCreate":
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("Agreement expiry cannot precede its effective date")
        return self


class PartnerAgreementView(BaseModel):
    id: str
    agreement_number: str
    status: AgreementStatus
    effective_from: date
    effective_until: date | None
    commission_percent: Decimal
    terms_summary: str | None
    file_name: str | None
    issued_at: datetime | None
    signed_at: datetime | None


class CommissionStructureCreate(BaseModel):
    project_id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=2, max_length=160)
    rate_percent: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)
    calculation_basis: Literal["AGREED_VALUE"] = "AGREED_VALUE"
    effective_from: date
    effective_until: date | None = None

    @model_validator(mode="after")
    def valid_dates(self) -> "CommissionStructureCreate":
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("Structure expiry cannot precede its effective date")
        return self


class CommissionStructureView(BaseModel):
    id: str
    project_id: str | None
    project_name: str | None
    name: str
    rate_percent: Decimal
    calculation_basis: str
    effective_from: date
    effective_until: date | None
    is_active: bool


class PartnerLeadCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    preferred_location: str | None = Field(default=None, max_length=200)
    requirements: str | None = Field(default=None, max_length=5000)
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    registration_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_lead(self) -> "PartnerLeadCreate":
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class PartnerLeadView(BaseModel):
    id: str
    lead_id: str
    lead_name: str
    email: str | None
    phone: str | None
    status: WorkflowStatus
    registered_at: datetime
    protected_until: date | None
    registration_notes: str | None


class CommissionDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(min_length=2, max_length=2000)


class CommissionView(BaseModel):
    id: str
    booking_id: str
    booking_number: str
    status: CommissionStatus
    rate_percent: Decimal
    amount: Decimal
    currency: str
    commission_payout_id: str | None


class PayoutCreate(BaseModel):
    payout_number: str = Field(min_length=2, max_length=60)
    commission_ids: list[str] = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class PayoutProcess(BaseModel):
    reference_number: str = Field(min_length=2, max_length=100)


class PayoutView(BaseModel):
    id: str
    payout_number: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    reference_number: str | None
    notes: str | None
    decision_notes: str | None
    requested_at: datetime
    approved_at: datetime | None
    paid_at: datetime | None
    commission_ids: list[str]


class DisputeCreate(BaseModel):
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=5, max_length=5000)
    partner_lead_id: str | None = Field(default=None, max_length=36)
    booking_id: str | None = Field(default=None, max_length=36)
    commission_id: str | None = Field(default=None, max_length=36)
    commission_payout_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def related_record(self) -> "DisputeCreate":
        if not any(
            (self.partner_lead_id, self.booking_id, self.commission_id, self.commission_payout_id)
        ):
            raise ValueError("A related lead, booking, commission, or payout is required")
        return self


class DisputeAssign(BaseModel):
    assigned_to_user_id: str = Field(min_length=1, max_length=36)


class DisputeDecision(BaseModel):
    status: Literal["COMPLETED", "REJECTED"]
    resolution: str = Field(min_length=5, max_length=5000)


class DisputeView(BaseModel):
    id: str
    dispute_number: str
    category: str
    status: WorkflowStatus
    description: str
    resolution: str | None
    related_type: str
    related_id: str
    assigned_to_name: str | None
    raised_at: datetime
    resolved_at: datetime | None


class LifecycleAction(BaseModel):
    notes: str = Field(min_length=2, max_length=2000)


class PartnerSummary(BaseModel):
    id: str
    code: str
    name: str
    legal_name: str | None
    partner_type: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    city: str | None
    status: PartnerStatus
    manager_name: str | None
    active_leads: int
    confirmed_bookings: int
    payable_commission: Decimal
    currency: str | None
    created_at: datetime
    updated_at: datetime


class PartnerDetail(BaseModel):
    partner: PartnerSummary
    registration_number: str | None
    registration_date: date | None
    website: str | None
    address: dict[str, str | None]
    tax: dict[str, str | None]
    bank: dict[str, str | None]
    lead_protection_days: int
    application_notes: str | None
    review_notes: str | None
    rejection_reason: str | None
    territory_ids: list[str]
    project_ids: list[str]
    contacts: list[PartnerContactView]
    documents: list[PartnerDocumentView]
    agreements: list[PartnerAgreementView]
    commission_structures: list[CommissionStructureView]
    leads: list[PartnerLeadView]
    commissions: list[CommissionView]
    payouts: list[PayoutView]
    disputes: list[DisputeView]
    lifecycle: dict[str, datetime | None]


class PartnerStats(BaseModel):
    total: int
    applications: int
    verification: int
    approval_queue: int
    active: int
    suspended: int
    payable_commission: Decimal


class PartnerOption(BaseModel):
    id: str
    label: str


class PartnerOptions(BaseModel):
    managers: list[PartnerOption]
    territories: list[PartnerOption]
    projects: list[PartnerOption]
