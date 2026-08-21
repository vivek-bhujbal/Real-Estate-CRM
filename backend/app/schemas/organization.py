import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.auth import validate_password_strength


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int


class OrganizationManagementView(BaseModel):
    id: str
    name: str
    slug: str
    legal_name: str | None
    contact_email: str | None
    contact_phone: str | None
    timezone: str | None
    currency: str | None
    date_format: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    legal_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=30)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    date_format: str | None = Field(default=None, max_length=24)

    @field_validator("name", "legal_name")
    @classmethod
    def clean_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("contact_email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if not re.fullmatch(r"[+0-9() .-]{7,30}", cleaned):
            raise ValueError("Enter a valid contact phone number")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        try:
            ZoneInfo(cleaned)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Enter a valid IANA timezone") from exc
        return cleaned

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().upper()
        if not cleaned.isalpha() or len(cleaned) != 3:
            raise ValueError("Currency must be a three-letter ISO code")
        return cleaned

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().upper()
        if cleaned not in {"DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"}:
            raise ValueError("Choose a supported date format")
        return cleaned

    @model_validator(mode="after")
    def at_least_one_field(self) -> "OrganizationUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Organization name cannot be empty")
        return self


class ActiveFilter(BaseModel):
    is_active: bool | None = None


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class BranchUpdate(BranchCreate):
    pass


class BranchView(BranchCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    department_count: int = 0
    user_count: int = 0


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    branch_id: str | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned


class DepartmentUpdate(DepartmentCreate):
    pass


class DepartmentView(DepartmentCreate):
    id: str
    branch_name: str | None = None
    user_count: int = 0
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    branch_id: str | None = None
    department_id: str | None = None
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UserUpdate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    branch_id: str | None = None
    department_id: str | None = None
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned


class UserManagementView(BaseModel):
    id: str
    email: str
    full_name: str
    branch_id: str | None
    branch_name: str | None = None
    department_id: str | None
    department_name: str | None = None
    is_active: bool
    role_names: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    description: str | None = Field(default=None, max_length=500)
    branch_id: str | None = None
    manager_user_id: str | None = None
    member_ids: list[str] = Field(default_factory=list, max_length=500)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("member_ids")
    @classmethod
    def unique_members(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Team members must be unique")
        return value


class TeamUpdate(TeamCreate):
    pass


class TeamView(TeamCreate):
    id: str
    branch_name: str | None = None
    manager_name: str | None = None
    member_names: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TerritoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    description: str | None = Field(default=None, max_length=500)
    branch_id: str | None = None
    parent_id: str | None = None
    manager_user_id: str | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class TerritoryUpdate(TerritoryCreate):
    pass


class TerritoryView(TerritoryCreate):
    id: str
    branch_name: str | None = None
    parent_name: str | None = None
    manager_name: str | None = None
    created_at: datetime
    updated_at: datetime


class AuditLogView(BaseModel):
    id: str
    actor_user_id: str | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: str
    previous_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    request_id: str | None
    ip_address: str | None
    created_at: datetime
