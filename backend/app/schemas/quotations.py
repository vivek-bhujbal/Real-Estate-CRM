from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import ApprovalStatus, CostSheetStatus, QuotationStatus, RecordStatus

CalculationType = Literal["fixed", "per_sqft", "percentage"]


class PricingLineRule(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    label: str = Field(min_length=1, max_length=180)
    calculation: CalculationType
    value: Decimal = Field(ge=0)
    taxable: bool = True
    optional: bool = False
    match_field: Literal["unit_type", "facing", "tower_id", "floor_id"] | None = None
    match_value: str | None = Field(default=None, max_length=100)

    @field_validator("code", mode="before")
    @classmethod
    def code_upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("label", "match_value")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value is not None else None

    @model_validator(mode="after")
    def matching_pair(self) -> "PricingLineRule":
        if (self.match_field is None) != (self.match_value is None):
            raise ValueError("Match field and value must be provided together")
        return self


class UnitPriceOverride(BaseModel):
    base_price: Decimal | None = Field(default=None, ge=0)
    adjustment: Decimal = Field(default=Decimal("0"))
    label: str = Field(default="Unit-specific adjustment", min_length=1, max_length=180)


class FloorRiseRule(BaseModel):
    label: str = Field(default="Floor rise", min_length=1, max_length=180)
    start_floor: int
    amount_per_floor: Decimal | None = Field(default=None, ge=0)
    rate_per_sqft_per_floor: Decimal | None = Field(default=None, ge=0)
    taxable: bool = True

    @model_validator(mode="after")
    def one_rate(self) -> "FloorRiseRule":
        if (self.amount_per_floor is None) == (self.rate_per_sqft_per_floor is None):
            raise ValueError("Configure one floor-rise calculation method")
        return self


class TaxRule(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    label: str = Field(min_length=1, max_length=180)
    rate_percent: Decimal = Field(ge=0, le=100)
    applies_to: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("code", mode="before")
    @classmethod
    def code_upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class DiscountPolicy(BaseModel):
    self_approval_limit_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    maximum_discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    approval_matrix: list["DiscountApprovalLevel"] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_matrix(self) -> "DiscountPolicy":
        ordered = sorted(self.approval_matrix, key=lambda item: item.minimum_discount_percent)
        for index, level in enumerate(ordered):
            if level.maximum_discount_percent is not None and (
                level.maximum_discount_percent < level.minimum_discount_percent
            ):
                raise ValueError("Approval level maximum must be at least its minimum")
            if index:
                previous_maximum = ordered[index - 1].maximum_discount_percent
                if previous_maximum is None or level.minimum_discount_percent <= previous_maximum:
                    raise ValueError("Discount approval levels must not overlap")
        return self


class DiscountApprovalLevel(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    minimum_discount_percent: Decimal = Field(ge=0, le=100)
    maximum_discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    approver_user_ids: list[str] = Field(default_factory=list, max_length=100)
    approver_role_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def approver_required(self) -> "DiscountApprovalLevel":
        if not self.approver_user_ids and not self.approver_role_ids:
            raise ValueError("Each approval level needs an approver user or role")
        return self


class ApprovalMatrixOption(BaseModel):
    id: str
    name: str


class ApprovalMatrixOptions(BaseModel):
    users: list[ApprovalMatrixOption]
    roles: list[ApprovalMatrixOption]


class BookingAmountRule(BaseModel):
    calculation: Literal["fixed", "percentage"]
    value: Decimal = Field(ge=0)


class PricingRules(BaseModel):
    base_rate_per_sqft: Decimal | None = Field(default=None, ge=0)
    unit_overrides: dict[str, UnitPriceOverride] = Field(default_factory=dict)
    floor_rise: FloorRiseRule | None = None
    premiums: list[PricingLineRule] = Field(default_factory=list, max_length=100)
    parking_options: list[PricingLineRule] = Field(default_factory=list, max_length=50)
    amenity_charges: list[PricingLineRule] = Field(default_factory=list, max_length=100)
    charges: list[PricingLineRule] = Field(default_factory=list, max_length=100)
    taxes: list[TaxRule] = Field(default_factory=list, max_length=50)
    discount_policy: DiscountPolicy = Field(default_factory=DiscountPolicy)
    booking_amount: BookingAmountRule | None = None

    @model_validator(mode="after")
    def unique_codes(self) -> "PricingRules":
        codes = [
            item.code
            for group in (
                self.premiums,
                self.parking_options,
                self.amenity_charges,
                self.charges,
            )
            for item in group
        ]
        if len(codes) != len(set(codes)):
            raise ValueError("Pricing component codes must be unique")
        tax_codes = [item.code for item in self.taxes]
        if len(tax_codes) != len(set(tax_codes)):
            raise ValueError("Tax codes must be unique")
        return self


class PriceListCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    currency: str = Field(min_length=3, max_length=3)
    effective_from: date
    effective_to: date | None = None
    pricing_rules: PricingRules

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("code", "currency", mode="before")
    @classmethod
    def upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def date_range(self) -> "PriceListCreate":
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Effective-to date must be on or after effective-from")
        return self


class PriceListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    effective_from: date | None = None
    effective_to: date | None = None
    pricing_rules: PricingRules | None = None

    @model_validator(mode="after")
    def fields_required(self) -> "PriceListUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class PriceListStatusPayload(BaseModel):
    status: Literal["ACTIVE", "INACTIVE", "ARCHIVED"]


class PriceListView(BaseModel):
    id: str
    project_id: str
    project_name: str
    name: str
    code: str
    version: int
    status: RecordStatus
    currency: str
    effective_from: date
    effective_to: date | None
    pricing_rules: PricingRules
    cost_sheet_count: int = 0
    created_at: datetime
    updated_at: datetime


class ParkingSelection(BaseModel):
    code: str
    quantity: int = Field(ge=1, le=100)

    @field_validator("code", mode="before")
    @classmethod
    def upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class CostSheetCreate(BaseModel):
    customer_id: str
    lead_id: str | None = None
    unit_id: str
    price_list_id: str
    parking: list[ParkingSelection] = Field(default_factory=list, max_length=50)
    amenity_codes: list[str] = Field(default_factory=list, max_length=100)
    optional_premium_codes: list[str] = Field(default_factory=list, max_length=100)
    requested_discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    final_agreed_value: Decimal | None = Field(default=None, ge=0)
    booking_amount_override: Decimal | None = Field(default=None, ge=0)
    request_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("amenity_codes", "optional_premium_codes", mode="before")
    @classmethod
    def upper_codes(cls, value: object) -> object:
        if isinstance(value, list):
            return [str(item).strip().upper() for item in value]
        return value

    @model_validator(mode="after")
    def discount_input(self) -> "CostSheetCreate":
        if self.final_agreed_value is not None and self.requested_discount_amount != 0:
            raise ValueError("Provide either final agreed value or requested discount, not both")
        return self


class CostSheetItemView(BaseModel):
    id: str | None = None
    sequence: int
    category: str
    label: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    taxable: bool
    metadata_json: dict[str, Any] | None = None


class DiscountApprovalView(BaseModel):
    id: str
    status: ApprovalStatus
    requested_by_user_id: str
    requested_by_name: str | None = None
    approver_user_id: str | None
    approver_name: str | None = None
    requested_discount_amount: Decimal
    requested_discount_percent: Decimal
    self_approval_limit_percent: Decimal
    approval_level_name: str
    required_approver_user_ids: list[str]
    required_approver_role_ids: list[str]
    previous_value: Decimal
    final_approved_value: Decimal | None
    request_notes: str | None
    decision_notes: str | None
    decided_at: datetime | None
    created_at: datetime


class CostSheetView(BaseModel):
    id: str | None = None
    customer_id: str
    customer_name: str
    lead_id: str | None
    lead_name: str | None = None
    unit_id: str
    unit_number: str
    project_id: str
    project_name: str
    price_list_id: str
    price_list_name: str
    price_list_version: int
    created_by_user_id: str
    created_by_name: str
    status: CostSheetStatus
    currency: str
    base_price: Decimal
    gross_value: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    final_agreed_value: Decimal
    booking_amount: Decimal
    pricing_snapshot: dict[str, Any]
    items: list[CostSheetItemView] = Field(default_factory=list)
    approval: DiscountApprovalView | None = None
    quotation_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApprovalDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)


class QuotationCreate(BaseModel):
    cost_sheet_id: str
    valid_until: date


class QuotationVersionCreate(BaseModel):
    cost_sheet_id: str
    valid_until: date


class QuotationStatusPayload(BaseModel):
    status: Literal["SENT", "ACCEPTED", "REJECTED", "EXPIRED"]


class QuotationItemView(BaseModel):
    id: str
    sequence: int
    category: str | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal


class QuotationHistoryItem(BaseModel):
    id: str
    version: int
    status: QuotationStatus
    total: Decimal
    valid_until: date
    created_at: datetime


class QuotationView(BaseModel):
    id: str
    lead_id: str | None
    lead_name: str | None = None
    customer_id: str | None
    customer_name: str | None = None
    project_id: str
    project_name: str
    unit_id: str | None
    unit_number: str | None = None
    cost_sheet_id: str | None
    parent_quotation_id: str | None
    created_by_user_id: str
    created_by_name: str
    quotation_number: str
    version: int
    status: QuotationStatus
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    final_agreed_value: Decimal | None
    booking_amount: Decimal | None
    pricing_snapshot: dict[str, Any] | None
    valid_until: date
    issued_at: datetime | None
    items: list[QuotationItemView] = Field(default_factory=list)
    history: list[QuotationHistoryItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class QuotationStats(BaseModel):
    total: int
    drafts: int
    sent: int
    accepted: int
    pending_discount_approvals: int
