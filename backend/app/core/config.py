from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Real Estate CRM API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "mysql+asyncmy://crm_app:password@localhost:3306/realestate_crm"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "development-secret-change-before-deployment"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "realestate-crm-api"
    jwt_audience: str = "realestate-crm-web"
    jwt_leeway_seconds: int = Field(default=5, ge=0, le=60)
    access_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    refresh_token_idle_days: int = Field(default=7, ge=1, le=30)
    password_reset_ttl_minutes: int = Field(default=30, ge=10, le=120)
    public_web_url: str = "http://localhost:3000"
    password_reset_delivery: Literal["disabled", "smtp"] = "disabled"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: EmailStr | None = None
    smtp_starttls: bool = True
    allow_organization_registration: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]
    storage_backend: Literal["local"] = "local"
    storage_local_path: Path = Path("uploads")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.refresh_token_idle_days > self.refresh_token_ttl_days:
            raise ValueError("REFRESH_TOKEN_IDLE_DAYS cannot exceed REFRESH_TOKEN_TTL_DAYS")
        if self.app_env in {"staging", "production"}:
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key.startswith("development-"):
                raise ValueError("JWT_SECRET_KEY must be a strong, non-default secret")
            if self.password_reset_delivery != "smtp":
                raise ValueError("PASSWORD_RESET_DELIVERY must be smtp outside development/test")
            if self.smtp_host is None or self.smtp_from_email is None:
                raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required for password reset")
            if not self.public_web_url.startswith("https://"):
                raise ValueError("PUBLIC_WEB_URL must use HTTPS outside development/test")
            if self.smtp_username and self.smtp_password is None:
                raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is configured")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.app_env in {"development", "test"}

    @property
    def secure_cookies(self) -> bool:
        return self.app_env in {"staging", "production"}

    @property
    def refresh_cookie_name(self) -> str:
        return "__Secure-refresh_token" if self.secure_cookies else "refresh_token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
