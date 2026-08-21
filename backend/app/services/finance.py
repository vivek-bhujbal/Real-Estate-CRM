from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Booking,
    Customer,
    CustomerLedger,
    DemandLetter,
    FinancialCharge,
    Installment,
    Payment,
    PaymentAllocation,
    PaymentPlan,
    PaymentReconciliation,
    Project,
    Receipt,
    Refund,
    Unit,
)
from app.models.enums import (
    BookingStatus,
    FinancialChargeStatus,
    InstallmentStatus,
    LedgerEntryType,
    PaymentStatus,
    ReconciliationStatus,
    RecordStatus,
)
from app.schemas.finance import (
    ChargeCreate,
    ChargeWaive,
    CollectionAccount,
    CollectionAccountDetail,
    CollectionPaymentCreate,
    DemandCreate,
    FinanceAllocation,
    FinanceCharge,
    FinanceDemand,
    FinanceInstallment,
    FinancePayment,
    FinanceReconciliation,
    FinanceRefund,
    FinanceSummary,
    LedgerEntryView,
    PaymentAllocationRequest,
    ReconciliationCreate,
    RefundCreate,
    RefundDecision,
    RefundProcess,
)
from app.schemas.organization import Page
from app.services.organization import MutationContext

ZERO = Decimal("0.00")
MONEY = Decimal("0.01")


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
        raise _error("RESOURCE_NOT_FOUND", "Financial record not found", 404)
    return item


async def _plan(db: AsyncSession, org: str, booking_id: str) -> PaymentPlan | None:
    return (
        await db.scalars(
            select(PaymentPlan)
            .where(PaymentPlan.organization_id == org, PaymentPlan.booking_id == booking_id)
            .order_by(PaymentPlan.created_at.desc())
        )
    ).first()


async def _installments(
    db: AsyncSession, org: str, plan_id: str, *, lock: bool = False
) -> list[Installment]:
    statement = (
        select(Installment)
        .where(Installment.organization_id == org, Installment.payment_plan_id == plan_id)
        .order_by(Installment.due_date, Installment.sequence)
    )
    if lock:
        statement = statement.with_for_update()
    items = list(await db.scalars(statement))
    today = date.today()
    for item in items:
        if item.status == InstallmentStatus.WAIVED:
            continue
        if item.paid_amount >= item.amount:
            item.status = InstallmentStatus.PAID
        elif item.paid_amount > ZERO:
            item.status = (
                InstallmentStatus.PARTIALLY_PAID
                if item.due_date >= today
                else InstallmentStatus.OVERDUE
            )
        elif item.due_date < today:
            item.status = InstallmentStatus.OVERDUE
        elif item.due_date == today:
            item.status = InstallmentStatus.DUE
        else:
            item.status = InstallmentStatus.SCHEDULED
    return items


async def _account(db: AsyncSession, org: str, booking: Booking) -> CollectionAccount:
    customer = await _entity(db, Customer, org, booking.customer_id)
    unit = await _entity(db, Unit, org, booking.unit_id)
    project = await _entity(db, Project, org, unit.project_id)
    debits = (
        await db.scalar(
            select(func.coalesce(func.sum(CustomerLedger.amount), 0)).where(
                CustomerLedger.organization_id == org,
                CustomerLedger.booking_id == booking.id,
                CustomerLedger.entry_type == LedgerEntryType.DEBIT,
            )
        )
        or ZERO
    )
    credits = (
        await db.scalar(
            select(func.coalesce(func.sum(CustomerLedger.amount), 0)).where(
                CustomerLedger.organization_id == org,
                CustomerLedger.booking_id == booking.id,
                CustomerLedger.entry_type == LedgerEntryType.CREDIT,
            )
        )
        or ZERO
    )
    plan = await _plan(db, org, booking.id)
    overdue = ZERO
    next_due: date | None = None
    if plan:
        for item in await _installments(db, org, plan.id):
            remaining = max(item.amount - item.paid_amount, ZERO)
            if item.due_date < date.today() and item.status != InstallmentStatus.WAIVED:
                overdue += remaining
            if remaining > ZERO and (next_due is None or item.due_date < next_due):
                next_due = item.due_date
    return CollectionAccount(
        booking_id=booking.id,
        booking_number=booking.booking_number,
        booking_status=booking.status.value,
        customer_id=customer.id,
        customer_name=customer.full_name,
        project_name=project.name,
        unit_number=unit.unit_number,
        currency=booking.currency,
        total_value=debits,
        received=credits,
        outstanding=max(debits - credits, ZERO),
        overdue=overdue,
        next_due_date=next_due,
    )


