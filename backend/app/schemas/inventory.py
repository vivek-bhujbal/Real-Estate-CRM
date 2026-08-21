from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import BookingStatus, HoldStatus, HoldType, ProjectStatus, UnitStatus


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()) or None


def _clean_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    cleaned = list(dict.fromkeys(item for value in values if (item := _clean(value))))
    return cleaned or None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    description: str | None = Field(default=None, max_length=5000)
    project_type: str | None = Field(default=None, max_length=80)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    rera_number: str | None = Field(default=None, max_length=80)
    launch_date: date | None = None
    expected_possession_date: date | None = None
    default_currency: str = Field(default="INR", min_length=3, max_length=3)
    amenities: list[str] | None = Field(default=None, max_length=100)
    configuration: dict[str, Any] | None = None
    status: ProjectStatus = ProjectStatus.PLANNING

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean(value) or value

    @field_validator("code", "default_currency", mode="before")
    @classmethod
    def uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator(
        "description",
        "project_type",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        "rera_number",
    )
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("amenities")
    @classmethod
    def clean_amenities(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "ProjectCreate":
        if self.launch_date and self.expected_possession_date:
            if self.expected_possession_date < self.launch_date:
                raise ValueError("Expected possession cannot be before launch")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    project_type: str | None = Field(default=None, max_length=80)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    rera_number: str | None = Field(default=None, max_length=80)
    launch_date: date | None = None
    expected_possession_date: date | None = None
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    amenities: list[str] | None = Field(default=None, max_length=100)
    configuration: dict[str, Any] | None = None
    status: ProjectStatus | None = None

    @field_validator(
        "name",
        "description",
        "project_type",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        "rera_number",
    )
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("default_currency", mode="before")
    @classmethod
    def uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("amenities")
    @classmethod
    def clean_amenities(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value)

    @model_validator(mode="after")
    def not_empty(self) -> "ProjectUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Project name cannot be empty")
        return self


class ProjectView(BaseModel):
    id: str
    name: str
    code: str
    description: str | None
    project_type: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    rera_number: str | None
    launch_date: date | None
    expected_possession_date: date | None
    default_currency: str
    amenities: list[str] | None
    configuration: dict[str, Any] | None
    status: ProjectStatus
    tower_count: int = 0
    unit_count: int = 0
    available_unit_count: int = 0
    created_at: datetime
    updated_at: datetime


class TowerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean(value) or value

    @field_validator("code", mode="before")
    @classmethod
    def uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class TowerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(
        default=None, min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$"
    )
    is_active: bool | None = None

    @model_validator(mode="after")
    def not_empty(self) -> "TowerUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class TowerView(TowerCreate):
    id: str
    project_id: str
    floor_count: int = 0
    unit_count: int = 0
    created_at: datetime
    updated_at: datetime


class FloorCreate(BaseModel):
    tower_id: str
    name: str = Field(min_length=1, max_length=80)
    floor_number: int = Field(ge=-20, le=300)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean(value) or value


class FloorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    floor_number: int | None = Field(default=None, ge=-20, le=300)
    is_active: bool | None = None

    @model_validator(mode="after")
    def not_empty(self) -> "FloorUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class FloorView(BaseModel):
    id: str
    project_id: str
    tower_id: str
    tower_name: str
    name: str
    floor_number: int
    is_active: bool
    unit_count: int = 0
    created_at: datetime
    updated_at: datetime


class UnitCreate(BaseModel):
    tower_id: str | None = None
    floor_id: str | None = None
    unit_number: str = Field(min_length=1, max_length=50)
    unit_type: str | None = Field(default=None, max_length=80)
    area_sqft: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    carpet_area_sqft: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    built_up_area_sqft: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    facing: str | None = Field(default=None, max_length=40)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    balconies: int | None = Field(default=None, ge=0, le=100)
    base_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    amenities: list[str] | None = Field(default=None, max_length=100)
    price_components: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None

    @field_validator("unit_number", "unit_type", "facing")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("currency", mode="before")
    @classmethod
    def uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("amenities")
    @classmethod
    def clean_amenities(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value)

    @model_validator(mode="after")
    def hierarchy_and_price_are_valid(self) -> "UnitCreate":
        if self.floor_id and not self.tower_id:
            raise ValueError("Tower is required when a floor is selected")
        if self.base_price is None and self.currency is not None:
            raise ValueError("Currency requires a base price")
        return self


