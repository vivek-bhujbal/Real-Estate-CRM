import csv
from io import StringIO

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models.entities import AuditLog

REGISTRATION = {
    "organization_name": "Northstar Realty",
    "organization_slug": "northstar-realty",
    "admin_full_name": "Asha Rao",
    "admin_email": "asha@example.com",
    "password": "Secure-password-42!",
}


async def _register(client: AsyncClient) -> dict[str, str]:
    async with SessionFactory() as db:
        assert (await db.scalar(select(func.count()).select_from(AuditLog))) == 0
    response = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_audit_records_capture_changes_actor_tenant_and_device_context(
    client: AsyncClient,
) -> None:
    headers = await _register(client)
    mutation_headers = {
        **headers,
        "User-Agent": "EstateOps-Audit-Test/1.0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-CH-UA-Mobile": "?0",
    }
    created = await client.post(
        "/api/v1/organization/users",
        headers=mutation_headers,
        json={
            "email": "auditor@example.com",
            "full_name": "Initial Auditor",
            "password": "Strong-auditor-password-45!",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/organization/users/{user_id}",
        headers=mutation_headers,
        json={
            "email": "auditor@example.com",
            "full_name": "Compliance Auditor",
            "is_active": True,
        },
    )
    assert updated.status_code == 200, updated.text

    audit = await client.get(
        f"/api/v1/organization/audit-logs?action=user.updated&entity_id={user_id}",
        headers=headers,
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["total"] == 1
    record = audit.json()["items"][0]
    assert record["organization_id"]
    assert record["organization_name"] == REGISTRATION["organization_name"]
    assert record["actor_name"] == REGISTRATION["admin_full_name"]
    assert record["old_value"]["full_name"] == "Initial Auditor"
    assert record["new_value"]["full_name"] == "Compliance Auditor"
    assert record["ip_address"].startswith("test-client-")
    assert record["user_agent"] == "EstateOps-Audit-Test/1.0"
    assert record["device_metadata"] == {"platform": '"Windows"', "mobile": "?0"}
    assert record["request_id"]

    options = await client.get("/api/v1/organization/audit-logs/options", headers=headers)
    assert options.status_code == 200
    assert "user.created" in options.json()["actions"]
    assert "user" in options.json()["entity_types"]
    assert REGISTRATION["admin_full_name"] in {
        actor["name"] for actor in options.json()["actors"]
    }

    exported = await client.get(
        f"/api/v1/organization/audit-logs/export?action=user.updated&entity_id={user_id}",
        headers=headers,
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["cache-control"] == "no-store"
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert len(rows) == 1
    assert rows[0]["action"] == "user.updated"
    assert rows[0]["entity_id"] == user_id


async def test_auditor_role_is_strictly_read_only_and_can_export(client: AsyncClient) -> None:
    administrator_headers = await _register(client)
    created = await client.post(
        "/api/v1/organization/users",
        headers=administrator_headers,
        json={
            "email": "readonly@example.com",
            "full_name": "Read Only Auditor",
            "password": "Auditor-secure-password-46!",
        },
    )
    roles = (await client.get("/api/v1/rbac/roles", headers=administrator_headers)).json()
    auditor_role = next(role for role in roles if role["name"] == "Auditor / Compliance User")
    assigned = await client.put(
        f"/api/v1/rbac/users/{created.json()['id']}/roles",
        headers=administrator_headers,
        json={"role_ids": [auditor_role["id"]]},
    )
    assert assigned.status_code == 200, assigned.text

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": REGISTRATION["organization_slug"],
            "email": "readonly@example.com",
            "password": "Auditor-secure-password-46!",
        },
    )
    assert login.status_code == 200, login.text
    auditor_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    permissions = login.json()["user"]["permissions"]
    assert permissions
    assert all(code.endswith((".view", ".export")) for code in permissions)
    assert "audit.manage" not in permissions

    readable = await client.get("/api/v1/organization/audit-logs", headers=auditor_headers)
    exportable = await client.get(
        "/api/v1/organization/audit-logs/export", headers=auditor_headers
    )
    forbidden_update = await client.patch(
        "/api/v1/organization",
        headers=auditor_headers,
        json={"name": "Unauthorized change"},
    )
    forbidden_role = await client.post(
        "/api/v1/rbac/roles",
        headers=auditor_headers,
        json={"name": "Unauthorized role", "permission_codes": []},
    )
    assert readable.status_code == exportable.status_code == 200
    assert forbidden_update.status_code == forbidden_role.status_code == 403


async def test_audit_model_rejects_record_mutation(client: AsyncClient) -> None:
    await _register(client)
    async with SessionFactory() as db:
        record = (await db.scalars(select(AuditLog))).first()
        assert record is not None
        record.action = "tampered"
        with pytest.raises(ValueError, match="append-only"):
            await db.flush()
        await db.rollback()
