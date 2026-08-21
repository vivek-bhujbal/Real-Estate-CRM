from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import PaymentStatus, WorkflowStatus
from app.schemas.bookings import PaymentPlanInput


class CancellationCreate(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class CancellationReview(BaseModel):
    deduction_type: Literal["FIXED", "PERCENTAGE"]
    deduction_value: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    notes: str = Field(min_length=2, max_length=2000)

    @model_validator(mode="after")
    def percentage_limit(self) -> "CancellationReview":
        if self.deduction_type == "PERCENTAGE" and self.deduction_value > 100:
            raise ValueError("Percentage deduction cannot exceed 100")
        return self


class WorkflowDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(min_length=2, max_length=2000)


class RefundSummary(BaseModel):
    id: str
    status: PaymentStatus
    amount: Decimal
    reference_number: str | None


class CancellationView(BaseModel):
    id: str
    booking_id: str
    booking_number: str
    customer_id: str
    customer_name: str
    unit_id: str
    unit_number: str
    status: WorkflowStatus
    reason: str
    review_notes: str | None
    decision_notes: str | None
    paid_amount_snapshot: Decimal
    deduction_amount: Decimal
    refund_amount: Decimal
    currency: str
    requested_by_name: str
    reviewed_by_name: str | None
    approved_by_name: str | None
    requested_at: datetime
    reviewed_at: datetime | None
    decided_at: datetime | None
    unit_released_at: datetime | None
    document_number: str | None
    document_generated_at: datetime | None
    refund: RefundSummary | None
    created_at: datetime
    updated_at: datetime


class UnitTransferCreate(BaseModel):
    quotation_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=5, max_length=2000)
    revised_payment_plan: PaymentPlanInput


class UnitTransferReview(BaseModel):
    notes: str = Field(min_length=2, max_length=2000)


class UnitTransferView(BaseModel):
    id: str
    booking_id: str
    booking_number: str
    customer_id: str
    customer_name: str
    from_unit_id: str
    from_unit_number: str
    to_unit_id: str
    to_unit_number: str
    quotation_id: str
    quotation_number: str
    status: WorkflowStatus
    reason: str
    review_notes: str | None
    decision_notes: str | None
    old_agreed_price: Decimal
    new_agreed_price: Decimal
    price_difference: Decimal
    paid_amount_snapshot: Decimal
    currency: str
    commission_snapshot: dict[str, object] | None
    requested_by_name: str
    reviewed_by_name: str | None
    approved_by_name: str | None
    requested_at: datetime
    reviewed_at: datetime | None
    decided_at: datetime | None
    document_number: str | None
    document_generated_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PostSalesStats(BaseModel):
    cancellation_requested: int
    cancellation_under_review: int
    cancellation_approved: int
    refunds_processing: int
    transfer_requested: int
    transfer_under_review: int
    transfer_approved: int


class BookingOption(BaseModel):
    id: str
    booking_number: str
    customer_id: str
    customer_name: str
    unit_number: str
    currency: str
    agreed_price: Decimal


class TransferQuotationOption(BaseModel):
    id: str
    quotation_number: str
    customer_id: str
    unit_id: str
    unit_number: str
    final_agreed_value: Decimal
    currency: str


class PostSalesOptions(BaseModel):
    bookings: list[BookingOption]
    transfer_quotations: list[TransferQuotationOption]