class UnitUpdate(BaseModel):
    tower_id: str | None = None
    floor_id: str | None = None
    unit_number: str | None = Field(default=None, min_length=1, max_length=50)
    unit_type: str | None = Field(default=None, max_length=80)
    area_sqft: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    carpet_area_sqft: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    built_up_area_sqft: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    facing: str | None = Field(default=None, max_length=40)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    balconies: int | None = Field(default=None, ge=0, le=100)
    base_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    amenities: list[str] | None = Field(default=None, max_length=100)
    price_components: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None

    @model_validator(mode="after")
    def not_empty(self) -> "UnitUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class UnitView(BaseModel):
    id: str
    project_id: str
    project_name: str
    tower_id: str | None
    tower_name: str | None
    floor_id: str | None
    floor_name: str | None
    floor_number: int | None
    unit_number: str
    unit_type: str | None
    area_sqft: Decimal | None
    carpet_area_sqft: Decimal | None
    built_up_area_sqft: Decimal | None
    facing: str | None
    bedrooms: int | None
    bathrooms: int | None
    balconies: int | None
    status: UnitStatus
    base_price: Decimal | None
    currency: str | None
    amenities: list[str] | None
    price_components: dict[str, Any] | None
    configuration: dict[str, Any] | None
    active_hold_id: str | None = None
    created_at: datetime
    updated_at: datetime


class InventoryStats(BaseModel):
    total: int
    available: int
    held: int
    booking_initiated: int
    booked: int
    sold: int


class UnitStatusPayload(BaseModel):
    status: UnitStatus


class UnitHoldCreate(BaseModel):
    hold_type: Literal["SOFT_HOLD", "HARD_HOLD"]
    expires_at: datetime
    hold_reason: str = Field(min_length=2, max_length=1000)
    customer_id: str
    lead_id: str | None = None
    salesperson_user_id: str | None = None

    @field_validator("hold_reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        return " ".join(value.split())


class UnitHoldView(BaseModel):
    id: str
    unit_id: str
    unit_number: str
    project_id: str
    project_name: str
    hold_type: HoldType | None
    hold_reason: str | None
    customer_id: str | None
    customer_name: str | None
    lead_id: str | None
    held_by_user_id: str
    salesperson_name: str
    approved_by_user_id: str | None
    approver_name: str | None
    status: HoldStatus
    starts_at: datetime
    expires_at: datetime
    released_at: datetime | None
    approved_at: datetime | None
    rejected_at: datetime | None
    approval_notes: str | None
    release_reason: str | None
    created_at: datetime
    updated_at: datetime


class HoldApprovalDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(min_length=2, max_length=1000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str) -> str:
        return " ".join(value.split())


class HoldReleasePayload(BaseModel):
    reason: str = Field(min_length=2, max_length=255)

    @field_validator("reason")
    @classmethod
    def clean_release_reason(cls, value: str) -> str:
        return " ".join(value.split())


class HoldStats(BaseModel):
    total: int
    pending_approval: int
    active: int
    released: int
    expired: int
    rejected: int
    converted: int


class HoldExpiryResult(BaseModel):
    expired_count: int
    processed_at: datetime


class HoldSalespersonOption(BaseModel):
    id: str
    full_name: str
    email: str


class BookingInitiate(BaseModel):
    customer_id: str
    lead_id: str | None = None
    quotation_id: str | None = None
    booking_number: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_/-]*$")
    booking_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("booking_number", "currency", mode="before")
    @classmethod
    def uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class BookingStatusPayload(BaseModel):
    status: Literal["CONFIRMED", "CANCELLED"]


class InventoryBookingView(BaseModel):
    id: str
    unit_id: str
    unit_number: str
    customer_id: str
    lead_id: str | None
    quotation_id: str | None
    booked_by_user_id: str
    booking_number: str
    booking_amount: Decimal
    currency: str
    status: BookingStatus
    booked_at: datetime | None
    created_at: datetime
