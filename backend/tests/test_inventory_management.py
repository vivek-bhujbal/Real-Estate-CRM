from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from app.db.session import SessionFactory
from app.models.entities import UnitHold


async def _register(
    client: AsyncClient,
    *,
    slug: str = "inventory-workspace",
    email: str = "inventory-admin@example.com",
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": f"Workspace {slug}",
            "organization_slug": slug,
            "admin_full_name": "Inventory Administrator",
            "admin_email": email,
            "password": "Secure-inventory-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _hierarchy(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str]:
    project = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Riverside Residences",
            "code": "riverside",
            "project_type": "Residential",
            "city": "Pune",
            "default_currency": "inr",
            "amenities": ["Pool", "Gym"],
            "configuration": {"parking_policy": "one_per_unit"},
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    tower = await client.post(
        f"/api/v1/projects/{project_id}/towers",
        headers=headers,
        json={"name": "Tower A", "code": "a"},
    )
    assert tower.status_code == 201, tower.text
    floor = await client.post(
        f"/api/v1/projects/{project_id}/floors",
        headers=headers,
        json={"tower_id": tower.json()["id"], "name": "Fifth floor", "floor_number": 5},
    )
    assert floor.status_code == 201, floor.text
    return project_id, tower.json()["id"], floor.json()["id"]


async def _unit(
    client: AsyncClient,
    headers: dict[str, str],
    project_id: str,
    tower_id: str,
    floor_id: str,
    number: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/projects/{project_id}/units",
        headers=headers,
        json={
            "tower_id": tower_id,
            "floor_id": floor_id,
            "unit_number": number,
            "unit_type": "3 BHK",
            "area_sqft": "1450",
            "carpet_area_sqft": "1080",
            "built_up_area_sqft": "1320",
            "facing": "East",
            "bedrooms": 3,
            "bathrooms": 3,
            "balconies": 2,
            "base_price": "12500000",
            "amenities": ["Pool", "Parking"],
            "price_components": {"parking": 500000},
            "configuration": {"parking_slots": 1},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["currency"] == "INR"
    return response.json()


async def test_project_hierarchy_inventory_search_and_holds(client: AsyncClient) -> None:
    headers, _ = await _register(client)
    assert (await client.get("/api/v1/projects", headers=headers)).json()["items"] == []
    project_id, tower_id, floor_id = await _hierarchy(client, headers)
    unit = await _unit(client, headers, project_id, tower_id, floor_id, "A-501")

    duplicate = await client.post(
        f"/api/v1/projects/{project_id}/units",
        headers=headers,
        json={"unit_number": "A-501"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_UNIT"

    search = await client.get(
        f"/api/v1/inventory/units?project_id={project_id}&status=AVAILABLE&min_area=1200&max_price=13000000&amenity=Pool",
        headers=headers,
    )
    assert search.status_code == 200, search.text
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["floor_number"] == 5

    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Inventory Buyer", "email": "inventory-buyer@example.com"},
    )
    assert customer.status_code == 201
    hold = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/hold",
        headers=headers,
        json={
            "hold_type": "SOFT_HOLD",
            "expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "customer_id": customer.json()["id"],
            "hold_reason": "Customer requested a decision window",
        },
    )
    assert hold.status_code == 201, hold.text
    assert hold.json()["status"] == "PENDING_APPROVAL"
    blocked = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/hold",
        headers=headers,
        json={
            "hold_type": "HARD_HOLD",
            "expires_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
            "customer_id": customer.json()["id"],
            "hold_reason": "Customer submitted booking intent",
        },
    )
    assert blocked.status_code == 409
    released = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/hold/release",
        headers=headers,
        json={"reason": "Customer changed shortlist"},
    )
    assert released.status_code == 200
    assert released.json()["status"] == "AVAILABLE"

    project = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert project.json()["tower_count"] == 1
    assert project.json()["unit_count"] == 1
    assert project.json()["available_unit_count"] == 1


async def test_booking_lock_prevents_duplicate_unit_booking(client: AsyncClient) -> None:
    headers, _ = await _register(client, slug="booking-lock", email="booking-lock@example.com")
    project_id, tower_id, floor_id = await _hierarchy(client, headers)
    unit = await _unit(client, headers, project_id, tower_id, floor_id, "A-502")
    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Booking Buyer", "phone": "+91 90000 00502"},
    )
    booking_payload = {
        "customer_id": customer.json()["id"],
        "booking_number": "BK/A502",
        "booking_amount": "500000",
        "currency": "inr",
    }
    booking = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/booking",
        headers=headers,
        json=booking_payload,
    )
    assert booking.status_code == 201, booking.text
    assert booking.json()["status"] == "DRAFT"
    assert (await client.get(f"/api/v1/inventory/units/{unit['id']}", headers=headers)).json()[
        "status"
    ] == "BOOKING_INITIATED"

    duplicate = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/booking",
        headers=headers,
        json={**booking_payload, "booking_number": "BK/A502-SECOND"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "UNIT_ALREADY_BOOKED"

    confirmed = await client.post(
        f"/api/v1/inventory/bookings/{booking.json()['id']}/status",
        headers=headers,
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 409, confirmed.text
    assert confirmed.json()["error"]["code"] == "BOOKING_APPROVAL_REQUIRED"


async def test_cancelled_booking_releases_unit_and_tenant_scope(client: AsyncClient) -> None:
    headers, _ = await _register(client, slug="release-unit", email="release-unit@example.com")
    project_id, tower_id, floor_id = await _hierarchy(client, headers)
    unit = await _unit(client, headers, project_id, tower_id, floor_id, "A-503")
    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Release Buyer", "phone": "+91 90000 00503"},
    )
    booking = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/booking",
        headers=headers,
        json={
            "customer_id": customer.json()["id"],
            "booking_number": "BK/A503",
            "booking_amount": "400000",
            "currency": "INR",
        },
    )
    cancelled = await client.post(
        f"/api/v1/inventory/bookings/{booking.json()['id']}/status",
        headers=headers,
        json={"status": "CANCELLED"},
    )
    assert cancelled.status_code == 200
    released = await client.get(f"/api/v1/inventory/units/{unit['id']}", headers=headers)
    assert released.json()["status"] == "CANCELLED_RELEASED"
    available = await client.post(
        f"/api/v1/inventory/units/{unit['id']}/status",
        headers=headers,
        json={"status": "AVAILABLE"},
    )
    assert available.status_code == 200

    other_headers, _ = await _register(
        client, slug="inventory-other", email="inventory-other@example.com"
    )
    hidden = await client.get(f"/api/v1/projects/{project_id}", headers=other_headers)
    assert hidden.status_code == 404
    other_inventory = await client.get("/api/v1/inventory/units", headers=other_headers)
    assert other_inventory.json()["items"] == []


