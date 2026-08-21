import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.entities import (
    AuditLog,
    ChannelPartner,
    CommissionStructure,
    Customer,
    CustomerDocument,
    PartnerProject,
    Project,
    Quotation,
    Unit,
    UnitHold,
)
from app.models.enums import (
    DocumentStatus,
    HoldStatus,
    HoldType,
    PartnerStatus,
    QuotationStatus,
    UnitStatus,
)


async def _setup(client: AsyncClient) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    registered = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Booking Workspace",
            "organization_slug": "booking-workspace",
            "admin_full_name": "Booking Administrator",
            "admin_email": "booking-admin@example.com",
            "password": "Secure-booking-admin-42!",
        },
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    admin = {"Authorization": f"Bearer {body['access_token']}"}
    approver_user = await client.post(
        "/api/v1/organization/users",
        headers=admin,
        json={
            "full_name": "Booking Approver",
            "email": "booking-approver@example.com",
            "password": "Secure-booking-approver-42!",
            "is_active": True,
        },
    )
    role = await client.post(
        "/api/v1/rbac/roles",
        headers=admin,
        json={
            "name": "Booking Approval Test",
            "permission_codes": ["bookings.view", "bookings.approve"],
        },
    )
    assert approver_user.status_code == role.status_code == 201
    assigned = await client.put(
        f"/api/v1/rbac/users/{approver_user.json()['id']}/roles",
        headers=admin,
        json={"role_ids": [role.json()["id"]]},
    )
    assert assigned.status_code == 200
    logged_in = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "booking-workspace",
            "email": "booking-approver@example.com",
            "password": "Secure-booking-approver-42!",
        },
    )
    assert logged_in.status_code == 200
    return (
        admin,
        {"Authorization": f"Bearer {logged_in.json()['access_token']}"},
        {
            "organization_id": body["user"]["organization"]["id"],
            "admin_id": body["user"]["id"],
            "approver_id": approver_user.json()["id"],
        },
    )


