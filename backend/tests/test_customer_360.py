from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import SessionFactory
from app.models.entities import AuditLog, Permission, RolePermission, User


async def _register(
    client: AsyncClient,
    *,
    slug: str = "customer-workspace",
    email: str = "customer-admin@example.com",
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Workspace {slug}",
            "organization_slug": slug,
            "admin_full_name": "Customer Administrator",
            "admin_email": email,
            "password": "Secure-customer-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def test_customer_crud_activity_timeline_and_audit(client: AsyncClient) -> None:
    headers, session = await _register(client)
    empty = await client.get("/api/v1/customers", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    created = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "full_name": "Anaya Mehta",
            "email": "anaya@example.com",
            "phone": "+91 98765 43000",
            "preferred_location": "Pune",
            "requirements": "Three bedroom home with possession this year",
            "budget_min": "10000000",
            "budget_max": "15000000",
            "owner_user_id": session["user"]["id"],
            "communication_preferences": {"email": True, "sms": False},
        },
    )
    assert created.status_code == 201, created.text
    customer_id = created.json()["id"]
    assert created.json()["owner_name"] == "Customer Administrator"

    duplicate = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Anaya M", "email": "ANAYA@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_CUSTOMER"

    activity = await client.post(
        f"/api/v1/customers/{customer_id}/activities",
        headers=headers,
        json={
            "activity_type": "CALL",
            "subject": "Discussed shortlisted units",
            "notes": "Customer requested a weekend visit",
            "channel": "PHONE",
            "direction": "OUTBOUND",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert activity.status_code == 201, activity.text

    updated = await client.patch(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
        json={"status": "ACTIVE", "city": "Pune"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "ACTIVE"

    profile = await client.get(f"/api/v1/customers/{customer_id}/360", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["customer"]["requirements"].startswith("Three bedroom")
    assert profile.json()["activities"][0]["subject"] == "Discussed shortlisted units"
    assert "payments" in profile.json()["available_sections"]
    assert profile.json()["financial_summary"]["outstanding_amount"] == "0"
    assert {item["kind"] for item in profile.json()["timeline"]} >= {"customer", "activity"}

    filtered = await client.get("/api/v1/customers?q=anaya&status=ACTIVE", headers=headers)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1

    async with SessionFactory() as db:
        actions = set(
            (
                await db.scalars(
                    select(AuditLog.action).where(
                        AuditLog.entity_id.in_([customer_id, activity.json()["id"]])
                    )
                )
            ).all()
        )
    assert actions >= {"customer.created", "customer.updated", "customer.activity.created"}


async def test_customer_tenant_isolation_and_backend_permissions(client: AsyncClient) -> None:
    first_headers, _ = await _register(
        client, slug="customer-one", email="customer-one@example.com"
    )
    created = await client.post(
        "/api/v1/customers",
        headers=first_headers,
        json={"full_name": "Hidden Customer", "phone": "+91 90000 00111"},
    )
    assert created.status_code == 201

    second_headers, _ = await _register(
        client, slug="customer-two", email="customer-two@example.com"
    )
    hidden = await client.get(
        f"/api/v1/customers/{created.json()['id']}/360", headers=second_headers
    )
    assert hidden.status_code == 404

    async with SessionFactory() as db:
        administrator = (
            await db.scalars(select(User).where(User.email == "customer-one@example.com"))
        ).one()
        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.organization_id == administrator.organization_id,
                        Permission.code.in_(
                            [
                                "customers.create",
                                "customers.manage",
                                "payments.view",
                                "payments.manage",
                                "collections.view",
                                "collections.manage",
                            ]
                        ),
                    )
                )
            ).all()
        )
        await db.execute(
            delete(RolePermission).where(
                RolePermission.organization_id == administrator.organization_id,
                RolePermission.permission_id.in_([item.id for item in permissions]),
            )
        )
        await db.commit()

    restricted_profile = await client.get(
        f"/api/v1/customers/{created.json()['id']}/360", headers=first_headers
    )
    assert restricted_profile.status_code == 200
    assert "payments" not in restricted_profile.json()["available_sections"]
    assert restricted_profile.json()["financial_summary"] is None

    denied = await client.post(
        "/api/v1/customers",
        headers=first_headers,
        json={"full_name": "Denied Customer", "email": "denied-customer@example.com"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
