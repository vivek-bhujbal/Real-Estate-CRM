import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import ActivityType, LeadStatus

PHONE_PATTERN = re.compile(r"^[+0-9() .-]{7,32}$")


def _clean_required(value: str) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) < 2:
        raise ValueError("Value must contain at least two characters")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()) or None


def _clean_phone(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    if cleaned is not None and not PHONE_PATTERN.fullmatch(cleaned):
        raise ValueError("Enter a valid phone number")
    return cleaned


class LeadCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=160)
    source_id: str | None = None
    owner_user_id: str | None = None
    branch_id: str | None = None
    preferred_location: str | None = Field(default=None, max_length=200)
    requirements: str | None = Field(default=None, max_length=5000)
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    metadata_json: dict[str, Any] | None = None
    duplicate_override: bool = False

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone", "alternate_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)

    @field_validator("company_name", "preferred_location", "requirements")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def validate_contact_and_budget(self) -> "LeadCreate":
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class LeadUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=160)
    source_id: str | None = None
    branch_id: str | None = None
    preferred_location: str | None = Field(default=None, max_length=200)
    requirements: str | None = Field(default=None, max_length=5000)
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    metadata_json: dict[str, Any] | None = None

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return _clean_required(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone", "alternate_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)

    @field_validator("company_name", "preferred_location", "requirements")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def validate_payload(self) -> "LeadUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("Lead name cannot be empty")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class LeadView(BaseModel):
    id: str
    full_name: str
    email: str | None
    phone: str | None
    alternate_phone: str | None
    company_name: str | None
    source_id: str | None
    source_name: str | None = None
    owner_user_id: str | None
    owner_name: str | None = None
    branch_id: str | None
    branch_name: str | None = None
    preferred_location: str | None
    requirements: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    status: LeadStatus
    score: int
    score_breakdown: dict[str, Any] | None
    qualification_notes: str | None
    lost_reason_id: str | None
    lost_reason_name: str | None = None
    lost_notes: str | None
    duplicate_of_lead_id: str | None
    qualified_at: datetime | None
    converted_at: datetime | None
    last_activity_at: datetime | None
    next_follow_up_at: datetime | None
    metadata_json: dict[str, Any] | None
    activity_count: int = 0
    created_at: datetime
    updated_at: datetime


class LeadStats(BaseModel):
    total: int
    active: int
    unassigned: int
    follow_ups_due: int
    converted: int
    average_score: float


class LeadSourcePayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class LeadSourceView(LeadSourcePayload):
    id: str
    lead_count: int = 0
    created_at: datetime
    updated_at: datetime


class LostReasonPayload(LeadSourcePayload):
    pass


class LostReasonView(LostReasonPayload):
    id: str
    lead_count: int = 0
    created_at: datetime
    updated_at: datetime


class LeadAssignmentPayload(BaseModel):
    assigned_user_id: str | None


