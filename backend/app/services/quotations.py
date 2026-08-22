from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import ceil
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    CostSheet,
    CostSheetItem,
    Customer,
    DiscountApproval,
    Floor,
    Lead,
    Permission,
    PriceList,
    Project,
    Quotation,
    QuotationItem,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.models.enums import (
    ApprovalStatus,
    CostSheetStatus,
    NotificationEventType,
    QuotationStatus,
    RecordStatus,
)
from app.schemas.organization import Page
from app.schemas.quotations import (
    ApprovalDecision,
    ApprovalMatrixOption,
    ApprovalMatrixOptions,
    CostSheetCreate,
    CostSheetItemView,
    CostSheetView,
    DiscountApprovalLevel,
    DiscountApprovalView,
    PriceListCreate,
    PriceListStatusPayload,
    PriceListUpdate,
    PriceListView,
    PricingLineRule,
    PricingRules,
    QuotationCreate,
    QuotationHistoryItem,
    QuotationItemView,
    QuotationStats,
    QuotationStatusPayload,
    QuotationVersionCreate,
    QuotationView,
)
from app.services import notifications as notification_service
from app.services.organization import MutationContext

MONEY = Decimal("0.01")
RATE = Decimal("0.0001")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(slots=True)
class CalculatedLine:
    sequence: int
    category: str
    label: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    taxable: bool
    metadata: dict[str, Any] | None = None


async def _validate_approval_matrix(
    db: AsyncSession, organization_id: str, rules: PricingRules
) -> None:
    user_ids = {
        user_id
        for level in rules.discount_policy.approval_matrix
        for user_id in level.approver_user_ids
    }
    role_ids = {
        role_id
        for level in rules.discount_policy.approval_matrix
        for role_id in level.approver_role_ids
    }
    eligible_user_ids, eligible_role_ids = await _eligible_discount_approvers(db, organization_id)
    if not user_ids.issubset(eligible_user_ids) or not role_ids.issubset(eligible_role_ids):
        raise AppError(
            status_code=400,
            code="INVALID_APPROVAL_MATRIX",
            message="Approval matrix contains an ineligible user or role",
        )


async def _eligible_discount_approvers(
    db: AsyncSession, organization_id: str
) -> tuple[set[str], set[str]]:
    eligible_role_ids = set(
        await db.scalars(
            select(RolePermission.role_id)
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                RolePermission.organization_id == organization_id,
                Permission.code.in_(["quotations.approve", "quotations.manage"]),
            )
        )
    )
    eligible_user_ids = (
        set(
            await db.scalars(
                select(User.id)
                .join(
                    UserRole,
                    (UserRole.organization_id == User.organization_id)
                    & (UserRole.user_id == User.id),
                )
                .where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    UserRole.role_id.in_(eligible_role_ids),
                )
            )
        )
        if eligible_role_ids
        else set()
    )
    return eligible_user_ids, eligible_role_ids


def _approval_level(rules: PricingRules, discount_percent: Decimal) -> DiscountApprovalLevel | None:
    for level in sorted(
        rules.discount_policy.approval_matrix,
        key=lambda item: item.minimum_discount_percent,
    ):
        if discount_percent < level.minimum_discount_percent:
            continue
        if (
            level.maximum_discount_percent is None
            or discount_percent <= level.maximum_discount_percent
        ):
            return level
    return None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            status_code=400,
            code="INVALID_PRICING_RULE",
            message=f"{label} must be a valid number",
        ) from exc
    if not result.is_finite():
        raise AppError(
            status_code=400,
            code="INVALID_PRICING_RULE",
            message=f"{label} must be finite",
        )
    return result


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested pricing or quotation record was not found",
    )


async def _entity[T](
    db: AsyncSession,
    model: type[T],
    organization_id: str,
    entity_id: str,
    *,
    lock: bool = False,
) -> T:
    statement = select(model).where(
        model.organization_id == organization_id,  # type: ignore[attr-defined]
        model.id == entity_id,  # type: ignore[attr-defined]
    )
    if lock:
        statement = statement.with_for_update()
    item = (await db.scalars(statement)).first()
    if item is None:
        raise _not_found()
    return item


def _audit(
    organization_id: str,
    context: MutationContext,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=before,
        new_value=after,
        request_id=context.request_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
        created_at=_now(),
    )


