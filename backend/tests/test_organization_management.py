from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import SessionFactory
from app.models.entities import Permission, RolePermission, User

REGISTRATION = {
    "organization_name": "Northstar Realty",
    "organization_slug": "northstar-realty",
    "admin_full_name": "Asha Rao",
    "admin_email": "asha@example.com",
    "password": "Secure-password-42!",
}


async def _register(client: AsyncClient) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post("/api/v1/auth/register-organization", json=REGISTRATION)
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def test_complete_organization_management_workflow(client: AsyncClient) -> None:
    headers, session = await _register(client)

    organization = await client.get("/api/v1/organization", headers=headers)
    assert organization.status_code == 200
    assert organization.json()["legal_name"] is None

    updated_organization = await client.patch(
        "/api/v1/organization",
        headers=headers,
        json={
            "name": "Northstar Realty Group",
            "legal_name": "Northstar Realty Private Limited",
            "contact_email": "ops@northstar.example",
            "contact_phone": "+91 98765 43210",
            "timezone": "Asia/Kolkata",
            "currency": "inr",
            "date_format": "DD/MM/YYYY",
        },
    )
    assert updated_organization.status_code == 200, updated_organization.text
    assert updated_organization.json()["currency"] == "INR"

    empty_branches = await client.get("/api/v1/organization/branches", headers=headers)
    assert empty_branches.json()["items"] == []

    branch = await client.post(
        "/api/v1/organization/branches",
        headers=headers,
        json={"name": "Mumbai Central", "code": "mum-central"},
    )
    second_branch = await client.post(
        "/api/v1/organization/branches",
        headers=headers,
        json={"name": "Pune", "code": "PUNE"},
    )
    assert branch.status_code == second_branch.status_code == 201
    assert branch.json()["code"] == "MUM-CENTRAL"

    branch_search = await client.get(
        "/api/v1/organization/branches?q=mumbai&page=1&page_size=1", headers=headers
    )
    assert branch_search.json()["total"] == 1
    assert branch_search.json()["pages"] == 1

    department = await client.post(
        "/api/v1/organization/departments",
        headers=headers,
        json={"name": "Residential Sales", "branch_id": branch.json()["id"]},
    )
    assert department.status_code == 201, department.text
    assert department.json()["branch_name"] == "Mumbai Central"

    mismatch = await client.post(
        "/api/v1/organization/users",
        headers=headers,
        json={
            "email": "wrong-branch@example.com",
            "full_name": "Wrong Branch",
            "password": "Strong-password-43!",
            "branch_id": second_branch.json()["id"],
            "department_id": department.json()["id"],
        },
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "DEPARTMENT_BRANCH_MISMATCH"

    teammate = await client.post(
        "/api/v1/organization/users",
        headers=headers,
        json={
            "email": "sales@example.com",
            "full_name": "Sales Teammate",
            "password": "Strong-password-43!",
            "branch_id": branch.json()["id"],
            "department_id": department.json()["id"],
        },
    )
    assert teammate.status_code == 201, teammate.text

    invalid_user_update = await client.put(
        f"/api/v1/organization/users/{teammate.json()['id']}",
        headers=headers,
        json={"email": "sales@example.com", "full_name": "  ", "is_active": True},
    )
    assert invalid_user_update.status_code == 422

    filtered_users = await client.get(
        f"/api/v1/organization/users?q=sales&branch_id={branch.json()['id']}&is_active=true",
        headers=headers,
    )
    assert filtered_users.json()["total"] == 1
    assert filtered_users.json()["items"][0]["department_name"] == "Residential Sales"

    team = await client.post(
        "/api/v1/organization/teams",
        headers=headers,
        json={
            "name": "West Sales",
            "code": "west-sales",
            "branch_id": branch.json()["id"],
            "manager_user_id": session["user"]["id"],
            "member_ids": [session["user"]["id"], teammate.json()["id"]],
        },
    )
    assert team.status_code == 201, team.text
    assert team.json()["member_names"] == ["Asha Rao", "Sales Teammate"]

    invalid_team = await client.post(
        "/api/v1/organization/teams",
        headers=headers,
        json={"name": "  ", "code": "BLANK"},
    )
    assert invalid_team.status_code == 422

    parent = await client.post(
        "/api/v1/organization/territories",
        headers=headers,
        json={"name": "West India", "code": "WEST", "manager_user_id": session["user"]["id"]},
    )
    child = await client.post(
        "/api/v1/organization/territories",
        headers=headers,
        json={
            "name": "Mumbai Metro",
            "code": "MUMBAI",
            "branch_id": branch.json()["id"],
            "parent_id": parent.json()["id"],
            "manager_user_id": teammate.json()["id"],
        },
    )
    assert child.status_code == 201, child.text
    assert child.json()["parent_name"] == "West India"

    cycle = await client.put(
        f"/api/v1/organization/territories/{parent.json()['id']}",
        headers=headers,
        json={
            "name": "West India",
            "code": "WEST",
            "parent_id": child.json()["id"],
        },
    )
    assert cycle.status_code == 400
    assert cycle.json()["error"]["code"] == "TERRITORY_CYCLE"

    audit = await client.get(
        "/api/v1/organization/audit-logs?entity_type=team&page_size=10", headers=headers
    )
    assert audit.status_code == 200
    assert audit.json()["items"][0]["action"] == "team.created"


async def test_organization_resources_are_tenant_hidden_and_permissions_enforced(
    client: AsyncClient,
) -> None:
    first_headers, _ = await _register(client)
    branch = await client.post(
        "/api/v1/organization/branches",
        headers=first_headers,
        json={"name": "Private Branch", "code": "PRIVATE"},
    )
    second = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Bluebird Estates",
            "organization_slug": "bluebird-estates",
            "admin_full_name": "Kabir Mehta",
            "admin_email": "kabir@example.com",
            "password": "Another-secure-password-44!",
        },
    )
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    hidden = await client.put(
        f"/api/v1/organization/branches/{branch.json()['id']}",
        headers=second_headers,
        json={"name": "Stolen", "code": "STOLEN", "is_active": True},
    )
    assert hidden.status_code == 404

    async with SessionFactory() as db:
        administrator = (
            await db.scalars(select(User).where(User.email == "kabir@example.com"))
        ).one()
        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.organization_id == administrator.organization_id,
                        Permission.code.in_(
                            [
                                "branches.create",
                                "branches.manage",
                                "teams.assign",
                                "teams.manage",
                            ]
                        ),
                    )
                )
            ).all()
        )
        await db.execute(
            delete(RolePermission).where(
                RolePermission.organization_id == administrator.organization_id,
                RolePermission.permission_id.in_([permission.id for permission in permissions]),
            )
        )
        await db.commit()

    denied = await client.post(
        "/api/v1/organization/branches",
        headers=second_headers,
        json={"name": "Denied", "code": "DENIED"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"

    denied_assignment = await client.post(
        "/api/v1/organization/teams",
        headers=second_headers,
        json={
            "name": "Assignment bypass",
            "code": "NO-ASSIGN",
            "manager_user_id": second.json()["user"]["id"],
        },
    )
    assert denied_assignment.status_code == 403
    assert denied_assignment.json()["error"]["code"] == "PERMISSION_DENIED"