async def summary(db: AsyncSession, org: str) -> FinanceSummary:
    debits = (
        await db.scalar(
            select(func.coalesce(func.sum(CustomerLedger.amount), 0)).where(
                CustomerLedger.organization_id == org,
                CustomerLedger.entry_type == LedgerEntryType.DEBIT,
            )
        )
        or ZERO
    )
    credits = (
        await db.scalar(
            select(func.coalesce(func.sum(CustomerLedger.amount), 0)).where(
                CustomerLedger.organization_id == org,
                CustomerLedger.entry_type == LedgerEntryType.CREDIT,
            )
        )
        or ZERO
    )
    overdue = (
        await db.scalar(
            select(func.coalesce(func.sum(Installment.amount - Installment.paid_amount), 0))
            .join(
                PaymentPlan,
                (PaymentPlan.organization_id == Installment.organization_id)
                & (PaymentPlan.id == Installment.payment_plan_id),
            )
            .where(
                Installment.organization_id == org,
                Installment.due_date < date.today(),
                Installment.status.not_in((InstallmentStatus.PAID, InstallmentStatus.WAIVED)),
            )
        )
        or ZERO
    )
    completed = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == org, Payment.status == PaymentStatus.COMPLETED
            )
        )
        or ZERO
    )
    allocated = (
        await db.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.organization_id == org, PaymentAllocation.reversed_at.is_(None)
            )
        )
        or ZERO
    )
    pending_reconciliation = (
        await db.scalar(
            select(func.count(Payment.id)).where(
                Payment.organization_id == org,
                Payment.status.in_((PaymentStatus.PENDING, PaymentStatus.PROCESSING)),
            )
        )
        or 0
    )
    pending_refunds = (
        await db.scalar(
            select(func.count(Refund.id)).where(
                Refund.organization_id == org,
                Refund.status.in_((PaymentStatus.PENDING, PaymentStatus.PROCESSING)),
            )
        )
        or 0
    )
    return FinanceSummary(
        total_receivable=debits,
        received=credits,
        outstanding=max(debits - credits, ZERO),
        overdue=overdue,
        unapplied_payments=max(completed - allocated, ZERO),
        pending_reconciliation=pending_reconciliation,
        pending_refunds=pending_refunds,
    )


