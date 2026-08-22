from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.entities import (
    Booking,
    ChannelPartner,
    Commission,
    Customer,
    Installment,
    Lead,
    LeadSource,
    Organization,
    PartnerLead,
    Payment,
    PaymentPlan,
    Project,
    ServiceRequest,
    Unit,
    User,
)
from app.models.enums import (
    BookingStatus,
    CommissionStatus,
    CustomerStatus,
    InstallmentStatus,
    LeadStatus,
    PartnerStatus,
    PaymentStatus,
    TicketStatus,
    UnitStatus,
    WorkflowStatus,
)


async def _organization(client: AsyncClient) -> tuple[dict[str, str], str, str]:
    response = await client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Dashboard Realty",
            "organization_slug": "dashboard-realty",
            "admin_full_name": "Dashboard Administrator",
            "admin_email": "dashboard-admin@example.com",
            "password": "Secure-dashboard-password-42!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return (
        {"Authorization": f"Bearer {body['access_token']}"},
        str(body["user"]["organization_id"]),
        str(body["user"]["id"]),
    )


def _metric(view: dict[str, object], key: str) -> Decimal:
    metrics = view["metrics"]
    assert isinstance(metrics, list)
    item = next(metric for metric in metrics if metric["key"] == key)
    return Decimal(str(item["value"]))


async def test_every_dashboard_has_a_real_zero_state(client: AsyncClient) -> None:
    headers, _, _ = await _organization(client)
    catalog = await client.get("/api/v1/dashboard/catalog", headers=headers)
    assert catalog.status_code == 200, catalog.text
    kinds = [item["kind"] for item in catalog.json()["items"]]
    assert kinds == [
        "EXECUTIVE",
        "SALES",
        "MARKETING",
        "INVENTORY",
        "COLLECTIONS",
        "PARTNER",
        "CUSTOMER",
    ]
    assert catalog.json()["default_dashboard"] == "EXECUTIVE"

    for kind in kinds:
        response = await client.get(f"/api/v1/dashboard/{kind}", headers=headers)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["kind"] == kind
        assert view["metrics"]
        assert all(Decimal(str(metric["value"])) == 0 for metric in view["metrics"])
        assert view["charts"]
        assert all(
            not chart["points"]
            or all(Decimal(str(point["value"])) == 0 for point in chart["points"])
            for chart in view["charts"]
        )


