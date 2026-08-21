from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class PermissionView(BaseModel):
    id: str
    code: str
    description: str


class RoleView(BaseModel):
    id: str
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str]
    user_count: int
    created_at: datetime
    updated_at: datetime


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Role name must contain at least two characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("permission_codes")
    @classmethod
    def unique_permission_codes(cls, value: list[str]) -> list[str]:
        normalized = [code.strip() for code in value]
        if any(not code for code in normalized):
            raise ValueError("Permission codes cannot be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Permission codes must be unique")
        return normalized


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Role name must contain at least two characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("permission_codes")
    @classmethod
    def unique_permission_codes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [code.strip() for code in value]
        if any(not code for code in normalized):
            raise ValueError("Permission codes cannot be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Permission codes must be unique")
        return normalized

    @model_validator(mode="after")
    def at_least_one_change(self) -> "RoleUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class UserRoleAssignment(BaseModel):
    role_ids: list[str] = Field(max_length=50)

    @field_validator("role_ids")
    @classmethod
    def unique_role_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Role IDs must be unique")
        return value


class UserRoleView(BaseModel):
    user_id: str
    role_ids: list[str]


class UserAccessView(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    role_ids: list[str]
    role_names: list[str]
