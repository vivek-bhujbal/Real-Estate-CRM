from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DocumentStatus


class DocumentRequestCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=36)
    booking_id: str | None = Field(default=None, max_length=36)
    document_type: str = Field(min_length=2, max_length=80)
    expiry_date: date | None = None


class DocumentStartReview(BaseModel):
    reviewer_user_id: str | None = Field(default=None, max_length=36)
    notes: str | None = Field(default=None, max_length=2000)


class DocumentReviewDecision(BaseModel):
    status: Literal["VERIFIED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)
    rejection_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "DocumentReviewDecision":
        if self.status == "REJECTED" and not (self.rejection_reason or "").strip():
            raise ValueError("Rejection reason is required when rejecting a document")
        if self.status == "VERIFIED" and self.rejection_reason:
            raise ValueError("Rejection reason is only valid for rejected documents")
        return self


class DocumentView(BaseModel):
    id: str
    document_set_id: str
    supersedes_document_id: str | None
    customer_id: str
    customer_name: str
    booking_id: str | None
    booking_number: str | None
    document_type: str
    version: int
    is_current: bool
    file_name: str | None
    content_type: str | None
    size_bytes: int | None
    status: DocumentStatus
    expiry_date: date | None
    uploaded_by_user_id: str | None
    uploaded_by_name: str | None
    reviewed_by_user_id: str | None
    reviewer_name: str | None
    rejection_reason: str | None
    review_notes: str | None
    uploaded_at: datetime | None
    review_started_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentStats(BaseModel):
    total_current: int
    pending: int
    uploaded: int
    under_review: int
    verified: int
    rejected: int
    expired: int


class DocumentCustomerOption(BaseModel):
    id: str
    full_name: str
    email: str | None
    phone: str | None


class DocumentBookingOption(BaseModel):
    id: str
    customer_id: str
    booking_number: str
    status: str


class DocumentReviewerOption(BaseModel):
    id: str
    full_name: str
    email: str


class DocumentOptions(BaseModel):
    customers: list[DocumentCustomerOption]
    bookings: list[DocumentBookingOption]
    reviewers: list[DocumentReviewerOption]