async def test_hold_approval_history_expiry_and_concurrency(client: AsyncClient) -> None:
    headers, registration = await _register(
        client, slug="hold-lifecycle", email="hold-admin@example.com"
    )
    project_id, tower_id, floor_id = await _hierarchy(client, headers)
    first_unit = await _unit(client, headers, project_id, tower_id, floor_id, "H-601")
    second_unit = await _unit(client, headers, project_id, tower_id, floor_id, "H-602")
    customer = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Hold Customer", "email": "hold-customer@example.com"},
    )
    salesperson = await client.post(
        "/api/v1/organization/users",
        headers=headers,
        json={
            "full_name": "Hold Salesperson",
            "email": "hold-salesperson@example.com",
            "password": "Secure-hold-salesperson-42!",
            "is_active": True,
        },
    )
    assert salesperson.status_code == 201, salesperson.text
    salesperson_options = await client.get("/api/v1/inventory/hold-salespeople", headers=headers)
    assert salesperson_options.status_code == 200
    assert salesperson.json()["id"] in {item["id"] for item in salesperson_options.json()}
    payload = {
        "hold_type": "SOFT_HOLD",
        "expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "hold_reason": "Customer needs time to complete financial verification",
        "customer_id": customer.json()["id"],
        "salesperson_user_id": salesperson.json()["id"],
    }
    hold = await client.post(
        f"/api/v1/inventory/units/{first_unit['id']}/hold", headers=headers, json=payload
    )
    assert hold.status_code == 201, hold.text
    assert hold.json()["status"] == "PENDING_APPROVAL"
    assert hold.json()["salesperson_name"] == "Hold Salesperson"
    assert hold.json()["hold_reason"] == payload["hold_reason"]

    availability = await client.get(
        f"/api/v1/inventory/units?project_id={project_id}&status=AVAILABLE", headers=headers
    )
    assert {item["id"] for item in availability.json()["items"]} == {second_unit["id"]}
    first_unit_state = await client.get(
        f"/api/v1/inventory/units/{first_unit['id']}", headers=headers
    )
    assert first_unit_state.json()["status"] == "SOFT_HOLD"

    approved = await client.post(
        f"/api/v1/inventory/holds/{hold.json()['id']}/approval",
        headers=headers,
        json={"status": "APPROVED", "notes": "Customer documents verified"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "ACTIVE"
    assert approved.json()["approver_name"] == registration["user"]["full_name"]

    history = await client.get(f"/api/v1/inventory/units/{first_unit['id']}/holds", headers=headers)
    assert history.status_code == 200
    assert history.json()[0]["id"] == hold.json()["id"]
    assert history.json()[0]["approved_at"] is not None

    released = await client.post(
        f"/api/v1/inventory/units/{first_unit['id']}/hold/release",
        headers=headers,
        json={"reason": "Customer withdrew the hold request"},
    )
    assert released.status_code == 200
    assert released.json()["status"] == "AVAILABLE"

    self_hold = await client.post(
        f"/api/v1/inventory/units/{first_unit['id']}/hold",
        headers=headers,
        json={**payload, "salesperson_user_id": registration["user"]["id"]},
    )
    self_approval = await client.post(
        f"/api/v1/inventory/holds/{self_hold.json()['id']}/approval",
        headers=headers,
        json={"status": "APPROVED", "notes": "Self approval attempt"},
    )
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "SELF_APPROVAL_NOT_ALLOWED"
    pending_booking = await client.post(
        f"/api/v1/inventory/units/{first_unit['id']}/booking",
        headers=headers,
        json={
            "customer_id": customer.json()["id"],
            "booking_number": "PENDING-HOLD-BLOCK",
            "booking_amount": "100000",
            "currency": "INR",
        },
    )
    assert pending_booking.status_code == 409
    assert pending_booking.json()["error"]["code"] == "HOLD_APPROVAL_PENDING"
    await client.post(
        f"/api/v1/inventory/units/{first_unit['id']}/hold/release",
        headers=headers,
        json={"reason": "Clear pending self-approval test"},
    )

    hard_hold = await client.post(
        f"/api/v1/inventory/units/{first_unit['id']}/hold",
        headers=headers,
        json={**payload, "hold_type": "HARD_HOLD", "hold_reason": "Final inventory block"},
    )
    rejected = await client.post(
        f"/api/v1/inventory/holds/{hard_hold.json()['id']}/approval",
        headers=headers,
        json={"status": "REJECTED", "notes": "Required commercial proof was not supplied"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["rejected_at"] is not None

    first_attempt = await client.post(
        f"/api/v1/inventory/units/{second_unit['id']}/hold",
        headers=headers,
        json={**payload, "hold_reason": "First competing request"},
    )
    second_attempt = await client.post(
        f"/api/v1/inventory/units/{second_unit['id']}/hold",
        headers=headers,
        json={**payload, "hold_reason": "Second competing request"},
    )
    assert first_attempt.status_code == 201
    assert second_attempt.status_code == 409
    winning_hold = first_attempt.json()
    approved_expiring = await client.post(
        f"/api/v1/inventory/holds/{winning_hold['id']}/approval",
        headers=headers,
        json={"status": "APPROVED", "notes": "Approved before automated expiry"},
    )
    assert approved_expiring.status_code == 200
    async with SessionFactory() as db:
        await db.execute(
            update(UnitHold)
            .where(UnitHold.id == winning_hold["id"])
            .values(expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1))
        )
        await db.commit()
    expiry = await client.post("/api/v1/inventory/holds/expire-due", headers=headers)
    assert expiry.status_code == 200, expiry.text
    assert expiry.json()["expired_count"] == 1
    expired_history = await client.get(
        f"/api/v1/inventory/units/{second_unit['id']}/holds", headers=headers
    )
    assert expired_history.json()[0]["status"] == "EXPIRED"
    assert expired_history.json()[0]["release_reason"] == "Expired automatically"
    second_unit_state = await client.get(
        f"/api/v1/inventory/units/{second_unit['id']}", headers=headers
    )
    assert second_unit_state.json()["status"] == "AVAILABLE"

    audits = await client.get(
        "/api/v1/organization/audit-logs?entity_type=unit_hold&page_size=100",
        headers=headers,
    )
    actions = {item["action"] for item in audits.json()["items"]}
    assert {
        "unit.hold.created",
        "unit.hold.approved",
        "unit.hold.released",
        "unit.hold.expired",
    } <= actions
