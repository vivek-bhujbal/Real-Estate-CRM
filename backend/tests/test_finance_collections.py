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
    Unit,
)
from app.models.enums import (
    BookingStatus,
    InstallmentStatus,
    LedgerEntryType,
    RecordStatus,
    UnitStatus,
)


async def _register(client: AsyncClient) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Finance Workspace",
            "organization_slug": "finance-workspace",
            "admin_full_name": "Finance Administrator",
            "admin_email": "finance-admin@example.com",
            "password": "Secure-finance-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


async def _approver(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    permissions = (await client.get("/api/v1/rbac/permissions", headers=headers)).json()
    codes = {item["code"]: item["id"] for item in permissions}
    role = await client.post(
        "/api/v1/rbac/roles",
        headers=headers,
        json={
            "name": "Refund Approver",
            "permission_codes": ["payments.approve", "collections.view"],
        },
    )
    assert role.status_code == 201, role.text
    user = await client.post(
        "/api/v1/organization/users",
        headers=headers,
        json={
            "full_name": "Independent Refund Approver",
            "email": "refund-approver@example.com",
            "password": "Secure-refund-approver-42!",
            "role_ids": [role.json()["id"]],
            "is_active": True,
        },
    )
    assert user.status_code == 201, user.text
    assigned = await client.put(
        f"/api/v1/rbac/users/{user.json()['id']}/roles",
        headers=headers,
        json={"role_ids": [role.json()["id"]]},
    )
    assert assigned.status_code == 200, assigned.text
    assert codes["payments.approve"]
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "finance-workspace",
            "email": "refund-approver@example.com",
            "password": "Secure-refund-approver-42!",
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _setup(org_id: str, admin_id: str) -> dict[str, str]:
    async with SessionFactory() as db:
        customer = Customer(
            organization_id=org_id, full_name="Collections Customer", status="ACTIVE"
        )
        project = Project(
            organization_id=org_id, name="Collections Project", code="COLL", default_currency="INR"
        )
        db.add_all([customer, project])
        await db.flush()
        unit = Unit(
            organization_id=org_id,
            project_id=project.id,
            unit_number="C-101",
            status=UnitStatus.BOOKED,
            currency="INR",
        )
        db.add(unit)
        await db.flush()
        booking = Booking(
            organization_id=org_id,
            unit_id=unit.id,
            customer_id=customer.id,
            booked_by_user_id=admin_id,
            booking_number="FIN-001",
            status=BookingStatus.CONFIRMED,
            booking_amount=Decimal("100"),
            agreed_price=Decimal("1000"),
            discount_amount=Decimal("0"),
            currency="INR",
            active_unit_key=unit.id,
        )
        db.add(booking)
        await db.flush()
        plan = PaymentPlan(
            organization_id=org_id,
            booking_id=booking.id,
            name="Milestone plan",
            status=RecordStatus.ACTIVE,
            currency="INR",
            total_amount=Decimal("1000"),
            effective_from=date.today() - timedelta(days=60),
        )
        db.add(plan)
        await db.flush()
        first = Installment(
            organization_id=org_id,
            payment_plan_id=plan.id,
            sequence=1,
            name="Booking milestone",
            due_date=date.today() - timedelta(days=30),
            amount=Decimal("400"),
            paid_amount=Decimal("0"),
            status=InstallmentStatus.OVERDUE,
        )
        second = Installment(
            organization_id=org_id,
            payment_plan_id=plan.id,
            sequence=2,
            name="Possession milestone",
            due_date=date.today() + timedelta(days=30),
            amount=Decimal("600"),
            paid_amount=Decimal("0"),
            status=InstallmentStatus.SCHEDULED,
        )
        db.add_all(
            [
                first,
                second,
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
                ),
            ]
        )
        await db.commit()
        return {"booking_id": booking.id, "installment_id": first.id}