async def list_accounts(
    db: AsyncSession, org: str, *, q: str | None, overdue_only: bool, page: int, page_size: int
) -> Page[CollectionAccount]:
    statement = select(Booking).where(Booking.organization_id == org)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.join(
            Customer,
            (Customer.organization_id == Booking.organization_id)
            & (Customer.id == Booking.customer_id),
        ).where(or_(Booking.booking_number.ilike(pattern), Customer.full_name.ilike(pattern)))
    bookings = list(await db.scalars(statement.order_by(Booking.created_at.desc())))
    accounts = [await _account(db, org, item) for item in bookings]
    if overdue_only:
        accounts = [item for item in accounts if item.overdue > ZERO]
    total = len(accounts)
    start = (page - 1) * page_size
    return Page(
        items=accounts[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def detail(db: AsyncSession, org: str, booking_id: str) -> CollectionAccountDetail:
    booking = await _entity(db, Booking, org, booking_id)
    account = await _account(db, org, booking)
    plan = await _plan(db, org, booking.id)
    installments = await _installments(db, org, plan.id) if plan else []
    demands = list(
        await db.scalars(
            select(DemandLetter)
            .where(DemandLetter.organization_id == org, DemandLetter.booking_id == booking.id)
            .order_by(DemandLetter.issue_date.desc())
        )
    )
    payments = list(
        await db.scalars(
            select(Payment)
            .where(Payment.organization_id == org, Payment.booking_id == booking.id)
            .order_by(Payment.created_at.desc())
        )
    )
    allocations = list(
        await db.scalars(
            select(PaymentAllocation)
            .where(
                PaymentAllocation.organization_id == org,
                PaymentAllocation.payment_id.in_([item.id for item in payments] or [""]),
            )
            .order_by(PaymentAllocation.allocated_at)
        )
    )
    reconciliations = list(
        await db.scalars(
            select(PaymentReconciliation)
            .where(
                PaymentReconciliation.organization_id == org,
                PaymentReconciliation.payment_id.in_([item.id for item in payments] or [""]),
            )
            .order_by(PaymentReconciliation.reconciled_at.desc())
        )
    )
    receipts = {
        item.payment_id: item.receipt_number
        for item in list(
            await db.scalars(
                select(Receipt).where(
                    Receipt.organization_id == org,
                    Receipt.payment_id.in_([item.id for item in payments] or [""]),
                )
            )
        )
    }
    allocated_by_payment: dict[str, Decimal] = {}
    for item in allocations:
        if item.reversed_at is None:
            allocated_by_payment[item.payment_id] = (
                allocated_by_payment.get(item.payment_id, ZERO) + item.amount
            )
    charges = list(
        await db.scalars(
            select(FinancialCharge)
            .where(FinancialCharge.organization_id == org, FinancialCharge.booking_id == booking.id)
            .order_by(FinancialCharge.created_at.desc())
        )
    )
    refunds = list(
        await db.scalars(
            select(Refund)
            .where(Refund.organization_id == org, Refund.booking_id == booking.id)
            .order_by(Refund.requested_at.desc())
        )
    )
    ledger = list(
        await db.scalars(
            select(CustomerLedger)
            .where(CustomerLedger.organization_id == org, CustomerLedger.booking_id == booking.id)
            .order_by(CustomerLedger.posted_at.desc())
        )
    )
    return CollectionAccountDetail(
        account=account,
        plan_name=plan.name if plan else None,
        installments=[
            FinanceInstallment(
                id=i.id,
                sequence=i.sequence,
                name=i.name,
                due_date=i.due_date,
                amount=i.amount,
                paid_amount=i.paid_amount,
                outstanding=max(i.amount - i.paid_amount, ZERO),
                status=i.status,
            )
            for i in installments
        ],
        demands=[
            FinanceDemand(
                id=i.id,
                installment_id=i.installment_id,
                demand_number=i.demand_number,
                status=i.status,
                issue_date=i.issue_date,
                due_date=i.due_date,
                amount=i.amount,
                currency=i.currency,
            )
            for i in demands
        ],
        payments=[
            FinancePayment(
                id=i.id,
                amount=i.amount,
                allocated_amount=allocated_by_payment.get(i.id, ZERO),
                unallocated_amount=max(i.amount - allocated_by_payment.get(i.id, ZERO), ZERO),
                currency=i.currency,
                method=i.method,
                status=i.status,
                reference_number=i.reference_number,
                paid_at=i.paid_at,
                verified_at=i.verified_at,
                receipt_number=receipts.get(i.id),
                created_at=i.created_at,
            )
            for i in payments
        ],
        allocations=[
            FinanceAllocation.model_validate(i, from_attributes=True) for i in allocations
        ],
        reconciliations=[
            FinanceReconciliation.model_validate(i, from_attributes=True) for i in reconciliations
        ],
        charges=[FinanceCharge.model_validate(i, from_attributes=True) for i in charges],
        refunds=[FinanceRefund.model_validate(i, from_attributes=True) for i in refunds],
        ledger=[LedgerEntryView.model_validate(i, from_attributes=True) for i in ledger],
    )


async def create_demand(
    db: AsyncSession, org: str, booking_id: str, payload: DemandCreate, context: MutationContext
) -> CollectionAccountDetail:
    booking = await _entity(db, Booking, org, booking_id, lock=True)
    installment = await _entity(db, Installment, org, payload.installment_id, lock=True)
    plan = await _entity(db, PaymentPlan, org, installment.payment_plan_id)
    if plan.booking_id != booking.id:
        raise _error(
            "INSTALLMENT_BOOKING_MISMATCH", "Installment does not belong to the booking", 422
        )
    amount = _money(max(installment.amount - installment.paid_amount, ZERO))
    if amount <= ZERO:
        raise _error("INSTALLMENT_ALREADY_PAID", "A paid installment cannot be demanded")
    demand = DemandLetter(
        organization_id=org,
        booking_id=booking.id,
        customer_id=booking.customer_id,
        installment_id=installment.id,
        demand_number=payload.demand_number.strip().upper(),
        status=RecordStatus.ACTIVE,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        amount=amount,
        currency=booking.currency,
    )
    db.add(demand)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("DEMAND_NUMBER_EXISTS", "Demand number already exists") from exc
    db.add(
        _audit(
            org,
            context,
            "collection.demand.issued",
            "demand_letter",
            demand.id,
            None,
            {"booking_id": booking.id, "installment_id": installment.id, "amount": str(amount)},
        )
    )
    await db.commit()
    return await detail(db, org, booking.id)


async def create_payment(
    db: AsyncSession,
    org: str,
    booking_id: str,
    payload: CollectionPaymentCreate,
    context: MutationContext,
) -> CollectionAccountDetail:
    booking = await _entity(db, Booking, org, booking_id, lock=True)
    existing = (
        await db.scalars(
            select(Payment).where(
                Payment.organization_id == org, Payment.idempotency_key == payload.idempotency_key
            )
        )
    ).first()
    if existing:
        if existing.booking_id != booking.id or existing.amount != payload.amount:
            raise _error("IDEMPOTENCY_CONFLICT", "Idempotency key was used for another payment")
        return await detail(db, org, booking.id)
    payment = Payment(
        organization_id=org,
        booking_id=booking.id,
        customer_id=booking.customer_id,
        amount=payload.amount,
        currency=booking.currency,
        method=payload.method.strip().upper(),
        status=PaymentStatus.PENDING,
        reference_number=payload.reference_number,
        idempotency_key=payload.idempotency_key,
        paid_at=payload.paid_at or _now(),
    )
    db.add(payment)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "collection.payment.submitted",
            "payment",
            payment.id,
            None,
            {
                "booking_id": booking.id,
                "amount": str(payment.amount),
                "status": payment.status.value,
            },
        )
    )
    await db.commit()
    return await detail(db, org, booking.id)


