from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import SessionFactory
from app.models.entities import Permission, RolePermission, User


async def _register(
    client: AsyncClient,
    *,
    slug: str = "lead-workspace",
    email: str = "lead-admin@example.com",
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Workspace {slug}",
            "organization_slug": slug,
            "admin_full_name": "Lead Administrator",
            "admin_email": email,
            "password": "Secure-lead-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def test_complete_lead_lifecycle_and_supporting_workflows(client: AsyncClient) -> None:
    headers, session = await _register(client)
    assert (await client.get("/api/v1/leads", headers=headers)).json()["items"] == []
    assert (await client.get("/api/v1/leads/sources", headers=headers)).json() == []

    source = await client.post(
        "/api/v1/leads/sources",
        headers=headers,
        json={"name": "Website enquiry", "code": "website"},
    )
    reason = await client.post(
        "/api/v1/leads/lost-reasons",
        headers=headers,
        json={"name": "Budget mismatch", "code": "budget"},
    )
    rule = await client.post(
        "/api/v1/leads/score-rules",
        headers=headers,
        json={
            "name": "High budget",
            "field": "budget_max",
            "operator": "gte",
            "comparison_value": "10000000",
            "points": 20,
        },
    )
    assert source.status_code == reason.status_code == rule.status_code == 201

    lead = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "full_name": "Riya Sharma",
            "email": "riya@example.com",
            "phone": "+91 98765 41000",
            "source_id": source.json()["id"],
            "owner_user_id": session["user"]["id"],
            "preferred_location": "Mumbai",
            "budget_min": "8000000",
            "budget_max": "12000000",
            "requirements": "Two bedroom apartment",
        },
    )
    assert lead.status_code == 201, lead.text
    assert lead.json()["status"] == "ASSIGNED"
    assert lead.json()["score"] >= 50
    lead_id = lead.json()["id"]

    duplicate = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Riya S", "email": "RIYA@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "POTENTIAL_DUPLICATE"

    filtered = await client.get(
        f"/api/v1/leads?q=riya&source_id={source.json()['id']}&min_score=20&page_size=1",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1

    due_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    follow_up = await client.post(
        f"/api/v1/leads/{lead_id}/activities",
        headers=headers,
        json={
            "activity_type": "FOLLOW_UP",
            "subject": "Discuss shortlist",
            "occurred_at": datetime.now(UTC).isoformat(),
            "due_at": due_at,
        },
    )
    assert follow_up.status_code == 201, follow_up.text
    assert follow_up.json()["is_completed"] is False

    completed = await client.post(
        f"/api/v1/leads/{lead_id}/activities/{follow_up.json()['id']}/complete",
        headers=headers,
        json={"outcome": "Customer requested a site visit"},
    )
    assert completed.status_code == 200
    assert completed.json()["is_completed"] is True

    note = await client.post(
        f"/api/v1/leads/{lead_id}/notes",
        headers=headers,
        json={"body": "Prefers a higher floor", "is_pinned": True},
    )
    assert note.status_code == 201

    qualified = await client.post(
        f"/api/v1/leads/{lead_id}/qualify",
        headers=headers,
        json={"notes": "Budget and timeline confirmed"},
    )
    assert qualified.status_code == 200
    assert qualified.json()["status"] == "QUALIFIED"

    converted = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        headers=headers,
        json={},
    )
    assert converted.status_code == 201, converted.text
    assert converted.json()["lead"]["status"] == "CONVERTED"
    assert converted.json()["customer_id"]

    timeline = await client.get(f"/api/v1/leads/{lead_id}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert {item["kind"] for item in timeline.json()} >= {"activity", "note", "assignment"}

    lost_candidate = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Kabir Shah", "phone": "+91 98765 42000"},
    )
    lost = await client.post(
        f"/api/v1/leads/{lost_candidate.json()['id']}/lost",
        headers=headers,
        json={"reason_id": reason.json()["id"], "notes": "Outside budget"},
    )
    assert lost.status_code == 200
    assert lost.json()["lost_reason_name"] == "Budget mismatch"

    stats = await client.get("/api/v1/leads/stats", headers=headers)
    assert stats.json()["total"] == 2
    assert stats.json()["converted"] == 1


async def test_duplicates_import_allocation_ageing_and_tenant_security(
    client: AsyncClient,
) -> None:
    headers, session = await _register(client, slug="pipeline-one", email="one@example.com")
    first = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "First Buyer", "phone": "+91 90000 00001"},
    )
    second = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "full_name": "Second Buyer",
            "phone": "+91 90000 00001",
            "duplicate_override": True,
        },
    )
    assert first.status_code == second.status_code == 201

    groups = await client.get("/api/v1/leads/duplicates", headers=headers)
    assert groups.status_code == 200
    assert len(groups.json()) == 1
    resolved = await client.post(
        "/api/v1/leads/duplicates/resolve",
        headers=headers,
        json={
            "primary_lead_id": first.json()["id"],
            "duplicate_lead_ids": [second.json()["id"]],
        },
    )
    assert resolved.status_code == 204
    assert (await client.get("/api/v1/leads/duplicates", headers=headers)).json() == []

    preview = await client.post(
        "/api/v1/leads/imports/preview",
        headers=headers,
        json={
            "filename": "new-leads.csv",
            "rows": [
                {"full_name": "Imported Buyer", "email": "imported@example.com"},
                {"full_name": "Existing Buyer", "phone": "+91 90000 00001"},
                {"full_name": "Invalid Buyer"},
            ],
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["ready_rows"] == 1
    assert preview.json()["duplicate_rows"] == 1
    assert preview.json()["error_rows"] == 1

    imported = await client.post(
        "/api/v1/leads/imports",
        headers=headers,
        json={
            "filename": "new-leads.csv",
            "rows": [
                {"full_name": "Imported Buyer", "email": "imported@example.com"},
                {"full_name": "Existing Buyer", "phone": "+91 90000 00001"},
            ],
        },
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported_rows"] == 1
    assert imported.json()["skipped_rows"] == 1

    allocation = await client.get("/api/v1/leads/allocation", headers=headers)
    assert allocation.status_code == 200
    assert allocation.json()["total"] == 2
    assigned = await client.post(
        "/api/v1/leads/bulk-assign",
        headers=headers,
        json={
            "lead_ids": [first.json()["id"]],
            "assigned_user_id": session["user"]["id"],
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()[0]["owner_name"] == "Lead Administrator"

    ageing = await client.get("/api/v1/leads/ageing/buckets", headers=headers)
    assert ageing.status_code == 200
    assert sum(bucket["count"] for bucket in ageing.json()) == 2

    second_headers, _ = await _register(client, slug="pipeline-two", email="two@example.com")
    hidden = await client.get(f"/api/v1/leads/{first.json()['id']}", headers=second_headers)
    assert hidden.status_code == 404


async def test_lead_backend_permissions_are_authoritative(client: AsyncClient) -> None:
    headers, _ = await _register(client, slug="permission-leads", email="permissions@example.com")
    async with SessionFactory() as db:
        administrator = (
            await db.scalars(select(User).where(User.email == "permissions@example.com"))
        ).one()
        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.organization_id == administrator.organization_id,
                        Permission.code.in_(["leads.create", "leads.manage", "leads.approve"]),
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
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Denied Lead", "email": "denied@example.com"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"

    denied_source = await client.post(
        "/api/v1/leads/sources",
        headers=headers,
        json={"name": "Denied Source", "code": "DENIED"},
    )
    assert denied_source.status_code == 403
