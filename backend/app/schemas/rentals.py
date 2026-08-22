from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import (
    DocumentStatus,
    InvoiceStatus,
    LeaseStatus,
    PaymentStatus,
    RentalPropertyStatus,
    RentScheduleStatus,
    ServiceStatus,
    TenantStatus,
    WorkflowStatus,
)


class RentalPropertyCreate(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=200)
    property_type: str = Field(min_length=2, max_length=80)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=2, max_length=20)
    country: str = Field(min_length=2, max_length=100)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    area_sqft: Decimal | None = Field(default=None, gt=0)
    amenities: list[str] = Field(default_factory=list, max_length=100)
    default_monthly_rent: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    default_security_deposit: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    manager_user_id: str | None = Field(default=None, max_length=36)
    notes: str | None = Field(default=None, max_length=3000)


class RentalPropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    status: RentalPropertyStatus | None = None
    default_monthly_rent: Decimal | None = Field(default=None, ge=0)
    default_security_deposit: Decimal | None = Field(default=None, ge=0)
    manager_user_id: str | None = Field(default=None, max_length=36)
    amenities: list[str] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=3000)


class RentalPropertyView(BaseModel):
    id: str
    code: str
    name: str
    property_type: str
    address: str
    city: str
    bedrooms: int | None
    bathrooms: int | None
    area_sqft: Decimal | None
    amenities: list[str]
    default_monthly_rent: Decimal
    default_security_deposit: Decimal
    currency: str
    status: RentalPropertyStatus
    manager_user_id: str | None
    manager_name: str | None
    active_lease_id: str | None
    created_at: datetime
    updated_at: datetime


class TenantCreate(BaseModel):
    user_id: str | None = Field(default=None, max_length=36)
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str = Field(min_length=7, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    identity_type: str | None = Field(default=None, max_length=50)
    identity_reference: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=2000)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)


class TenantUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=2000)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    status: TenantStatus | None = None


class TenantView(BaseModel):
    id: str
    user_id: str | None
    full_name: str
    email: str | None
    phone: str | None
    alternate_phone: str | None
    identity_type: str | None
    identity_reference: str | None
    address: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    status: TenantStatus
    active_leases: int
    outstanding_rent: Decimal
    created_at: datetime
    updated_at: datetime


class LeaseCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=36)
    property_id: str = Field(min_length=1, max_length=36)
    lease_number: str = Field(min_length=2, max_length=60)
    start_date: date
    end_date: date
    monthly_rent: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    security_deposit: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    rent_due_day: int = Field(ge=1, le=28)
    notice_period_days: int = Field(ge=0, le=365)
    terms: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def valid_dates(self) -> "LeaseCreate":
        if self.end_date <= self.start_date:
            raise ValueError("Lease end date must be after start date")
        return self


class LeaseTransition(BaseModel):
    status: Literal["PENDING_SIGNATURE", "SIGNED"]
    notes: str | None = Field(default=None, max_length=2000)


class LeaseDocumentCreate(BaseModel):
    document_type: str = Field(min_length=2, max_length=80)
    is_required: bool = True


class LeaseDocumentDecision(BaseModel):
    status: Literal["VERIFIED", "REJECTED"]
    notes: str = Field(min_length=2, max_length=2000)


class InvoiceCreate(BaseModel):
    schedule_item_id: str = Field(min_length=1, max_length=36)
    invoice_number: str = Field(min_length=2, max_length=60)
    issue_date: date
    due_date: date
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: str = Field(min_length=2, max_length=40)
    reference_number: str | None = Field(default=None, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=100)
    paid_at: datetime | None = None


class PaymentDecision(BaseModel):
    status: Literal["COMPLETED", "FAILED"]
    notes: str = Field(min_length=2, max_length=2000)


class RenewalCreate(BaseModel):
    proposed_end_date: date
    proposed_monthly_rent: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reason: str = Field(min_length=5, max_length=3000)


class WorkflowDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(min_length=2, max_length=3000)


