from httpx import AsyncClient


async def _create_portal_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    role_name: str,
    email: str,
) -> tuple[dict[str, str], dict[str, object]]:
    roles_response = await client.get("/api/v1/rbac/roles", headers=admin_headers)
    assert roles_response.status_code == 200, roles_response.text
    role_id = next(row["id"] for row in roles_response.json() if row["name"] == role_name)
    password = "Portal-security-password-42!"
    created = await client.post(
        "/api/v1/organization/users",
        headers=admin_headers,
        json={
            "full_name": role_name,
            "email": email,
            "password": password,
            "role_ids": [role_id],
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    assigned = await client.put(
        f"/api/v1/rbac/users/{created.json()['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [role_id]},
    )
    assert assigned.status_code == 200, assigned.text
    logged_in = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "portal-security",
            "email": email,
            "password": password,
        },
    )
    assert logged_in.status_code == 200, logged_in.text
    body = logged_in.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def test_unbound_portal_roles_cannot_read_organization_wide_records(
    client: AsyncClient,
) -> None:
    registration = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Portal Security",
            "organization_slug": "portal-security",
            "admin_full_name": "Portal Security Admin",
            "admin_email": "portal-security-admin@example.com",
            "password": "Portal-security-admin-password-42!",
        },
    )
    assert registration.status_code == 201, registration.text
    admin_headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

    buyer, buyer_session = await _create_portal_user(
        client,
        admin_headers,
        role_name="Customer / Buyer",
        email="buyer-security@example.com",
    )
    assert "service_requests.view" in buyer_session["user"]["permissions"]
    assert "bookings.view" not in buyer_session["user"]["permissions"]
    assert "documents.view" not in buyer_session["user"]["permissions"]
    assert (await client.get("/api/v1/bookings", headers=buyer)).status_code == 403
    assert (await client.get("/api/v1/documents", headers=buyer)).status_code == 403

    tenant, tenant_session = await _create_portal_user(
        client,
        admin_headers,
        role_name="Tenant",
        email="tenant-security@example.com",
    )
    assert "leases.view" in tenant_session["user"]["permissions"]
    assert "documents.view" not in tenant_session["user"]["permissions"]
    assert "payments.create" in tenant_session["user"]["permissions"]
    assert (await client.get("/api/v1/documents", headers=tenant)).status_code == 403
    assert (
        await client.post(
            "/api/v1/bookings/not-a-booking/payments",
            headers=tenant,
            json={},
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/collections/bookings/not-a-booking/payments",
            headers=tenant,
            json={},
        )
    ).status_code == 403

    broker, broker_session = await _create_portal_user(
        client,
        admin_headers,
        role_name="Broker / Channel Partner",
        email="broker-security@example.com",
    )
    assert "leads.create" in broker_session["user"]["permissions"]
    assert "leads.view" not in broker_session["user"]["permissions"]
    assert "partners.view" not in broker_session["user"]["permissions"]
    assert (await client.get("/api/v1/leads", headers=broker)).status_code == 403
    assert (await client.get("/api/v1/partners", headers=broker)).status_code == 403
