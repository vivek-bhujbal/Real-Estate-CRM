from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.entities import (
    AuditLog,
    Booking,
    Customer,
    CustomerLedger,
    Installment,
    PaymentPlan,
    Project,
    Quotation,
    Unit,
)
from app.models.enums import (
    BookingStatus,
    InstallmentStatus,
    LedgerEntryType,
    QuotationStatus,
    RecordStatus,
    UnitStatus,
)


async def _register(client: AsyncClient) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Post Sales Workspace",
            "organization_slug": "post-sales-workspace",
            "admin_full_name": "Post Sales Administrator",
            "admin_email": "post-sales-admin@example.com",
            "password": "Secure-post-sales-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _workflow_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    name: str,
    email: str,
    role_name: str,
    permission_codes: list[str],
) -> dict[str, str]:
    role = await client.post(
        "/api/v1/rbac/roles",
        headers=admin_headers,
        json={"name": role_name, "permission_codes": permission_codes},
    )
    assert role.status_code == 201, role.text
    password = "Secure-workflow-user-password-42!"
    user = await client.post(
        "/api/v1/organization/users",
        headers=admin_headers,
        json={
            "full_name": name,
            "email": email,
            "password": password,
            "role_ids": [role.json()["id"]],
            "is_active": True,
        },
    )
    assert user.status_code == 201, user.text
    assigned = await client.put(
        f"/api/v1/rbac/users/{user.json()['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [role.json()["id"]]},
    )
    assert assigned.status_code == 200, assigned.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "post-sales-workspace",
            "email": email,
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _setup(org_id: str, admin_id: str) -> dict[str, str]:
    async with SessionFactory() as db:
        customer = Customer(
            organization_id=org_id, full_name="Post Sales Customer", status="ACTIVE"
        )
        project = Project(
            organization_id=org_id,
            name="Post Sales Project",
            code="PST",
            default_currency="INR",
        )
        db.add_all([customer, project])
        await db.flush()
        cancel_unit = Unit(
            organization_id=org_id,
            project_id=project.id,
            unit_number="C-101",
            status=UnitStatus.BOOKED,
            currency="INR",
        )
        transfer_old = Unit(
            organization_id=org_id,
            project_id=project.id,
            unit_number="T-201",
            status=UnitStatus.BOOKED,
            currency="INR",
        )
        transfer_new = Unit(
            organization_id=org_id,
            project_id=project.id,
            unit_number="T-301",
            status=UnitStatus.AVAILABLE,
            currency="INR",
        )
        db.add_all([cancel_unit, transfer_old, transfer_new])
        await db.flush()
        cancellation_booking = Booking(
            organization_id=org_id,
            unit_id=cancel_unit.id,
            customer_id=customer.id,
            booked_by_user_id=admin_id,
            booking_number="CAN-BOOK-001",
            status=BookingStatus.CONFIRMED,
            booking_amount=Decimal("100"),
            agreed_price=Decimal("1000"),
            discount_amount=Decimal("0"),
            currency="INR",
            active_unit_key=cancel_unit.id,
        )
        transfer_booking = Booking(
            organization_id=org_id,
            unit_id=transfer_old.id,
            customer_id=customer.id,
            booked_by_user_id=admin_id,
            booking_number="UTR-BOOK-001",
            status=BookingStatus.CONFIRMED,
            booking_amount=Decimal("100"),
            agreed_price=Decimal("1000"),
            discount_amount=Decimal("0"),
            currency="INR",
            active_unit_key=transfer_old.id,
        )
        db.add_all([cancellation_booking, transfer_booking])
        await db.flush()
        quote = Quotation(
            organization_id=org_id,
            customer_id=customer.id,
            project_id=project.id,
            unit_id=transfer_new.id,
            created_by_user_id=admin_id,
            quotation_number="TRANSFER-Q-001",
            version=1,
            status=QuotationStatus.ACCEPTED,
            currency="INR",
            subtotal=Decimal("1200"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total=Decimal("1200"),
            final_agreed_value=Decimal("1200"),
            booking_amount=Decimal("120"),
            pricing_snapshot={"source": "accepted quotation"},
            valid_until=date.today() + timedelta(days=30),
        )
        db.add(quote)
        cancellation_installment_id = ""
        for booking in (cancellation_booking, transfer_booking):
            plan = PaymentPlan(
                organization_id=org_id,
                booking_id=booking.id,
                name=f"Original {booking.booking_number}",
                status=RecordStatus.ACTIVE,
                currency="INR",
                total_amount=Decimal("1000"),
                effective_from=date.today(),
            )
            db.add(plan)
            await db.flush()
            installment = Installment(
                organization_id=org_id,
                payment_plan_id=plan.id,
                sequence=1,
                name="Original schedule",
                due_date=date.today() + timedelta(days=30),
                amount=Decimal("1000"),
                paid_amount=Decimal("0"),
                status=InstallmentStatus.SCHEDULED,
            )
            db.add(installment)
            await db.flush()
            if booking.id == cancellation_booking.id:
                cancellation_installment_id = installment.id
            db.add(
                CustomerLedger(
                    organization_id=org_id,
                    customer_id=customer.id,
                    booking_id=booking.id,
                    entry_type=LedgerEntryType.DEBIT,
                    amount=Decimal("1000"),
                    currency="INR",
                    description="Agreed booking value",
                    idempotency_key=f"booking:{booking.id}:agreed-value",
                    posted_at=booking.created_at,
                )
            )
        await db.commit()
        return {
            "cancellation_booking": cancellation_booking.id,
            "cancellation_unit": cancel_unit.id,
            "cancellation_installment": cancellation_installment_id,
            "transfer_booking": transfer_booking.id,
            "transfer_old": transfer_old.id,
            "transfer_new": transfer_new.id,
            "transfer_quote": quote.id,
        }


async def test_cancellation_refund_and_unit_transfer_are_governed_and_audited(
    client: AsyncClient,
) -> None:
    admin_headers, session = await _register(client)
    reviewer_headers = await _workflow_user(
        client,
        admin_headers,
        name="Independent Reviewer",
        email="post-sales-reviewer@example.com",
        role_name="Post Sales Reviewer",
        permission_codes=["bookings.view", "bookings.update", "collections.view"],
    )
    approver_headers = await _workflow_user(
        client,
        admin_headers,
        name="Independent Approver",
        email="post-sales-approver@example.com",
        role_name="Post Sales Approver",
        permission_codes=[
            "bookings.view",
            "bookings.approve",
            "collections.view",
            "collections.approve",
            "payments.approve",
        ],
    )
    setup = await _setup(session["user"]["organization"]["id"], session["user"]["id"])

    payment = await client.post(
        f"/api/v1/collections/bookings/{setup['cancellation_booking']}/payments",
        headers=admin_headers,
        json={
            "amount": "250",
            "method": "BANK_TRANSFER",
            "reference_number": "CAN-PAY-250",
            "idempotency_key": "post-sales-cancellation-payment",
        },
    )
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["payments"][0]["id"]
    reconciled = await client.post(
        f"/api/v1/collections/payments/{payment_id}/reconciliations",
        headers=admin_headers,
        json={
            "received_amount": "250",
            "external_reference": "CAN-STMT-250",
            "idempotency_key": "post-sales-cancellation-reconciliation",
        },
    )
    assert reconciled.status_code == 201, reconciled.text
    allocated = await client.post(
        f"/api/v1/collections/payments/{payment_id}/allocate",
        headers=admin_headers,
        json={"installment_ids": [setup["cancellation_installment"]]},
    )
    assert allocated.status_code == 200, allocated.text

    requested = await client.post(
        f"/api/v1/post-sales/bookings/{setup['cancellation_booking']}/cancellations",
        headers=admin_headers,
        json={"reason": "Customer formally requested contract cancellation"},
    )
    assert requested.status_code == 201, requested.text
    cancellation_id = requested.json()["id"]
    reviewed = await client.post(
        f"/api/v1/post-sales/cancellations/{cancellation_id}/review",
        headers=reviewer_headers,
        json={
            "deduction_type": "FIXED",
            "deduction_value": "50",
            "notes": "Request evidence verified",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    self_approval = await client.post(
        f"/api/v1/post-sales/cancellations/{cancellation_id}/decision",
        headers=reviewer_headers,
        json={"status": "APPROVED", "notes": "Reviewer self approval attempt"},
    )
    assert self_approval.status_code == 403
    approved = await client.post(
        f"/api/v1/post-sales/cancellations/{cancellation_id}/decision",
        headers=approver_headers,
        json={"status": "APPROVED", "notes": "Cancellation approved"},
    )
    assert approved.status_code == 200, approved.text
    completed = await client.post(
        f"/api/v1/post-sales/cancellations/{cancellation_id}/complete",
        headers=approver_headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["refund_amount"] == "200.00"
    assert completed.json()["refund"]["status"] == "PROCESSING"
    refund_id = completed.json()["refund"]["id"]
    processed_refund = await client.post(
        f"/api/v1/collections/refunds/{refund_id}/process",
        headers=approver_headers,
        json={"reference_number": "CAN-REFUND-200"},
    )
    assert processed_refund.status_code == 200, processed_refund.text
    assert processed_refund.json()["refunds"][0]["status"] == "COMPLETED"
    document = await client.get(
        f"/api/v1/post-sales/cancellations/{cancellation_id}/document",
        headers=admin_headers,
    )
    assert document.status_code == 200
    assert document.content.startswith(b"%PDF-")

    transfer = await client.post(
        f"/api/v1/post-sales/bookings/{setup['transfer_booking']}/transfers",
        headers=admin_headers,
        json={
            "quotation_id": setup["transfer_quote"],
            "reason": "Customer requested a higher-floor unit",
            "revised_payment_plan": {
                "name": "Revised transfer plan",
                "effective_from": str(date.today()),
                "installments": [
                    {
                        "name": "Revised balance",
                        "due_date": str(date.today() + timedelta(days=30)),
                        "amount": "1200",
                    }
                ],
            },
        },
    )
    assert transfer.status_code == 201, transfer.text
    transfer_id = transfer.json()["id"]
    reviewed_transfer = await client.post(
        f"/api/v1/post-sales/transfers/{transfer_id}/review",
        headers=reviewer_headers,
        json={"notes": "Target unit and commercial terms verified"},
    )
    assert reviewed_transfer.status_code == 200, reviewed_transfer.text
    approved_transfer = await client.post(
        f"/api/v1/post-sales/transfers/{transfer_id}/decision",
        headers=approver_headers,
        json={"status": "APPROVED", "notes": "Transfer approved"},
    )
    assert approved_transfer.status_code == 200, approved_transfer.text
    completed_transfer = await client.post(
        f"/api/v1/post-sales/transfers/{transfer_id}/complete",
        headers=approver_headers,
    )
    assert completed_transfer.status_code == 200, completed_transfer.text
    assert completed_transfer.json()["status"] == "COMPLETED"
    assert completed_transfer.json()["price_difference"] == "200.00"
    transfer_document = await client.get(
        f"/api/v1/post-sales/transfers/{transfer_id}/document",
        headers=admin_headers,
    )
    assert transfer_document.status_code == 200
    assert transfer_document.content.startswith(b"%PDF-")

    async with SessionFactory() as db:
        cancelled_booking = await db.get(Booking, setup["cancellation_booking"])
        cancellation_unit = await db.get(Unit, setup["cancellation_unit"])
        transferred_booking = await db.get(Booking, setup["transfer_booking"])
        old_unit = await db.get(Unit, setup["transfer_old"])
        new_unit = await db.get(Unit, setup["transfer_new"])
        actions = set(await db.scalars(select(AuditLog.action)))
    assert cancelled_booking and cancelled_booking.status == BookingStatus.CANCELLED
    assert cancellation_unit and cancellation_unit.status == UnitStatus.CANCELLED_RELEASED
    assert transferred_booking and transferred_booking.unit_id == setup["transfer_new"]
    assert transferred_booking.agreed_price == Decimal("1200.00")
    assert old_unit and old_unit.status == UnitStatus.CANCELLED_RELEASED
    assert new_unit and new_unit.status == UnitStatus.BOOKED
    assert {
        "cancellation.requested",
        "cancellation.reviewed",
        "cancellation.decided",
        "cancellation.completed",
        "unit_transfer.requested",
        "unit_transfer.reviewed",
        "unit_transfer.decided",
        "unit_transfer.completed",
    }.issubset(actions)