class MoveCreate(BaseModel):
    move_type: Literal["MOVE_IN", "MOVE_OUT"]
    scheduled_at: datetime
    notes: str | None = Field(default=None, max_length=3000)


class MoveComplete(BaseModel):
    checklist: dict[str, object] = Field(default_factory=dict)
    meter_readings: dict[str, object] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=3000)


class MaintenanceCreate(BaseModel):
    lease_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5, max_length=3000)
    scheduled_at: datetime | None = None


class MaintenanceUpdate(BaseModel):
    status: Literal["ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED"]
    assigned_user_id: str | None = Field(default=None, max_length=36)
    scheduled_at: datetime | None = None
    cost: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def cost_currency(self) -> "MaintenanceUpdate":
        if (self.cost is None) != (self.currency is None):
            raise ValueError("Cost and currency must be supplied together")
        return self


class LeaseDocumentView(BaseModel):
    id: str
    document_type: str
    version: int
    is_required: bool
    status: DocumentStatus
    file_name: str | None
    rejection_reason: str | None
    uploaded_at: datetime | None
    reviewed_at: datetime | None


class ScheduleView(BaseModel):
    id: str
    sequence: int
    period_start: date
    period_end: date
    due_date: date
    amount: Decimal
    currency: str
    status: RentScheduleStatus


class InvoiceView(BaseModel):
    id: str
    rent_schedule_item_id: str | None
    invoice_number: str
    status: InvoiceStatus
    period_start: date
    period_end: date
    issue_date: date
    due_date: date
    amount: Decimal
    tax_amount: Decimal
    total: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    currency: str


class PaymentView(BaseModel):
    id: str
    rental_invoice_id: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    method: str
    reference_number: str | None
    paid_at: datetime | None
    verified_at: datetime | None
    rejection_reason: str | None


class RenewalView(BaseModel):
    id: str
    status: WorkflowStatus
    previous_end_date: date
    proposed_end_date: date
    previous_monthly_rent: Decimal
    proposed_monthly_rent: Decimal
    reason: str
    decision_notes: str | None
    requested_at: datetime
    decided_at: datetime | None
    applied_at: datetime | None


class MoveView(BaseModel):
    id: str
    move_type: str
    status: WorkflowStatus
    scheduled_at: datetime
    checklist: dict[str, object] | None
    meter_readings: dict[str, object] | None
    notes: str | None
    requested_at: datetime
    approved_at: datetime | None
    completed_at: datetime | None


class MaintenanceView(BaseModel):
    id: str
    lease_id: str | None
    rental_property_id: str | None
    title: str
    description: str | None
    status: ServiceStatus
    assigned_user_id: str | None
    scheduled_at: datetime | None
    completed_at: datetime | None
    cost: Decimal | None
    currency: str | None
    created_at: datetime


class LeaseSummary(BaseModel):
    id: str
    lease_number: str
    status: LeaseStatus
    tenant_id: str
    tenant_name: str
    property_id: str
    property_name: str
    property_code: str
    start_date: date
    end_date: date
    monthly_rent: Decimal
    currency: str
    outstanding: Decimal
    overdue_invoices: int
    updated_at: datetime


class LeaseDetail(BaseModel):
    lease: LeaseSummary
    security_deposit: Decimal
    rent_due_day: int
    notice_period_days: int
    terms: str | None
    documents: list[LeaseDocumentView]
    schedule: list[ScheduleView]
    invoices: list[InvoiceView]
    payments: list[PaymentView]
    renewals: list[RenewalView]
    moves: list[MoveView]
    maintenance: list[MaintenanceView]


class RentalStats(BaseModel):
    total_properties: int
    available_properties: int
    occupied_properties: int
    active_leases: int
    overdue_invoices: int
    outstanding_rent: Decimal
    open_maintenance: int


class RentalOptions(BaseModel):
    properties: list[RentalPropertyView]
    tenants: list[TenantView]
    managers: list[dict[str, str]]