async def test_dashboard_metrics_are_aggregated_from_persisted_records(
    client: AsyncClient,
) -> None:
    headers, organization_id, admin_id = await _organization(client)
    now = datetime.now(UTC).replace(tzinfo=None)
    async with SessionFactory() as db:
        organization = await db.get(Organization, organization_id)
        assert organization is not None
        organization.currency = "INR"
        source = LeadSource(
            organization_id=organization_id,
            name="Referral",
            code="REFERRAL",
            is_active=True,
        )
        lead = Lead(
            organization_id=organization_id,
            source_id=source.id,
            owner_user_id=admin_id,
            full_name="Converted Buyer",
            status=LeadStatus.CONVERTED,
            score=80,
            converted_at=now,
        )
        project = Project(
            organization_id=organization_id,
            name="Real Project",
            code="REAL-PROJECT",
            default_currency="INR",
        )
        db.add_all((source, project))
        await db.flush()
        lead.source_id = source.id
        sold_unit = Unit(
            organization_id=organization_id,
            project_id=project.id,
            unit_number="A-101",
            status=UnitStatus.SOLD,
            base_price=Decimal("1000.00"),
            currency="INR",
        )
        available_unit = Unit(
            organization_id=organization_id,
            project_id=project.id,
            unit_number="A-102",
            status=UnitStatus.AVAILABLE,
            base_price=Decimal("1200.00"),
            currency="INR",
        )
        customer = Customer(
            organization_id=organization_id,
            converted_from_lead_id=lead.id,
            owner_user_id=admin_id,
            full_name="Converted Buyer",
            status=CustomerStatus.ACTIVE,
        )
        partner = ChannelPartner(
            organization_id=organization_id,
            code="PARTNER-REAL",
            name="Real Channel Partner",
            status=PartnerStatus.ACTIVE,
            lead_protection_days=30,
            applied_at=now,
        )
        db.add_all((lead, sold_unit, available_unit, customer, partner))
        await db.flush()
        booking = Booking(
            organization_id=organization_id,
            unit_id=sold_unit.id,
            lead_id=lead.id,
            customer_id=customer.id,
            booked_by_user_id=admin_id,
            salesperson_user_id=admin_id,
            channel_partner_id=partner.id,
            booking_number="BOOK-REAL-1",
            status=BookingStatus.CONFIRMED,
            booking_amount=Decimal("100.00"),
            agreed_price=Decimal("1000.00"),
            discount_amount=Decimal("0.00"),
            currency="INR",
            active_unit_key=sold_unit.id,
            booked_at=now,
        )
        db.add(booking)
        await db.flush()
        plan = PaymentPlan(
            organization_id=organization_id,
            booking_id=booking.id,
            name="Actual Plan",
            currency="INR",
            total_amount=Decimal("1000.00"),
            effective_from=date.today(),
        )
        db.add(plan)
        await db.flush()
        installment = Installment(
            organization_id=organization_id,
            payment_plan_id=plan.id,
            sequence=1,
            name="Actual installment",
            due_date=date.today() - timedelta(days=1),
            amount=Decimal("1000.00"),
            paid_amount=Decimal("400.00"),
            status=InstallmentStatus.PARTIALLY_PAID,
        )
        payment = Payment(
            organization_id=organization_id,
            booking_id=booking.id,
            customer_id=customer.id,
            amount=Decimal("400.00"),
            currency="INR",
            method="BANK_TRANSFER",
            status=PaymentStatus.COMPLETED,
            idempotency_key="dashboard-real-payment",
            paid_at=now,
            verified_at=now,
            verified_by_user_id=admin_id,
        )
        partner_lead = PartnerLead(
            organization_id=organization_id,
            channel_partner_id=partner.id,
            lead_id=lead.id,
            registered_by_user_id=admin_id,
            approved_by_user_id=admin_id,
            status=WorkflowStatus.APPROVED,
            registered_at=now,
            decided_at=now,
        )
        commission = Commission(
            organization_id=organization_id,
            channel_partner_id=partner.id,
            booking_id=booking.id,
            status=CommissionStatus.APPROVED,
            rate_percent=Decimal("5.00"),
            amount=Decimal("50.00"),
            currency="INR",
            approved_by_user_id=admin_id,
        )
        ticket = ServiceRequest(
            organization_id=organization_id,
            customer_id=customer.id,
            opened_by_user_id=admin_id,
            request_number="SR-REAL-1",
            category="Handover",
            status=TicketStatus.OPEN,
            subject="Actual customer request",
            description="Persisted request used by the dashboard query.",
            opened_at=now,
            is_escalated=False,
        )
        db.add_all((installment, payment, partner_lead, commission, ticket))
        await db.commit()

    executive = (await client.get("/api/v1/dashboard/EXECUTIVE", headers=headers)).json()
    assert _metric(executive, "confirmed_bookings") == 1
    assert _metric(executive, "confirmed_sales_value") == Decimal("1000")
    assert _metric(executive, "collections_received") == Decimal("400")
    assert _metric(executive, "outstanding") == Decimal("600")
    assert executive["currency"] == "INR"

    sales = (await client.get("/api/v1/dashboard/SALES", headers=headers)).json()
    assert _metric(sales, "total_leads") == 1
    assert _metric(sales, "conversion_rate") == Decimal("100")
    assert _metric(sales, "booked_value") == Decimal("1000")

    inventory = (await client.get("/api/v1/dashboard/INVENTORY", headers=headers)).json()
    assert _metric(inventory, "total_units") == 2
    assert _metric(inventory, "available_units") == 1
    assert _metric(inventory, "available_base_value") == Decimal("1200")

    collections = (await client.get("/api/v1/dashboard/COLLECTIONS", headers=headers)).json()
    assert _metric(collections, "scheduled_receivable") == Decimal("1000")
    assert _metric(collections, "overdue") == Decimal("600")

    partner_view = (await client.get("/api/v1/dashboard/PARTNER", headers=headers)).json()
    assert _metric(partner_view, "active_partners") == 1
    assert _metric(partner_view, "attributed_value") == Decimal("1000")
    assert _metric(partner_view, "pending_commission") == Decimal("50")

    customer_view = (await client.get("/api/v1/dashboard/CUSTOMER", headers=headers)).json()
    assert _metric(customer_view, "total_customers") == 1
    assert _metric(customer_view, "open_service_requests") == 1

    async with SessionFactory() as db:
        assert await db.scalar(select(User.id).where(User.id == admin_id)) == admin_id


async def test_dashboard_queries_enforce_underlying_domain_permissions(
    client: AsyncClient,
) -> None:
    admin_headers, _, _ = await _organization(client)
    roles = (await client.get("/api/v1/rbac/roles", headers=admin_headers)).json()
    inside_sales_role = next(
        role for role in roles if role["name"] == "Inside Sales / Telecalling Executive"
    )
    created = await client.post(
        "/api/v1/organization/users",
        headers=admin_headers,
        json={
            "full_name": "Inside Sales User",
            "email": "inside-dashboard@example.com",
            "password": "Secure-inside-dashboard-password-42!",
            "role_ids": [inside_sales_role["id"]],
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    assignment = await client.put(
        f"/api/v1/rbac/users/{created.json()['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [inside_sales_role["id"]]},
    )
    assert assignment.status_code == 200, assignment.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "dashboard-realty",
            "email": "inside-dashboard@example.com",
            "password": "Secure-inside-dashboard-password-42!",
        },
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    catalog = await client.get("/api/v1/dashboard/catalog", headers=headers)
    assert catalog.status_code == 200
    assert [item["kind"] for item in catalog.json()["items"]] == [
        "MARKETING",
        "INVENTORY",
    ]
    assert catalog.json()["default_dashboard"] == "MARKETING"
    assert (await client.get("/api/v1/dashboard/MARKETING", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/dashboard/EXECUTIVE", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/dashboard/summary", headers=headers)).status_code == 403