async def reconcile_payment(
    db: AsyncSession,
    org: str,
    payment_id: str,
    payload: ReconciliationCreate,
    context: MutationContext,
) -> CollectionAccountDetail:
    payment = await _entity(db, Payment, org, payment_id, lock=True)
    if payment.status not in (PaymentStatus.PENDING, PaymentStatus.PROCESSING):
        raise _error("PAYMENT_FINALIZED", "Only pending payments can be reconciled")
    existing = (
        await db.scalars(
            select(PaymentReconciliation).where(
                PaymentReconciliation.organization_id == org,
                PaymentReconciliation.idempotency_key == payload.idempotency_key,
            )
        )
    ).first()
    if not existing:
        difference = _money(payload.received_amount - payment.amount)
        status = (
            ReconciliationStatus.MATCHED if difference == ZERO else ReconciliationStatus.MISMATCHED
        )
        item = PaymentReconciliation(
            organization_id=org,
            payment_id=payment.id,
            reconciled_by_user_id=context.actor_user_id,
            status=status,
            expected_amount=payment.amount,
            received_amount=payload.received_amount,
            difference_amount=difference,
            external_reference=payload.external_reference,
            idempotency_key=payload.idempotency_key,
            notes=payload.notes,
            reconciled_at=_now(),
        )
        db.add(item)
        payment.status = PaymentStatus.PROCESSING
        await db.flush()
        db.add(
            _audit(
                org,
                context,
                "collection.payment.reconciled",
                "payment_reconciliation",
                item.id,
                None,
                {"payment_id": payment.id, "status": status.value, "difference": str(difference)},
            )
        )
        await db.commit()
    return await detail(db, org, payment.booking_id)


