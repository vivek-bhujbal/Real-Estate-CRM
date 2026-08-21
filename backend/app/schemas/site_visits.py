from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import VisitStatus


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()) or None


class SiteVisitCreate(BaseModel):
    lead_id: str | None = None
    customer_id: str | None = None
    project_id: str
    interested_unit_ids: list[str] = Field(default_factory=list, max_length=100)
    assigned_user_id: str | None = None
    scheduled_at: datetime
    attendees: list[str] = Field(default_factory=list, max_length=100)
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("interested_unit_ids")
    @classmethod
    def unique_units(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Interested units must be unique")
        return value

    @field_validator("attendees")
    @classmethod
    def clean_attendees(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(item.split()) for item in value if item.strip()]
        if len(cleaned) != len(set(item.casefold() for item in cleaned)):
            raise ValueError("Attendees must be unique")
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def contact_required(self) -> "SiteVisitCreate":
        if not self.lead_id and not self.customer_id:
            raise ValueError("A lead or customer is required")
        return self


class SiteVisitUpdate(BaseModel):
    lead_id: str | None = None
    customer_id: str | None = None
    project_id: str | None = None
    interested_unit_ids: list[str] | None = Field(default=None, max_length=100)
    assigned_user_id: str | None = None
    scheduled_at: datetime | None = None
    attendees: list[str] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("interested_unit_ids")
    @classmethod
    def unique_units(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Interested units must be unique")
        return value

    @field_validator("attendees")
    @classmethod
    def clean_attendees(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [" ".join(item.split()) for item in value if item.strip()]
        if len(cleaned) != len(set(item.casefold() for item in cleaned)):
            raise ValueError("Attendees must be unique")
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def fields_required(self) -> "SiteVisitUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class VisitStatusPayload(BaseModel):
    status: Literal["CONFIRMED", "CANCELLED", "NO_SHOW"]
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class CheckInPayload(BaseModel):
    attendees: list[str] | None = Field(default=None, max_length=100)

    @field_validator("attendees")
    @classmethod
    def clean_attendees(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [" ".join(item.split()) for item in value if item.strip()]


class CheckOutPayload(BaseModel):
    feedback: str | None = Field(default=None, max_length=10_000)
    outcome: str = Field(min_length=2, max_length=120)
    next_follow_up_at: datetime | None = None

    @field_validator("feedback")
    @classmethod
    def clean_feedback(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("outcome")
    @classmethod
    def clean_outcome(cls, value: str) -> str:
        return " ".join(value.split())


class InterestedUnitView(BaseModel):
    id: str
    unit_number: str
    unit_type: str | None
    status: str
    tower_name: str | None = None
    floor_name: str | None = None


class SiteVisitView(BaseModel):
    id: str
    lead_id: str | None
    lead_name: str | None = None
    customer_id: str | None
    customer_name: str | None = None
    project_id: str
    project_name: str
    interested_units: list[InterestedUnitView] = Field(default_factory=list)
    assigned_user_id: str | None
    assigned_user_name: str | None = None
    created_by_user_id: str | None
    created_by_user_name: str | None = None
    scheduled_at: datetime
    check_in_at: datetime | None
    check_out_at: datetime | None
    completed_at: datetime | None
    status: VisitStatus
    attendees: list[str] = Field(default_factory=list)
    notes: str | None
    feedback: str | None
    outcome: str | None
    next_follow_up_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SiteVisitStats(BaseModel):
    total: int
    upcoming: int
    today: int
    checked_in: int
    completed: int


class SalespersonOption(BaseModel):
    id: str
    full_name: str
    email: str
