import jwt

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
        jwt.decode(token, "wrong-secret", algorithms=["HS256"])
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("Expected invalid signature")
