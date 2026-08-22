from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import EscalationStatus, ServicePriority, TicketStatus


class CategoryCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class CategoryView(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    is_active: bool
    policy_count: int
    ticket_count: int
    created_at: datetime
    updated_at: datetime


class SLAPolicyCreate(BaseModel):
    category_id: str = Field(min_length=1, max_length=36)
    priority: ServicePriority
    first_response_minutes: int = Field(gt=0, le=525_600)
    escalation_minutes: int = Field(gt=0, le=525_600)
    resolution_minutes: int = Field(gt=0, le=525_600)

    @model_validator(mode="after")
    def valid_order(self) -> "SLAPolicyCreate":
        if not (self.first_response_minutes <= self.escalation_minutes <= self.resolution_minutes):
            raise ValueError(
                "First response must be due before escalation, and escalation before resolution"
            )
        return self


class SLAPolicyUpdate(BaseModel):
    first_response_minutes: int | None = Field(default=None, gt=0, le=525_600)
    escalation_minutes: int | None = Field(default=None, gt=0, le=525_600)
    resolution_minutes: int | None = Field(default=None, gt=0, le=525_600)
    is_active: bool | None = None


class SLAPolicyView(BaseModel):
    id: str
    category_id: str
    category_name: str
    priority: ServicePriority
    first_response_minutes: int
    escalation_minutes: int
    resolution_minutes: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TicketCreate(BaseModel):
    category_id: str = Field(min_length=1, max_length=36)
    priority: ServicePriority = ServicePriority.MEDIUM
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=10_000)
    customer_id: str | None = Field(default=None, max_length=36)
    tenant_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)
    unit_id: str | None = Field(default=None, max_length=36)
    assigned_user_id: str | None = Field(default=None, max_length=36)


class TicketUpdate(BaseModel):
    category_id: str | None = Field(default=None, max_length=36)
    priority: ServicePriority | None = None
    subject: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=5, max_length=10_000)


class AssignmentCreate(BaseModel):
    assigned_user_id: str = Field(min_length=1, max_length=36)
    notes: str | None = Field(default=None, max_length=2000)


class StatusTransition(BaseModel):
    status: Literal["IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED", "CLOSED"]
    notes: str = Field(min_length=2, max_length=5000)
    resolution_summary: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def resolution_required(self) -> "StatusTransition":
        if self.status == "RESOLVED" and not self.resolution_summary:
            raise ValueError("Resolution summary is required when resolving a ticket")
        return self


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)
    is_internal: bool = False


class EscalationCreate(BaseModel):
    to_user_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=5, max_length=5000)


class EscalationDecision(BaseModel):
    action: Literal["ACKNOWLEDGE", "RESOLVE"]
    notes: str | None = Field(default=None, max_length=3000)


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comments: str | None = Field(default=None, max_length=3000)


class CommentView(BaseModel):
    id: str
    author_user_id: str
    author_name: str
    body: str
    is_internal: bool
    created_at: datetime


class AttachmentView(BaseModel):
    id: str
    comment_id: str | None
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str
    created_at: datetime


class EscalationView(BaseModel):
    id: str
    status: EscalationStatus
    from_user_name: str | None
    to_user_id: str
    to_user_name: str
    escalated_by_name: str | None
    acknowledged_by_name: str | None
    reason: str
    escalated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class FeedbackView(BaseModel):
    id: str
    rating: int
    comments: str | None
    submitted_by_name: str
    submitted_at: datetime


class SLAView(BaseModel):
    configured: bool
    response_state: Literal["NOT_CONFIGURED", "ON_TRACK", "MET", "BREACHED"]
    resolution_state: Literal["NOT_CONFIGURED", "ON_TRACK", "MET", "BREACHED"]
    response_due_at: datetime | None
    resolution_due_at: datetime | None
    escalation_due_at: datetime | None
    first_responded_at: datetime | None
    response_remaining_minutes: int | None
    resolution_remaining_minutes: int | None
    escalation_due: bool


class TicketSummary(BaseModel):
    id: str
    request_number: str
    subject: str
    category_id: str | None
    category_name: str
    priority: ServicePriority
    status: TicketStatus
    requester_name: str
    requester_type: str
    assigned_user_id: str | None
    assigned_user_name: str | None
    is_escalated: bool
    sla: SLAView
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class TicketDetail(BaseModel):
    ticket: TicketSummary
    description: str
    customer_id: str | None
    tenant_id: str | None
    project_id: str | None
    project_name: str | None
    unit_id: str | None
    unit_number: str | None
    resolution_summary: str | None
    closure_notes: str | None
    comments: list[CommentView]
    attachments: list[AttachmentView]
    escalations: list[EscalationView]
    feedback: FeedbackView | None


class TicketStats(BaseModel):
    total_open: int
    unassigned: int
    in_progress: int
    waiting_for_customer: int
    resolved: int
    sla_breached: int
    escalated: int
    average_feedback: float | None


class TicketOptions(BaseModel):
    categories: list[CategoryView]
    agents: list[dict[str, str]]
    customers: list[dict[str, str | None]]
    tenants: list[dict[str, str | None]]
    projects: list[dict[str, str]]
    units: list[dict[str, str]]
