import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def validate_password_strength(value: str) -> str:
    classes = [r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"]
    if not all(re.search(pattern, value) for pattern in classes):
        raise ValueError("Password must include upper, lower, number, and symbol characters")
    return value


class OrganizationRegistration(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    organization_slug: str = Field(
        min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    admin_full_name: str = Field(min_length=2, max_length=160)
    admin_email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("organization_name", "admin_full_name")
    @classmethod
    def clean_display_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("organization_slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("admin_email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginRequest(BaseModel):
    organization_slug: str = Field(min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("organization_slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class OrganizationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str
    organization_id: str
    branch_id: str | None
    department_id: str | None
    is_active: bool
    created_at: datetime


class CurrentUserView(UserView):
    organization: OrganizationView
    permissions: list[str]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUserView


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)


class ForgotPasswordRequest(BaseModel):
    organization_slug: str = Field(min_length=3, max_length=80)
    email: EmailStr

    @field_validator("organization_slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)


class MessageResponse(BaseModel):
    message: str