async def allocate_payment(
    db: AsyncSession,
    org: str,
    payment_id: str,
    payload: PaymentAllocationRequest,
    context: MutationContext,
) -> CollectionAccountDetail:
    payment = await _entity(db, Payment, org, payment_id, lock=True)
    booking = await _entity(db, Booking, org, payment.booking_id, lock=True)
    if payment.status not in (PaymentStatus.PENDING, PaymentStatus.PROCESSING):
        raise _error("PAYMENT_FINALIZED", "Payment is already finalized")
    reconciliation = (
        await db.scalars(
            select(PaymentReconciliation)
            .where(
                PaymentReconciliation.organization_id == org,
                PaymentReconciliation.payment_id == payment.id,
            )
            .order_by(PaymentReconciliation.reconciled_at.desc())
        )
    ).first()
    if (
        reconciliation is None or reconciliation.status != ReconciliationStatus.MATCHED
    ) and not payload.manual_reconciliation_reason:
        raise _error(
            "RECONCILIATION_REQUIRED", "A matched reconciliation or documented override is required"
        )
    plan = await _plan(db, org, booking.id)
    if plan is None:
        raise _error("PAYMENT_PLAN_REQUIRED", "Booking has no payment plan")
    installments = await _installments(db, org, plan.id, lock=True)
    if payload.installment_ids:
        order = {value: index for index, value in enumerate(payload.installment_ids)}
        if any(
            value not in {item.id for item in installments} for value in payload.installment_ids
        ):
            raise _error("INSTALLMENT_BOOKING_MISMATCH", "Allocation includes another booking", 422)
        installments.sort(
            key=lambda item: (order.get(item.id, len(order)), item.due_date, item.sequence)
        )
    capacity = sum(
        (
            max(item.amount - item.paid_amount, ZERO)
            for item in installments
            if item.status != InstallmentStatus.WAIVED
        ),
        ZERO,
    )
    if payment.amount > capacity and not payload.allow_unallocated_credit:
        raise _error(
            "UNALLOCATED_PAYMENT",
            "Payment exceeds open installments; allow customer credit explicitly",
        )
    remaining = payment.amount
    for index, installment in enumerate(installments, start=1):
        open_amount = max(installment.amount - installment.paid_amount, ZERO)
        amount = min(open_amount, remaining)
        if amount <= ZERO:
            continue
        demand_id = await db.scalar(
            select(DemandLetter.id)
            .where(
                DemandLetter.organization_id == org,
                DemandLetter.installment_id == installment.id,
                DemandLetter.status == RecordStatus.ACTIVE,
            )
            .order_by(DemandLetter.created_at.desc())
        )
        db.add(
            PaymentAllocation(
                organization_id=org,
                payment_id=payment.id,
                installment_id=installment.id,
                demand_letter_id=demand_id,
                allocated_by_user_id=context.actor_user_id,
                amount=amount,
                idempotency_key=f"payment:{payment.id}:allocation:{index}",
                allocated_at=_now(),
            )
        )
        installment.paid_amount += amount
        installment.status = (
            InstallmentStatus.PAID
            if installment.paid_amount >= installment.amount
            else InstallmentStatus.PARTIALLY_PAID
        )
        remaining -= amount
        if remaining <= ZERO:
            break
    payment.status = PaymentStatus.COMPLETED
    payment.verified_by_user_id = context.actor_user_id
    payment.verified_at = _now()
    completed_total = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == org,
                Payment.booking_id == booking.id,
                Payment.status == PaymentStatus.COMPLETED,
            )
        )
    ) or ZERO
    if (
        completed_total >= booking.booking_amount
        and booking.status == BookingStatus.PAYMENT_PENDING
    ):
        booking.status = BookingStatus.VERIFICATION
        booking.submitted_at = _now()
        booking.verification_completed_at = _now()
    receipt = Receipt(
        organization_id=org,
        payment_id=payment.id,
        customer_id=payment.customer_id,
        receipt_number=f"RCT-{_now().year}-{payment.id[:8].upper()}",
        status=RecordStatus.ACTIVE,
        issued_at=_now(),
    )
    db.add(receipt)
    await db.flush()
    db.add(
        CustomerLedger(
            organization_id=org,
            customer_id=booking.customer_id,
            booking_id=booking.id,
            payment_id=payment.id,
            receipt_id=receipt.id,
            entry_type=LedgerEntryType.CREDIT,
            amount=payment.amount,
            currency=payment.currency,
            description=f"Verified payment receipt {receipt.receipt_number}",
            idempotency_key=f"payment:{payment.id}:ledger",
            posted_at=_now(),
        )
    )
    db.add(
        _audit(
            org,
            context,
            "collection.payment.allocated",
            "payment",
            payment.id,
            {"status": PaymentStatus.PROCESSING.value},
            {
                "status": PaymentStatus.COMPLETED.value,
                "allocated": str(payment.amount - remaining),
                "unallocated": str(remaining),
                "manual_override": payload.manual_reconciliation_reason,
            },
        )
    )
    db.add(
        _audit(
            org,
            context,
            "booking.payment.verified",
            "payment",
            payment.id,
            {"status": PaymentStatus.PROCESSING.value},
            {"status": PaymentStatus.COMPLETED.value, "receipt_number": receipt.receipt_number},
        )
    )
    await db.commit()
    return await detail(db, org, booking.id)


