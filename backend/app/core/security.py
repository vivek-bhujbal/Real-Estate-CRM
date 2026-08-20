import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$r2Rm509OqiyqSH2+obPY/Q$"
    "kzgvc5sHFFMbJBo+Yivy1UgnFyhSiCudXxQaWeXSYCA"
)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, password_digest: str) -> bool:
    return password_hash.verify(password, password_digest)


def verify_and_update_password(password: str, password_digest: str) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(password, password_digest)


def create_access_token(
    *, user_id: str, organization_id: str, session_id: str, auth_version: int
) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    claims: dict[str, Any] = {
        "sub": user_id,
        "org": organization_id,
        "sid": session_id,
        "av": auth_version,
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": expires,
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, settings.access_token_ttl_minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        leeway=settings.jwt_leeway_seconds,
        options={
            "require": [
                "sub",
                "org",
                "sid",
                "av",
                "type",
                "iss",
                "aud",
                "exp",
                "iat",
                "nbf",
                "jti",
            ]
        },
    )


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(64)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_password_reset_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)
