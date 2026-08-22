from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.models.enums import LeadStatus
from app.schemas.bookings import FinancingInput, InstallmentInput, PaymentPlanInput
from app.schemas.leads import LeadCreate
from app.schemas.post_sales import CancellationReview
from app.schemas.service_requests import SLAPolicyCreate, StatusTransition
from app.services.leads import _ensure_transition


def test_lead_schema_normalizes_identity_and_rejects_invalid_contact_or_budget() -> None:
    valid = LeadCreate(
        full_name="  Riya   Sharma ",
        email="RIYA@EXAMPLE.COM",
        budget_min=Decimal("8000000"),
        budget_max=Decimal("12000000"),
    )
    assert valid.full_name == "Riya Sharma"
    assert valid.email == "riya@example.com"

    with pytest.raises(ValidationError, match="Email or phone is required"):
        LeadCreate(full_name="No Contact")
    with pytest.raises(ValidationError, match="Minimum budget cannot exceed maximum budget"):
        LeadCreate(
            full_name="Invalid Budget",
            phone="+91 98765 40000",
            budget_min=Decimal("20"),
            budget_max=Decimal("10"),
        )


def test_booking_finance_and_schedule_validation_are_server_authoritative() -> None:
    effective = date.today()
    with pytest.raises(ValidationError, match="cannot precede"):
        PaymentPlanInput(
            name="Invalid schedule",
            effective_from=effective,
            installments=[
                InstallmentInput(
                    name="Past installment",
                    due_date=effective - timedelta(days=1),
                    amount=Decimal("100"),
                )
            ],
        )
    with pytest.raises(ValidationError, match="Lender name is required"):
        FinancingInput(status="APPLIED", loan_amount=Decimal("500000"))


def test_workflow_payloads_require_governed_values() -> None:
    with pytest.raises(ValidationError, match="before escalation"):
        SLAPolicyCreate(
            category_id="category",
            priority="URGENT",
            first_response_minutes=60,
            escalation_minutes=30,
            resolution_minutes=120,
        )
    with pytest.raises(ValidationError, match="Resolution summary is required"):
        StatusTransition(status="RESOLVED", notes="Work completed")
    with pytest.raises(ValidationError, match="cannot exceed 100"):
        CancellationReview(
            deduction_type="PERCENTAGE",
            deduction_value=Decimal("100.01"),
            notes="Invalid deduction",
        )


def test_lead_state_machine_accepts_only_declared_transitions() -> None:
    _ensure_transition(LeadStatus.NEW, LeadStatus.CONTACTED)
    _ensure_transition(LeadStatus.CONTACTED, LeadStatus.CONTACTED)
    with pytest.raises(AppError) as blocked:
        _ensure_transition(LeadStatus.CONVERTED, LeadStatus.NEW)
    assert blocked.value.status_code == 409
    assert blocked.value.code == "INVALID_LEAD_TRANSITION"
