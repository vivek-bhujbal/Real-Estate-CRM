from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models.entities import AuditLog, ServiceRequest


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "service-desk",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _user(
    client: AsyncClient,
    admin: dict[str, str],
    *,
    name: str,
    email: str,
    password: str,
    role_id: str,
) -> str:
    response = await client.post(
        "/api/v1/organization/users",
        headers=admin,
        json={
            "full_name": name,
            "email": email,
            "password": password,
            "role_ids": [role_id],
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    user_id = str(response.json()["id"])
    assignment = await client.put(
        f"/api/v1/rbac/users/{user_id}/roles",
        headers=admin,
        json={"role_ids": [role_id]},
    )
    assert assignment.status_code == 200, assignment.text
    return user_id


async def test_complete_ticket_workflow_with_sla_and_customer_scope(
    client: AsyncClient,
) -> None:
    registration = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Service Desk",
            "organization_slug": "service-desk",
            "admin_full_name": "Service Administrator",
            "admin_email": "service-admin@example.com",
            "password": "Secure-service-admin-password-42!",
        },
    )
    assert registration.status_code == 201, registration.text
    session = registration.json()
    admin = {"Authorization": f"Bearer {session['access_token']}"}
    org_id = session["user"]["organization_id"]

    empty = await client.get("/api/v1/service-requests", headers=admin)
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert (await client.get("/api/v1/service-requests/categories", headers=admin)).json() == []

    category = await client.post(
        "/api/v1/service-requests/categories",
        headers=admin,
        json={
            "code": "HANDOVER",
            "name": "Handover support",
            "description": "Customer handover assistance",
        },
    )
    assert category.status_code == 201, category.text
    category_id = category.json()["id"]
    policy = await client.post(
        "/api/v1/service-requests/sla-policies",
        headers=admin,
        json={
            "category_id": category_id,
            "priority": "HIGH",
            "first_response_minutes": 30,
            "escalation_minutes": 120,
            "resolution_minutes": 480,
        },
    )
    assert policy.status_code == 201, policy.text

    roles = (await client.get("/api/v1/rbac/roles", headers=admin)).json()
    role_ids = {item["name"]: item["id"] for item in roles}
    agent_one_password = "Secure-agent-one-password-42!"
    agent_two_password = "Secure-agent-two-password-42!"
    customer_password = "Secure-customer-password-42!"
    other_customer_password = "Secure-other-customer-password-42!"
    agent_one_id = await _user(
        client,
        admin,
        name="Service Agent One",
        email="agent-one@example.com",
        password=agent_one_password,
        role_id=role_ids["CRM Executive"],
    )
    agent_two_id = await _user(
        client,
        admin,
        name="Service Agent Two",
        email="agent-two@example.com",
        password=agent_two_password,
        role_id=role_ids["CRM Executive"],
    )
    portal_customer_id = await _user(
        client,
        admin,
        name="Portal Customer",
        email="portal-customer@example.com",
        password=customer_password,
        role_id=role_ids["Customer / Buyer"],
    )
    await _user(
        client,
        admin,
        name="Other Portal Customer",
        email="other-portal-customer@example.com",
        password=other_customer_password,
        role_id=role_ids["Customer / Buyer"],
    )
    agent_one = await _login(client, "agent-one@example.com", agent_one_password)
    agent_two = await _login(client, "agent-two@example.com", agent_two_password)
    customer = await _login(client, "portal-customer@example.com", customer_password)
    other_customer = await _login(
        client, "other-portal-customer@example.com", other_customer_password
    )

    created = await client.post(
        "/api/v1/service-requests",
        headers=customer,
        json={
            "category_id": category_id,
            "priority": "HIGH",
            "subject": "Need help with handover documents",
            "description": "The handover checklist is missing one signed acknowledgement.",
            "assigned_user_id": agent_one_id,
        },
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["ticket"]["id"]
    assert created.json()["ticket"]["status"] == "OPEN"
    assert created.json()["ticket"]["assigned_user_id"] is None
    assert created.json()["ticket"]["sla"]["configured"] is True
    assert created.json()["ticket"]["sla"]["response_due_at"] is not None

    own_list = await client.get("/api/v1/service-requests", headers=customer)
    assert [item["id"] for item in own_list.json()["items"]] == [ticket_id]
    assert (await client.get("/api/v1/service-requests", headers=other_customer)).json()[
        "items"
    ] == []
    hidden = await client.get(f"/api/v1/service-requests/{ticket_id}", headers=other_customer)
    assert hidden.status_code == 404

    agent_options = await client.get("/api/v1/service-requests/options", headers=agent_one)
    assert agent_options.status_code == 200
    assert portal_customer_id not in {
        item["id"] for item in agent_options.json()["agents"]
    }
    invalid_assignment = await client.post(
        f"/api/v1/service-requests/{ticket_id}/assignment",
        headers=agent_one,
        json={"assigned_user_id": portal_customer_id},
    )
    assert invalid_assignment.status_code == 422

    assignment = await client.post(
        f"/api/v1/service-requests/{ticket_id}/assignment",
        headers=agent_one,
        json={
            "assigned_user_id": agent_one_id,
            "notes": "Assigned to the post-handover service queue.",
        },
    )
    assert assignment.status_code == 200, assignment.text
    assert assignment.json()["ticket"]["status"] == "ASSIGNED"

    started = await client.post(
        f"/api/v1/service-requests/{ticket_id}/status",
        headers=agent_one,
        json={"status": "IN_PROGRESS", "notes": "Investigation started."},
    )
    assert started.status_code == 200, started.text
    assert started.json()["ticket"]["sla"]["first_responded_at"] is not None

    internal = await client.post(
        f"/api/v1/service-requests/{ticket_id}/comments",
        headers=agent_one,
        json={"body": "Internal verification with legal is pending.", "is_internal": True},
    )
    assert internal.status_code == 201, internal.text
    customer_detail = await client.get(f"/api/v1/service-requests/{ticket_id}", headers=customer)
    assert all(not item["is_internal"] for item in customer_detail.json()["comments"])
    assert not any(
        "legal is pending" in item["body"] for item in customer_detail.json()["comments"]
    )

    waiting = await client.post(
        f"/api/v1/service-requests/{ticket_id}/status",
        headers=agent_one,
        json={
            "status": "WAITING_FOR_CUSTOMER",
            "notes": "Please upload the acknowledgement copy.",
        },
    )
    assert waiting.status_code == 200, waiting.text
    reply = await client.post(
        f"/api/v1/service-requests/{ticket_id}/comments",
        headers=customer,
        json={"body": "The signed acknowledgement is attached.", "is_internal": False},
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["ticket"]["status"] == "IN_PROGRESS"

    attachment = await client.post(
        f"/api/v1/service-requests/{ticket_id}/attachments",
        headers=customer,
        files={
            "file": (
                "acknowledgement.pdf",
                b"%PDF-1.4 customer acknowledgement",
                "application/pdf",
            )
        },
    )
    assert attachment.status_code == 201, attachment.text
    attachment_id = attachment.json()["attachments"][0]["id"]
    download = await client.get(
        f"/api/v1/service-requests/{ticket_id}/attachments/{attachment_id}/download",
        headers=customer,
    )
    assert download.status_code == 200
    assert download.headers["cache-control"] == "private, no-store, max-age=0"
    forbidden_download = await client.get(
        f"/api/v1/service-requests/{ticket_id}/attachments/{attachment_id}/download",
        headers=other_customer,
    )
    assert forbidden_download.status_code == 404

    async with SessionFactory() as db:
        stored = await db.get(ServiceRequest, ticket_id)
        assert stored is not None
        stored.resolution_due_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
        await db.commit()
    breached = await client.get("/api/v1/service-requests/stats", headers=agent_one)
    assert breached.status_code == 200
    assert breached.json()["sla_breached"] == 1

    escalated = await client.post(
        f"/api/v1/service-requests/{ticket_id}/escalations",
        headers=agent_one,
        json={
            "to_user_id": agent_two_id,
            "reason": "Resolution SLA is breached and legal ownership is required.",
        },
    )
    assert escalated.status_code == 201, escalated.text
    escalation_id = escalated.json()["escalations"][0]["id"]
    wrong_ack = await client.post(
        f"/api/v1/service-requests/{ticket_id}/escalations/{escalation_id}",
        headers=agent_one,
        json={"action": "ACKNOWLEDGE", "notes": "Attempt by prior assignee"},
    )
    assert wrong_ack.status_code == 403
    acknowledged = await client.post(
        f"/api/v1/service-requests/{ticket_id}/escalations/{escalation_id}",
        headers=agent_two,
        json={"action": "ACKNOWLEDGE", "notes": "Escalation ownership accepted"},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["escalations"][0]["status"] == "ACKNOWLEDGED"

    customer_cannot_resolve = await client.post(
        f"/api/v1/service-requests/{ticket_id}/status",
        headers=customer,
        json={
            "status": "RESOLVED",
            "notes": "Attempt to bypass agent resolution",
            "resolution_summary": "Not allowed",
        },
    )
    assert customer_cannot_resolve.status_code == 403
    resolved = await client.post(
        f"/api/v1/service-requests/{ticket_id}/status",
        headers=agent_two,
        json={
            "status": "RESOLVED",
            "notes": "Signed acknowledgement indexed and verified.",
            "resolution_summary": (
                "Missing acknowledgement was received and added to handover records."
            ),
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["ticket"]["status"] == "RESOLVED"
    assert resolved.json()["escalations"][0]["status"] == "RESOLVED"

    closed = await client.post(
        f"/api/v1/service-requests/{ticket_id}/status",
        headers=customer,
        json={"status": "CLOSED", "notes": "Customer confirms the issue is resolved."},
    )
    assert closed.status_code == 200, closed.text
    feedback = await client.post(
        f"/api/v1/service-requests/{ticket_id}/feedback",
        headers=customer,
        json={"rating": 5, "comments": "Clear updates and quick resolution."},
    )
    assert feedback.status_code == 201, feedback.text
    assert feedback.json()["feedback"]["rating"] == 5
    duplicate_feedback = await client.post(
        f"/api/v1/service-requests/{ticket_id}/feedback",
        headers=customer,
        json={"rating": 4, "comments": "Duplicate attempt"},
    )
    assert duplicate_feedback.status_code == 409
    final_stats = await client.get("/api/v1/service-requests/stats", headers=agent_one)
    assert final_stats.status_code == 200
    assert final_stats.json()["sla_breached"] == 1
    assert final_stats.json()["average_feedback"] == 5.0

    async with SessionFactory() as db:
        assert int(await db.scalar(select(func.count(ServiceRequest.id))) or 0) == 1
        actions = set(
            await db.scalars(select(AuditLog.action).where(AuditLog.organization_id == org_id))
        )
        assert {
            "service.ticket.created",
            "service.ticket.assigned",
            "service.comment.added",
            "service.attachment.uploaded",
            "service.ticket.escalated",
            "service.escalation.updated",
            "service.ticket.status_changed",
            "service.feedback.submitted",
        } <= actions
