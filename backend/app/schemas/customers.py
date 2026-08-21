import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import ActivityType, CustomerStatus

PHONE_PATTERN = re.compile(r"^[+0-9() .-]{7,32}$")


def _clean(value: str | None) -> str | None:
    return " ".join(value.split()) or None if value is not None else None


class CustomerCreate(BaseModel):
    full_name: str | None = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    occupation: str | None = Field(default=None, max_length=120)
    company_name: str | None = Field(default=None, max_length=160)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    preferred_location: str | None = Field(default=None, max_length=200)
    requirements: str | None = Field(default=None, max_length=5000)
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    owner_user_id: str | None = None
    branch_id: str | None = None
    communication_preferences: dict[str, Any] | None = None

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        cleaned = _clean(value)
        if cleaned is None or len(cleaned) < 2:
            raise ValueError("Customer name must contain at least two characters")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone", "alternate_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        cleaned = _clean(value)
        if cleaned is not None and not PHONE_PATTERN.fullmatch(cleaned):
            raise ValueError("Enter a valid phone number")
        return cleaned

    @field_validator(
        "gender",
        "occupation",
        "company_name",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        "preferred_location",
        "requirements",
    )
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @model_validator(mode="after")
    def validate_contact_and_budget(self) -> "CustomerCreate":
        if self.__class__ is CustomerCreate:
            if self.full_name is None:
                raise ValueError("Customer name is required")
            if not self.email and not self.phone:
                raise ValueError("Email or phone is required")
        if self.date_of_birth is not None and self.date_of_birth >= date.today():
            raise ValueError("Date of birth must be in the past")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class CustomerUpdate(CustomerCreate):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    status: CustomerStatus | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "CustomerUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("Customer name cannot be empty")
        if self.date_of_birth is not None and self.date_of_birth >= date.today():
            raise ValueError("Date of birth must be in the past")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class CustomerView(BaseModel):
    id: str
    converted_from_lead_id: str | None
    full_name: str
    email: str | None
    phone: str | None
    alternate_phone: str | None
    date_of_birth: date | None
    gender: str | None
    occupation: str | None
    company_name: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    preferred_location: str | None
    requirements: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    owner_user_id: str | None
    owner_name: str | None = None
    branch_id: str | None
    branch_name: str | None = None
    communication_preferences: dict[str, Any] | None
    status: CustomerStatus
    activity_count: int = 0
    booking_count: int = 0
    created_at: datetime
    updated_at: datetime


class CustomerStats(BaseModel):
    total: int
    prospects: int
    active: int
    inactive: int
    blocked: int


class CustomerActivityPayload(BaseModel):
    activity_type: ActivityType
    subject: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    channel: str | None = Field(default=None, max_length=40)
    direction: Literal["INBOUND", "OUTBOUND"] | None = None
    occurred_at: datetime | None = None

    @field_validator("subject", "notes", "channel")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean(value)


class CustomerActivityView(BaseModel):
    id: str
    activity_type: ActivityType
    subject: str
    notes: str | None
    channel: str | None
    direction: str | None
    performed_by_user_id: str | None
    performed_by_name: str | None = None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class JourneyRecord(BaseModel):
    id: str
    status: str
    source_name: str | None = None
    score: int
    created_at: datetime
    converted_at: datetime | None


class SalesRecord(BaseModel):
    id: str
    kind: Literal["site_visit", "quotation", "booking"]
    reference: str
    status: str
    project_name: str | None = None
    unit_number: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    occurred_at: datetime
    secondary_date: date | datetime | None = None


class DocumentRecord(BaseModel):
    id: str
    document_type: str
    file_name: str | None
    content_type: str | None
    size_bytes: int | None
    status: str
    version: int
    expiry_date: date | None
    booking_id: str | None
    rejection_reason: str | None
    uploaded_by_name: str | None = None
    created_at: datetime


class PaymentRecord(BaseModel):
    id: str
    booking_number: str | None = None
    amount: Decimal
    currency: str
    method: str
    status: str
    reference_number: str | None
    paid_at: datetime | None
    created_at: datetime


class AgreementRecord(BaseModel):
    id: str
    booking_number: str
    agreement_number: str
    status: str
    issued_at: datetime | None
    signed_at: datetime | None
    registered_at: datetime | None


class PossessionRecord(BaseModel):
    id: str
    booking_number: str
    unit_number: str
    status: str
    offered_at: datetime | None
    scheduled_at: datetime | None
    completed_at: datetime | None


class ServiceRequestRecord(BaseModel):
    id: str
    request_number: str
    category: str
    priority: str
    status: str
    subject: str
    opened_at: datetime
    resolved_at: datetime | None


class TimelineRecord(BaseModel):
    id: str
    kind: str
    title: str
    detail: str | None = None
    status: str | None = None
    occurred_at: datetime


class FinancialSummary(BaseModel):
    currency: str | None
    paid_amount: Decimal
    outstanding_amount: Decimal


class Customer360View(BaseModel):
    customer: CustomerView
    available_sections: list[str]
    lead_history: list[JourneyRecord] = []
    activities: list[CustomerActivityView] = []
    sales: list[SalesRecord] = []
    documents: list[DocumentRecord] = []
    payments: list[PaymentRecord] = []
    financial_summary: FinancialSummary | None = None
    agreements: list[AgreementRecord] = []
    possessions: list[PossessionRecord] = []
    service_requests: list[ServiceRequestRecord] = []
    timeline: list[TimelineRecord] = []
