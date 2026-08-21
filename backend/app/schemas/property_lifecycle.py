from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    AgreementStatus,
    PossessionStatus,
    PostBookingStage,
    ProgressStatus,
    SnagStatus,
    WorkflowStatus,
)


class CaseCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class AgreementCreate(BaseModel):
    agreement_number: str = Field(min_length=2, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)


class AgreementTransition(BaseModel):
    status: Literal["ISSUED", "SIGNED", "REGISTERED"]
    registration_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def registered_number(self) -> "AgreementTransition":
        if self.status == "REGISTERED" and not self.registration_number:
            raise ValueError("Registration number is required")
        return self


class ConstructionCreate(BaseModel):
    tower_id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5, max_length=5000)
    progress_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    update_date: date


class FinalDemandCreate(BaseModel):
    demand_number: str = Field(min_length=2, max_length=60)
    issue_date: date
    due_date: date

    @model_validator(mode="after")
    def valid_dates(self) -> "FinalDemandCreate":
        if self.due_date < self.issue_date:
            raise ValueError("Due date cannot precede issue date")
        return self


class SnagCreate(BaseModel):
    area: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=3000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class SnagDecision(BaseModel):
    status: Literal["IN_PROGRESS", "RESOLVED", "ACCEPTED", "WAIVED"]
    notes: str = Field(min_length=2, max_length=3000)


class OverrideCreate(BaseModel):
    reason: str = Field(min_length=10, max_length=3000)


class OverrideDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(min_length=5, max_length=3000)


class PossessionAction(BaseModel):
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class HandoverDocumentCreate(BaseModel):
    document_type: str = Field(min_length=2, max_length=80)
    is_required: bool = True


class AcknowledgementCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=160)
    notes: str = Field(min_length=2, max_length=2000)


class ReadinessCondition(BaseModel):
    code: str
    label: str
    complete: bool
    blocking: bool = True
    detail: str | None = None


class ReadinessView(BaseModel):
    ready: bool
    financially_ready: bool
    documents_ready: bool
    outstanding_amount: Decimal
    currency: str
    conditions: list[ReadinessCondition]
    active_override_id: str | None = None


class AgreementView(BaseModel):
    id: str
    agreement_number: str
    status: AgreementStatus
    registration_number: str | None
    file_name: str | None
    issued_at: datetime | None
    signed_at: datetime | None
    registered_at: datetime | None
    notes: str | None


class ConstructionView(BaseModel):
    id: str
    project_id: str
    tower_id: str | None
    title: str
    description: str
    progress_percent: Decimal
    status: ProgressStatus
    update_date: date
    published_at: datetime | None


class DemandView(BaseModel):
    id: str
    demand_number: str
    issue_date: date
    due_date: date
    amount: Decimal
    currency: str
    status: str


class NoDuesView(BaseModel):
    id: str
    certificate_number: str
    issued_at: datetime
    financial_snapshot: dict[str, object]


class SnagView(BaseModel):
    id: str
    area: str
    description: str
    severity: str
    status: SnagStatus
    resolution_notes: str | None
    reported_at: datetime
    resolved_at: datetime | None
    accepted_at: datetime | None


class OverrideView(BaseModel):
    id: str
    status: WorkflowStatus
    reason: str
    missing_conditions: list[str]
    requested_by_name: str
    decided_by_name: str | None
    decision_notes: str | None
    requested_at: datetime
    decided_at: datetime | None


class PossessionView(BaseModel):
    id: str
    status: PossessionStatus
    offered_at: datetime | None
    scheduled_at: datetime | None
    completed_at: datetime | None
    readiness_override_id: str | None
    notes: str | None


class HandoverDocumentView(BaseModel):
    id: str
    document_type: str
    is_required: bool
    file_name: str | None
    uploaded_at: datetime | None


class HandoverView(BaseModel):
    id: str
    status: WorkflowStatus
    handover_at: datetime | None
    notes: str | None
    customer_acknowledgement_name: str | None
    customer_acknowledgement_notes: str | None
    customer_acknowledged_at: datetime | None
    documents: list[HandoverDocumentView]


class CaseSummary(BaseModel):
    id: str
    booking_id: str
    booking_number: str
    customer_name: str
    project_name: str
    unit_number: str
    stage: PostBookingStage
    readiness: ReadinessView
    updated_at: datetime


class CaseDetail(BaseModel):
    case: CaseSummary
    agreement: AgreementView | None
    construction_updates: list[ConstructionView]
    final_demand: DemandView | None
    no_dues: NoDuesView | None
    snags: list[SnagView]
    overrides: list[OverrideView]
    possession: PossessionView | None
    handover: HandoverView | None


class LifecycleStats(BaseModel):
    total: int
    readiness_blocked: int
    ready_for_possession: int
    possession_scheduled: int
    handed_over: int


class BookingOption(BaseModel):
    id: str
    booking_number: str
    customer_name: str
    project_name: str
    unit_number: str
