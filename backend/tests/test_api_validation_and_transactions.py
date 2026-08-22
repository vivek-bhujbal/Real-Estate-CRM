from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models.entities import Booking, Unit, UnitHold
from app.models.enums import HoldStatus, UnitStatus
from tests.factories import organization_factory
from tests.test_booking_management import _eligible_records, _setup


async def test_unauthorized_and_invalid_lead_requests_never_persist_rows(
    client: AsyncClient,
) -> None:
    unauthorized = await client.get("/api/v1/leads")
    assert unauthorized.status_code == 401

    organization = await organization_factory(client, permissions_label="lead-validation")
    invalid = await client.post(
        "/api/v1/leads",
        headers=organization.headers,
        json={"full_name": "Missing Contact"},
    )
    assert invalid.status_code == 422
    async with SessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(Booking)) == 0
        from app.models.entities import Lead

        assert await db.scalar(select(func.count()).select_from(Lead)) == 0


async def test_failed_booking_rolls_back_booking_hold_and_inventory_mutations(
    client: AsyncClient,
) -> None:
    admin, _, ids = await _setup(client)
    records = await _eligible_records(ids)
    invalid_plan = {
        "quotation_id": records["quote_id"],
        "unit_hold_id": records["hold_id"],
        "booking_number": "BK-ROLLBACK-1",
        "salesperson_user_id": ids["admin_id"],
        "payment_plan": {
            "name": "Mismatched plan",
            "effective_from": str(date.today()),
            "installments": [
                {
                    "name": "Incorrect total",
                    "due_date": str(date.today() + timedelta(days=1)),
                    "amount": "1.00",
                }
            ],
        },
    }
    failed = await client.post("/api/v1/bookings", headers=admin, json=invalid_plan)
    assert failed.status_code == 422, failed.text
    assert failed.json()["error"]["code"] == "PAYMENT_PLAN_TOTAL_MISMATCH"

    async with SessionFactory() as db:
        booking_count = await db.scalar(
            select(func.count()).select_from(Booking).where(
                Booking.organization_id == ids["organization_id"]
            )
        )
        unit_status = await db.scalar(select(Unit.status).where(Unit.id == records["unit_id"]))
        hold_status = await db.scalar(
            select(UnitHold.status).where(UnitHold.id == records["hold_id"])
        )
    assert booking_count == 0
    assert unit_status == UnitStatus.SOFT_HOLD
    assert hold_status == HoldStatus.ACTIVE

    corrected = {
        **invalid_plan,
        "booking_number": "BK-ROLLBACK-2",
        "payment_plan": {
            **invalid_plan["payment_plan"],
            "installments": [
                {
                    "name": "Agreed value",
                    "due_date": str(date.today() + timedelta(days=1)),
                    "amount": "10000000.00",
                }
            ],
        },
    }
    created = await client.post("/api/v1/bookings", headers=admin, json=corrected)
    assert created.status_code == 201, created.text
