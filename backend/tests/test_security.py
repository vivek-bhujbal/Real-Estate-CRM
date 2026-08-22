import jwt
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.responses import private_file_response
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_not_plaintext() -> None:
    raw = "Secure-password-42!"
    digest = hash_password(raw)
    assert digest != raw
    assert verify_password(raw, digest)
    assert not verify_password("not-the-password", digest)


def test_access_token_has_required_tenant_claims() -> None:
    token, expires_in = create_access_token(
        user_id="user-id",
        organization_id="organization-id",
        session_id="session-id",
        auth_version=3,
    )
    claims = decode_access_token(token)
    assert expires_in > 0
    assert claims["sub"] == "user-id"
    assert claims["org"] == "organization-id"
    assert claims["sid"] == "session-id"
    assert claims["av"] == 3
    assert claims["type"] == "access"
    assert claims["iss"]
    assert claims["aud"]


def test_access_token_rejects_wrong_signature() -> None:
    token, _ = create_access_token(
        user_id="user-id",
        organization_id="organization-id",
        session_id="session-id",
        auth_version=1,
    )
    try:
        jwt.decode(token, "wrong-signing-secret-with-32-characters", algorithms=["HS256"])
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("Expected invalid signature")


def test_known_example_jwt_secrets_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key="replace-with-at-least-32-random-characters")


def test_wildcard_cors_is_rejected_when_credentials_are_enabled() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key="unique-security-test-secret-key-42!", cors_origins=["*"])


def test_blank_optional_smtp_values_remain_valid_in_development() -> None:
    settings = Settings(
        jwt_secret_key="unique-security-test-secret-key-42!",
        smtp_host="",
        smtp_username="",
        smtp_password="",
        smtp_from_email="",
    )
    assert settings.smtp_host is None
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_from_email is None


def test_production_requires_complete_password_reset_delivery() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret_key="unique-production-signing-secret-key-42!",
            password_reset_delivery="smtp",
            public_web_url="https://crm.example.com",
            smtp_host="smtp.example.com",
            smtp_username="mailer",
            smtp_password="",
            smtp_from_email="no-reply@example.com",
        )

    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret_key="unique-production-signing-secret-key-42!",
            password_reset_delivery="smtp",
            public_web_url="https://crm.example.com",
            smtp_host="smtp.example.com",
            smtp_from_email="no-reply@example.com",
            cors_origins=["https://crm.example.com"],
        )

    configured = Settings(
        app_env="production",
        jwt_secret_key="unique-production-signing-secret-key-42!",
        password_reset_delivery="smtp",
        public_web_url="https://crm.example.com",
        smtp_host="smtp.example.com",
        smtp_username="mailer",
        smtp_password="runtime-secret",
        smtp_from_email="no-reply@example.com",
        cors_origins=["https://crm.example.com"],
        malware_scan_mode="clamav",
        clamav_host="scanner.internal",
        metrics_bearer_token="production-metrics-token-with-32-characters",
        storage_backend="s3",
        s3_bucket="estateops-private-documents",
        s3_region="ap-south-1",
    )
    assert configured.secure_cookies is True


def test_private_file_response_forces_non_cacheable_attachment() -> None:
    response = private_file_response(
        __file__, filename="security.txt", media_type="text/plain"
    )
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"


@pytest.mark.asyncio
async def test_untrusted_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "bad request id"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad request id"
    assert " " not in response.headers["X-Request-ID"]