class BulkAssignmentPayload(BaseModel):
    lead_ids: list[str] = Field(min_length=1, max_length=500)
    assigned_user_id: str

    @field_validator("lead_ids")
    @classmethod
    def unique_leads(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Lead IDs must be unique")
        return value


class AssigneeView(BaseModel):
    id: str
    full_name: str
    email: str
    branch_id: str | None


class StatusTransitionPayload(BaseModel):
    status: LeadStatus
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class QualificationPayload(BaseModel):
    notes: str = Field(min_length=2, max_length=5000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str) -> str:
        return _clean_required(value)


class LostLeadPayload(BaseModel):
    reason_id: str
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class LeadConversionPayload(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return _clean_required(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)


class LeadConversionView(BaseModel):
    lead: LeadView
    customer_id: str


class LeadActivityPayload(BaseModel):
    activity_type: ActivityType
    subject: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    occurred_at: datetime
    due_at: datetime | None = None
    outcome: str | None = Field(default=None, max_length=255)
    is_completed: bool = False

    @field_validator("subject")
    @classmethod
    def clean_subject(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("notes", "outcome")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def validate_follow_up(self) -> "LeadActivityPayload":
        if self.activity_type == ActivityType.FOLLOW_UP and self.due_at is None:
            raise ValueError("Follow-up due date is required")
        return self


class LeadActivityView(LeadActivityPayload):
    id: str
    lead_id: str
    performed_by_user_id: str | None
    performed_by_name: str | None = None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompleteFollowUpPayload(BaseModel):
    outcome: str = Field(min_length=2, max_length=255)

    @field_validator("outcome")
    @classmethod
    def clean_outcome(cls, value: str) -> str:
        return _clean_required(value)


class LeadNotePayload(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    is_pinned: bool = False

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Note cannot be empty")
        return cleaned


class LeadNoteView(LeadNotePayload):
    id: str
    lead_id: str
    created_by_user_id: str | None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class TimelineItem(BaseModel):
    id: str
    kind: Literal["activity", "assignment", "note", "audit", "site_visit"]
    title: str
    detail: str | None
    actor_name: str | None
    occurred_at: datetime


class DuplicateCheckPayload(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    exclude_lead_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)

    @model_validator(mode="after")
    def require_identifier(self) -> "DuplicateCheckPayload":
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        return self


class DuplicateMatch(BaseModel):
    lead: LeadView
    matched_on: list[Literal["email", "phone"]]


class DuplicateGroup(BaseModel):
    key: str
    matched_on: Literal["email", "phone"]
    leads: list[LeadView]


class DuplicateResolutionPayload(BaseModel):
    primary_lead_id: str
    duplicate_lead_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_ids(self) -> "DuplicateResolutionPayload":
        if self.primary_lead_id in self.duplicate_lead_ids:
            raise ValueError("Primary lead cannot also be a duplicate")
        if len(set(self.duplicate_lead_ids)) != len(self.duplicate_lead_ids):
            raise ValueError("Duplicate lead IDs must be unique")
        return self


class ScoreRulePayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    field: Literal[
        "email_present",
        "phone_present",
        "source_code",
        "budget_min",
        "budget_max",
        "status",
        "activity_count",
        "days_since_created",
        "assigned",
    ]
    operator: Literal["eq", "neq", "gte", "lte", "contains", "present"]
    comparison_value: str | None = Field(default=None, max_length=255)
    points: int = Field(ge=-100, le=100)
    priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("comparison_value")
    @classmethod
    def clean_value(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def validate_comparison(self) -> "ScoreRulePayload":
        if self.operator != "present" and self.comparison_value is None:
            raise ValueError("Comparison value is required for this operator")
        return self


class ScoreRuleView(ScoreRulePayload):
    id: str
    created_at: datetime
    updated_at: datetime


class ImportLeadRow(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    source_code: str | None = Field(default=None, max_length=50)
    owner_email: EmailStr | None = None
    preferred_location: str | None = Field(default=None, max_length=200)
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    requirements: str | None = Field(default=None, max_length=5000)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("email", "owner_email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)

    @field_validator("source_code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) and value.strip() else None

    @field_validator("preferred_location", "requirements")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def validate_row(self) -> "ImportLeadRow":
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class ImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    skip_duplicates: bool = True

    @field_validator("filename")
    @classmethod
    def clean_filename(cls, value: str) -> str:
        return value.strip().replace("\\", "_").replace("/", "_")


class ImportRowResult(BaseModel):
    row_number: int
    status: Literal["ready", "duplicate", "error"]
    message: str | None = None
    duplicate_lead_ids: list[str] = Field(default_factory=list)


class ImportPreview(BaseModel):
    total_rows: int
    ready_rows: int
    duplicate_rows: int
    error_rows: int
    rows: list[ImportRowResult]


class ImportBatchView(BaseModel):
    id: str
    filename: str
    status: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    error_rows: int
    errors: list[dict[str, Any]]
    completed_at: datetime | None
    created_at: datetime


class AgeingBucket(BaseModel):
    label: str
    minimum_days: int
    maximum_days: int | None
    count: int


class KanbanColumn(BaseModel):
    status: LeadStatus
    total: int
    items: list[LeadView]