async def _commit_conflict(db: AsyncSession, code: str, message: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(status_code=409, code=code, message=message) from exc


def _rules(value: dict[str, Any]) -> PricingRules:
    try:
        return PricingRules.model_validate(value)
    except ValidationError as exc:
        raise AppError(
            status_code=400,
            code="INVALID_PRICING_RULES",
            message="Price-list rules are invalid",
            details=exc.errors(include_url=False),
        ) from exc


async def _price_list_views(
    db: AsyncSession, organization_id: str, price_lists: list[PriceList]
) -> list[PriceListView]:
    if not price_lists:
        return []
    project_ids = {item.project_id for item in price_lists}
    projects = {
        item.id: item.name
        for item in (
            await db.scalars(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.id.in_(project_ids),
                )
            )
        ).all()
    }
    ids = [item.id for item in price_lists]
    count_rows = (
        await db.execute(
            select(CostSheet.price_list_id, func.count(CostSheet.id))
            .where(
                CostSheet.organization_id == organization_id,
                CostSheet.price_list_id.in_(ids),
            )
            .group_by(CostSheet.price_list_id)
        )
    ).all()
    counts: dict[str, int] = {price_list_id: count for price_list_id, count in count_rows}
    return [
        PriceListView(
            id=item.id,
            project_id=item.project_id,
            project_name=projects[item.project_id],
            name=item.name,
            code=item.code,
            version=item.version,
            status=item.status,
            currency=item.currency,
            effective_from=item.effective_from,
            effective_to=item.effective_to,
            pricing_rules=_rules(item.pricing_rules),
            cost_sheet_count=counts.get(item.id, 0),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in price_lists
    ]


async def list_price_lists(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    project_id: str | None,
    status: RecordStatus | None,
    page: int,
    page_size: int,
) -> Page[PriceListView]:
    conditions: list[Any] = [PriceList.organization_id == organization_id]
    if project_id:
        conditions.append(PriceList.project_id == project_id)
    if status:
        conditions.append(PriceList.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(or_(PriceList.name.ilike(pattern), PriceList.code.ilike(pattern)))
    total = await db.scalar(select(func.count(PriceList.id)).where(*conditions)) or 0
    rows = list(
        (
            await db.scalars(
                select(PriceList)
                .where(*conditions)
                .order_by(PriceList.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=await _price_list_views(db, organization_id, rows),
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def create_price_list(
    db: AsyncSession,
    organization_id: str,
    payload: PriceListCreate,
    context: MutationContext,
) -> PriceListView:
    await _entity(db, Project, organization_id, payload.project_id)
    await _validate_approval_matrix(db, organization_id, payload.pricing_rules)
    item = PriceList(
        organization_id=organization_id,
        project_id=payload.project_id,
        name=payload.name,
        code=payload.code,
        version=1,
        status=RecordStatus.DRAFT,
        currency=payload.currency,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        pricing_rules=payload.pricing_rules.model_dump(mode="json"),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            organization_id,
            context,
            "price_list.created",
            "price_list",
            item.id,
            None,
            {"code": item.code, "version": item.version, "status": item.status.value},
        )
    )
    await _commit_conflict(db, "DUPLICATE_PRICE_LIST", "Price-list code and version already exist")
    await db.refresh(item)
    return (await _price_list_views(db, organization_id, [item]))[0]


async def approval_matrix_options(db: AsyncSession, organization_id: str) -> ApprovalMatrixOptions:
    eligible_user_ids, eligible_role_ids = await _eligible_discount_approvers(db, organization_id)
    users = list(
        await db.scalars(
            select(User)
            .where(
                User.organization_id == organization_id,
                User.id.in_(eligible_user_ids),
            )
            .order_by(User.full_name)
        )
    )
    roles = list(
        await db.scalars(
            select(Role)
            .where(
                Role.organization_id == organization_id,
                Role.id.in_(eligible_role_ids),
            )
            .order_by(Role.name)
        )
    )
    return ApprovalMatrixOptions(
        users=[ApprovalMatrixOption(id=item.id, name=item.full_name) for item in users],
        roles=[ApprovalMatrixOption(id=item.id, name=item.name) for item in roles],
    )


async def get_price_list(
    db: AsyncSession, organization_id: str, price_list_id: str
) -> PriceListView:
    item = await _entity(db, PriceList, organization_id, price_list_id)
    return (await _price_list_views(db, organization_id, [item]))[0]


async def update_price_list(
    db: AsyncSession,
    organization_id: str,
    price_list_id: str,
    payload: PriceListUpdate,
    context: MutationContext,
) -> PriceListView:
    item = await _entity(db, PriceList, organization_id, price_list_id, lock=True)
    if item.status != RecordStatus.DRAFT:
        raise AppError(
            status_code=409,
            code="PRICE_LIST_IMMUTABLE",
            message="Only a draft price list can be edited",
        )
    before = {"name": item.name, "effective_from": str(item.effective_from)}
    changes = payload.model_dump(exclude_unset=True)
    if "pricing_rules" in changes and changes["pricing_rules"] is not None:
        pricing_rules = payload.pricing_rules
        if pricing_rules is not None:
            await _validate_approval_matrix(db, organization_id, pricing_rules)
            changes["pricing_rules"] = pricing_rules.model_dump(mode="json")
    effective_from = changes.get("effective_from", item.effective_from)
    effective_to = changes.get("effective_to", item.effective_to)
    if effective_from is None or (effective_to and effective_to < effective_from):
        raise AppError(
            status_code=400,
            code="INVALID_EFFECTIVE_DATES",
            message="Price-list effective dates are invalid",
        )
    for field, value in changes.items():
        setattr(item, field, value)
    db.add(
        _audit(
            organization_id,
            context,
            "price_list.updated",
            "price_list",
            item.id,
            before,
            {"name": item.name, "effective_from": str(item.effective_from)},
        )
    )
    await db.commit()
    await db.refresh(item)
    return (await _price_list_views(db, organization_id, [item]))[0]


async def change_price_list_status(
    db: AsyncSession,
    organization_id: str,
    price_list_id: str,
    payload: PriceListStatusPayload,
    context: MutationContext,
) -> PriceListView:
    item = await _entity(db, PriceList, organization_id, price_list_id, lock=True)
    target = RecordStatus(payload.status)
    allowed = {
        RecordStatus.DRAFT: {RecordStatus.ACTIVE, RecordStatus.ARCHIVED},
        RecordStatus.ACTIVE: {RecordStatus.INACTIVE, RecordStatus.ARCHIVED},
        RecordStatus.INACTIVE: {RecordStatus.ACTIVE, RecordStatus.ARCHIVED},
    }
    if target not in allowed.get(item.status, set()):
        raise AppError(
            status_code=409,
            code="INVALID_PRICE_LIST_TRANSITION",
            message=f"Cannot move price list from {item.status.value} to {target.value}",
        )
    before = item.status.value
    item.status = target
    db.add(
        _audit(
            organization_id,
            context,
            "price_list.status.changed",
            "price_list",
            item.id,
            {"status": before},
            {"status": target.value},
        )
    )
    await db.commit()
    await db.refresh(item)
    return (await _price_list_views(db, organization_id, [item]))[0]


async def delete_price_list(
    db: AsyncSession,
    organization_id: str,
    price_list_id: str,
    context: MutationContext,
) -> None:
    item = await _entity(db, PriceList, organization_id, price_list_id, lock=True)
    if item.status != RecordStatus.DRAFT:
        raise AppError(
            status_code=409,
            code="PRICE_LIST_NOT_DELETABLE",
            message="Only a draft price list can be deleted",
        )
    db.add(
        _audit(
            organization_id,
            context,
            "price_list.deleted",
            "price_list",
            item.id,
            {"code": item.code, "version": item.version},
            None,
        )
    )
    await db.delete(item)
    await _commit_conflict(db, "PRICE_LIST_IN_USE", "Price list is already used by a cost sheet")


def _rule_matches(rule: PricingLineRule, unit: Unit) -> bool:
    if rule.match_field is None:
        return True
    value = getattr(unit, rule.match_field)
    return value is not None and str(value).casefold() == str(rule.match_value).casefold()


def _line_amount(
    rule: PricingLineRule,
    *,
    area: Decimal | None,
    percentage_basis: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    if rule.calculation == "fixed":
        return Decimal("1"), rule.value, _money(rule.value)
    if rule.calculation == "per_sqft":
        if area is None:
            raise AppError(
                status_code=400,
                code="UNIT_AREA_REQUIRED",
                message=f"Unit area is required for {rule.label}",
            )
        return area, rule.value, _money(area * rule.value)
    return Decimal("1"), rule.value, _money(percentage_basis * rule.value / HUNDRED)


async def calculate_cost_sheet(
    db: AsyncSession,
    organization_id: str,
    payload: CostSheetCreate,
    context: MutationContext,
) -> CostSheetView:
    customer = await _entity(db, Customer, organization_id, payload.customer_id)
    lead = await _entity(db, Lead, organization_id, payload.lead_id) if payload.lead_id else None
    unit = await _entity(db, Unit, organization_id, payload.unit_id)
    project = await _entity(db, Project, organization_id, unit.project_id)
    price_list = await _entity(db, PriceList, organization_id, payload.price_list_id)
    creator = await _entity(db, User, organization_id, context.actor_user_id)
    if price_list.project_id != unit.project_id:
        raise AppError(
            status_code=400,
            code="PRICE_LIST_PROJECT_MISMATCH",
            message="Price list and unit must belong to the same project",
        )
    today = date.today()
    if (
        price_list.status != RecordStatus.ACTIVE
        or price_list.effective_from > today
        or (price_list.effective_to and price_list.effective_to < today)
    ):
        raise AppError(
            status_code=409,
            code="PRICE_LIST_NOT_EFFECTIVE",
            message="Choose an active price list within its effective dates",
        )
    rules = _rules(price_list.pricing_rules)
    area = unit.area_sqft or unit.built_up_area_sqft or unit.carpet_area_sqft
    override = rules.unit_overrides.get(unit.id) or rules.unit_overrides.get(unit.unit_number)
    if override and override.base_price is not None:
        base_price = _money(override.base_price)
        base_metadata: dict[str, Any] = {"source": "price_list_unit_override"}
    elif unit.base_price is not None:
        base_price = _money(unit.base_price)
        base_metadata = {"source": "unit_base_price"}
    elif rules.base_rate_per_sqft is not None and area is not None:
        base_price = _money(rules.base_rate_per_sqft * area)
        base_metadata = {"source": "price_list_rate_per_sqft", "area_sqft": str(area)}
    else:
        raise AppError(
            status_code=400,
            code="BASE_PRICE_NOT_CONFIGURED",
            message="Configure a unit base price, unit override, or base rate per square foot",
        )
    lines = [
        CalculatedLine(
            sequence=1,
            category="BASE_PRICE",
            label="Base price",
            quantity=Decimal("1"),
            rate=base_price,
            amount=base_price,
            taxable=True,
            metadata=base_metadata,
        )
    ]

    def add_line(
        category: str,
        label: str,
        quantity: Decimal,
        rate: Decimal,
        amount: Decimal,
        taxable: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if amount == ZERO:
            return
        lines.append(
            CalculatedLine(
                sequence=len(lines) + 1,
                category=category,
                label=label,
                quantity=quantity,
                rate=rate,
                amount=_money(amount),
                taxable=taxable,
                metadata=metadata,
            )
        )

    unit_adjustment = ZERO
    if unit.price_components:
        unit_adjustment += _decimal(
            unit.price_components.get("unit_specific_adjustment", ZERO),
            "Unit-specific adjustment",
        )
    if override:
        unit_adjustment += override.adjustment
    add_line(
        "UNIT_ADJUSTMENT",
        override.label if override else "Unit-specific adjustment",
        Decimal("1"),
        unit_adjustment,
        unit_adjustment,
        True,
    )
    floor = await _entity(db, Floor, organization_id, unit.floor_id) if unit.floor_id else None
    if rules.floor_rise and floor and floor.floor_number >= rules.floor_rise.start_floor:
        floor_count = floor.floor_number - rules.floor_rise.start_floor + 1
        if rules.floor_rise.amount_per_floor is not None:
            quantity = Decimal(floor_count)
            rate = rules.floor_rise.amount_per_floor
            amount = quantity * rate
        else:
            if area is None or rules.floor_rise.rate_per_sqft_per_floor is None:
                raise AppError(
                    status_code=400,
                    code="UNIT_AREA_REQUIRED",
                    message="Unit area is required for floor-rise pricing",
                )
            quantity = area * Decimal(floor_count)
            rate = rules.floor_rise.rate_per_sqft_per_floor
            amount = quantity * rate
        add_line(
            "FLOOR_RISE",
            rules.floor_rise.label,
            quantity,
            rate,
            amount,
            rules.floor_rise.taxable,
            {"floor_number": floor.floor_number, "chargeable_floors": floor_count},
        )
    selected_premiums = set(payload.optional_premium_codes)
    for rule in rules.premiums:
        if not _rule_matches(rule, unit) or (rule.optional and rule.code not in selected_premiums):
            continue
        basis = sum((line.amount for line in lines), ZERO)
        quantity, rate, amount = _line_amount(rule, area=area, percentage_basis=basis)
        add_line("PREMIUM", rule.label, quantity, rate, amount, rule.taxable, {"code": rule.code})
    parking_by_code = {item.code: item for item in rules.parking_options}
    for selection in payload.parking:
        parking_rule = parking_by_code.get(selection.code)
        if parking_rule is None:
            raise AppError(
                status_code=400,
                code="INVALID_PARKING_OPTION",
                message=f"Parking option {selection.code} is not configured",
            )
        if parking_rule.calculation == "percentage":
            basis = sum((line.amount for line in lines), ZERO)
            _, rate, per_unit = _line_amount(parking_rule, area=area, percentage_basis=basis)
        else:
            _, rate, per_unit = _line_amount(parking_rule, area=area, percentage_basis=ZERO)
        quantity = Decimal(selection.quantity)
        add_line(
            "PARKING",
            parking_rule.label,
            quantity,
            rate,
            per_unit * quantity,
            parking_rule.taxable,
            {"code": parking_rule.code},
        )
    amenities_by_code = {item.code: item for item in rules.amenity_charges}
    for code in payload.amenity_codes:
        amenity_rule = amenities_by_code.get(code)
        if amenity_rule is None:
            raise AppError(
                status_code=400,
                code="INVALID_AMENITY_CHARGE",
                message=f"Amenity charge {code} is not configured",
            )
        basis = sum((line.amount for line in lines), ZERO)
        quantity, rate, amount = _line_amount(amenity_rule, area=area, percentage_basis=basis)
        add_line(
            "AMENITY",
            amenity_rule.label,
            quantity,
            rate,
            amount,
            amenity_rule.taxable,
            {"code": code},
        )
    for rule in rules.charges:
        if rule.optional or not _rule_matches(rule, unit):
            continue
        basis = sum((line.amount for line in lines), ZERO)
        quantity, rate, amount = _line_amount(rule, area=area, percentage_basis=basis)
        add_line("CHARGE", rule.label, quantity, rate, amount, rule.taxable, {"code": rule.code})
    gross_value = _money(sum((line.amount for line in lines), ZERO))
    tax_amount = ZERO
    for tax in rules.taxes:
        basis = sum(
            (
                line.amount
                for line in lines
                if line.taxable and (not tax.applies_to or line.category in tax.applies_to)
            ),
            ZERO,
        )
        amount = _money(basis * tax.rate_percent / HUNDRED)
        tax_amount += amount
        add_line(
            "TAX",
            tax.label,
            Decimal("1"),
            tax.rate_percent,
            amount,
            False,
            {"code": tax.code, "taxable_basis": str(_money(basis))},
        )
    tax_amount = _money(tax_amount)
    pre_discount_total = gross_value + tax_amount
    if payload.final_agreed_value is not None:
        if payload.final_agreed_value > pre_discount_total:
            raise AppError(
                status_code=400,
                code="INVALID_FINAL_VALUE",
                message="Final agreed value cannot exceed the calculated value",
            )
        discount_amount = _money(pre_discount_total - payload.final_agreed_value)
    else:
        discount_amount = _money(payload.requested_discount_amount)
    if discount_amount > pre_discount_total:
        raise AppError(
            status_code=400,
            code="INVALID_DISCOUNT",
            message="Discount cannot exceed the calculated value",
        )
    discount_percent = (
        (discount_amount * HUNDRED / pre_discount_total).quantize(RATE, rounding=ROUND_HALF_UP)
        if pre_discount_total
        else ZERO
    )
    maximum = rules.discount_policy.maximum_discount_percent
    if maximum is not None and discount_percent > maximum:
        raise AppError(
            status_code=400,
            code="DISCOUNT_LIMIT_EXCEEDED",
            message="Requested discount exceeds the price-list maximum",
        )
    final_value = _money(pre_discount_total - discount_amount)
    if discount_amount:
        add_line(
            "DISCOUNT",
            "Discount",
            Decimal("1"),
            discount_amount,
            -discount_amount,
            False,
            {"discount_percent": str(discount_percent)},
        )
    if payload.booking_amount_override is not None:
        booking_amount = _money(payload.booking_amount_override)
    elif rules.booking_amount is not None:
        booking_amount = _money(
            rules.booking_amount.value
            if rules.booking_amount.calculation == "fixed"
            else final_value * rules.booking_amount.value / HUNDRED
        )
    else:
        raise AppError(
            status_code=400,
            code="BOOKING_AMOUNT_NOT_CONFIGURED",
            message="Configure a booking-amount rule or provide an override",
        )
    if booking_amount > final_value:
        raise AppError(
            status_code=400,
            code="INVALID_BOOKING_AMOUNT",
            message="Booking amount cannot exceed the final agreed value",
        )
    approval_required = (
        discount_amount > ZERO
        and discount_percent > rules.discount_policy.self_approval_limit_percent
    )
    selected_approval_level = (
        _approval_level(rules, discount_percent) if approval_required else None
    )
    if approval_required and selected_approval_level is None:
        raise AppError(
            status_code=409,
            code="APPROVAL_MATRIX_NOT_CONFIGURED",
            message="No approval-matrix level covers the requested discount",
        )
    if approval_required and not payload.request_notes:
        raise AppError(
            status_code=400,
            code="DISCOUNT_REASON_REQUIRED",
            message="A reason is required for a discount approval request",
        )
    status = CostSheetStatus.PENDING_APPROVAL if approval_required else CostSheetStatus.APPROVED
    snapshot: dict[str, Any] = {
        "price_list": {
            "id": price_list.id,
            "code": price_list.code,
            "version": price_list.version,
            "rules": rules.model_dump(mode="json"),
        },
        "unit": {
            "id": unit.id,
            "number": unit.unit_number,
            "area_sqft": str(area) if area is not None else None,
            "floor_number": floor.floor_number if floor else None,
            "facing": unit.facing,
            "unit_type": unit.unit_type,
        },
        "selections": {
            "parking": [item.model_dump(mode="json") for item in payload.parking],
            "amenity_codes": payload.amenity_codes,
            "optional_premium_codes": payload.optional_premium_codes,
        },
        "approval_required": approval_required,
        "discount_percent": str(discount_percent),
        "self_approval_limit_percent": str(rules.discount_policy.self_approval_limit_percent),
        "previous_value": str(pre_discount_total),
        "selected_approval_level": (
            selected_approval_level.model_dump(mode="json")
            if selected_approval_level is not None
            else None
        ),
    }
    item_views = [
        CostSheetItemView(
            sequence=line.sequence,
            category=line.category,
            label=line.label,
            quantity=line.quantity,
            rate=line.rate,
            amount=line.amount,
            taxable=line.taxable,
            metadata_json=line.metadata,
        )
        for line in lines
    ]
    return CostSheetView(
        customer_id=customer.id,
        customer_name=customer.full_name,
        lead_id=lead.id if lead else None,
        lead_name=lead.full_name if lead else None,
        unit_id=unit.id,
        unit_number=unit.unit_number,
        project_id=project.id,
        project_name=project.name,
        price_list_id=price_list.id,
        price_list_name=price_list.name,
        price_list_version=price_list.version,
        created_by_user_id=creator.id,
        created_by_name=creator.full_name,
        status=status,
        currency=price_list.currency,
        base_price=base_price,
        gross_value=gross_value,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        final_agreed_value=final_value,
        booking_amount=booking_amount,
        pricing_snapshot=snapshot,
        items=item_views,
    )


async def create_cost_sheet(
    db: AsyncSession,
    organization_id: str,
    payload: CostSheetCreate,
    context: MutationContext,
) -> CostSheetView:
    calculated = await calculate_cost_sheet(db, organization_id, payload, context)
    sheet = CostSheet(
        organization_id=organization_id,
        customer_id=calculated.customer_id,
        lead_id=calculated.lead_id,
        unit_id=calculated.unit_id,
        price_list_id=calculated.price_list_id,
        created_by_user_id=context.actor_user_id,
        status=calculated.status,
        currency=calculated.currency,
        base_price=calculated.base_price,
        gross_value=calculated.gross_value,
        discount_amount=calculated.discount_amount,
        tax_amount=calculated.tax_amount,
        final_agreed_value=calculated.final_agreed_value,
        booking_amount=calculated.booking_amount,
        pricing_snapshot=calculated.pricing_snapshot,
    )
    db.add(sheet)
    await db.flush()
    for item in calculated.items:
        db.add(
            CostSheetItem(
                organization_id=organization_id,
                cost_sheet_id=sheet.id,
                sequence=item.sequence,
                category=item.category,
                label=item.label,
                quantity=item.quantity,
                rate=item.rate,
                amount=item.amount,
                taxable=item.taxable,
                metadata_json=item.metadata_json,
            )
        )
    if sheet.status == CostSheetStatus.PENDING_APPROVAL:
        approval_level = calculated.pricing_snapshot["selected_approval_level"]
        if not isinstance(approval_level, dict):
            raise AppError(
                status_code=409,
                code="APPROVAL_MATRIX_NOT_CONFIGURED",
                message="The required discount approval level is unavailable",
            )
        approval = DiscountApproval(
            organization_id=organization_id,
            cost_sheet_id=sheet.id,
            requested_by_user_id=context.actor_user_id,
            status=ApprovalStatus.PENDING,
            requested_discount_amount=sheet.discount_amount,
            requested_discount_percent=Decimal(str(sheet.pricing_snapshot["discount_percent"])),
            self_approval_limit_percent=_decimal(
                sheet.pricing_snapshot.get("self_approval_limit_percent", ZERO),
                "Self-approval limit",
            ),
            approval_level_name=str(approval_level["name"]),
            required_approver_user_ids=list(approval_level["approver_user_ids"]),
            required_approver_role_ids=list(approval_level["approver_role_ids"]),
            previous_value=_decimal(sheet.pricing_snapshot["previous_value"], "Previous value"),
            final_approved_value=None,
            request_notes=payload.request_notes,
        )
        db.add(approval)
        await db.flush()
        db.add(
            _audit(
                organization_id,
                context,
                "discount_approval.requested",
                "discount_approval",
                approval.id,
                {"final_value": str(approval.previous_value)},
                {
                    "cost_sheet_id": sheet.id,
                    "requested_amount": str(approval.requested_discount_amount),
                    "requested_percentage": str(approval.requested_discount_percent),
                    "reason": approval.request_notes,
                    "approval_level": approval.approval_level_name,
                    "requested_final_value": str(sheet.final_agreed_value),
                },
            )
        )
        approver_ids = set(approval.required_approver_user_ids)
        approver_ids.update(
            await notification_service.recipients_for_roles(
                db, organization_id, approval.required_approver_role_ids
            )
        )
        approver_ids.discard(context.actor_user_id)
        notification_service.queue_in_app(
            db,
            organization_id=organization_id,
            recipient_user_ids=approver_ids,
            event_type=NotificationEventType.DISCOUNT_APPROVAL_REQUESTED,
            title="Discount approval requested",
            body=(
                f"{approval.approval_level_name}: "
                f"{sheet.currency} {approval.requested_discount_amount}"
            ),
            related_entity_type="discount_approval",
            related_entity_id=approval.id,
            action_url=f"/cost-sheets/{sheet.id}",
            data={
                "cost_sheet_id": sheet.id,
                "requested_by_user_id": context.actor_user_id,
                "requested_percentage": str(approval.requested_discount_percent),
            },
        )
    db.add(
        _audit(
            organization_id,
            context,
            "cost_sheet.created",
            "cost_sheet",
            sheet.id,
            None,
            {
                "status": sheet.status.value,
                "unit_id": sheet.unit_id,
                "final_agreed_value": str(sheet.final_agreed_value),
            },
        )
    )
    await db.commit()
    return await get_cost_sheet(db, organization_id, sheet.id)


async def _cost_sheet_view(
    db: AsyncSession, organization_id: str, sheet: CostSheet
) -> CostSheetView:
    customer = await _entity(db, Customer, organization_id, sheet.customer_id)
    lead = await _entity(db, Lead, organization_id, sheet.lead_id) if sheet.lead_id else None
    unit = await _entity(db, Unit, organization_id, sheet.unit_id)
    project = await _entity(db, Project, organization_id, unit.project_id)
    price_list = await _entity(db, PriceList, organization_id, sheet.price_list_id)
    creator = await _entity(db, User, organization_id, sheet.created_by_user_id)
    items = list(
        (
            await db.scalars(
                select(CostSheetItem)
                .where(
                    CostSheetItem.organization_id == organization_id,
                    CostSheetItem.cost_sheet_id == sheet.id,
                )
                .order_by(CostSheetItem.sequence)
            )
        ).all()
    )
    approval = (
        await db.scalars(
            select(DiscountApproval).where(
                DiscountApproval.organization_id == organization_id,
                DiscountApproval.cost_sheet_id == sheet.id,
            )
        )
    ).first()
    approval_view = None
    if approval:
        requester = await _entity(db, User, organization_id, approval.requested_by_user_id)
        approver = (
            await _entity(db, User, organization_id, approval.approver_user_id)
            if approval.approver_user_id
            else None
        )
        approval_view = DiscountApprovalView(
            id=approval.id,
            status=approval.status,
            requested_by_user_id=requester.id,
            requested_by_name=requester.full_name,
            approver_user_id=approver.id if approver else None,
            approver_name=approver.full_name if approver else None,
            requested_discount_amount=approval.requested_discount_amount,
            requested_discount_percent=approval.requested_discount_percent,
            self_approval_limit_percent=approval.self_approval_limit_percent,
            approval_level_name=approval.approval_level_name,
            required_approver_user_ids=approval.required_approver_user_ids,
            required_approver_role_ids=approval.required_approver_role_ids,
            previous_value=approval.previous_value,
            final_approved_value=approval.final_approved_value,
            request_notes=approval.request_notes,
            decision_notes=approval.decision_notes,
            decided_at=approval.decided_at,
            created_at=approval.created_at,
        )
    quotation_id = await db.scalar(
        select(Quotation.id).where(
            Quotation.organization_id == organization_id,
            Quotation.cost_sheet_id == sheet.id,
        )
    )
    return CostSheetView(
        id=sheet.id,
        customer_id=customer.id,
        customer_name=customer.full_name,
        lead_id=lead.id if lead else None,
        lead_name=lead.full_name if lead else None,
        unit_id=unit.id,
        unit_number=unit.unit_number,
        project_id=project.id,
        project_name=project.name,
        price_list_id=price_list.id,
        price_list_name=price_list.name,
        price_list_version=price_list.version,
        created_by_user_id=creator.id,
        created_by_name=creator.full_name,
        status=sheet.status,
        currency=sheet.currency,
        base_price=sheet.base_price,
        gross_value=sheet.gross_value,
        discount_amount=sheet.discount_amount,
        tax_amount=sheet.tax_amount,
        final_agreed_value=sheet.final_agreed_value,
        booking_amount=sheet.booking_amount,
        pricing_snapshot=sheet.pricing_snapshot,
        items=[
            CostSheetItemView(
                id=item.id,
                sequence=item.sequence,
                category=item.category,
                label=item.label,
                quantity=item.quantity,
                rate=item.rate,
                amount=item.amount,
                taxable=item.taxable,
                metadata_json=item.metadata_json,
            )
            for item in items
        ],
        approval=approval_view,
        quotation_id=quotation_id,
        created_at=sheet.created_at,
        updated_at=sheet.updated_at,
    )


async def get_cost_sheet(
    db: AsyncSession, organization_id: str, cost_sheet_id: str
) -> CostSheetView:
    sheet = await _entity(db, CostSheet, organization_id, cost_sheet_id)
    return await _cost_sheet_view(db, organization_id, sheet)


async def list_cost_sheets(
    db: AsyncSession,
    organization_id: str,
    *,
    customer_id: str | None,
    status: CostSheetStatus | None,
    page: int,
    page_size: int,
) -> Page[CostSheetView]:
    conditions: list[Any] = [CostSheet.organization_id == organization_id]
    if customer_id:
        conditions.append(CostSheet.customer_id == customer_id)
    if status:
        conditions.append(CostSheet.status == status)
    total = await db.scalar(select(func.count(CostSheet.id)).where(*conditions)) or 0
    sheets = list(
        (
            await db.scalars(
                select(CostSheet)
                .where(*conditions)
                .order_by(CostSheet.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=[await _cost_sheet_view(db, organization_id, sheet) for sheet in sheets],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def decide_discount(
    db: AsyncSession,
    organization_id: str,
    cost_sheet_id: str,
    payload: ApprovalDecision,
    context: MutationContext,
) -> CostSheetView:
    sheet = await _entity(db, CostSheet, organization_id, cost_sheet_id, lock=True)
    approval = (
        await db.scalars(
            select(DiscountApproval)
            .where(
                DiscountApproval.organization_id == organization_id,
                DiscountApproval.cost_sheet_id == sheet.id,
            )
            .with_for_update()
        )
    ).first()
    if not approval or approval.status != ApprovalStatus.PENDING:
        raise AppError(
            status_code=409,
            code="APPROVAL_NOT_PENDING",
            message="This cost sheet has no pending discount approval",
        )
    if approval.requested_by_user_id == context.actor_user_id:
        raise AppError(
            status_code=403,
            code="SELF_APPROVAL_NOT_ALLOWED",
            message="A different authorized user must approve this discount",
        )
    actor_role_ids = set(
        await db.scalars(
            select(UserRole.role_id).where(
                UserRole.organization_id == organization_id,
                UserRole.user_id == context.actor_user_id,
            )
        )
    )
    is_matrix_approver = context.actor_user_id in approval.required_approver_user_ids or bool(
        actor_role_ids.intersection(approval.required_approver_role_ids)
    )
    has_management_override = permission_is_granted(context.permissions, "quotations.manage")
    if not is_matrix_approver and not has_management_override:
        raise AppError(
            status_code=403,
            code="APPROVER_NOT_IN_MATRIX",
            message="You are not an eligible approver for this discount level",
        )
    before = sheet.status.value
    approval.status = ApprovalStatus(payload.status)
    approval.approver_user_id = context.actor_user_id
    approval.decision_notes = payload.notes
    approval.decided_at = _now()
    approval.final_approved_value = (
        sheet.final_agreed_value if approval.status == ApprovalStatus.APPROVED else None
    )
    sheet.status = (
        CostSheetStatus.APPROVED
        if approval.status == ApprovalStatus.APPROVED
        else CostSheetStatus.REJECTED
    )
    db.add(
        _audit(
            organization_id,
            context,
            "discount_approval.decided",
            "discount_approval",
            approval.id,
            {
                "status": before,
                "final_value": str(approval.previous_value),
            },
            {
                "status": sheet.status.value,
                "decision": approval.status.value,
                "approver_user_id": context.actor_user_id,
                "decision_notes": approval.decision_notes,
                "final_approved_value": (
                    str(approval.final_approved_value)
                    if approval.final_approved_value is not None
                    else None
                ),
                "management_override": has_management_override and not is_matrix_approver,
            },
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids=[approval.requested_by_user_id],
        event_type=NotificationEventType.DISCOUNT_APPROVAL_DECIDED,
        title=f"Discount request {approval.status.value.lower()}",
        body=approval.decision_notes or f"Decision: {approval.status.value}",
        related_entity_type="discount_approval",
        related_entity_id=approval.id,
        action_url=f"/cost-sheets/{sheet.id}",
        data={"cost_sheet_id": sheet.id, "status": approval.status.value},
    )
    await db.commit()
    return await get_cost_sheet(db, organization_id, sheet.id)


async def _quotation_view(
    db: AsyncSession, organization_id: str, quote: Quotation
) -> QuotationView:
    lead = await _entity(db, Lead, organization_id, quote.lead_id) if quote.lead_id else None
    customer = (
        await _entity(db, Customer, organization_id, quote.customer_id)
        if quote.customer_id
        else None
    )
    project = await _entity(db, Project, organization_id, quote.project_id)
    unit = await _entity(db, Unit, organization_id, quote.unit_id) if quote.unit_id else None
    creator = await _entity(db, User, organization_id, quote.created_by_user_id)
    items = list(
        (
            await db.scalars(
                select(QuotationItem)
                .where(
                    QuotationItem.organization_id == organization_id,
                    QuotationItem.quotation_id == quote.id,
                )
                .order_by(QuotationItem.sequence)
            )
        ).all()
    )
    history = list(
        (
            await db.scalars(
                select(Quotation)
                .where(
                    Quotation.organization_id == organization_id,
                    Quotation.quotation_number == quote.quotation_number,
                )
                .order_by(Quotation.version.desc())
            )
        ).all()
    )
    return QuotationView(
        id=quote.id,
        lead_id=quote.lead_id,
        lead_name=lead.full_name if lead else None,
        customer_id=quote.customer_id,
        customer_name=customer.full_name if customer else None,
        project_id=project.id,
        project_name=project.name,
        unit_id=unit.id if unit else None,
        unit_number=unit.unit_number if unit else None,
        cost_sheet_id=quote.cost_sheet_id,
        parent_quotation_id=quote.parent_quotation_id,
        created_by_user_id=creator.id,
        created_by_name=creator.full_name,
        quotation_number=quote.quotation_number,
        version=quote.version,
        status=quote.status,
        currency=quote.currency,
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
        total=quote.total,
        final_agreed_value=quote.final_agreed_value,
        booking_amount=quote.booking_amount,
        pricing_snapshot=quote.pricing_snapshot,
        valid_until=quote.valid_until,
        issued_at=quote.issued_at,
        items=[
            QuotationItemView(
                id=item.id,
                sequence=item.sequence,
                category=item.category,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_amount=item.discount_amount,
                tax_amount=item.tax_amount,
                total=item.total,
            )
            for item in items
        ],
        history=[
            QuotationHistoryItem(
                id=item.id,
                version=item.version,
                status=item.status,
                total=item.total,
                valid_until=item.valid_until,
                created_at=item.created_at,
            )
            for item in history
        ],
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


async def _create_quotation_record(
    db: AsyncSession,
    organization_id: str,
    sheet: CostSheet,
    *,
    quotation_number: str,
    version: int,
    valid_until: date,
    parent_quotation_id: str | None,
    context: MutationContext,
) -> Quotation:
    unit = await _entity(db, Unit, organization_id, sheet.unit_id)
    quote = Quotation(
        organization_id=organization_id,
        lead_id=sheet.lead_id,
        customer_id=sheet.customer_id,
        project_id=unit.project_id,
        unit_id=unit.id,
        cost_sheet_id=sheet.id,
        parent_quotation_id=parent_quotation_id,
        created_by_user_id=context.actor_user_id,
        quotation_number=quotation_number,
        version=version,
        status=QuotationStatus.DRAFT,
        currency=sheet.currency,
        subtotal=sheet.gross_value,
        discount_amount=sheet.discount_amount,
        tax_amount=sheet.tax_amount,
        total=sheet.final_agreed_value,
        final_agreed_value=sheet.final_agreed_value,
        booking_amount=sheet.booking_amount,
        pricing_snapshot=sheet.pricing_snapshot,
        valid_until=valid_until,
    )
    db.add(quote)
    await db.flush()
    items = list(
        (
            await db.scalars(
                select(CostSheetItem)
                .where(
                    CostSheetItem.organization_id == organization_id,
                    CostSheetItem.cost_sheet_id == sheet.id,
                )
                .order_by(CostSheetItem.sequence)
            )
        ).all()
    )
    for item in items:
        db.add(
            QuotationItem(
                organization_id=organization_id,
                quotation_id=quote.id,
                unit_id=unit.id if item.category == "BASE_PRICE" else None,
                sequence=item.sequence,
                category=item.category,
                description=item.label,
                quantity=item.quantity,
                unit_price=(item.rate if item.category not in {"DISCOUNT", "TAX"} else ZERO),
                discount_amount=(-item.amount if item.category == "DISCOUNT" else ZERO),
                tax_amount=(item.amount if item.category == "TAX" else ZERO),
                total=ZERO if item.category == "DISCOUNT" else item.amount,
            )
        )
    sheet.status = CostSheetStatus.CONVERTED
    return quote


async def create_quotation(
    db: AsyncSession,
    organization_id: str,
    payload: QuotationCreate,
    context: MutationContext,
) -> QuotationView:
    sheet = await _entity(db, CostSheet, organization_id, payload.cost_sheet_id, lock=True)
    if sheet.status != CostSheetStatus.APPROVED:
        raise AppError(
            status_code=409,
            code="COST_SHEET_NOT_APPROVED",
            message="Cost sheet must be approved before creating a quotation",
        )
    if payload.valid_until < date.today():
        raise AppError(
            status_code=400,
            code="INVALID_VALIDITY",
            message="Quotation validity cannot be in the past",
        )
    number = f"QT-{date.today():%Y%m}-{uuid4().hex[:10].upper()}"
    quote = await _create_quotation_record(
        db,
        organization_id,
        sheet,
        quotation_number=number,
        version=1,
        valid_until=payload.valid_until,
        parent_quotation_id=None,
        context=context,
    )
    db.add(
        _audit(
            organization_id,
            context,
            "quotation.created",
            "quotation",
            quote.id,
            None,
            {"quotation_number": quote.quotation_number, "version": 1},
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids=[quote.created_by_user_id],
        event_type=NotificationEventType.QUOTATION_CREATED,
        title="Quotation created",
        body=f"{quote.quotation_number} · Version {quote.version}",
        related_entity_type="quotation",
        related_entity_id=quote.id,
        action_url=f"/quotations/{quote.id}",
        data={"quotation_number": quote.quotation_number, "version": quote.version},
    )
    await _commit_conflict(db, "DUPLICATE_QUOTATION", "Quotation could not be created")
    await db.refresh(quote)
    return await _quotation_view(db, organization_id, quote)


async def create_quotation_version(
    db: AsyncSession,
    organization_id: str,
    quote_id: str,
    payload: QuotationVersionCreate,
    context: MutationContext,
) -> QuotationView:
    source = await _entity(db, Quotation, organization_id, quote_id, lock=True)
    if source.status == QuotationStatus.ACCEPTED:
        raise AppError(
            status_code=409,
            code="ACCEPTED_QUOTATION_IMMUTABLE",
            message="An accepted quotation cannot be revised",
        )
    sheet = await _entity(db, CostSheet, organization_id, payload.cost_sheet_id, lock=True)
    if sheet.status != CostSheetStatus.APPROVED:
        raise AppError(
            status_code=409,
            code="COST_SHEET_NOT_APPROVED",
            message="The revision cost sheet must be approved",
        )
    if sheet.customer_id != source.customer_id or sheet.unit_id != source.unit_id:
        raise AppError(
            status_code=400,
            code="REVISION_SCOPE_MISMATCH",
            message="Quotation revisions must retain the same customer and unit",
        )
    locked_versions = list(
        await db.scalars(
            select(Quotation)
            .where(
                Quotation.organization_id == organization_id,
                Quotation.quotation_number == source.quotation_number,
            )
            .with_for_update()
        )
    )
    if not locked_versions:
        raise AppError(
            status_code=409,
            code="QUOTATION_VERSION_CONFLICT",
            message="Quotation version history is unavailable",
        )
    latest_version = max(item.version for item in locked_versions)
    await db.execute(
        update(Quotation)
        .where(
            Quotation.organization_id == organization_id,
            Quotation.quotation_number == source.quotation_number,
            Quotation.status.not_in([QuotationStatus.ACCEPTED, QuotationStatus.REJECTED]),
        )
        .values(status=QuotationStatus.SUPERSEDED)
    )
    quote = await _create_quotation_record(
        db,
        organization_id,
        sheet,
        quotation_number=source.quotation_number,
        version=latest_version + 1,
        valid_until=payload.valid_until,
        parent_quotation_id=source.id,
        context=context,
    )
    db.add(
        _audit(
            organization_id,
            context,
            "quotation.version.created",
            "quotation",
            quote.id,
            {"parent_quotation_id": source.id},
            {"version": quote.version, "cost_sheet_id": sheet.id},
        )
    )
    await _commit_conflict(db, "VERSION_CONFLICT", "A quotation version was created concurrently")
    await db.refresh(quote)
    return await _quotation_view(db, organization_id, quote)


async def list_quotations(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: QuotationStatus | None,
    customer_id: str | None,
    unit_id: str | None,
    page: int,
    page_size: int,
) -> Page[QuotationView]:
    conditions: list[Any] = [Quotation.organization_id == organization_id]
    if status:
        conditions.append(Quotation.status == status)
    if customer_id:
        conditions.append(Quotation.customer_id == customer_id)
    if unit_id:
        conditions.append(Quotation.unit_id == unit_id)
    statement = (
        select(Quotation)
        .outerjoin(
            Customer,
            (Customer.organization_id == Quotation.organization_id)
            & (Customer.id == Quotation.customer_id),
        )
        .outerjoin(
            Unit,
            (Unit.organization_id == Quotation.organization_id) & (Unit.id == Quotation.unit_id),
        )
        .where(*conditions)
    )
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Quotation.quotation_number.ilike(pattern),
                Customer.full_name.ilike(pattern),
                Unit.unit_number.ilike(pattern),
            )
        )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    quotes = list(
        (
            await db.scalars(
                statement.order_by(Quotation.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=[await _quotation_view(db, organization_id, quote) for quote in quotes],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def get_quotation(db: AsyncSession, organization_id: str, quotation_id: str) -> QuotationView:
    quote = await _entity(db, Quotation, organization_id, quotation_id)
    return await _quotation_view(db, organization_id, quote)


async def change_quotation_status(
    db: AsyncSession,
    organization_id: str,
    quotation_id: str,
    payload: QuotationStatusPayload,
    context: MutationContext,
) -> QuotationView:
    quote = await _entity(db, Quotation, organization_id, quotation_id, lock=True)
    target = QuotationStatus(payload.status)
    allowed = {
        QuotationStatus.DRAFT: {QuotationStatus.SENT, QuotationStatus.EXPIRED},
        QuotationStatus.SENT: {
            QuotationStatus.ACCEPTED,
            QuotationStatus.REJECTED,
            QuotationStatus.EXPIRED,
        },
    }
    if target not in allowed.get(quote.status, set()):
        raise AppError(
            status_code=409,
            code="INVALID_QUOTATION_TRANSITION",
            message=f"Cannot move quotation from {quote.status.value} to {target.value}",
        )
    before = quote.status.value
    quote.status = target
    if target == QuotationStatus.SENT:
        quote.issued_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "quotation.status.changed",
            "quotation",
            quote.id,
            {"status": before},
            {"status": target.value},
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids=[quote.created_by_user_id],
        event_type=NotificationEventType.QUOTATION_STATUS_CHANGED,
        title="Quotation status updated",
        body=f"{quote.quotation_number}: {before} → {target.value}",
        related_entity_type="quotation",
        related_entity_id=quote.id,
        action_url=f"/quotations/{quote.id}",
        data={"previous_status": before, "status": target.value},
    )
    await db.commit()
    await db.refresh(quote)
    return await _quotation_view(db, organization_id, quote)


async def stats(db: AsyncSession, organization_id: str) -> QuotationStats:
    rows = (
        await db.execute(
            select(Quotation.status, func.count(Quotation.id))
            .where(Quotation.organization_id == organization_id)
            .group_by(Quotation.status)
        )
    ).all()
    counts: dict[QuotationStatus, int] = {status: count for status, count in rows}
    pending = (
        await db.scalar(
            select(func.count(DiscountApproval.id)).where(
                DiscountApproval.organization_id == organization_id,
                DiscountApproval.status == ApprovalStatus.PENDING,
            )
        )
        or 0
    )
    return QuotationStats(
        total=sum(counts.values()),
        drafts=counts.get(QuotationStatus.DRAFT, 0),
        sent=counts.get(QuotationStatus.SENT, 0),
        accepted=counts.get(QuotationStatus.ACCEPTED, 0),
        pending_discount_approvals=pending,
    )