async def create_charge(
    db: AsyncSession, org: str, installment_id: str, payload: ChargeCreate, context: MutationContext
) -> CollectionAccountDetail:
    installment = await _entity(db, Installment, org, installment_id, lock=True)
    plan = await _entity(db, PaymentPlan, org, installment.payment_plan_id)
    booking = await _entity(db, Booking, org, plan.booking_id, lock=True)
    existing = (
        await db.scalars(
            select(FinancialCharge).where(
                FinancialCharge.organization_id == org,
                FinancialCharge.idempotency_key == payload.idempotency_key,
            )
        )
    ).first()
    if existing:
        return await detail(db, org, booking.id)
    principal = _money(max(installment.amount - installment.paid_amount, ZERO))
    if principal <= ZERO:
        raise _error("NO_CHARGEABLE_OUTSTANDING", "Installment has no outstanding principal")
    days = max((payload.calculation_date - installment.due_date).days, 0)
    rate = payload.annual_rate_percent or ZERO
    raw_amount = payload.fixed_amount
    if raw_amount is None:
        raw_amount = principal * rate * Decimal(days) / Decimal("36500")
    amount = _money(raw_amount)
    if amount <= ZERO:
        raise _error("ZERO_FINANCIAL_CHARGE", "Calculated charge is zero", 422)
    item = FinancialCharge(
        organization_id=org,
        booking_id=booking.id,
        customer_id=booking.customer_id,
        installment_id=installment.id,
        created_by_user_id=context.actor_user_id,
        charge_type=payload.charge_type,
        status=FinancialChargeStatus.APPLIED,
        principal_amount=principal,
        rate_percent=rate,
        days_calculated=days,
        amount=amount,
        paid_amount=ZERO,
        currency=booking.currency,
        calculation_date=payload.calculation_date,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
    )
    db.add(item)
    await db.flush()
    db.add(
        CustomerLedger(
            organization_id=org,
            customer_id=booking.customer_id,
            booking_id=booking.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=amount,
            currency=booking.currency,
            description=f"{payload.charge_type.value.title()} charge: {payload.reason}",
            idempotency_key=f"charge:{item.id}:applied",
            posted_at=_now(),
        )
    )
    db.add(
        _audit(
            org,
            context,
            "collection.charge.applied",
            "financial_charge",
            item.id,
            None,
            {"principal": str(principal), "rate": str(rate), "days": days, "amount": str(amount)},
        )
    )
    await db.commit()
    return await detail(db, org, booking.id)


