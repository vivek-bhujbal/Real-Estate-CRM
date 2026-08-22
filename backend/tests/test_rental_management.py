from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models.entities import AuditLog, Booking, Lease, RentalInvoice, RentalProperty
from app.models.enums import LeaseStatus, RentalPropertyStatus


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "rental-operations",
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


async def test_complete_rental_lifecycle_isolated_from_sales(client: AsyncClient) -> None:
    registration = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Rental Operations",
            "organization_slug": "rental-operations",
            "admin_full_name": "Rental Administrator",
            "admin_email": "rental-admin@example.com",
            "password": "Secure-rental-admin-password-42!",
        },
    )
    assert registration.status_code == 201, registration.text
    session = registration.json()
    admin = {"Authorization": f"Bearer {session['access_token']}"}
    org_id = str(session["user"]["organization_id"])

    roles = (await client.get("/api/v1/rbac/roles", headers=admin)).json()
    role_ids = {item["name"]: item["id"] for item in roles}
    manager_password = "Secure-rental-manager-password-42!"
    tenant_password = "Secure-rental-tenant-password-42!"
    other_password = "Secure-other-tenant-password-42!"
    await _user(
        client,
        admin,
        name="Independent Property Manager",
        email="rental-manager@example.com",
        password=manager_password,
        role_id=role_ids["Property Manager"],
    )
    tenant_user_id = await _user(
        client,
        admin,
        name="Rental Tenant",
        email="tenant@example.com",
        password=tenant_password,
        role_id=role_ids["Tenant"],
    )
    other_user_id = await _user(
        client,
        admin,
        name="Other Rental Tenant",
        email="other-tenant@example.com",
        password=other_password,
        role_id=role_ids["Tenant"],
    )
    manager = await _login(client, "rental-manager@example.com", manager_password)
    tenant_headers = await _login(client, "tenant@example.com", tenant_password)
    other_headers = await _login(client, "other-tenant@example.com", other_password)

    property_response = await client.post(
        "/api/v1/rentals/properties",
        headers=admin,
        json={
            "code": "RENT-A-101",
            "name": "Lakeside Rental Apartment",
            "property_type": "Apartment",
            "address_line1": "101 Lakeside Road",
            "city": "Pune",
            "state": "Maharashtra",
            "postal_code": "411001",
            "country": "India",
            "bedrooms": 2,
            "bathrooms": 2,
            "area_sqft": "980.00",
            "amenities": ["Parking", "Security"],
            "default_monthly_rent": "30000.00",
            "default_security_deposit": "90000.00",
            "currency": "INR",
        },
    )
    assert property_response.status_code == 201, property_response.text
    property_id = property_response.json()["id"]

    tenant_response = await client.post(
        "/api/v1/rentals/tenants",
        headers=admin,
        json={
            "user_id": tenant_user_id,
            "full_name": "Rental Tenant",
            "email": "tenant@example.com",
            "phone": "+919876543210",
            "identity_type": "PASSPORT",
            "identity_reference": "RENTAL-KYC-REF",
        },
    )
    assert tenant_response.status_code == 201, tenant_response.text
    tenant_id = tenant_response.json()["id"]
    other_tenant = await client.post(
        "/api/v1/rentals/tenants",
        headers=admin,
        json={
            "user_id": other_user_id,
            "full_name": "Other Rental Tenant",
            "email": "other-tenant@example.com",
            "phone": "+919876543211",
        },
    )
    assert other_tenant.status_code == 201, other_tenant.text

    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=364)
    lease_response = await client.post(
        "/api/v1/rentals/leases",
        headers=admin,
        json={
            "tenant_id": tenant_id,
            "property_id": property_id,
            "lease_number": "LEASE-2026-001",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "monthly_rent": "30000.00",
            "security_deposit": "90000.00",
            "currency": "INR",
            "rent_due_day": 5,
            "notice_period_days": 30,
            "terms": "Residential rental use only.",
        },
    )
    assert lease_response.status_code == 201, lease_response.text
    lease_id = lease_response.json()["lease"]["id"]
    document_id = lease_response.json()["documents"][0]["id"]

    async with SessionFactory() as db:
        stored_lease = await db.get(Lease, lease_id)
        assert stored_lease is not None
        assert stored_lease.property_id == property_id
        assert stored_lease.unit_id is None
        assert int(await db.scalar(select(func.count(Booking.id))) or 0) == 0

    sent = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/transition",
        headers=admin,
        json={"status": "PENDING_SIGNATURE", "notes": "Issued to tenant"},
    )
    assert sent.status_code == 200, sent.text
    upload = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/documents/{document_id}/upload",
        headers=admin,
        files={"file": ("signed-lease.pdf", b"%PDF-1.4 signed rental lease", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    self_review = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/documents/{document_id}/decision",
        headers=admin,
        json={"status": "VERIFIED", "notes": "Attempted self review"},
    )
    assert self_review.status_code == 403
    verified = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/documents/{document_id}/decision",
        headers=manager,
        json={"status": "VERIFIED", "notes": "Signature and parties independently verified"},
    )
    assert verified.status_code == 200, verified.text
    signed = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/transition",
        headers=manager,
        json={"status": "SIGNED", "notes": "Lease approved for move-in"},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["lease"]["status"] == "MOVE_IN_PENDING"
    assert len(signed.json()["schedule"]) == 12

    tenant_list = await client.get("/api/v1/rentals/leases", headers=tenant_headers)
    assert tenant_list.status_code == 200
    assert [item["id"] for item in tenant_list.json()["items"]] == [lease_id]
    other_list = await client.get("/api/v1/rentals/leases", headers=other_headers)
    assert other_list.status_code == 200
    assert other_list.json()["items"] == []
    hidden_detail = await client.get(f"/api/v1/rentals/leases/{lease_id}", headers=other_headers)
    assert hidden_detail.status_code == 404
    assert (
        len(
            (await client.get("/api/v1/rentals/properties", headers=tenant_headers)).json()["items"]
        )
        == 1
    )
    assert (await client.get("/api/v1/rentals/properties", headers=other_headers)).json()[
        "items"
    ] == []

    move_request = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/moves",
        headers=tenant_headers,
        json={
            "move_type": "MOVE_IN",
            "scheduled_at": f"{start.isoformat()}T10:00:00+05:30",
            "notes": "Tenant requested key handover",
        },
    )
    assert move_request.status_code == 201, move_request.text
    move_id = move_request.json()["moves"][0]["id"]
    approved_move = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/moves/{move_id}/decision",
        headers=manager,
        json={"status": "APPROVED", "notes": "Move-in inspection scheduled"},
    )
    assert approved_move.status_code == 200, approved_move.text
    completed_move = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/moves/{move_id}/complete",
        headers=manager,
        json={
            "checklist": {"keys_handed_over": True, "inspection_completed": True},
            "meter_readings": {"electricity": "1402"},
            "notes": "Tenant acknowledgement recorded",
        },
    )
    assert completed_move.status_code == 200, completed_move.text
    assert completed_move.json()["lease"]["status"] == "ACTIVE"

    schedule = completed_move.json()["schedule"][0]
    invoice_response = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/invoices",
        headers=admin,
        json={
            "schedule_item_id": schedule["id"],
            "invoice_number": "RENT-INV-001",
            "issue_date": date.today().isoformat(),
            "due_date": schedule["due_date"],
            "tax_amount": "1500.00",
        },
    )
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()["invoices"][0]
    assert Decimal(invoice["amount"]) == Decimal("30000.00")
    assert Decimal(invoice["total"]) == Decimal("31500.00")

    payment_response = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/invoices/{invoice['id']}/payments",
        headers=tenant_headers,
        json={
            "amount": "31500.00",
            "method": "BANK_TRANSFER",
            "reference_number": "RENT-TXN-001",
            "idempotency_key": "rental-payment-001",
        },
    )
    assert payment_response.status_code == 200, payment_response.text
    payment_id = payment_response.json()["payments"][0]["id"]
    payment_decision = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/payments/{payment_id}/decision",
        headers=manager,
        json={"status": "COMPLETED", "notes": "Bank credit independently reconciled"},
    )
    assert payment_decision.status_code == 200, payment_decision.text
    assert payment_decision.json()["invoices"][0]["status"] == "PAID"

    maintenance = await client.post(
        "/api/v1/rentals/maintenance",
        headers=tenant_headers,
        json={
            "lease_id": lease_id,
            "title": "Kitchen tap leak",
            "description": "Slow leak under the kitchen tap requires inspection.",
        },
    )
    assert maintenance.status_code == 201, maintenance.text
    assert maintenance.json()["maintenance"][0]["rental_property_id"] == property_id

    renewal = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/renewals",
        headers=tenant_headers,
        json={
            "proposed_end_date": (end + timedelta(days=365)).isoformat(),
            "proposed_monthly_rent": "32000.00",
            "reason": "Tenant requests a further twelve-month term.",
        },
    )
    assert renewal.status_code == 201, renewal.text
    renewal_id = renewal.json()["renewals"][0]["id"]
    renewal_decision = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/renewals/{renewal_id}/decision",
        headers=manager,
        json={"status": "APPROVED", "notes": "Renewal terms approved by property manager"},
    )
    assert renewal_decision.status_code == 200, renewal_decision.text
    assert renewal_decision.json()["renewals"][0]["status"] == "COMPLETED"
    assert len(renewal_decision.json()["schedule"]) > 12

    move_out = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/moves",
        headers=tenant_headers,
        json={
            "move_type": "MOVE_OUT",
            "scheduled_at": f"{end.isoformat()}T10:00:00+05:30",
            "notes": "Tenant served move-out notice",
        },
    )
    assert move_out.status_code == 201, move_out.text
    move_out_id = move_out.json()["moves"][0]["id"]
    assert (
        await client.post(
            f"/api/v1/rentals/leases/{lease_id}/moves/{move_out_id}/decision",
            headers=manager,
            json={"status": "APPROVED", "notes": "Move-out inspection approved"},
        )
    ).status_code == 200
    finished = await client.post(
        f"/api/v1/rentals/leases/{lease_id}/moves/{move_out_id}/complete",
        headers=manager,
        json={
            "checklist": {"keys_returned": True, "inspection_completed": True},
            "meter_readings": {"electricity": "1780"},
            "notes": "Move-out complete",
        },
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["lease"]["status"] == "TERMINATED"

    async with SessionFactory() as db:
        stored_property = await db.get(RentalProperty, property_id)
        stored_lease = await db.get(Lease, lease_id)
        assert (
            stored_property is not None and stored_property.status == RentalPropertyStatus.AVAILABLE
        )
        assert stored_lease is not None and stored_lease.status == LeaseStatus.TERMINATED
        assert int(await db.scalar(select(func.count(RentalInvoice.id))) or 0) == 1
        actions = set(
            await db.scalars(select(AuditLog.action).where(AuditLog.organization_id == org_id))
        )
        assert {
            "rental.lease.created",
            "rental.lease_document.reviewed",
            "rental.invoice.issued",
            "rental.payment.reviewed",
            "rental.renewal.decided",
            "rental.move.completed",
            "rental.maintenance.created",
        } <= actions
