from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.api.v1 import auth as auth_routes
from app.db.session import SessionFactory
from app.models.entities import User

REGISTRATION = {
    "organization_name": "Northstar Realty",
    "organization_slug": "northstar-realty",
    "admin_full_name": "Asha Rao",
    "admin_email": "asha@example.com",
    "password": "Secure-password-42!",
}


async def test_database_starts_without_users() -> None:
    async with SessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0


async def test_organization_onboarding_and_empty_dashboard(client: AsyncClient) -> None:
    registered = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["user"]["organization"]["slug"] == "northstar-realty"
    assert "dashboard.view" in body["user"]["permissions"]
    assert "refresh_token" not in body
    assert client.cookies.get("refresh_token")

    dashboard = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json() == {
        "leads": 0,
        "projects": 0,
        "available_units": 0,
        "bookings": 0,
    }


async def test_login_failure_is_non_enumerating(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "does-not-exist",
            "email": "nobody@example.com",
            "password": "wrong",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_refresh_rotates_cookie(client: AsyncClient) -> None:
    registered = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    first_cookie = client.cookies.get("refresh_token")
    refreshed = await client.post("/api/v1/auth/refresh")
    second_cookie = client.cookies.get("refresh_token")
    assert registered.status_code == 201
    assert refreshed.status_code == 200, refreshed.text
    assert first_cookie != second_cookie
    assert refreshed.json()["access_token"]


async def test_cookie_authenticated_routes_reject_untrusted_origins(client: AsyncClient) -> None:
    registered = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    rejected = await client.post(
        "/api/v1/auth/refresh", headers={"Origin": "https://attacker.example"}
    )
    assert registered.status_code == 201
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"

    fetch_metadata_rejected = await client.post(
        "/api/v1/auth/refresh", headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert fetch_metadata_rejected.status_code == 403
    assert fetch_metadata_rejected.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


async def test_duplicate_organization_is_rejected(client: AsyncClient) -> None:
    assert (
        await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    ).status_code == 201
    duplicate = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    assert duplicate.status_code == 409


async def test_current_user_and_logout_revoke_access_session(client: AsyncClient) -> None:
    registered = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    access_token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    current = await client.get("/api/v1/auth/me", headers=headers)
    assert current.status_code == 200
    assert current.json()["email"] == REGISTRATION["admin_email"]

    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204
    assert client.cookies.get("refresh_token") is None

    revoked = await client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "SESSION_REVOKED"


async def test_password_change_requires_current_password_and_revokes_sessions(
    client: AsyncClient,
) -> None:
    registered = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    access_token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    wrong = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "wrong", "new_password": "New-secure-password-43!"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "CURRENT_PASSWORD_INVALID"

    changed = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": REGISTRATION["password"],
            "new_password": "New-secure-password-43!",
        },
    )
    assert changed.status_code == 204

    revoked = await client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "SESSION_REVOKED"

    old_login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": REGISTRATION["organization_slug"],
            "email": REGISTRATION["admin_email"],
            "password": REGISTRATION["password"],
        },
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": REGISTRATION["organization_slug"],
            "email": REGISTRATION["admin_email"],
            "password": "New-secure-password-43!",
        },
    )
    assert new_login.status_code == 200


async def test_forgot_and_reset_password_are_non_enumerating_and_one_time(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    old_access_token = registered.json()["access_token"]
    captured: dict[str, str] = {}

    async def capture_reset_email(**values: Any) -> bool:
        captured.update({key: str(value) for key, value in values.items()})
        return True

    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture_reset_email)
    existing = await client.post(
        "/api/v1/auth/forgot-password",
        json={
            "organization_slug": REGISTRATION["organization_slug"],
            "email": REGISTRATION["admin_email"],
        },
    )
    missing = await client.post(
        "/api/v1/auth/forgot-password",
        json={"organization_slug": "missing-org", "email": "missing@example.com"},
    )
    assert existing.status_code == missing.status_code == 202
    assert existing.json() == missing.json()
    assert "token" not in existing.json()
    assert captured["recipient"] == REGISTRATION["admin_email"]

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured["token"], "new_password": "Reset-secure-password-44!"},
    )
    assert reset.status_code == 200

    reused = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured["token"], "new_password": "Another-secure-password-45!"},
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "INVALID_RESET_TOKEN"

    revoked = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access_token}"}
    )
    assert revoked.status_code == 401

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": REGISTRATION["organization_slug"],
            "email": REGISTRATION["admin_email"],
            "password": "Reset-secure-password-44!",
        },
    )
    assert login.status_code == 200