async def waive_charge(
    db: AsyncSession, org: str, charge_id: str, payload: ChargeWaive, context: MutationContext
) -> CollectionAccountDetail:
    item = await _entity(db, FinancialCharge, org, charge_id, lock=True)
    if item.status not in (FinancialChargeStatus.APPLIED, FinancialChargeStatus.PARTIALLY_PAID):
        raise _error("CHARGE_FINALIZED", "Charge cannot be waived")
    remaining = item.amount - item.paid_amount
    item.status = FinancialChargeStatus.WAIVED
    item.waived_by_user_id = context.actor_user_id
    item.waived_reason = payload.reason
    item.waived_at = _now()
    db.add(
        CustomerLedger(
            organization_id=org,
            customer_id=item.customer_id,
            booking_id=item.booking_id,
            entry_type=LedgerEntryType.CREDIT,
            amount=remaining,
            currency=item.currency,
            description=f"Waived {item.charge_type.value.lower()}: {payload.reason}",
            idempotency_key=f"charge:{item.id}:waived",
            posted_at=_now(),
        )
    )
    db.add(
        _audit(
            org,
            context,
            "collection.charge.waived",
            "financial_charge",
            item.id,
            {"status": FinancialChargeStatus.APPLIED.value},
            {"status": item.status.value, "amount": str(remaining), "reason": payload.reason},
        )
    )
    await db.commit()
    return await detail(db, org, item.booking_id)


async def request_refund(
    db: AsyncSession, org: str, payment_id: str, payload: RefundCreate, context: MutationContext
) -> CollectionAccountDetail:
    payment = await _entity(db, Payment, org, payment_id, lock=True)
    if payment.status not in (PaymentStatus.COMPLETED, PaymentStatus.REFUNDED):
        raise _error("PAYMENT_NOT_REFUNDABLE", "Only verified payments can be refunded")
    existing = (
        await db.scalars(
            select(Refund).where(
                Refund.organization_id == org, Refund.idempotency_key == payload.idempotency_key
            )
        )
    ).first()
    if existing:
        return await detail(db, org, payment.booking_id)
    committed = (
        await db.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.organization_id == org,
                Refund.payment_id == payment.id,
                Refund.status.in_(
                    (PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.COMPLETED)
                ),
            )
        )
        or ZERO
    )
    if committed + payload.amount > payment.amount:
        raise _error("REFUND_EXCEEDS_PAYMENT", "Refunds cannot exceed the verified payment", 422)
    item = Refund(
        organization_id=org,
        cancellation_id=None,
        booking_id=payment.booking_id,
        payment_id=payment.id,
        customer_id=payment.customer_id,
        requested_by_user_id=context.actor_user_id,
        status=PaymentStatus.PENDING,
        amount=payload.amount,
        currency=payment.currency,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
        requested_at=_now(),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "collection.refund.requested",
            "refund",
            item.id,
            None,
            {"payment_id": payment.id, "amount": str(item.amount), "reason": item.reason},
        )
    )
    await db.commit()
    return await detail(db, org, payment.booking_id)


