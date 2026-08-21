from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.documents.workflow_pdf import WorkflowPdfDocument, WorkflowPdfRenderer
from app.models.entities import (
    Agreement,
    AuditLog,
    Booking,
    Cancellation,
    Commission,
    Customer,
    CustomerLedger,
    Installment,
    Organization,
    Payment,
    PaymentAllocation,
    PaymentPlan,
    Quotation,
    Refund,
    Unit,
    UnitHold,
    UnitTransfer,
    User,
)
from app.models.enums import (
    AgreementStatus,
    BookingStatus,
    CommissionStatus,
    HoldStatus,
    InstallmentStatus,
    LedgerEntryType,
    PaymentStatus,
    QuotationStatus,
    RecordStatus,
    UnitStatus,
    WorkflowStatus,
)
from app.schemas.organization import Page
from app.schemas.post_sales import (
    BookingOption,
    CancellationCreate,
    CancellationReview,
    CancellationView,
    PostSalesOptions,
    PostSalesStats,
    RefundSummary,
    TransferQuotationOption,
    UnitTransferCreate,
    UnitTransferReview,
    UnitTransferView,
    WorkflowDecision,
)
from app.services.organization import MutationContext
from app.storage.local import LocalStorage

ZERO = Decimal("0.00")
MONEY = Decimal("0.01")
ACTIVE_WORKFLOWS = (
    WorkflowStatus.REQUESTED,
    WorkflowStatus.UNDER_REVIEW,
    WorkflowStatus.APPROVED,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _error(code: str, message: str, status: int = 409) -> AppError:
    return AppError(status_code=status, code=code, message=message)


def _audit(
    org: str,
    context: MutationContext,
    action: str,
    kind: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=org,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type=kind,
        entity_id=entity_id,
        previous_value=before,
        new_value=after,
        request_id=context.request_id,
        ip_address=context.ip_address,
        created_at=_now(),
    )


async def _entity[T](
    db: AsyncSession, model: type[T], org: str, entity_id: str, *, lock: bool = False
) -> T:
    statement = select(model).where(model.organization_id == org, model.id == entity_id)  # type: ignore[attr-defined]
    if lock:
        statement = statement.with_for_update()
    item = (await db.scalars(statement)).first()
    if item is None:
        raise _error("RESOURCE_NOT_FOUND", "Post-sales record not found", 404)
    return item


async def _name(db: AsyncSession, org: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = await db.scalar(
        select(User.full_name).where(User.organization_id == org, User.id == user_id)
    )
    return str(value) if value else None


async def _paid_amount(db: AsyncSession, org: str, booking_id: str) -> Decimal:
    paid = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == org,
                Payment.booking_id == booking_id,
                Payment.status.in_((PaymentStatus.COMPLETED, PaymentStatus.REFUNDED)),
            )
        )
        or ZERO
    )
    refunded = (
        await db.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.organization_id == org,
                Refund.booking_id == booking_id,
                Refund.status == PaymentStatus.COMPLETED,
            )
        )
        or ZERO
    )
    return _money(max(paid - refunded, ZERO))


async def _unit_is_available(db: AsyncSession, org: str, unit: Unit) -> bool:
    if unit.status != UnitStatus.AVAILABLE:
        return False
    active_hold = await db.scalar(
        select(UnitHold.id).where(
            UnitHold.organization_id == org,
            UnitHold.active_unit_key == unit.id,
            UnitHold.status.in_((HoldStatus.ACTIVE, HoldStatus.PENDING_APPROVAL)),
        )
    )
    active_booking = await db.scalar(
        select(Booking.id).where(Booking.organization_id == org, Booking.active_unit_key == unit.id)
    )
    return active_hold is None and active_booking is None


async def _save_document(
    db: AsyncSession,
    org: str,
    kind: str,
    workflow_id: str,
    number: str,
    title: str,
    lines: tuple[str, ...],
) -> str:
    organization_name = str(
        await db.scalar(select(Organization.name).where(Organization.id == org)) or "Organization"
    )
    content = WorkflowPdfRenderer().render(
        WorkflowPdfDocument(
            organization_name=organization_name,
            title=title,
            document_number=number,
            lines=lines,
        )
    )
    key = f"{org}/post-sales/{kind}/{workflow_id}/{number}.pdf"
    await LocalStorage(get_settings().storage_local_path).save_bytes(key=key, content=content)
    return key


async def _refund_for_cancellation(
    db: AsyncSession, org: str, cancellation_id: str
) -> Refund | None:
    return (
        await db.scalars(
            select(Refund).where(
                Refund.organization_id == org, Refund.cancellation_id == cancellation_id
            )
        )
    ).first()


