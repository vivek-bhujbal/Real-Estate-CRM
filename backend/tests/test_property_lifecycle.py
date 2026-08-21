from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.entities import (
    AuditLog,
    Booking,
    Customer,
    CustomerDocument,
    CustomerLedger,
    Installment,
    PaymentPlan,
    Project,
    Unit,
)
from app.models.enums import (
    BookingStatus,
    DocumentStatus,
    InstallmentStatus,
    LedgerEntryType,
    RecordStatus,
    UnitStatus,
)


async def _register(client: AsyncClient) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Property Lifecycle Workspace",
            "organization_slug": "property-lifecycle-workspace",
            "admin_full_name": "Property Lifecycle Administrator",
            "admin_email": "lifecycle-admin@example.com",
            "password": "Secure-property-lifecycle-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _approver(client: AsyncClient, admin: dict[str, str]) -> tuple[dict[str, str], str]:
    permissions = [
        "possession.view",
        "possession.approve",
        "agreements.approve",
        "construction.approve",
        "collections.approve",
    ]
    role = await client.post(
        "/api/v1/rbac/roles",
        headers=admin,
        json={"name": "Property Lifecycle Approver", "permission_codes": permissions},
    )
    assert role.status_code == 201, role.text
    password = "Secure-property-approver-password-42!"
    user = await client.post(
        "/api/v1/organization/users",
        headers=admin,
        json={
            "full_name": "Independent Possession Approver",
            "email": "lifecycle-approver@example.com",
            "password": password,
            "role_ids": [role.json()["id"]],
            "is_active": True,
        },
    )
    assert user.status_code == 201, user.text
    await client.put(
        f"/api/v1/rbac/users/{user.json()['id']}/roles",
        headers=admin,
        json={"role_ids": [role.json()["id"]]},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "property-lifecycle-workspace",
            "email": "lifecycle-approver@example.com",
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user.json()["id"]


async def _booking(org: str, admin_id: str) -> str:
    now = datetime.now(UTC).replace(tzinfo=None)
    async with SessionFactory() as db:
        customer = Customer(
            organization_id=org,
            full_name="Possession Customer",
            email="possession-customer@example.com",
            status="ACTIVE",
        )
        project = Project(
            organization_id=org,
            name="Possession Project",
            code="POSSESSION-PROJECT",
            default_currency="INR",
        )
        db.add_all([customer, project])
        await db.flush()
        unit = Unit(
            organization_id=org,
            project_id=project.id,
            unit_number="P-1001",
            status=UnitStatus.BOOKED,
            base_price=Decimal("100000.00"),
            currency="INR",
        )
        db.add(unit)
        await db.flush()
        booking = Booking(
            organization_id=org,
            unit_id=unit.id,
            customer_id=customer.id,
            booked_by_user_id=admin_id,
            booking_number="POS-BOOK-001",
            status=BookingStatus.CONFIRMED,
            booking_amount=Decimal("10000.00"),
            agreed_price=Decimal("100000.00"),
            discount_amount=Decimal("0.00"),
            currency="INR",
            active_unit_key=unit.id,
            booked_at=now,
        )
        db.add(booking)
        await db.flush()
        plan = PaymentPlan(
            organization_id=org,
            booking_id=booking.id,
            name="Construction linked plan",
            status=RecordStatus.ACTIVE,
            currency="INR",
            total_amount=Decimal("100000.00"),
            effective_from=date.today(),
        )
        db.add(plan)
        await db.flush()
        db.add_all(
            [
                Installment(
                    organization_id=org,
                    payment_plan_id=plan.id,
                    sequence=1,
                    name="Final installment",
                    due_date=date.today(),
                    amount=Decimal("100000.00"),
                    paid_amount=Decimal("100000.00"),
                    status=InstallmentStatus.PAID,
                ),
                CustomerLedger(
                    organization_id=org,
                    customer_id=customer.id,
                    booking_id=booking.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=Decimal("100000.00"),
                    currency="INR",
                    description="Booked unit agreed value",
                    idempotency_key="possession-booking-debit",
                    posted_at=now,
                ),
                CustomerLedger(
                    organization_id=org,
                    customer_id=customer.id,
                    booking_id=booking.id,
                    entry_type=LedgerEntryType.CREDIT,
                    amount=Decimal("100000.00"),
                    currency="INR",
                    description="Verified final payment",
                    idempotency_key="possession-booking-credit",
                    posted_at=now,
                ),
                CustomerDocument(
                    organization_id=org,
                    customer_id=customer.id,
                    booking_id=booking.id,
                    document_set_id="possession-kyc-set",
                    current_version_key="possession-kyc-current",
                    version=1,
                    is_current=True,
                    document_type="PAN",
                    status=DocumentStatus.VERIFIED,
                    reviewed_by_user_id=admin_id,
                    reviewed_at=now,
                ),
            ]
        )
        await db.commit()
        return booking.id


async def test_post_booking_gates_override_handover_and_audit(client: AsyncClient) -> None:
    admin, session = await _register(client)
    approver, _ = await _approver(client, admin)
    org = session["user"]["organization"]["id"]
    booking_id = await _booking(org, session["user"]["id"])

    created = await client.post(
        f"/api/v1/property-lifecycle/bookings/{booking_id}", headers=admin, json={}
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case"]["id"]
    blocked = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/possession/offer",
        headers=admin,
        json={"notes": "Must remain blocked"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "POSSESSION_CONDITIONS_INCOMPLETE"

    override = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/overrides",
        headers=admin,
        json={"reason": "Regulatory occupancy deadline requires controlled early possession"},
    )
    assert override.status_code == 201, override.text
    override_id = override.json()["overrides"][0]["id"]
    self_approval = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/overrides/{override_id}/decision",
        headers=admin,
        json={"status": "APPROVED", "notes": "Requester self approval attempt"},
    )
    assert self_approval.status_code == 403
    approved = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/overrides/{override_id}/decision",
        headers=approver,
        json={"status": "APPROVED", "notes": "Risk reviewed and exception explicitly approved"},
    )
    assert approved.status_code == 200, approved.text
    offered = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/possession/offer",
        headers=admin,
        json={"notes": "Possession offered under approved exception"},
    )
    assert offered.status_code == 200, offered.text
    assert offered.json()["possession"]["readiness_override_id"] == override_id

    agreement = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/agreement",
        headers=admin,
        json={"agreement_number": "AGR-POS-001", "notes": "Customer sale agreement"},
    )
    assert agreement.status_code == 201, agreement.text
    upload = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/agreement/upload",
        headers=admin,
        files={"file": ("signed-agreement.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    for status, registration in (
        ("ISSUED", None),
        ("SIGNED", None),
        ("REGISTERED", "REG-POS-001"),
    ):
        transitioned = await client.post(
            f"/api/v1/property-lifecycle/{case_id}/agreement/transition",
            headers=approver,
            json={
                "status": status,
                "registration_number": registration,
                "notes": f"Agreement {status.lower()}",
            },
        )
        assert transitioned.status_code == 200, transitioned.text

    construction = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/construction",
        headers=admin,
        json={
            "title": "Construction completion",
            "description": "Occupancy-ready construction milestone completed",
            "progress_percent": "100.00",
            "update_date": str(date.today()),
        },
    )
    assert construction.status_code == 201, construction.text
    update_id = construction.json()["construction_updates"][0]["id"]
    published = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/construction/{update_id}/publish",
        headers=approver,
    )
    assert published.status_code == 200, published.text
    demand = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/final-demand",
        headers=admin,
        json={
            "demand_number": "FINAL-POS-001",
            "issue_date": str(date.today()),
            "due_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert demand.status_code == 201, demand.text
    assert demand.json()["final_demand"]["amount"] == "0.00"
    certificate = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/no-dues", headers=approver
    )
    assert certificate.status_code == 201, certificate.text

    snag = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/snags",
        headers=admin,
        json={
            "area": "Living room",
            "description": "Window latch requires alignment",
            "severity": "LOW",
        },
    )
    snag_id = snag.json()["snags"][0]["id"]
    for status, notes in (
        ("IN_PROGRESS", "Assigned to finishing contractor"),
        ("RESOLVED", "Latch aligned and tested"),
        ("ACCEPTED", "Customer accepted the completed repair"),
    ):
        snag = await client.post(
            f"/api/v1/property-lifecycle/{case_id}/snags/{snag_id}/decision",
            headers=admin,
            json={"status": status, "notes": notes},
        )
        assert snag.status_code == 200, snag.text

    scheduled_at = datetime.now(UTC) + timedelta(days=2)
    scheduled = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/possession/schedule",
        headers=admin,
        json={"scheduled_at": scheduled_at.isoformat(), "notes": "Customer confirmed schedule"},
    )
    assert scheduled.status_code == 200, scheduled.text
    completed = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/possession/complete",
        headers=admin,
        json={"notes": "Physical possession completed"},
    )
    assert completed.status_code == 200, completed.text
    handover = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/handover",
        headers=admin,
        json={"notes": "Handover checklist initiated"},
    )
    assert handover.status_code == 201, handover.text
    acknowledgement_blocked = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/handover/acknowledge",
        headers=admin,
        json={"customer_name": "Possession Customer", "notes": "Accepted all documents"},
    )
    assert acknowledgement_blocked.status_code == 409
    for document in handover.json()["handover"]["documents"]:
        uploaded = await client.post(
            f"/api/v1/property-lifecycle/{case_id}/handover/documents/{document['id']}/upload",
            headers=admin,
            files={
                "file": (
                    f"{document['document_type'].lower()}.pdf",
                    b"%PDF-1.4\n%%EOF",
                    "application/pdf",
                )
            },
        )
        assert uploaded.status_code == 200, uploaded.text
    acknowledged = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/handover/acknowledge",
        headers=admin,
        json={
            "customer_name": "Possession Customer",
            "notes": "Customer received keys and required handover documents",
        },
    )
    assert acknowledged.status_code == 200, acknowledged.text
    final = await client.post(
        f"/api/v1/property-lifecycle/{case_id}/handover/complete", headers=approver
    )
    assert final.status_code == 200, final.text
    assert final.json()["case"]["stage"] == "COMPLETED"

    secure_download = await client.get(
        f"/api/v1/property-lifecycle/{case_id}/no-dues/download", headers=admin
    )
    assert secure_download.status_code == 200
    assert secure_download.content.startswith(b"%PDF-")
    private_download = await client.get(f"/api/v1/property-lifecycle/{case_id}/agreement/download")
    assert private_download.status_code == 401

    async with SessionFactory() as db:
        actions = set(await db.scalars(select(AuditLog.action)))
    assert {
        "property_lifecycle.created",
        "property_lifecycle.agreement.status_changed",
        "property_lifecycle.construction.published",
        "property_lifecycle.final_demand.issued",
        "property_lifecycle.no_dues.issued",
        "property_lifecycle.possession_override.requested",
        "property_lifecycle.possession_override.decided",
        "property_lifecycle.possession.complete",
        "property_lifecycle.handover.acknowledged",
        "property_lifecycle.handover.completed",
    }.issubset(actions)
