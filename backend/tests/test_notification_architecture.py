from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models.entities import Notification
from app.models.enums import ExternalNotificationChannel, NotificationEventType
from app.services.notifications import (
    DeliveryReceipt,
    NotificationTransportRegistry,
    OutboundNotification,
)


async def _register(
    client: AsyncClient,
    *,
    slug: str = "notification-workspace",
    email: str = "notification-admin@example.com",
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Workspace {slug}",
            "organization_slug": slug,
            "admin_full_name": "Notification Administrator",
            "admin_email": email,
            "password": "Secure-notification-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _create_notification_user(
    client: AsyncClient, headers: dict[str, str]
) -> tuple[dict[str, str], str]:
    user = await client.post(
        "/api/v1/organization/users",
        headers=headers,
        json={
            "email": "inside-sales@example.com",
            "full_name": "Inside Sales User",
            "password": "Inside-sales-password-43!",
        },
    )
    assert user.status_code == 201, user.text

    roles = await client.get("/api/v1/rbac/roles", headers=headers)
    assert roles.status_code == 200, roles.text
    role = next(
        item
        for item in roles.json()
        if item["name"] == "Inside Sales / Telecalling Executive"
    )
    assigned = await client.put(
        f"/api/v1/rbac/users/{user.json()['id']}/roles",
        headers=headers,
        json={"role_ids": [role["id"]]},
    )
    assert assigned.status_code == 200, assigned.text

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "notification-workspace",
            "email": "inside-sales@example.com",
            "password": "Inside-sales-password-43!",
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user.json()["id"]


async def test_registration_does_not_seed_notifications(client: AsyncClient) -> None:
    headers, _ = await _register(client)

    inbox = await client.get("/api/v1/notifications", headers=headers)
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["items"] == []
    assert inbox.json()["total"] == 0

    async with SessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 0


async def test_real_lead_assignment_is_recipient_scoped_and_readable(
    client: AsyncClient,
) -> None:
    admin_headers, _ = await _register(client)
    recipient_headers, recipient_id = await _create_notification_user(client, admin_headers)

    lead = await client.post(
        "/api/v1/leads",
        headers=admin_headers,
        json={
            "full_name": "Prospective Customer",
            "email": "real-prospect@example.com",
            "owner_user_id": recipient_id,
        },
    )
    assert lead.status_code == 201, lead.text

    admin_inbox = await client.get("/api/v1/notifications", headers=admin_headers)
    assert admin_inbox.json()["total"] == 0

    recipient_inbox = await client.get(
        "/api/v1/notifications?unread_only=true", headers=recipient_headers
    )
    assert recipient_inbox.status_code == 200, recipient_inbox.text
    assert recipient_inbox.json()["total"] == 1
    notification = recipient_inbox.json()["items"][0]
    assert notification["event_type"] == "LEAD_ASSIGNED"
    assert notification["related_entity_id"] == lead.json()["id"]
    assert notification["action_url"] == f"/leads/{lead.json()['id']}"

    hidden = await client.patch(
        f"/api/v1/notifications/{notification['id']}/read", headers=admin_headers
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    unread = await client.get("/api/v1/notifications/unread-count", headers=recipient_headers)
    assert unread.json() == {"unread": 1}
    marked = await client.patch(
        f"/api/v1/notifications/{notification['id']}/read", headers=recipient_headers
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["status"] == "READ"
    assert marked.json()["read_at"] is not None
    assert (
        await client.get("/api/v1/notifications/unread-count", headers=recipient_headers)
    ).json() == {"unread": 0}


async def test_due_follow_up_processing_is_repeat_safe(client: AsyncClient) -> None:
    headers, session = await _register(client)
    user_id = session["user"]["id"]
    lead = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "full_name": "Reminder Customer",
            "email": "reminder-customer@example.com",
            "owner_user_id": user_id,
        },
    )
    assert lead.status_code == 201, lead.text
    activity = await client.post(
        f"/api/v1/leads/{lead.json()['id']}/activities",
        headers=headers,
        json={
            "activity_type": "FOLLOW_UP",
            "subject": "Call customer about requirements",
            "occurred_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            "due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
    )
    assert activity.status_code == 201, activity.text

    first = await client.post("/api/v1/notifications/process-due", headers=headers)
    second = await client.post("/api/v1/notifications/process-due", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["follow_up_reminders"] == 1
    assert second.json()["follow_up_reminders"] == 0

    reminders = await client.get(
        "/api/v1/notifications?event_type=FOLLOW_UP_REMINDER", headers=headers
    )
    assert reminders.json()["total"] == 1
    assert reminders.json()["items"][0]["related_entity_id"] == activity.json()["id"]


async def test_external_transport_registry_is_provider_neutral() -> None:
    class EmailTransport:
        channel = ExternalNotificationChannel.EMAIL

        async def send(self, message: OutboundNotification) -> DeliveryReceipt:
            assert message.recipient == "real@example.com"
            return DeliveryReceipt(
                provider_message_id="provider-reference",
                accepted_at=datetime.now(UTC),
            )

    registry = NotificationTransportRegistry()
    registry.register(EmailTransport())
    message = OutboundNotification(
        organization_id="organization-id",
        event_type=NotificationEventType.BOOKING_CREATED,
        recipient="real@example.com",
        title="Booking created",
        body="A real booking event was created.",
        data={"booking_id": "booking-id"},
    )

    receipt = await registry.send(ExternalNotificationChannel.EMAIL, message)
    assert receipt.provider_message_id == "provider-reference"
    with pytest.raises(RuntimeError, match="WHATSAPP"):
        await registry.send(ExternalNotificationChannel.WHATSAPP, message)