async def decide_refund(
    db: AsyncSession, org: str, refund_id: str, payload: RefundDecision, context: MutationContext
) -> CollectionAccountDetail:
    item = await _entity(db, Refund, org, refund_id, lock=True)
    if item.status != PaymentStatus.PENDING:
        raise _error("REFUND_FINALIZED", "Refund decision is already recorded")
    if item.requested_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Refund requester cannot approve the refund", 403)
    item.approved_by_user_id = context.actor_user_id
    item.decision_notes = payload.notes
    if payload.status == "APPROVED":
        item.status = PaymentStatus.PROCESSING
        item.approved_at = _now()
    else:
        item.status = PaymentStatus.FAILED
        item.rejected_at = _now()
    db.add(
        _audit(
            org,
            context,
            "collection.refund.decided",
            "refund",
            item.id,
            {"status": PaymentStatus.PENDING.value},
            {"status": item.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await detail(db, org, str(item.booking_id))


async def process_refund(
    db: AsyncSession, org: str, refund_id: str, payload: RefundProcess, context: MutationContext
) -> CollectionAccountDetail:
    item = await _entity(db, Refund, org, refund_id, lock=True)
    if item.status != PaymentStatus.PROCESSING or not item.booking_id:
        raise _error("REFUND_NOT_APPROVED", "Refund must be approved before processing")
    if item.payment_id:
        payments = [await _entity(db, Payment, org, item.payment_id, lock=True)]
    elif item.cancellation_id:
        payments = list(
            await db.scalars(
                select(Payment)
                .where(
                    Payment.organization_id == org,
                    Payment.booking_id == item.booking_id,
                    Payment.status.in_((PaymentStatus.COMPLETED, PaymentStatus.REFUNDED)),
                )
                .order_by(Payment.paid_at.desc(), Payment.created_at.desc())
                .with_for_update()
            )
        )
    else:
        raise _error("REFUND_NOT_APPROVED", "Refund must be linked to a payment or cancellation")
    remaining = item.amount
    allocations = list(
        await db.scalars(
            select(PaymentAllocation)
            .where(
                PaymentAllocation.organization_id == org,
                PaymentAllocation.payment_id.in_([payment.id for payment in payments]),
                PaymentAllocation.reversed_at.is_(None),
            )
            .order_by(PaymentAllocation.allocated_at.desc())
            .with_for_update()
        )
    )
    for allocation in allocations:
        if remaining <= ZERO:
            break
        reverse = min(allocation.amount, remaining)
        if allocation.installment_id:
            installment = await _entity(db, Installment, org, allocation.installment_id, lock=True)
            installment.paid_amount = max(installment.paid_amount - reverse, ZERO)
            installment.status = (
                InstallmentStatus.OVERDUE
                if installment.due_date < date.today()
                else (
                    InstallmentStatus.PARTIALLY_PAID
                    if installment.paid_amount > ZERO
                    else InstallmentStatus.SCHEDULED
                )
            )
        if reverse == allocation.amount:
            allocation.reversed_at = _now()
        else:
            allocation.amount -= reverse
        remaining -= reverse
    for payment in payments:
        has_active_allocation = await db.scalar(
            select(PaymentAllocation.id).where(
                PaymentAllocation.organization_id == org,
                PaymentAllocation.payment_id == payment.id,
                PaymentAllocation.reversed_at.is_(None),
            )
        )
        if has_active_allocation is None:
            payment.status = PaymentStatus.REFUNDED
    item.status = PaymentStatus.COMPLETED
    item.reference_number = payload.reference_number
    item.processed_at = _now()
    if item.payment_id:
        payment = payments[0]
        refunded = (
            await db.scalar(
                select(func.coalesce(func.sum(Refund.amount), 0)).where(
                    Refund.organization_id == org,
                    Refund.payment_id == payment.id,
                    Refund.status == PaymentStatus.COMPLETED,
                )
            )
            or ZERO
        )
        if refunded + item.amount >= payment.amount:
            payment.status = PaymentStatus.REFUNDED
    db.add(
        CustomerLedger(
            organization_id=org,
            customer_id=item.customer_id,
            booking_id=item.booking_id,
            payment_id=item.payment_id,
            entry_type=LedgerEntryType.DEBIT,
            amount=item.amount,
            currency=item.currency,
            description=f"Processed refund {payload.reference_number}",
            idempotency_key=f"refund:{item.id}:processed",
            posted_at=_now(),
        )
    )
    db.add(
        _audit(
            org,
            context,
            "collection.refund.processed",
            "refund",
            item.id,
            {"status": PaymentStatus.PROCESSING.value},
            {
                "status": PaymentStatus.COMPLETED.value,
                "reference_number": payload.reference_number,
                "amount": str(item.amount),
            },
        )
    )
    await db.commit()
    return await detail(db, org, item.booking_id)
