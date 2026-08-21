from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def _register(
    client: AsyncClient,
    *,
    slug: str = "visit-workspace",
    email: str = "visit-admin@example.com",
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Workspace {slug}",
            "organization_slug": slug,
            "admin_full_name": "Visit Administrator",
            "admin_email": email,
            "password": "Secure-visit-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _sales_context(
    client: AsyncClient, headers: dict[str, str]
) -> tuple[str, str, list[str]]:
    lead = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Visit Lead", "phone": "+91 90000 00401"},
    )
    assert lead.status_code == 201, lead.text
    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Visit Customer", "email": "visit-customer@example.com"},
    )
    assert customer.status_code == 201, customer.text
    project = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Visit Project", "code": "VISIT-PROJECT"},
    )
    assert project.status_code == 201, project.text
    unit_ids: list[str] = []
    for number in ("V-101", "V-102"):
        unit = await client.post(
            f"/api/v1/projects/{project.json()['id']}/units",
            headers=headers,
            json={"unit_number": number, "unit_type": "2 BHK"},
        )
        assert unit.status_code == 201, unit.text
        unit_ids.append(unit.json()["id"])
    return lead.json()["id"], customer.json()["id"], [project.json()["id"], *unit_ids]


async def test_site_visit_lifecycle_calendar_and_timelines(client: AsyncClient) -> None:
    headers, session = await _register(client)
    lead_id, customer_id, identifiers = await _sales_context(client, headers)
    project_id, *unit_ids = identifiers
    scheduled_at = datetime.now(UTC) + timedelta(days=2)
    created = await client.post(
        "/api/v1/site-visits",
        headers=headers,
        json={
            "lead_id": lead_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "interested_unit_ids": unit_ids,
            "scheduled_at": scheduled_at.isoformat(),
            "attendees": ["Visit Customer", "Family Member"],
            "notes": "Meet at the sales lounge",
        },
    )
    assert created.status_code == 201, created.text
    visit = created.json()
    assert visit["assigned_user_id"] == session["user"]["id"]
    assert [item["unit_number"] for item in visit["interested_units"]] == ["V-101", "V-102"]

    filtered = await client.get(
        f"/api/v1/site-visits?lead_id={lead_id}&project_id={project_id}&status=SCHEDULED",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    calendar = await client.get(
        "/api/v1/site-visits/calendar",
        headers=headers,
        params={
            "date_from": (scheduled_at - timedelta(days=1)).isoformat(),
            "date_to": (scheduled_at + timedelta(days=1)).isoformat(),
        },
    )
    assert calendar.status_code == 200
    assert [item["id"] for item in calendar.json()] == [visit["id"]]

    confirmed = await client.post(
        f"/api/v1/site-visits/{visit['id']}/status",
        headers=headers,
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200
    checked_in = await client.post(
        f"/api/v1/site-visits/{visit['id']}/check-in",
        headers=headers,
        json={"attendees": ["Visit Customer"]},
    )
    assert checked_in.status_code == 200
    assert checked_in.json()["status"] == "CHECKED_IN"
    duplicate_check_in = await client.post(
        f"/api/v1/site-visits/{visit['id']}/check-in", headers=headers, json={}
    )
    assert duplicate_check_in.status_code == 409

    follow_up = datetime.now(UTC) + timedelta(days=4)
    completed = await client.post(
        f"/api/v1/site-visits/{visit['id']}/check-out",
        headers=headers,
        json={
            "feedback": "Customer preferred the second unit",
            "outcome": "Follow-up requested",
            "next_follow_up_at": follow_up.isoformat(),
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["outcome"] == "Follow-up requested"

    lead_timeline = await client.get(f"/api/v1/leads/{lead_id}/timeline", headers=headers)
    assert lead_timeline.status_code == 200
    assert any(item["kind"] == "site_visit" for item in lead_timeline.json())
    assert any(item["title"] == "Site visit completed" for item in lead_timeline.json())
    customer_360 = await client.get(f"/api/v1/customers/{customer_id}/360", headers=headers)
    assert customer_360.status_code == 200
    assert any(item["kind"] == "site_visit" for item in customer_360.json()["sales"])
    assert any(item["title"] == "Site visit completed" for item in customer_360.json()["timeline"])
    stats = await client.get("/api/v1/site-visits/stats", headers=headers)
    assert stats.json()["completed"] == 1


async def test_site_visit_validation_deletion_and_tenant_isolation(client: AsyncClient) -> None:
    headers, _ = await _register(
        client, slug="visit-isolation", email="visit-isolation@example.com"
    )
    lead_id, _, identifiers = await _sales_context(client, headers)
    project_id, first_unit_id, _ = identifiers
    invalid_contact = await client.post(
        "/api/v1/site-visits",
        headers=headers,
        json={
            "project_id": project_id,
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert invalid_contact.status_code == 422
    visit = await client.post(
        "/api/v1/site-visits",
        headers=headers,
        json={
            "lead_id": lead_id,
            "project_id": project_id,
            "interested_unit_ids": [first_unit_id],
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert visit.status_code == 201, visit.text
    deleted = await client.delete(f"/api/v1/site-visits/{visit.json()['id']}", headers=headers)
    assert deleted.status_code == 204

    other_headers, _ = await _register(client, slug="visit-other", email="visit-other@example.com")
    hidden = await client.get(f"/api/v1/site-visits/{visit.json()['id']}", headers=other_headers)
    assert hidden.status_code == 404
    assert (await client.get("/api/v1/site-visits", headers=other_headers)).json()["items"] == []