async def cancellation_view(db: AsyncSession, org: str, item: Cancellation) -> CancellationView:
    booking = await _entity(db, Booking, org, item.booking_id)
    customer = await _entity(db, Customer, org, booking.customer_id)
    unit = await _entity(db, Unit, org, booking.unit_id)
    refund = await _refund_for_cancellation(db, org, item.id)
    requested_name = await _name(db, org, item.requested_by_user_id)
    return CancellationView(
        id=item.id,
        booking_id=booking.id,
        booking_number=booking.booking_number,
        customer_id=customer.id,
        customer_name=customer.full_name,
        unit_id=unit.id,
        unit_number=unit.unit_number,
        status=item.status,
        reason=item.reason,
        review_notes=item.review_notes,
        decision_notes=item.decision_notes,
        paid_amount_snapshot=item.paid_amount_snapshot,
        deduction_amount=item.deduction_amount,
        refund_amount=item.refund_amount,
        currency=booking.currency,
        requested_by_name=requested_name or "Unknown user",
        reviewed_by_name=await _name(db, org, item.reviewed_by_user_id),
        approved_by_name=await _name(db, org, item.approved_by_user_id),
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        decided_at=item.decided_at,
        unit_released_at=item.unit_released_at,
        document_number=item.document_number,
        document_generated_at=item.document_generated_at,
        refund=(
            RefundSummary(
                id=refund.id,
                status=refund.status,
                amount=refund.amount,
                reference_number=refund.reference_number,
            )
            if refund
            else None
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def transfer_view(db: AsyncSession, org: str, item: UnitTransfer) -> UnitTransferView:
    booking = await _entity(db, Booking, org, item.booking_id)
    customer = await _entity(db, Customer, org, booking.customer_id)
    old_unit = await _entity(db, Unit, org, item.from_unit_id)
    new_unit = await _entity(db, Unit, org, item.to_unit_id)
    quote = await _entity(db, Quotation, org, item.quotation_id)
    requested_name = await _name(db, org, item.requested_by_user_id)
    return UnitTransferView(
        id=item.id,
        booking_id=booking.id,
        booking_number=booking.booking_number,
        customer_id=customer.id,
        customer_name=customer.full_name,
        from_unit_id=old_unit.id,
        from_unit_number=old_unit.unit_number,
        to_unit_id=new_unit.id,
        to_unit_number=new_unit.unit_number,
        quotation_id=quote.id,
        quotation_number=quote.quotation_number,
        status=item.status,
        reason=item.reason,
        review_notes=item.review_notes,
        decision_notes=item.decision_notes,
        old_agreed_price=item.old_agreed_price,
        new_agreed_price=item.new_agreed_price,
        price_difference=item.price_difference,
        paid_amount_snapshot=item.paid_amount_snapshot,
        currency=booking.currency,
        commission_snapshot=item.commission_snapshot,
        requested_by_name=requested_name or "Unknown user",
        reviewed_by_name=await _name(db, org, item.reviewed_by_user_id),
        approved_by_name=await _name(db, org, item.approved_by_user_id),
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        decided_at=item.decided_at,
        document_number=item.document_number,
        document_generated_at=item.document_generated_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def list_cancellations(
    db: AsyncSession,
    org: str,
    *,
    q: str | None,
    status: WorkflowStatus | None,
    page: int,
    page_size: int,
) -> Page[CancellationView]:
    filters: list[Any] = [Cancellation.organization_id == org]
    statement = (
        select(Cancellation)
        .join(
            Booking,
            (Booking.organization_id == Cancellation.organization_id)
            & (Booking.id == Cancellation.booking_id),
        )
        .join(
            Customer,
            (Customer.organization_id == Booking.organization_id)
            & (Customer.id == Booking.customer_id),
        )
        .join(
            Unit, (Unit.organization_id == Booking.organization_id) & (Unit.id == Booking.unit_id)
        )
    )
    if status:
        filters.append(Cancellation.status == status)
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                Booking.booking_number.ilike(like),
                Customer.full_name.ilike(like),
                Unit.unit_number.ilike(like),
            )
        )
    statement = statement.where(*filters)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = list(
        await db.scalars(
            statement.order_by(Cancellation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await cancellation_view(db, org, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def list_transfers(
    db: AsyncSession,
    org: str,
    *,
    q: str | None,
    status: WorkflowStatus | None,
    page: int,
    page_size: int,
) -> Page[UnitTransferView]:
    filters: list[Any] = [UnitTransfer.organization_id == org]
    statement = (
        select(UnitTransfer)
        .join(
            Booking,
            (Booking.organization_id == UnitTransfer.organization_id)
            & (Booking.id == UnitTransfer.booking_id),
        )
        .join(
            Customer,
            (Customer.organization_id == Booking.organization_id)
            & (Customer.id == Booking.customer_id),
        )
    )
    if status:
        filters.append(UnitTransfer.status == status)
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(Booking.booking_number.ilike(like), Customer.full_name.ilike(like)))
    statement = statement.where(*filters)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = list(
        await db.scalars(
            statement.order_by(UnitTransfer.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await transfer_view(db, org, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def stats(db: AsyncSession, org: str) -> PostSalesStats:
    async def count(model: type[Any], status: Any) -> int:
        return int(
            await db.scalar(
                select(func.count())
                .select_from(model)
                .where(model.organization_id == org, model.status == status)
            )
            or 0
        )

    return PostSalesStats(
        cancellation_requested=await count(Cancellation, WorkflowStatus.REQUESTED),
        cancellation_under_review=await count(Cancellation, WorkflowStatus.UNDER_REVIEW),
        cancellation_approved=await count(Cancellation, WorkflowStatus.APPROVED),
        refunds_processing=await count(Refund, PaymentStatus.PROCESSING),
        transfer_requested=await count(UnitTransfer, WorkflowStatus.REQUESTED),
        transfer_under_review=await count(UnitTransfer, WorkflowStatus.UNDER_REVIEW),
        transfer_approved=await count(UnitTransfer, WorkflowStatus.APPROVED),
    )


async def options(db: AsyncSession, org: str) -> PostSalesOptions:
    bookings = list(
        await db.scalars(
            select(Booking)
            .where(Booking.organization_id == org, Booking.status == BookingStatus.CONFIRMED)
            .order_by(Booking.created_at.desc())
            .limit(200)
        )
    )
    booking_options: list[BookingOption] = []
    quote_options: list[TransferQuotationOption] = []
    for booking in bookings:
        customer = await _entity(db, Customer, org, booking.customer_id)
        unit = await _entity(db, Unit, org, booking.unit_id)
        booking_options.append(
            BookingOption(
                id=booking.id,
                booking_number=booking.booking_number,
                customer_id=customer.id,
                customer_name=customer.full_name,
                unit_number=unit.unit_number,
                currency=booking.currency,
                agreed_price=booking.agreed_price or ZERO,
            )
        )
        quotes = list(
            await db.scalars(
                select(Quotation)
                .where(
                    Quotation.organization_id == org,
                    Quotation.customer_id == booking.customer_id,
                    Quotation.status == QuotationStatus.ACCEPTED,
                    Quotation.unit_id.is_not(None),
                    Quotation.unit_id != booking.unit_id,
                )
                .order_by(Quotation.created_at.desc())
                .limit(100)
            )
        )
        for quote in quotes:
            if quote.unit_id and quote.final_agreed_value is not None:
                target = await _entity(db, Unit, org, quote.unit_id)
                if await _unit_is_available(db, org, target):
                    quote_options.append(
                        TransferQuotationOption(
                            id=quote.id,
                            quotation_number=f"{quote.quotation_number} v{quote.version}",
                            customer_id=customer.id,
                            unit_id=target.id,
                            unit_number=target.unit_number,
                            final_agreed_value=quote.final_agreed_value,
                            currency=quote.currency,
                        )
                    )
    unique_quotes = {item.id: item for item in quote_options}
    return PostSalesOptions(
        bookings=booking_options, transfer_quotations=list(unique_quotes.values())
    )


async def request_cancellation(
    db: AsyncSession,
    org: str,
    booking_id: str,
    payload: CancellationCreate,
    context: MutationContext,
) -> CancellationView:
    booking = await _entity(db, Booking, org, booking_id, lock=True)
    if booking.status != BookingStatus.CONFIRMED:
        raise _error("BOOKING_NOT_CANCELLABLE", "Only a confirmed booking can enter cancellation")
    existing = await db.scalar(
        select(Cancellation.id).where(
            Cancellation.organization_id == org, Cancellation.active_booking_key == booking.id
        )
    )
    if existing:
        raise _error(
            "ACTIVE_CANCELLATION_EXISTS", "This booking already has an active cancellation"
        )
    now = _now()
    item = Cancellation(
        organization_id=org,
        booking_id=booking.id,
        requested_by_user_id=context.actor_user_id,
        status=WorkflowStatus.REQUESTED,
        reason=payload.reason.strip(),
        active_booking_key=booking.id,
        paid_amount_snapshot=ZERO,
        deduction_amount=ZERO,
        refund_amount=ZERO,
        requested_at=now,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "cancellation.requested",
            "cancellation",
            item.id,
            None,
            {"booking_id": booking.id, "reason": item.reason, "status": item.status.value},
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(
            "ACTIVE_CANCELLATION_EXISTS", "This booking already has an active cancellation"
        ) from exc
    return await cancellation_view(db, org, item)


async def review_cancellation(
    db: AsyncSession,
    org: str,
    cancellation_id: str,
    payload: CancellationReview,
    context: MutationContext,
) -> CancellationView:
    item = await _entity(db, Cancellation, org, cancellation_id, lock=True)
    if item.status != WorkflowStatus.REQUESTED:
        raise _error(
            "INVALID_CANCELLATION_TRANSITION", "Only a requested cancellation can be reviewed"
        )
    paid = await _paid_amount(db, org, item.booking_id)
    deduction = (
        payload.deduction_value
        if payload.deduction_type == "FIXED"
        else paid * payload.deduction_value / Decimal("100")
    )
    deduction = _money(min(deduction, paid))
    refund = _money(paid - deduction)
    item.status = WorkflowStatus.UNDER_REVIEW
    item.reviewed_by_user_id = context.actor_user_id
    item.review_notes = payload.notes.strip()
    item.reviewed_at = _now()
    item.paid_amount_snapshot = paid
    item.deduction_amount = deduction
    item.refund_amount = refund
    item.calculation_snapshot = {
        "basis": "net_verified_payments",
        "paid_amount": str(paid),
        "deduction_type": payload.deduction_type,
        "deduction_value": str(payload.deduction_value),
        "deduction_amount": str(deduction),
        "refund_amount": str(refund),
        "calculated_at": item.reviewed_at.isoformat(),
    }
    db.add(
        _audit(
            org,
            context,
            "cancellation.reviewed",
            "cancellation",
            item.id,
            {"status": WorkflowStatus.REQUESTED.value},
            {
                "status": item.status.value,
                "paid_amount": str(paid),
                "deduction_amount": str(deduction),
                "refund_amount": str(refund),
            },
        )
    )
    await db.commit()
    return await cancellation_view(db, org, item)


async def decide_cancellation(
    db: AsyncSession,
    org: str,
    cancellation_id: str,
    payload: WorkflowDecision,
    context: MutationContext,
) -> CancellationView:
    item = await _entity(db, Cancellation, org, cancellation_id, lock=True)
    if item.status != WorkflowStatus.UNDER_REVIEW:
        raise _error(
            "INVALID_CANCELLATION_TRANSITION", "Cancellation must be reviewed before a decision"
        )
    if context.actor_user_id in {item.requested_by_user_id, item.reviewed_by_user_id}:
        raise _error(
            "SELF_APPROVAL_NOT_ALLOWED",
            "Requester or reviewer cannot approve this cancellation",
            403,
        )
    item.approved_by_user_id = context.actor_user_id
    item.decision_notes = payload.notes.strip()
    item.decided_at = _now()
    item.status = (
        WorkflowStatus.APPROVED if payload.status == "APPROVED" else WorkflowStatus.REJECTED
    )
    if item.status == WorkflowStatus.REJECTED:
        item.active_booking_key = None
    db.add(
        _audit(
            org,
            context,
            "cancellation.decided",
            "cancellation",
            item.id,
            {"status": WorkflowStatus.UNDER_REVIEW.value},
            {"status": item.status.value, "notes": item.decision_notes},
        )
    )
    await db.commit()
    return await cancellation_view(db, org, item)


async def complete_cancellation(
    db: AsyncSession, org: str, cancellation_id: str, context: MutationContext
) -> CancellationView:
    ref = await _entity(db, Cancellation, org, cancellation_id)
    booking_ref = await _entity(db, Booking, org, ref.booking_id)
    unit = await _entity(db, Unit, org, booking_ref.unit_id, lock=True)
    booking = await _entity(db, Booking, org, booking_ref.id, lock=True)
    item = await _entity(db, Cancellation, org, cancellation_id, lock=True)
    if item.status != WorkflowStatus.APPROVED:
        raise _error(
            "INVALID_CANCELLATION_TRANSITION", "Cancellation must be approved before completion"
        )
    if (
        booking.status != BookingStatus.CONFIRMED
        or booking.active_unit_key != unit.id
        or unit.status not in (UnitStatus.BOOKED, UnitStatus.SOLD)
    ):
        raise _error(
            "BOOKING_STATE_CHANGED",
            "Booking or unit state changed; cancellation cannot be completed",
        )
    paid_now = await _paid_amount(db, org, booking.id)
    if paid_now != item.paid_amount_snapshot:
        raise _error(
            "PAYMENT_STATE_CHANGED", "Payments changed after review; review the cancellation again"
        )
    now = _now()
    agreed = booking.agreed_price or ZERO
    booking.status = BookingStatus.CANCELLED
    booking.active_unit_key = None
    booking.cancelled_at = now
    unit.status = UnitStatus.CANCELLED_RELEASED
    item.status = WorkflowStatus.COMPLETED
    item.active_booking_key = None
    item.unit_released_at = now
    item.completed_at = now
    db.add(
        CustomerLedger(
            organization_id=org,
            customer_id=booking.customer_id,
            booking_id=booking.id,
            entry_type=LedgerEntryType.CREDIT,
            amount=agreed,
            currency=booking.currency,
            description=f"Contract value reversed on cancellation {item.id}",
            idempotency_key=f"cancellation:{item.id}:contract-reversal",
            posted_at=now,
        )
    )
    if item.deduction_amount > ZERO:
        db.add(
            CustomerLedger(
                organization_id=org,
                customer_id=booking.customer_id,
                booking_id=booking.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=item.deduction_amount,
                currency=booking.currency,
                description=f"Approved cancellation deduction {item.id}",
                idempotency_key=f"cancellation:{item.id}:deduction",
                posted_at=now,
            )
        )
    refund: Refund | None = None
    if item.refund_amount > ZERO:
        refund = Refund(
            organization_id=org,
            cancellation_id=item.id,
            booking_id=booking.id,
            payment_id=None,
            customer_id=booking.customer_id,
            requested_by_user_id=item.requested_by_user_id,
            approved_by_user_id=item.approved_by_user_id,
            status=PaymentStatus.PROCESSING,
            amount=item.refund_amount,
            currency=booking.currency,
            reason=f"Approved cancellation {item.id}",
            decision_notes=item.decision_notes,
            idempotency_key=f"cancellation:{item.id}:refund",
            requested_at=item.requested_at,
            approved_at=item.decided_at,
        )
        db.add(refund)
        await db.flush()
    await db.execute(
        update(PaymentPlan)
        .where(
            PaymentPlan.organization_id == org,
            PaymentPlan.booking_id == booking.id,
            PaymentPlan.status == RecordStatus.ACTIVE,
        )
        .values(status=RecordStatus.ARCHIVED)
    )
    agreements = list(
        await db.scalars(
            select(Agreement)
            .where(Agreement.organization_id == org, Agreement.booking_id == booking.id)
            .with_for_update()
        )
    )
    for agreement in agreements:
        agreement.status = AgreementStatus.TERMINATED
    commissions = list(
        await db.scalars(
            select(Commission)
            .where(Commission.organization_id == org, Commission.booking_id == booking.id)
            .with_for_update()
        )
    )
    for commission in commissions:
        previous = commission.status
        commission.status = CommissionStatus.REVERSED
        db.add(
            _audit(
                org,
                context,
                "commission.reversed_on_cancellation",
                "commission",
                commission.id,
                {"status": previous.value, "amount": str(commission.amount)},
                {"status": commission.status.value, "cancellation_id": item.id},
            )
        )
    item.document_number = f"CAN-{now:%Y%m%d}-{item.id[:8].upper()}"
    item.document_storage_key = await _save_document(
        db,
        org,
        "cancellations",
        item.id,
        item.document_number,
        "BOOKING CANCELLATION",
        (
            f"Booking: {booking.booking_number}",
            f"Unit: {unit.unit_number}",
            f"Status: {item.status.value}",
            f"Paid amount: {booking.currency} {item.paid_amount_snapshot:.2f}",
            f"Approved deduction: {booking.currency} {item.deduction_amount:.2f}",
            f"Refund due: {booking.currency} {item.refund_amount:.2f}",
            f"Reason: {item.reason}",
        ),
    )
    item.document_generated_at = now
    db.add(
        _audit(
            org,
            context,
            "cancellation.completed",
            "cancellation",
            item.id,
            {"status": WorkflowStatus.APPROVED.value, "unit_status": UnitStatus.BOOKED.value},
            {
                "status": item.status.value,
                "unit_released": True,
                "refund_id": refund.id if refund else None,
                "refund_amount": str(item.refund_amount),
                "document_number": item.document_number,
            },
        )
    )
    await db.commit()
    return await cancellation_view(db, org, item)


async def request_transfer(
    db: AsyncSession,
    org: str,
    booking_id: str,
    payload: UnitTransferCreate,
    context: MutationContext,
) -> UnitTransferView:
    booking = await _entity(db, Booking, org, booking_id, lock=True)
    quote = await _entity(db, Quotation, org, payload.quotation_id)
    if booking.status != BookingStatus.CONFIRMED:
        raise _error("BOOKING_NOT_TRANSFERABLE", "Only a confirmed booking can be transferred")
    if (
        quote.status != QuotationStatus.ACCEPTED
        or not quote.unit_id
        or quote.final_agreed_value is None
        or quote.customer_id != booking.customer_id
    ):
        raise _error(
            "INVALID_TRANSFER_QUOTATION",
            "Use an accepted quotation for this customer and target unit",
            422,
        )
    if quote.currency != booking.currency:
        raise _error("CURRENCY_MISMATCH", "Transfer quotation must use the booking currency", 422)
    target = await _entity(db, Unit, org, quote.unit_id, lock=True)
    if target.id == booking.unit_id or not await _unit_is_available(db, org, target):
        raise _error("TARGET_UNIT_UNAVAILABLE", "Target unit is not available")
    total = _money(sum((entry.amount for entry in payload.revised_payment_plan.installments), ZERO))
    new_price = _money(quote.final_agreed_value)
    if total != new_price:
        raise _error(
            "PAYMENT_PLAN_TOTAL_MISMATCH",
            "Revised installments must equal the target quotation value",
            422,
        )
    if await db.scalar(
        select(UnitTransfer.id).where(
            UnitTransfer.organization_id == org, UnitTransfer.active_booking_key == booking.id
        )
    ):
        raise _error("ACTIVE_TRANSFER_EXISTS", "This booking already has an active unit transfer")
    now = _now()
    old_price = _money(booking.agreed_price or ZERO)
    item = UnitTransfer(
        organization_id=org,
        booking_id=booking.id,
        from_unit_id=booking.unit_id,
        to_unit_id=target.id,
        quotation_id=quote.id,
        requested_by_user_id=context.actor_user_id,
        status=WorkflowStatus.REQUESTED,
        reason=payload.reason.strip(),
        active_booking_key=booking.id,
        old_agreed_price=old_price,
        new_agreed_price=new_price,
        price_difference=_money(new_price - old_price),
        paid_amount_snapshot=ZERO,
        pricing_snapshot=quote.pricing_snapshot,
        payment_plan_snapshot=payload.revised_payment_plan.model_dump(mode="json"),
        requested_at=now,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "unit_transfer.requested",
            "unit_transfer",
            item.id,
            None,
            {
                "booking_id": booking.id,
                "from_unit_id": booking.unit_id,
                "to_unit_id": target.id,
                "old_price": str(old_price),
                "new_price": str(new_price),
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(
            "TARGET_UNIT_UNAVAILABLE", "Target unit or booking is already in another workflow"
        ) from exc
    return await transfer_view(db, org, item)


async def review_transfer(
    db: AsyncSession,
    org: str,
    transfer_id: str,
    payload: UnitTransferReview,
    context: MutationContext,
) -> UnitTransferView:
    item = await _entity(db, UnitTransfer, org, transfer_id, lock=True)
    if item.status != WorkflowStatus.REQUESTED:
        raise _error("INVALID_TRANSFER_TRANSITION", "Only a requested transfer can be reviewed")
    target = await _entity(db, Unit, org, item.to_unit_id, lock=True)
    quote = await _entity(db, Quotation, org, item.quotation_id)
    if (
        not await _unit_is_available(db, org, target)
        or quote.status != QuotationStatus.ACCEPTED
        or quote.final_agreed_value != item.new_agreed_price
    ):
        raise _error("TRANSFER_TERMS_CHANGED", "Target availability or accepted pricing changed")
    item.status = WorkflowStatus.UNDER_REVIEW
    item.reviewed_by_user_id = context.actor_user_id
    item.review_notes = payload.notes.strip()
    item.reviewed_at = _now()
    item.paid_amount_snapshot = await _paid_amount(db, org, item.booking_id)
    db.add(
        _audit(
            org,
            context,
            "unit_transfer.reviewed",
            "unit_transfer",
            item.id,
            {"status": WorkflowStatus.REQUESTED.value},
            {"status": item.status.value, "paid_amount": str(item.paid_amount_snapshot)},
        )
    )
    await db.commit()
    return await transfer_view(db, org, item)


async def decide_transfer(
    db: AsyncSession,
    org: str,
    transfer_id: str,
    payload: WorkflowDecision,
    context: MutationContext,
) -> UnitTransferView:
    item = await _entity(db, UnitTransfer, org, transfer_id, lock=True)
    if item.status != WorkflowStatus.UNDER_REVIEW:
        raise _error("INVALID_TRANSFER_TRANSITION", "Transfer must be reviewed before a decision")
    if context.actor_user_id in {item.requested_by_user_id, item.reviewed_by_user_id}:
        raise _error(
            "SELF_APPROVAL_NOT_ALLOWED", "Requester or reviewer cannot approve this transfer", 403
        )
    item.approved_by_user_id = context.actor_user_id
    item.decision_notes = payload.notes.strip()
    item.decided_at = _now()
    item.status = (
        WorkflowStatus.APPROVED if payload.status == "APPROVED" else WorkflowStatus.REJECTED
    )
    if item.status == WorkflowStatus.REJECTED:
        item.active_booking_key = None
    db.add(
        _audit(
            org,
            context,
            "unit_transfer.decided",
            "unit_transfer",
            item.id,
            {"status": WorkflowStatus.UNDER_REVIEW.value},
            {"status": item.status.value, "notes": item.decision_notes},
        )
    )
    await db.commit()
    return await transfer_view(db, org, item)


async def _revise_plan(
    db: AsyncSession, org: str, booking: Booking, item: UnitTransfer, actor: str
) -> None:
    current = (
        await db.scalars(
            select(PaymentPlan)
            .where(
                PaymentPlan.organization_id == org,
                PaymentPlan.booking_id == booking.id,
                PaymentPlan.status == RecordStatus.ACTIVE,
            )
            .with_for_update()
        )
    ).first()
    allocations: list[PaymentAllocation] = []
    if current:
        installment_ids = select(Installment.id).where(
            Installment.organization_id == org, Installment.payment_plan_id == current.id
        )
        allocations = list(
            await db.scalars(
                select(PaymentAllocation)
                .where(
                    PaymentAllocation.organization_id == org,
                    PaymentAllocation.installment_id.in_(installment_ids),
                    PaymentAllocation.reversed_at.is_(None),
                )
                .order_by(PaymentAllocation.allocated_at)
                .with_for_update()
            )
        )
        current.status = RecordStatus.ARCHIVED
    snapshot = item.payment_plan_snapshot
    plan = PaymentPlan(
        organization_id=org,
        booking_id=booking.id,
        name=f"{str(snapshot['name'])[:130]} - Transfer {item.id[:8]}",
        status=RecordStatus.ACTIVE,
        currency=booking.currency,
        total_amount=item.new_agreed_price,
        effective_from=date.fromisoformat(str(snapshot["effective_from"])),
    )
    db.add(plan)
    await db.flush()
    new_installments: list[Installment] = []
    installment_rows = cast(list[dict[str, Any]], snapshot["installments"])
    for sequence, row in enumerate(installment_rows, start=1):
        installment = Installment(
            organization_id=org,
            payment_plan_id=plan.id,
            sequence=sequence,
            name=str(row["name"]),
            due_date=date.fromisoformat(str(row["due_date"])),
            amount=Decimal(str(row["amount"])),
            paid_amount=ZERO,
            status=InstallmentStatus.SCHEDULED,
        )
        db.add(installment)
        new_installments.append(installment)
    await db.flush()
    index = 0
    for old_allocation in allocations:
        remaining = old_allocation.amount
        old_allocation.reversed_at = _now()
        while remaining > ZERO and index < len(new_installments):
            target = new_installments[index]
            capacity = target.amount - target.paid_amount
            transferred = min(capacity, remaining)
            if transferred > ZERO:
                db.add(
                    PaymentAllocation(
                        organization_id=org,
                        payment_id=old_allocation.payment_id,
                        installment_id=target.id,
                        demand_letter_id=None,
                        allocated_by_user_id=actor,
                        amount=transferred,
                        idempotency_key=f"transfer:{item.id}:allocation:{old_allocation.id}:{target.id}",
                        allocated_at=_now(),
                    )
                )
                target.paid_amount += transferred
                remaining -= transferred
            if target.paid_amount >= target.amount:
                target.status = InstallmentStatus.PAID
                index += 1
            elif target.paid_amount > ZERO:
                target.status = InstallmentStatus.PARTIALLY_PAID
                break
        if remaining > ZERO:
            raise _error(
                "PAYMENTS_EXCEED_NEW_PRICE", "Transferred payments exceed the new unit price"
            )


async def complete_transfer(
    db: AsyncSession, org: str, transfer_id: str, context: MutationContext
) -> UnitTransferView:
    ref = await _entity(db, UnitTransfer, org, transfer_id)
    units = list(
        await db.scalars(
            select(Unit)
            .where(
                Unit.organization_id == org, Unit.id.in_(sorted((ref.from_unit_id, ref.to_unit_id)))
            )
            .order_by(Unit.id)
            .with_for_update()
        )
    )
    unit_map = {unit.id: unit for unit in units}
    if len(unit_map) != 2:
        raise _error("RESOURCE_NOT_FOUND", "Transfer unit not found", 404)
    booking = await _entity(db, Booking, org, ref.booking_id, lock=True)
    item = await _entity(db, UnitTransfer, org, transfer_id, lock=True)
    old_unit, new_unit = unit_map[item.from_unit_id], unit_map[item.to_unit_id]
    if item.status != WorkflowStatus.APPROVED:
        raise _error("INVALID_TRANSFER_TRANSITION", "Transfer must be approved before completion")
    if (
        booking.status != BookingStatus.CONFIRMED
        or booking.unit_id != old_unit.id
        or booking.active_unit_key != old_unit.id
        or old_unit.status not in (UnitStatus.BOOKED, UnitStatus.SOLD)
    ):
        raise _error("BOOKING_STATE_CHANGED", "Booking or old unit state changed")
    if not await _unit_is_available(db, org, new_unit):
        raise _error("TARGET_UNIT_UNAVAILABLE", "Target unit is no longer available")
    quote = await _entity(db, Quotation, org, item.quotation_id)
    if (
        quote.status != QuotationStatus.ACCEPTED
        or quote.unit_id != new_unit.id
        or quote.final_agreed_value != item.new_agreed_price
    ):
        raise _error("TRANSFER_TERMS_CHANGED", "Accepted target quotation changed")
    if await _paid_amount(db, org, booking.id) != item.paid_amount_snapshot:
        raise _error(
            "PAYMENT_STATE_CHANGED", "Payments changed after review; review the transfer again"
        )
    now = _now()
    await _revise_plan(db, org, booking, item, context.actor_user_id)
    old_unit.status = UnitStatus.CANCELLED_RELEASED
    new_unit.status = UnitStatus.BOOKED
    booking.unit_id = new_unit.id
    booking.active_unit_key = new_unit.id
    booking.quotation_id = quote.id
    booking.agreed_price = item.new_agreed_price
    booking.discount_amount = quote.discount_amount
    booking.booking_amount = quote.booking_amount or ZERO
    if item.price_difference != ZERO:
        db.add(
            CustomerLedger(
                organization_id=org,
                customer_id=booking.customer_id,
                booking_id=booking.id,
                entry_type=LedgerEntryType.DEBIT
                if item.price_difference > ZERO
                else LedgerEntryType.CREDIT,
                amount=abs(item.price_difference),
                currency=booking.currency,
                description=f"Unit transfer price adjustment {item.id}",
                idempotency_key=f"unit-transfer:{item.id}:price-adjustment",
                posted_at=now,
            )
        )
    commissions = list(
        await db.scalars(
            select(Commission)
            .where(Commission.organization_id == org, Commission.booking_id == booking.id)
            .with_for_update()
        )
    )
    commission_rows: list[dict[str, object]] = []
    for commission in commissions:
        previous_amount = commission.amount
        new_amount = _money(item.new_agreed_price * commission.rate_percent / Decimal("100"))
        status = commission.status
        if status != CommissionStatus.PAID:
            commission.amount = new_amount
        commission_rows.append(
            {
                "commission_id": commission.id,
                "status": status.value,
                "previous_amount": str(previous_amount),
                "recalculated_amount": str(new_amount),
                "adjustment_amount": str(new_amount - previous_amount),
                "requires_settlement": status == CommissionStatus.PAID,
            }
        )
        db.add(
            _audit(
                org,
                context,
                "commission.adjusted_on_unit_transfer",
                "commission",
                commission.id,
                {"amount": str(previous_amount), "status": status.value},
                {
                    "amount": str(commission.amount),
                    "calculated_amount": str(new_amount),
                    "adjustment_amount": str(new_amount - previous_amount),
                    "requires_settlement": status == CommissionStatus.PAID,
                    "unit_transfer_id": item.id,
                },
            )
        )
    item.commission_snapshot = {"adjustments": commission_rows}
    item.status = WorkflowStatus.COMPLETED
    item.active_booking_key = None
    item.completed_at = now
    item.document_number = f"UTR-{now:%Y%m%d}-{item.id[:8].upper()}"
    item.document_storage_key = await _save_document(
        db,
        org,
        "unit-transfers",
        item.id,
        item.document_number,
        "UNIT TRANSFER ADDENDUM",
        (
            f"Booking: {booking.booking_number}",
            f"Old unit: {old_unit.unit_number}",
            f"New unit: {new_unit.unit_number}",
            f"Old value: {booking.currency} {item.old_agreed_price:.2f}",
            f"New value: {booking.currency} {item.new_agreed_price:.2f}",
            f"Price adjustment: {booking.currency} {item.price_difference:.2f}",
            f"Payments transferred: {booking.currency} {item.paid_amount_snapshot:.2f}",
            f"Reason: {item.reason}",
        ),
    )
    item.document_generated_at = now
    db.add(
        _audit(
            org,
            context,
            "unit_transfer.completed",
            "unit_transfer",
            item.id,
            {
                "status": WorkflowStatus.APPROVED.value,
                "unit_id": old_unit.id,
                "agreed_price": str(item.old_agreed_price),
            },
            {
                "status": item.status.value,
                "unit_id": new_unit.id,
                "agreed_price": str(item.new_agreed_price),
                "payment_plan_revised": True,
                "payments_transferred": str(item.paid_amount_snapshot),
                "commission_adjustments": commission_rows,
                "document_number": item.document_number,
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("TARGET_UNIT_UNAVAILABLE", "Target unit was allocated concurrently") from exc
    return await transfer_view(db, org, item)


async def document_path(
    db: AsyncSession, org: str, kind: str, workflow_id: str
) -> tuple[Path, str]:
    if kind == "cancellations":
        item: Cancellation | UnitTransfer = await _entity(db, Cancellation, org, workflow_id)
    else:
        item = await _entity(db, UnitTransfer, org, workflow_id)
    if not item.document_storage_key or not item.document_number:
        raise _error("DOCUMENT_NOT_READY", "Workflow document has not been generated", 404)
    try:
        path = await LocalStorage(get_settings().storage_local_path).path_for_read(
            key=item.document_storage_key
        )
    except FileNotFoundError as exc:
        raise _error("DOCUMENT_NOT_FOUND", "Workflow document is unavailable", 404) from exc
    return path, f"{item.document_number}.pdf"