async def _eligible_records(ids: dict[str, str]) -> dict[str, str]:
    organization_id = ids["organization_id"]
    customer_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    unit_id = str(uuid.uuid4())
    quote_id = str(uuid.uuid4())
    hold_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    broker_id = str(uuid.uuid4())
    now = datetime.now(UTC).replace(tzinfo=None)
    async with SessionFactory() as db:
        db.add_all(
            [
                Customer(
                    id=customer_id,
                    organization_id=organization_id,
                    full_name="Booking Buyer",
                    email="booking-buyer@example.com",
                ),
                Project(
                    id=project_id,
                    organization_id=organization_id,
                    name="Booking Project",
                    code="BOOKING-PROJECT",
                    default_currency="INR",
                ),
                ChannelPartner(
                    id=broker_id,
                    organization_id=organization_id,
                    code="BROKER-1",
                    name="Verified Broker",
                    status=PartnerStatus.ACTIVE,
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                PartnerProject(
                    organization_id=organization_id,
                    channel_partner_id=broker_id,
                    project_id=project_id,
                ),
                CommissionStructure(
                    organization_id=organization_id,
                    channel_partner_id=broker_id,
                    project_id=project_id,
                    name="Booking test commission",
                    rate_percent=Decimal("2.00"),
                    calculation_basis="AGREED_VALUE",
                    effective_from=date.today(),
                    is_active=True,
                    active_scope_key=f"{broker_id}:{project_id}",
                ),
            ]
        )
        db.add(
            Unit(
                id=unit_id,
                organization_id=organization_id,
                project_id=project_id,
                unit_number="BOOK-101",
                status=UnitStatus.SOFT_HOLD,
                base_price=Decimal("10000000"),
                currency="INR",
            )
        )
        db.add(
            Quotation(
                id=quote_id,
                organization_id=organization_id,
                customer_id=customer_id,
                project_id=project_id,
                unit_id=unit_id,
                created_by_user_id=ids["admin_id"],
                quotation_number="QT-BOOK-1",
                version=1,
                status=QuotationStatus.ACCEPTED,
                currency="INR",
                subtotal=Decimal("10500000"),
                discount_amount=Decimal("500000"),
                tax_amount=Decimal("0"),
                total=Decimal("10000000"),
                final_agreed_value=Decimal("10000000"),
                booking_amount=Decimal("1000000"),
                valid_until=date.today() + timedelta(days=10),
            )
        )
        db.add(
            UnitHold(
                id=hold_id,
                organization_id=organization_id,
                unit_id=unit_id,
                customer_id=customer_id,
                held_by_user_id=ids["admin_id"],
                approved_by_user_id=ids["approver_id"],
                hold_type=HoldType.SOFT_HOLD,
                hold_reason="Customer completed commercial and KYC checks",
                status=HoldStatus.ACTIVE,
                starts_at=now,
                expires_at=now + timedelta(days=1),
                approved_at=now,
                active_unit_key=unit_id,
            )
        )
        db.add(
            CustomerDocument(
                id=document_id,
                organization_id=organization_id,
                customer_id=customer_id,
                uploaded_by_user_id=ids["admin_id"],
                reviewed_by_user_id=ids["approver_id"],
                document_set_id=document_id,
                current_version_key=document_id,
                version=1,
                is_current=True,
                document_type="PAN_CARD",
                file_name="pan.pdf",
                storage_key=f"test/{document_id}.private",
                content_type="application/pdf",
                size_bytes=32,
                checksum_sha256="a" * 64,
                status=DocumentStatus.VERIFIED,
                uploaded_at=now,
                review_started_at=now,
                reviewed_at=now,
            )
        )
        await db.commit()
    return {
        "customer_id": customer_id,
        "unit_id": unit_id,
        "quote_id": quote_id,
        "hold_id": hold_id,
        "broker_id": broker_id,
    }


async def test_complete_booking_flow_and_duplicate_unit_protection(client: AsyncClient) -> None:
    admin, approver, ids = await _setup(client)
    records = await _eligible_records(ids)
    options = await client.get("/api/v1/bookings/options", headers=admin)
    assert options.status_code == 200, options.text
    assert options.json()["quotations"][0]["id"] == records["quote_id"]

    payload = {
        "quotation_id": records["quote_id"],
        "unit_hold_id": records["hold_id"],
        "booking_number": "BK-COMPLETE-1",
        "salesperson_user_id": ids["admin_id"],
        "channel_partner_id": records["broker_id"],
        "joint_applicants": [
            {
                "full_name": "Joint Applicant",
                "email": "joint@example.com",
                "relationship_to_primary": "Spouse",
            }
        ],
        "financing": {
            "status": "APPLIED",
            "lender_name": "Housing Bank",
            "loan_amount": "7000000",
            "application_number": "LOAN-1",
        },
        "payment_plan": {
            "name": "Construction linked plan",
            "effective_from": str(date.today()),
            "installments": [
                {"name": "Booking amount", "due_date": str(date.today()), "amount": "1000000"},
                {
                    "name": "Balance",
                    "due_date": str(date.today() + timedelta(days=30)),
                    "amount": "9000000",
                },
            ],
        },
    }
    created = await client.post("/api/v1/bookings", headers=admin, json=payload)
    assert created.status_code == 201, created.text
    booking = created.json()
    booking_id = booking["id"]
    assert booking["status"] == "PAYMENT_PENDING"
    assert booking["agreed_price"] == "10000000.00"
    assert booking["discount_amount"] == "500000.00"
    assert booking["booking_amount"] == "1000000.00"
    assert len(booking["applicants"]) == 2
    assert booking["applicants"][0]["is_primary"] is True
    assert booking["payment_plan"]["total_amount"] == "10000000.00"
    assert booking["broker_name"] == "Verified Broker"
    assert booking["documents"][0]["status"] == "VERIFIED"

    duplicate = await client.post(
        "/api/v1/bookings", headers=admin, json={**payload, "booking_number": "BK-DUPLICATE"}
    )
    assert duplicate.status_code == 409

    payment = await client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        headers=admin,
        json={
            "installment_id": booking["payment_plan"]["installments"][0]["id"],
            "amount": "1000000",
            "method": "BANK_TRANSFER",
            "reference_number": "UTR-BOOK-1",
            "idempotency_key": "booking-payment-unique-1",
        },
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["status"] == "VERIFICATION"
    payment_id = payment.json()["payments"][0]["id"]
    reconciled = await client.post(
        f"/api/v1/collections/payments/{payment_id}/reconciliations",
        headers=admin,
        json={
            "received_amount": "1000000",
            "external_reference": "UTR-BOOK-1",
            "idempotency_key": "booking-payment-reconciliation-1",
        },
    )
    assert reconciled.status_code == 201, reconciled.text
    verified = await client.post(
        f"/api/v1/collections/payments/{payment_id}/allocate",
        headers=admin,
        json={"installment_ids": [booking["payment_plan"]["installments"][0]["id"]]},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["account"]["received"] == "1000000.00"

    financing_block = await client.post(
        f"/api/v1/bookings/{booking_id}/approval-request",
        headers=admin,
        json={"approver_user_ids": [ids["approver_id"]]},
    )
    assert financing_block.status_code == 409
    assert financing_block.json()["error"]["code"] == "FINANCING_NOT_READY"
    financed = await client.put(
        f"/api/v1/bookings/{booking_id}/financing",
        headers=admin,
        json={
            "status": "SANCTIONED",
            "lender_name": "Housing Bank",
            "loan_amount": "7000000",
            "application_number": "LOAN-1",
            "sanction_reference": "SANCTION-1",
        },
    )
    assert financed.status_code == 200

    approval_request = await client.post(
        f"/api/v1/bookings/{booking_id}/approval-request",
        headers=admin,
        json={
            "approver_user_ids": [ids["approver_id"]],
            "comments": "Commercial, KYC, and payment checks completed",
        },
    )
    assert approval_request.status_code == 200, approval_request.text
    assert approval_request.json()["status"] == "APPROVAL"
    approval_id = approval_request.json()["approvals"][0]["id"]
    confirmed = await client.post(
        f"/api/v1/bookings/{booking_id}/approvals/{approval_id}/decision",
        headers=approver,
        json={"status": "APPROVED", "comments": "Booking approved"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["booked_at"] is not None

    async with SessionFactory() as db:
        unit_status = await db.scalar(select(Unit.status).where(Unit.id == records["unit_id"]))
        actions = set(
            await db.scalars(
                select(AuditLog.action).where(
                    AuditLog.organization_id == ids["organization_id"],
                    AuditLog.action.like("booking.%"),
                )
            )
        )
    assert unit_status == UnitStatus.BOOKED
    assert {
        "booking.created",
        "booking.payment.submitted",
        "booking.payment.verified",
        "booking.financing.updated",
        "booking.approval.requested",
        "booking.approval.decided",
    }.issubset(actions)
