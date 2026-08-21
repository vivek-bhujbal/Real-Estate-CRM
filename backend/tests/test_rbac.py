from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.core.authorization import (
    PERMISSION_ACTIONS,
    PERMISSION_CATALOG,
    PERMISSION_MODULES,
    ROLE_TEMPLATES,
)
from app.core.security import hash_password
from app.db.session import SessionFactory
from app.models.entities import AuditLog, Permission, RolePermission, User, UserRole

REGISTRATION = {
    "organization_name": "Northstar Realty",
    "organization_slug": "northstar-realty",
    "admin_full_name": "Asha Rao",
    "admin_email": "asha@example.com",
    "password": "Secure-password-42!",
}


async def _register(client: AsyncClient, payload: dict[str, str] | None = None) -> dict[str, str]:
    response = await client.post("/api/v1/auth/register-organization", json=payload or REGISTRATION)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_role_crud_uses_tenant_permission_catalog_and_audits(
    client: AsyncClient,
) -> None:
    headers = await _register(client)

    permissions = await client.get("/api/v1/rbac/permissions", headers=headers)
    assert permissions.status_code == 200, permissions.text
    assert [permission["code"] for permission in permissions.json()] == sorted(PERMISSION_CATALOG)
    assert len(permissions.json()) == len(PERMISSION_MODULES) * len(PERMISSION_ACTIONS)

    provisioned_roles = await client.get("/api/v1/rbac/roles", headers=headers)
    assert len(provisioned_roles.json()) == 15
    assert all(role["is_system"] for role in provisioned_roles.json())

    provisioned_users = await client.get("/api/v1/rbac/users", headers=headers)
    assert len(provisioned_users.json()) == 1
    assert provisioned_users.json()[0]["role_names"] == ["Organization Administrator"]

    created = await client.post(
        "/api/v1/rbac/roles",
        headers=headers,
        json={
            "name": "Sales Viewer",
            "description": "Read-only sales operations access",
            "permission_codes": ["dashboard.view", "users.view"],
        },
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["is_system"] is False
    assert role["permission_codes"] == ["dashboard.view", "users.view"]
    assert role["user_count"] == 0

    updated = await client.patch(
        f"/api/v1/rbac/roles/{role['id']}",
        headers=headers,
        json={"name": "Sales Coordinator", "permission_codes": ["dashboard.view"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Sales Coordinator"
    assert updated.json()["permission_codes"] == ["dashboard.view"]

    listed = await client.get("/api/v1/rbac/roles", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == len(ROLE_TEMPLATES) + 1
    assert {item["name"] for item in listed.json()} == {
        *(template.name for template in ROLE_TEMPLATES),
        "Sales Coordinator",
    }

    deleted = await client.delete(f"/api/v1/rbac/roles/{role['id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    async with SessionFactory() as db:
        actions = list(
            (
                await db.scalars(
                    select(AuditLog.action)
                    .where(AuditLog.entity_id == role["id"])
                    .order_by(AuditLog.created_at)
                )
            ).all()
        )
    assert actions == ["role.created", "role.updated", "role.deleted"]


async def test_system_role_is_immutable_and_invalid_permissions_are_rejected(
    client: AsyncClient,
) -> None:
    headers = await _register(client)
    roles = (await client.get("/api/v1/rbac/roles", headers=headers)).json()
    system_role = next(role for role in roles if role["name"] == "Organization Administrator")

    changed = await client.patch(
        f"/api/v1/rbac/roles/{system_role['id']}",
        headers=headers,
        json={"name": "Owner"},
    )
    removed = await client.delete(f"/api/v1/rbac/roles/{system_role['id']}", headers=headers)
    invalid = await client.post(
        "/api/v1/rbac/roles",
        headers=headers,
        json={"name": "Invalid Role", "permission_codes": ["unknown.manage"]},
    )

    assert changed.status_code == removed.status_code == 409
    assert changed.json()["error"]["code"] == "SYSTEM_ROLE_IMMUTABLE"
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_PERMISSION_CODES"

    sales_head = next(role for role in roles if role["name"] == "Sales Head")
    configured = await client.patch(
        f"/api/v1/rbac/roles/{sales_head['id']}",
        headers=headers,
        json={"permission_codes": ["dashboard.view", "leads.manage"]},
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["name"] == "Sales Head"
    assert configured.json()["permission_codes"] == ["dashboard.view", "leads.manage"]


async def test_role_resources_from_another_tenant_are_hidden(client: AsyncClient) -> None:
    first_headers = await _register(client)
    second_headers = await _register(
        client,
        {
            "organization_name": "Bluebird Estates",
            "organization_slug": "bluebird-estates",
            "admin_full_name": "Kabir Mehta",
            "admin_email": "kabir@example.com",
            "password": "Another-secure-password-43!",
        },
    )
    second_roles = (await client.get("/api/v1/rbac/roles", headers=second_headers)).json()

    hidden = await client.get(f"/api/v1/rbac/roles/{second_roles[0]['id']}", headers=first_headers)
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_role_assignment_invalidates_target_users_access_version(
    client: AsyncClient,
) -> None:
    headers = await _register(client)
    created_role = await client.post(
        "/api/v1/rbac/roles",
        headers=headers,
        json={"name": "Custom Auditor", "permission_codes": ["audit.view"]},
    )
    role_id = created_role.json()["id"]

    async with SessionFactory() as db:
        administrator = (await db.scalars(select(User))).first()
        assert administrator is not None
        administrator_id = administrator.id
        teammate = User(
            organization_id=administrator.organization_id,
            email="auditor@example.com",
            full_name="Dev Auditor",
            password_hash=hash_password("Auditor-password-44!"),
        )
        db.add(teammate)
        await db.commit()
        teammate_id = teammate.id

    assigned = await client.put(
        f"/api/v1/rbac/users/{teammate_id}/roles",
        headers=headers,
        json={"role_ids": [role_id]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json() == {"user_id": teammate_id, "role_ids": [role_id]}

    self_change = await client.put(
        f"/api/v1/rbac/users/{administrator_id}/roles",
        headers=headers,
        json={"role_ids": []},
    )
    assert self_change.status_code == 409
    assert self_change.json()["error"]["code"] == "SELF_ROLE_CHANGE_NOT_ALLOWED"

    users = await client.get("/api/v1/rbac/users", headers=headers)
    teammate_access = next(user for user in users.json() if user["id"] == teammate_id)
    assert teammate_access["role_names"] == ["Custom Auditor"]

    in_use = await client.delete(f"/api/v1/rbac/roles/{role_id}", headers=headers)
    assert in_use.status_code == 409
    assert in_use.json()["error"]["code"] == "ROLE_IN_USE"

    async with SessionFactory() as db:
        teammate = await db.get(User, teammate_id)
        assert teammate is not None
        assert teammate.auth_version == 2
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UserRole)
                .where(UserRole.user_id == teammate_id, UserRole.role_id == role_id)
            )
        ) == 1


async def test_roles_manage_permission_is_enforced(client: AsyncClient) -> None:
    headers = await _register(client)
    async with SessionFactory() as db:
        admin = (await db.scalars(select(User))).first()
        assert admin is not None
        manage_permission = (
            await db.scalars(
                select(Permission).where(
                    Permission.organization_id == admin.organization_id,
                    Permission.code.in_(["roles.create", "roles.manage"]),
                )
            )
        ).all()
        await db.execute(
            delete(RolePermission).where(
                RolePermission.organization_id == admin.organization_id,
                RolePermission.permission_id.in_(
                    [permission.id for permission in manage_permission]
                ),
            )
        )
        await db.commit()

    denied = await client.post(
        "/api/v1/rbac/roles",
        headers=headers,
        json={"name": "Should Not Exist", "permission_codes": []},
    )
    readable = await client.get("/api/v1/rbac/roles", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
    assert readable.status_code == 200


async def test_delegated_role_manager_cannot_escalate_permissions(client: AsyncClient) -> None:
    administrator_headers = await _register(client)
    delegated = await client.post(
        "/api/v1/rbac/roles",
        headers=administrator_headers,
        json={
            "name": "Delegated Role Manager",
            "permission_codes": [
                "roles.view",
                "roles.create",
                "roles.assign",
                "users.view",
                "users.assign",
                "leads.view",
            ],
        },
    )
    assert delegated.status_code == 201, delegated.text

    async with SessionFactory() as db:
        administrator = (await db.scalars(select(User))).one()
        operator = User(
            organization_id=administrator.organization_id,
            email="role-manager@example.com",
            full_name="Role Manager",
            password_hash=hash_password("Manager-password-45!"),
        )
        target = User(
            organization_id=administrator.organization_id,
            email="target@example.com",
            full_name="Target User",
            password_hash=hash_password("Target-password-46!"),
        )
        db.add_all([operator, target])
        await db.commit()
        operator_id = operator.id
        target_id = target.id

    assigned = await client.put(
        f"/api/v1/rbac/users/{operator_id}/roles",
        headers=administrator_headers,
        json={"role_ids": [delegated.json()["id"]]},
    )
    assert assigned.status_code == 200, assigned.text

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": REGISTRATION["organization_slug"],
            "email": "role-manager@example.com",
            "password": "Manager-password-45!",
        },
    )
    operator_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    escalated_role = await client.post(
        "/api/v1/rbac/roles",
        headers=operator_headers,
        json={"name": "Escalated", "permission_codes": ["payments.manage"]},
    )
    administrator_role = next(
        role
        for role in (await client.get("/api/v1/rbac/roles", headers=operator_headers)).json()
        if role["name"] == "Organization Administrator"
    )
    escalated_assignment = await client.put(
        f"/api/v1/rbac/users/{target_id}/roles",
        headers=operator_headers,
        json={"role_ids": [administrator_role["id"]]},
    )

    assert escalated_role.status_code == 403
    assert escalated_role.json()["error"]["code"] == "PERMISSION_GRANT_NOT_ALLOWED"
    assert escalated_assignment.status_code == 403
    assert escalated_assignment.json()["error"]["code"] == "PERMISSION_GRANT_NOT_ALLOWED"