async def test_finance_collection_allocation_reconciliation_charge_and_refund(
    client: AsyncClient,
) -> None:
    headers, session = await _register(client)
    approver_headers = await _approver(client, headers)
    setup = await _setup(session["user"]["organization"]["id"], session["user"]["id"])

    summary = await client.get("/api/v1/collections/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["outstanding"] == "1000.00"
    assert summary.json()["overdue"] == "400.00"

    demand = await client.post(
        f"/api/v1/collections/bookings/{setup['booking_id']}/demands",
        headers=headers,
        json={
            "installment_id": setup["installment_id"],
            "demand_number": "DEM-001",
            "issue_date": str(date.today()),
            "due_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert demand.status_code == 201, demand.text
    assert demand.json()["demands"][0]["amount"] == "400.00"

    payment = await client.post(
        f"/api/v1/collections/bookings/{setup['booking_id']}/payments",
        headers=headers,
        json={
            "amount": "250",
            "method": "BANK_TRANSFER",
            "reference_number": "BANK-250",
            "idempotency_key": "finance-payment-001",
        },
    )
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["payments"][0]["id"]
    mismatch = await client.post(
        f"/api/v1/collections/payments/{payment_id}/reconciliations",
        headers=headers,
        json={
            "received_amount": "240",
            "external_reference": "STMT-1",
            "idempotency_key": "finance-recon-001",
        },
    )
    assert mismatch.json()["reconciliations"][0]["status"] == "MISMATCHED"
    blocked = await client.post(
        f"/api/v1/collections/payments/{payment_id}/allocate",
        headers=headers,
        json={"installment_ids": [setup["installment_id"]]},
    )
    assert blocked.status_code == 409
    matched = await client.post(
        f"/api/v1/collections/payments/{payment_id}/reconciliations",
        headers=headers,
        json={
            "received_amount": "250",
            "external_reference": "STMT-2",
            "idempotency_key": "finance-recon-002",
        },
    )
    assert matched.status_code == 201
    allocated = await client.post(
        f"/api/v1/collections/payments/{payment_id}/allocate",
        headers=headers,
        json={"installment_ids": [setup["installment_id"]]},
    )
    assert allocated.status_code == 200, allocated.text
    assert allocated.json()["payments"][0]["status"] == "COMPLETED"
    assert allocated.json()["payments"][0]["receipt_number"]
    assert allocated.json()["installments"][0]["paid_amount"] == "250.00"
    assert allocated.json()["account"]["outstanding"] == "750.00"

    charge = await client.post(
        f"/api/v1/collections/installments/{setup['installment_id']}/charges",
        headers=headers,
        json={
            "charge_type": "INTEREST",
            "calculation_date": str(date.today()),
            "annual_rate_percent": "12",
            "reason": "Contractual overdue interest",
            "idempotency_key": "finance-charge-001",
        },
    )
    assert charge.status_code == 201, charge.text
    charge_id = charge.json()["charges"][0]["id"]
    assert Decimal(charge.json()["charges"][0]["amount"]) > 0
    waived = await client.post(
        f"/api/v1/collections/charges/{charge_id}/waive",
        headers=headers,
        json={"reason": "Approved customer service waiver"},
    )
    assert waived.status_code == 200
    assert waived.json()["charges"][0]["status"] == "WAIVED"

    refund = await client.post(
        f"/api/v1/collections/payments/{payment_id}/refunds",
        headers=headers,
        json={
            "amount": "100",
            "reason": "Approved booking adjustment",
            "idempotency_key": "finance-refund-001",
        },
    )
    refund_id = refund.json()["refunds"][0]["id"]
    self_decision = await client.post(
        f"/api/v1/collections/refunds/{refund_id}/decision",
        headers=headers,
        json={"status": "APPROVED", "notes": "Self approval attempt"},
    )
    assert self_decision.status_code == 403
    approved = await client.post(
        f"/api/v1/collections/refunds/{refund_id}/decision",
        headers=approver_headers,
        json={"status": "APPROVED", "notes": "Refund evidence verified"},
    )
    assert approved.status_code == 200, approved.text
    processed = await client.post(
        f"/api/v1/collections/refunds/{refund_id}/process",
        headers=approver_headers,
        json={"reference_number": "REF-100"},
    )
    assert processed.status_code == 200, processed.text
    assert processed.json()["installments"][0]["paid_amount"] == "150.00"
    assert processed.json()["account"]["outstanding"] == "850.00"

    async with SessionFactory() as db:
        actions = set(await db.scalars(select(AuditLog.action)))
    assert {
        "collection.demand.issued",
        "collection.payment.reconciled",
        "collection.payment.allocated",
        "collection.charge.applied",
        "collection.charge.waived",
        "collection.refund.processed",
    }.issubset(actions)
