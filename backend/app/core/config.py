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
    # Deliberately required: starting with a known signing key would let anyone
    # forge access tokens in an otherwise correctly configured deployment.
    jwt_secret_key: str = Field(min_length=32)
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
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: Path = Path("uploads")
    storage_temp_path: Path = Path("/tmp/estateops-object-cache")
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_server_side_encryption: Literal["AES256", "aws:kms"] = "AES256"
    s3_kms_key_id: str | None = None
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    malware_scan_mode: Literal["disabled", "clamav"] = "disabled"
    clamav_host: str | None = None
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: int = Field(default=30, ge=5, le=120)
    metrics_enabled: bool = True
    metrics_bearer_token: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "smtp_from_email",
        "clamav_host",
        "metrics_bearer_token",
        "s3_bucket",
        "s3_region",
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_kms_key_id",
        mode="before",
    )
    @classmethod
    def blank_optional_settings_are_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.refresh_token_idle_days > self.refresh_token_ttl_days:
            raise ValueError("REFRESH_TOKEN_IDLE_DAYS cannot exceed REFRESH_TOKEN_TTL_DAYS")
        normalized_secret = self.jwt_secret_key.strip().lower()
        weak_secret_markers = ("development-secret", "replace-with", "change-me")
        if any(marker in normalized_secret for marker in weak_secret_markers):
            raise ValueError("JWT_SECRET_KEY must not use an example or default value")
        if any(origin.strip() == "*" for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must list explicit trusted origins")
        if self.app_env in {"staging", "production"}:
            if self.password_reset_delivery != "smtp":
                raise ValueError("PASSWORD_RESET_DELIVERY must be smtp outside development/test")
            if self.smtp_host is None or self.smtp_from_email is None:
                raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required for password reset")
            if not self.public_web_url.startswith("https://"):
                raise ValueError("PUBLIC_WEB_URL must use HTTPS outside development/test")
            if self.smtp_username and (
                self.smtp_password is None or not self.smtp_password.get_secret_value()
            ):
                raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is configured")
            if self.malware_scan_mode != "clamav" or self.clamav_host is None:
                raise ValueError(
                    "MALWARE_SCAN_MODE=clamav and CLAMAV_HOST are required outside development/test"
                )
            if self.metrics_enabled and (
                self.metrics_bearer_token is None
                or len(self.metrics_bearer_token.get_secret_value()) < 32
            ):
                raise ValueError(
                    "METRICS_BEARER_TOKEN with at least 32 characters is required "
                    "when metrics are enabled"
                )
            if self.storage_backend != "s3" or not self.s3_bucket or not self.s3_region:
                raise ValueError(
                    "STORAGE_BACKEND=s3, S3_BUCKET and S3_REGION are required outside "
                    "development/test"
                )
        if self.s3_access_key_id and self.s3_secret_access_key is None:
            raise ValueError("S3_SECRET_ACCESS_KEY is required when S3_ACCESS_KEY_ID is set")
        if self.s3_server_side_encryption == "aws:kms" and not self.s3_kms_key_id:
            raise ValueError("S3_KMS_KEY_ID is required for aws:kms server-side encryption")
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
