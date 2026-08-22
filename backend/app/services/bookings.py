from datetime import UTC, date, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Booking,
    BookingApplicant,
    BookingApproval,
    BookingFinancing,
    ChannelPartner,
    Customer,
    CustomerDocument,
    CustomerLedger,
    Installment,
    PartnerLead,
    PartnerProject,
    Payment,
    PaymentPlan,
    Permission,
    Project,
    Quotation,
    RolePermission,
    Unit,
    UnitHold,
    User,
    UserRole,
)
from app.models.enums import (
    ApprovalStatus,
    BookingStatus,
    DocumentStatus,
    FinancingStatus,
    HoldStatus,
    InstallmentStatus,
    LedgerEntryType,
    NotificationEventType,
    PartnerStatus,
    PaymentStatus,
    QuotationStatus,
    RecordStatus,
    UnitStatus,
    WorkflowStatus,
)
from app.schemas.bookings import (
    BookingAdvance,
    BookingApplicantView,
    BookingApprovalDecision,
    BookingApprovalRequest,
    BookingApprovalView,
    BookingCancel,
    BookingCreate,
    BookingDocumentSummary,
    BookingOption,
    BookingOptions,
    BookingPaymentCreate,
    BookingPaymentDecision,
    BookingPaymentView,
    BookingStats,
    BookingView,
    EligibleQuotationOption,
    FinancingInput,
    FinancingView,
    InstallmentView,
    JointApplicantInput,
    PaymentPlanInput,
    PaymentPlanView,
)
from app.schemas.organization import Page
from app.services import notifications as notification_service
from app.services.documents import expire_due_documents
from app.services.organization import MutationContext

ZERO = Decimal("0")
FINAL_STATUSES = {BookingStatus.CONFIRMED, BookingStatus.REJECTED, BookingStatus.CANCELLED}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _not_found() -> AppError:
    return AppError(status_code=404, code="RESOURCE_NOT_FOUND", message="Booking not found")


def _audit(
    organization_id: str,
    context: MutationContext,
    action: str,
    entity_type: str,
    entity_id: str,
    previous_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=previous_value,
        new_value=new_value,
        request_id=context.request_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
        created_at=_now(),
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


async def _booking_and_unit(
    db: AsyncSession, organization_id: str, booking_id: str
) -> tuple[Booking, Unit]:
    booking_ref = await _entity(db, Booking, organization_id, booking_id)
    unit = await _entity(db, Unit, organization_id, booking_ref.unit_id, lock=True)
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    return booking, unit


async def _has_verified_kyc(db: AsyncSession, organization_id: str, customer_id: str) -> bool:
    return bool(
        await db.scalar(
            select(CustomerDocument.id).where(
                CustomerDocument.organization_id == organization_id,
                CustomerDocument.customer_id == customer_id,
                CustomerDocument.is_current.is_(True),
                CustomerDocument.status == DocumentStatus.VERIFIED,
            )
        )
    )


async def _payment_total(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    statuses: tuple[PaymentStatus, ...],
) -> Decimal:
    return (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == organization_id,
                Payment.booking_id == booking_id,
                Payment.status.in_(statuses),
            )
        )
    ) or ZERO


async def _name(db: AsyncSession, organization_id: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = await db.scalar(
        select(User.full_name).where(User.organization_id == organization_id, User.id == user_id)
    )
    return str(value) if value is not None else None


async def _applicant_views(
    db: AsyncSession, organization_id: str, booking_id: str
) -> list[BookingApplicantView]:
    items = list(
        await db.scalars(
            select(BookingApplicant)
            .where(
                BookingApplicant.organization_id == organization_id,
                BookingApplicant.booking_id == booking_id,
            )
            .order_by(BookingApplicant.sequence)
        )
    )
    return [
        BookingApplicantView(
            id=item.id,
            customer_id=item.customer_id,
            sequence=item.sequence,
            is_primary=item.is_primary,
            full_name=item.full_name,
            email=item.email,
            phone=item.phone,
            date_of_birth=item.date_of_birth,
            tax_identifier=item.tax_identifier,
            relationship_to_primary=item.relationship_to_primary,
        )
        for item in items
    ]


async def _plan_view(
    db: AsyncSession, organization_id: str, booking_id: str
) -> PaymentPlanView | None:
    plan = (
        await db.scalars(
            select(PaymentPlan)
            .where(
                PaymentPlan.organization_id == organization_id,
                PaymentPlan.booking_id == booking_id,
                PaymentPlan.status == RecordStatus.ACTIVE,
            )
            .order_by(PaymentPlan.created_at.desc())
        )
    ).first()
    if plan is None:
        return None
    installments = list(
        await db.scalars(
            select(Installment)
            .where(
                Installment.organization_id == organization_id,
                Installment.payment_plan_id == plan.id,
            )
            .order_by(Installment.sequence)
        )
    )
    return PaymentPlanView(
        id=plan.id,
        name=plan.name,
        status=plan.status.value,
        currency=plan.currency,
        total_amount=plan.total_amount,
        effective_from=plan.effective_from,
        installments=[
            InstallmentView(
                id=item.id,
                sequence=item.sequence,
                name=item.name,
                due_date=item.due_date,
                amount=item.amount,
                paid_amount=item.paid_amount,
                status=item.status.value,
            )
            for item in installments
        ],
    )


async def _payment_views(
    db: AsyncSession, organization_id: str, booking_id: str
) -> list[BookingPaymentView]:
    payments = list(
        await db.scalars(
            select(Payment)
            .where(Payment.organization_id == organization_id, Payment.booking_id == booking_id)
            .order_by(Payment.created_at.desc())
        )
    )
    return [
        BookingPaymentView(
            id=item.id,
            installment_id=item.installment_id,
            verified_by_user_id=item.verified_by_user_id,
            verifier_name=await _name(db, organization_id, item.verified_by_user_id),
            amount=item.amount,
            currency=item.currency,
            method=item.method,
            status=item.status,
            reference_number=item.reference_number,
            idempotency_key=item.idempotency_key,
            paid_at=item.paid_at,
            verified_at=item.verified_at,
            created_at=item.created_at,
        )
        for item in payments
    ]


async def _approval_views(
    db: AsyncSession, organization_id: str, booking_id: str
) -> list[BookingApprovalView]:
    approvals = list(
        await db.scalars(
            select(BookingApproval)
            .where(
                BookingApproval.organization_id == organization_id,
                BookingApproval.booking_id == booking_id,
            )
            .order_by(BookingApproval.step_number)
        )
    )
    return [
        BookingApprovalView(
            id=item.id,
            step_number=item.step_number,
            requested_by_user_id=item.requested_by_user_id,
            requested_by_name=await _name(db, organization_id, item.requested_by_user_id),
            approver_user_id=item.approver_user_id,
            approver_name=await _name(db, organization_id, item.approver_user_id),
            status=item.status,
            comments=item.comments,
            decided_at=item.decided_at,
            created_at=item.created_at,
        )
        for item in approvals
    ]


async def _financing_view(
    db: AsyncSession, organization_id: str, booking_id: str
) -> FinancingView | None:
    item = (
        await db.scalars(
            select(BookingFinancing).where(
                BookingFinancing.organization_id == organization_id,
                BookingFinancing.booking_id == booking_id,
            )
        )
    ).first()
    if item is None:
        return None
    return FinancingView(
        id=item.id,
        status=item.status,
        lender_name=item.lender_name,
        loan_amount=item.loan_amount,
        application_number=item.application_number,
        sanction_reference=item.sanction_reference,
        notes=item.notes,
    )


async def _booking_view(db: AsyncSession, organization_id: str, booking: Booking) -> BookingView:
    customer = await _entity(db, Customer, organization_id, booking.customer_id)
    unit = await _entity(db, Unit, organization_id, booking.unit_id)
    project = await _entity(db, Project, organization_id, unit.project_id)
    quotation_number = None
    if booking.quotation_id:
        quotation_number = await db.scalar(
            select(Quotation.quotation_number).where(
                Quotation.organization_id == organization_id,
                Quotation.id == booking.quotation_id,
            )
        )
    broker_name = None
    if booking.channel_partner_id:
        broker_name = await db.scalar(
            select(ChannelPartner.name).where(
                ChannelPartner.organization_id == organization_id,
                ChannelPartner.id == booking.channel_partner_id,
            )
        )
    documents = list(
        await db.scalars(
            select(CustomerDocument)
            .where(
                CustomerDocument.organization_id == organization_id,
                CustomerDocument.customer_id == booking.customer_id,
                CustomerDocument.is_current.is_(True),
                or_(
                    CustomerDocument.booking_id == booking.id,
                    CustomerDocument.booking_id.is_(None),
                ),
            )
            .order_by(CustomerDocument.updated_at.desc())
        )
    )
    paid_amount = await _payment_total(db, organization_id, booking.id, (PaymentStatus.COMPLETED,))
    return BookingView(
        id=booking.id,
        booking_number=booking.booking_number,
        status=booking.status,
        customer_id=booking.customer_id,
        customer_name=customer.full_name,
        lead_id=booking.lead_id,
        quotation_id=booking.quotation_id,
        quotation_number=quotation_number,
        unit_hold_id=booking.unit_hold_id,
        unit_id=booking.unit_id,
        unit_number=unit.unit_number,
        project_id=project.id,
        project_name=project.name,
        salesperson_user_id=booking.salesperson_user_id,
        salesperson_name=await _name(db, organization_id, booking.salesperson_user_id),
        channel_partner_id=booking.channel_partner_id,
        broker_name=broker_name,
        booked_by_user_id=booking.booked_by_user_id,
        booked_by_name=await _name(db, organization_id, booking.booked_by_user_id) or "Unknown",
        agreed_price=booking.agreed_price,
        discount_amount=booking.discount_amount,
        booking_amount=booking.booking_amount,
        currency=booking.currency,
        paid_amount=paid_amount,
        applicants=await _applicant_views(db, organization_id, booking.id),
        payment_plan=await _plan_view(db, organization_id, booking.id),
        payments=await _payment_views(db, organization_id, booking.id),
        documents=[
            BookingDocumentSummary(
                id=item.id,
                document_type=item.document_type,
                version=item.version,
                status=item.status.value,
                file_name=item.file_name,
                expiry_date=item.expiry_date,
            )
            for item in documents
        ],
        financing=await _financing_view(db, organization_id, booking.id),
        approvals=await _approval_views(db, organization_id, booking.id),
        submitted_at=booking.submitted_at,
        verification_completed_at=booking.verification_completed_at,
        approval_requested_at=booking.approval_requested_at,
        booked_at=booking.booked_at,
        rejected_at=booking.rejected_at,
        cancelled_at=booking.cancelled_at,
        rejection_reason=booking.rejection_reason,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


async def _add_applicants(
    db: AsyncSession,
    organization_id: str,
    booking: Booking,
    customer: Customer,
    joint_applicants: list[JointApplicantInput],
) -> None:
    db.add(
        BookingApplicant(
            organization_id=organization_id,
            booking_id=booking.id,
            customer_id=customer.id,
            sequence=1,
            is_primary=True,
            primary_booking_key=booking.id,
            full_name=customer.full_name,
            email=customer.email,
            phone=customer.phone,
            date_of_birth=customer.date_of_birth,
            relationship_to_primary=None,
        )
    )
    for sequence, item in enumerate(joint_applicants, start=2):
        if item.customer_id:
            linked = await _entity(db, Customer, organization_id, item.customer_id)
            if linked.id == customer.id:
                raise AppError(
                    status_code=422,
                    code="DUPLICATE_APPLICANT",
                    message="Primary customer cannot also be a joint applicant",
                )
        db.add(
            BookingApplicant(
                organization_id=organization_id,
                booking_id=booking.id,
                customer_id=item.customer_id,
                sequence=sequence,
                is_primary=False,
                primary_booking_key=None,
                full_name=item.full_name.strip(),
                email=str(item.email) if item.email else None,
                phone=item.phone,
                date_of_birth=item.date_of_birth,
                tax_identifier=item.tax_identifier,
                relationship_to_primary=item.relationship_to_primary.strip(),
            )
        )


async def _add_plan(
    db: AsyncSession,
    organization_id: str,
    booking: Booking,
    payload: PaymentPlanInput,
) -> PaymentPlan:
    agreed_price = booking.agreed_price or ZERO
    total = sum((item.amount for item in payload.installments), ZERO)
    if total != agreed_price:
        raise AppError(
            status_code=422,
            code="PAYMENT_PLAN_TOTAL_MISMATCH",
            message="Payment plan installments must equal the final agreed price",
        )
    await db.execute(
        update(PaymentPlan)
        .where(
            PaymentPlan.organization_id == organization_id,
            PaymentPlan.booking_id == booking.id,
            PaymentPlan.status == RecordStatus.ACTIVE,
        )
        .values(status=RecordStatus.ARCHIVED)
    )
    plan = PaymentPlan(
        organization_id=organization_id,
        booking_id=booking.id,
        name=payload.name.strip(),
        status=RecordStatus.ACTIVE,
        currency=booking.currency,
        total_amount=total,
        effective_from=payload.effective_from,
    )
    db.add(plan)
    await db.flush()
    db.add_all(
        [
            Installment(
                organization_id=organization_id,
                payment_plan_id=plan.id,
                sequence=sequence,
                name=item.name.strip(),
                due_date=item.due_date,
                amount=item.amount,
                paid_amount=ZERO,
                status=InstallmentStatus.SCHEDULED,
            )
            for sequence, item in enumerate(payload.installments, start=1)
        ]
    )
    return plan


async def _upsert_financing(
    db: AsyncSession,
    organization_id: str,
    booking: Booking,
    payload: FinancingInput,
) -> BookingFinancing:
    item = (
        await db.scalars(
            select(BookingFinancing)
            .where(
                BookingFinancing.organization_id == organization_id,
                BookingFinancing.booking_id == booking.id,
            )
            .with_for_update()
        )
    ).first()
    if item is None:
        item = BookingFinancing(organization_id=organization_id, booking_id=booking.id)
        db.add(item)
    item.status = payload.status
    item.lender_name = payload.lender_name
    item.loan_amount = payload.loan_amount
    item.application_number = payload.application_number
    item.sanction_reference = payload.sanction_reference
    item.notes = payload.notes
    return item


async def create_booking(
    db: AsyncSession,
    organization_id: str,
    payload: BookingCreate,
    context: MutationContext,
) -> BookingView:
    await expire_due_documents(db, organization_id)
    quote_ref = await _entity(db, Quotation, organization_id, payload.quotation_id)
    if quote_ref.unit_id is None or quote_ref.customer_id is None:
        raise AppError(
            status_code=409,
            code="QUOTATION_INCOMPLETE",
            message="Quotation must identify a customer and selected unit",
        )
    unit = await _entity(db, Unit, organization_id, quote_ref.unit_id, lock=True)
    quote = await _entity(db, Quotation, organization_id, payload.quotation_id, lock=True)
    hold = await _entity(db, UnitHold, organization_id, payload.unit_hold_id, lock=True)
    if quote.customer_id is None:
        raise AppError(
            status_code=409,
            code="QUOTATION_INCOMPLETE",
            message="Quotation must identify a customer",
        )
    if quote.status != QuotationStatus.ACCEPTED:
        raise AppError(
            status_code=409,
            code="QUOTATION_NOT_ACCEPTED",
            message="Only an accepted quotation can be booked",
        )
    if hold.unit_id != unit.id or hold.customer_id != quote.customer_id:
        raise AppError(
            status_code=409,
            code="HOLD_SCOPE_MISMATCH",
            message="The approved hold does not match the quotation customer and unit",
        )
    if hold.status != HoldStatus.ACTIVE or hold.expires_at <= _now():
        raise AppError(
            status_code=409,
            code="VALID_HOLD_REQUIRED",
            message="An approved, unexpired unit hold is required",
        )
    if unit.status not in {UnitStatus.SOFT_HOLD, UnitStatus.HARD_HOLD}:
        raise AppError(status_code=409, code="UNIT_NOT_HELD", message="Unit is not actively held")
    if await db.scalar(
        select(Booking.id).where(
            Booking.organization_id == organization_id,
            Booking.active_unit_key == unit.id,
        )
    ):
        raise AppError(
            status_code=409,
            code="UNIT_ALREADY_BOOKED",
            message="Unit already has an active booking",
        )
    customer = await _entity(db, Customer, organization_id, quote.customer_id)
    if not await _has_verified_kyc(db, organization_id, customer.id):
        raise AppError(
            status_code=409,
            code="KYC_NOT_VERIFIED",
            message="At least one current verified KYC document is required",
        )
    salesperson_id = payload.salesperson_user_id or context.actor_user_id
    salesperson = await _entity(db, User, organization_id, salesperson_id)
    if not salesperson.is_active:
        raise AppError(
            status_code=422, code="SALESPERSON_INACTIVE", message="Salesperson must be active"
        )
    if payload.channel_partner_id:
        broker = await _entity(db, ChannelPartner, organization_id, payload.channel_partner_id)
        if broker.status != PartnerStatus.ACTIVE:
            raise AppError(status_code=422, code="BROKER_INACTIVE", message="Broker must be active")
        if not await db.scalar(
            select(PartnerProject.id).where(
                PartnerProject.organization_id == organization_id,
                PartnerProject.channel_partner_id == broker.id,
                PartnerProject.project_id == quote.project_id,
            )
        ):
            raise AppError(
                status_code=422,
                code="BROKER_PROJECT_NOT_ASSIGNED",
                message="Broker is not authorized for this project",
            )
    if quote.lead_id:
        protected = (
            await db.scalars(
                select(PartnerLead).where(
                    PartnerLead.organization_id == organization_id,
                    PartnerLead.lead_id == quote.lead_id,
                    PartnerLead.status == WorkflowStatus.APPROVED,
                    PartnerLead.protected_until >= date.today(),
                )
            )
        ).first()
        if protected and protected.channel_partner_id != payload.channel_partner_id:
            raise AppError(
                status_code=409,
                code="PARTNER_LEAD_PROTECTED",
                message="This lead is protected for another channel partner",
            )
    agreed_price = quote.final_agreed_value or quote.total
    if quote.booking_amount is None:
        raise AppError(
            status_code=409,
            code="BOOKING_AMOUNT_MISSING",
            message="Accepted quotation does not define a booking amount",
        )
    booking = Booking(
        organization_id=organization_id,
        unit_id=unit.id,
        lead_id=quote.lead_id,
        customer_id=customer.id,
        quotation_id=quote.id,
        unit_hold_id=hold.id,
        booked_by_user_id=context.actor_user_id,
        salesperson_user_id=salesperson_id,
        channel_partner_id=payload.channel_partner_id,
        booking_number=payload.booking_number,
        status=BookingStatus.PAYMENT_PENDING,
        booking_amount=quote.booking_amount,
        agreed_price=agreed_price,
        discount_amount=quote.discount_amount,
        currency=quote.currency,
        active_unit_key=unit.id,
    )
    db.add(booking)
    await db.flush()
    await _add_applicants(db, organization_id, booking, customer, payload.joint_applicants)
    await _add_plan(db, organization_id, booking, payload.payment_plan)
    if payload.financing:
        await _upsert_financing(db, organization_id, booking, payload.financing)
    else:
        await _upsert_financing(db, organization_id, booking, FinancingInput())
    hold.status = HoldStatus.CONVERTED
    hold.active_unit_key = None
    hold.released_at = _now()
    unit.status = UnitStatus.BOOKING_INITIATED
    db.add(
        CustomerLedger(
            organization_id=organization_id,
            customer_id=customer.id,
            booking_id=booking.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=agreed_price,
            currency=booking.currency,
            description=f"Agreed value for booking {booking.booking_number}",
            idempotency_key=f"booking:{booking.id}:agreed-value",
            posted_at=_now(),
        )
    )
    db.add(
        _audit(
            organization_id,
            context,
            "booking.created",
            "booking",
            booking.id,
            None,
            {
                "quotation_id": quote.id,
                "unit_hold_id": hold.id,
                "unit_id": unit.id,
                "customer_id": customer.id,
                "agreed_price": str(agreed_price),
                "discount_amount": str(booking.discount_amount),
                "booking_amount": str(booking.booking_amount),
                "status": booking.status.value,
            },
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids={booking.booked_by_user_id, booking.salesperson_user_id or ""},
        event_type=NotificationEventType.BOOKING_CREATED,
        title="Booking created",
        body=f"{booking.booking_number} · {booking.currency} {booking.booking_amount}",
        related_entity_type="booking",
        related_entity_id=booking.id,
        action_url=f"/bookings/{booking.id}",
        data={"booking_number": booking.booking_number, "status": booking.status.value},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="BOOKING_CONFLICT",
            message="Booking number or selected unit is already reserved",
        ) from exc
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def list_bookings(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: BookingStatus | None,
    customer_id: str | None,
    salesperson_user_id: str | None,
    page: int,
    page_size: int,
) -> Page[BookingView]:
    conditions: list[Any] = [Booking.organization_id == organization_id]
    if status:
        conditions.append(Booking.status == status)
    if customer_id:
        conditions.append(Booking.customer_id == customer_id)
    if salesperson_user_id:
        conditions.append(Booking.salesperson_user_id == salesperson_user_id)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                Booking.booking_number.ilike(pattern),
                Booking.customer_id.in_(
                    select(Customer.id).where(
                        Customer.organization_id == organization_id,
                        Customer.full_name.ilike(pattern),
                    )
                ),
                Booking.unit_id.in_(
                    select(Unit.id).where(
                        Unit.organization_id == organization_id, Unit.unit_number.ilike(pattern)
                    )
                ),
            )
        )
    total = int(await db.scalar(select(func.count(Booking.id)).where(*conditions)) or 0)
    items = list(
        await db.scalars(
            select(Booking)
            .where(*conditions)
            .order_by(Booking.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _booking_view(db, organization_id, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def get_booking(db: AsyncSession, organization_id: str, booking_id: str) -> BookingView:
    await expire_due_documents(db, organization_id)
    return await _booking_view(
        db, organization_id, await _entity(db, Booking, organization_id, booking_id)
    )


async def advance_booking(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payload: BookingAdvance,
    context: MutationContext,
) -> BookingView:
    await expire_due_documents(db, organization_id)
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    payment_plan_id = await db.scalar(
        select(PaymentPlan.id).where(
            PaymentPlan.organization_id == organization_id,
            PaymentPlan.booking_id == booking.id,
        )
    )
    if (
        booking.quotation_id is None
        or booking.unit_hold_id is None
        or booking.agreed_price is None
        or payment_plan_id is None
    ):
        raise AppError(
            status_code=409,
            code="BOOKING_FLOW_REQUIRED",
            message=(
                "Legacy booking drafts cannot enter the controlled workflow; create the "
                "booking from an accepted quotation and approved hold"
            ),
        )
    target = BookingStatus(payload.status)
    allowed = {
        BookingStatus.DRAFT: {BookingStatus.DOCUMENTATION_PENDING},
        BookingStatus.DOCUMENTATION_PENDING: {BookingStatus.PAYMENT_PENDING},
        BookingStatus.PAYMENT_PENDING: {BookingStatus.VERIFICATION},
    }
    if target not in allowed.get(booking.status, set()):
        raise AppError(
            status_code=409,
            code="INVALID_BOOKING_TRANSITION",
            message=f"Cannot move booking from {booking.status.value} to {target.value}",
        )
    if target == BookingStatus.PAYMENT_PENDING and not await _has_verified_kyc(
        db, organization_id, booking.customer_id
    ):
        raise AppError(status_code=409, code="KYC_NOT_VERIFIED", message="Verified KYC is required")
    if target == BookingStatus.VERIFICATION:
        submitted = await _payment_total(
            db,
            organization_id,
            booking.id,
            (PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.COMPLETED),
        )
        if submitted < booking.booking_amount:
            raise AppError(
                status_code=409,
                code="BOOKING_AMOUNT_NOT_PAID",
                message="Submitted payments do not cover the booking amount",
            )
        booking.submitted_at = _now()
    before = booking.status.value
    booking.status = target
    db.add(
        _audit(
            organization_id,
            context,
            "booking.status.changed",
            "booking",
            booking.id,
            {"status": before},
            {"status": target.value},
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids={booking.booked_by_user_id, booking.salesperson_user_id or ""},
        event_type=NotificationEventType.BOOKING_STATUS_CHANGED,
        title="Booking status updated",
        body=f"{booking.booking_number}: {before} → {target.value}",
        related_entity_type="booking",
        related_entity_id=booking.id,
        action_url=f"/bookings/{booking.id}",
        data={"previous_status": before, "status": target.value},
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def replace_joint_applicants(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    items: list[JointApplicantInput],
    context: MutationContext,
) -> BookingView:
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    if booking.status in FINAL_STATUSES or booking.status == BookingStatus.APPROVAL:
        raise AppError(
            status_code=409,
            code="BOOKING_APPLICANTS_LOCKED",
            message="Applicants cannot change after approval begins",
        )
    existing = list(
        await db.scalars(
            select(BookingApplicant).where(
                BookingApplicant.organization_id == organization_id,
                BookingApplicant.booking_id == booking.id,
                BookingApplicant.is_primary.is_(False),
            )
        )
    )
    for existing_item in existing:
        await db.delete(existing_item)
    customer = await _entity(db, Customer, organization_id, booking.customer_id)
    for sequence, applicant in enumerate(items, start=2):
        if applicant.customer_id:
            await _entity(db, Customer, organization_id, applicant.customer_id)
        db.add(
            BookingApplicant(
                organization_id=organization_id,
                booking_id=booking.id,
                customer_id=applicant.customer_id,
                sequence=sequence,
                is_primary=False,
                full_name=applicant.full_name.strip(),
                email=str(applicant.email) if applicant.email else None,
                phone=applicant.phone,
                date_of_birth=applicant.date_of_birth,
                tax_identifier=applicant.tax_identifier,
                relationship_to_primary=applicant.relationship_to_primary,
            )
        )
    db.add(
        _audit(
            organization_id,
            context,
            "booking.applicants.updated",
            "booking",
            booking.id,
            {"joint_applicant_count": len(existing)},
            {"joint_applicant_count": len(items), "primary_customer_id": customer.id},
        )
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def set_payment_plan(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payload: PaymentPlanInput,
    context: MutationContext,
) -> BookingView:
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    if booking.status in FINAL_STATUSES or booking.status == BookingStatus.APPROVAL:
        raise AppError(
            status_code=409, code="PAYMENT_PLAN_LOCKED", message="Payment plan is locked"
        )
    plan = await _add_plan(db, organization_id, booking, payload)
    db.add(
        _audit(
            organization_id,
            context,
            "booking.payment_plan.updated",
            "booking",
            booking.id,
            None,
            {"payment_plan_id": plan.id, "total_amount": str(plan.total_amount)},
        )
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def set_financing(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payload: FinancingInput,
    context: MutationContext,
) -> BookingView:
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    if booking.status in FINAL_STATUSES:
        raise AppError(status_code=409, code="FINANCING_LOCKED", message="Financing is locked")
    previous = await _financing_view(db, organization_id, booking.id)
    item = await _upsert_financing(db, organization_id, booking, payload)
    db.add(
        _audit(
            organization_id,
            context,
            "booking.financing.updated",
            "booking",
            booking.id,
            {"status": previous.status.value} if previous else None,
            {"status": item.status.value, "loan_amount": str(item.loan_amount or ZERO)},
        )
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def create_payment(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payload: BookingPaymentCreate,
    context: MutationContext,
) -> BookingView:
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    if booking.status not in {BookingStatus.PAYMENT_PENDING, BookingStatus.VERIFICATION}:
        raise AppError(
            status_code=409,
            code="PAYMENT_NOT_ALLOWED",
            message="Payments are not accepted in the current booking state",
        )
    existing = (
        await db.scalars(
            select(Payment).where(
                Payment.organization_id == organization_id,
                Payment.idempotency_key == payload.idempotency_key,
            )
        )
    ).first()
    if existing:
        if existing.booking_id != booking.id or existing.amount != payload.amount:
            raise AppError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="Idempotency key was already used for another payment",
            )
        return await _booking_view(db, organization_id, booking)
    if payload.installment_id:
        installment = await _entity(db, Installment, organization_id, payload.installment_id)
        plan = await _entity(db, PaymentPlan, organization_id, installment.payment_plan_id)
        if plan.booking_id != booking.id:
            raise AppError(
                status_code=422,
                code="INSTALLMENT_BOOKING_MISMATCH",
                message="Installment does not belong to this booking",
            )
    committed = await _payment_total(
        db,
        organization_id,
        booking.id,
        (PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.COMPLETED),
    )
    if booking.agreed_price is not None and committed + payload.amount > booking.agreed_price:
        raise AppError(
            status_code=422,
            code="PAYMENT_EXCEEDS_AGREED_VALUE",
            message="Payment would exceed the final agreed value",
        )
    payment = Payment(
        organization_id=organization_id,
        booking_id=booking.id,
        customer_id=booking.customer_id,
        installment_id=payload.installment_id,
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
    if committed + payment.amount >= booking.booking_amount:
        booking.status = BookingStatus.VERIFICATION
        booking.submitted_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "booking.payment.submitted",
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
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="PAYMENT_CONFLICT",
            message="Payment reference was submitted concurrently",
        ) from exc
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def decide_payment(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payment_id: str,
    payload: BookingPaymentDecision,
    context: MutationContext,
) -> BookingView:
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    payment = await _entity(db, Payment, organization_id, payment_id, lock=True)
    if payment.booking_id != booking.id:
        raise _not_found()
    if payment.status not in {PaymentStatus.PENDING, PaymentStatus.PROCESSING}:
        raise AppError(
            status_code=409, code="PAYMENT_FINALIZED", message="Payment is already finalized"
        )
    if payload.status == "COMPLETED":
        raise AppError(
            status_code=409,
            code="FINANCE_WORKFLOW_REQUIRED",
            message="Reconcile and allocate the payment through the collections workflow",
        )
    before = payment.status.value
    payment.status = PaymentStatus(payload.status)
    payment.verified_by_user_id = context.actor_user_id
    payment.verified_at = _now()
    if payment.status == PaymentStatus.COMPLETED:
        if payment.installment_id:
            installment = await _entity(
                db, Installment, organization_id, payment.installment_id, lock=True
            )
            installment.paid_amount = min(
                installment.amount, installment.paid_amount + payment.amount
            )
            installment.status = (
                InstallmentStatus.PAID
                if installment.paid_amount >= installment.amount
                else InstallmentStatus.PARTIALLY_PAID
            )
        db.add(
            CustomerLedger(
                organization_id=organization_id,
                customer_id=booking.customer_id,
                booking_id=booking.id,
                payment_id=payment.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=payment.amount,
                currency=payment.currency,
                description=f"Verified payment for booking {booking.booking_number}",
                idempotency_key=f"payment:{payment.id}:verified",
                posted_at=_now(),
            )
        )
    db.add(
        _audit(
            organization_id,
            context,
            "booking.payment.verified"
            if payment.status == PaymentStatus.COMPLETED
            else "booking.payment.failed",
            "payment",
            payment.id,
            {"status": before},
            {"status": payment.status.value, "booking_id": booking.id, "notes": payload.notes},
        )
    )
    if payment.status == PaymentStatus.COMPLETED:
        notification_service.queue_in_app(
            db,
            organization_id=organization_id,
            recipient_user_ids={booking.booked_by_user_id, booking.salesperson_user_id or ""},
            event_type=NotificationEventType.PAYMENT_RECEIVED,
            title="Payment received",
            body=f"{payment.currency} {payment.amount} received for {booking.booking_number}",
            related_entity_type="payment",
            related_entity_id=payment.id,
            action_url=f"/bookings/{booking.id}",
            data={"booking_id": booking.id, "amount": str(payment.amount)},
        )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def _eligible_approver(db: AsyncSession, organization_id: str, user_id: str) -> User | None:
    return (
        await db.scalars(
            select(User)
            .join(
                UserRole,
                (UserRole.organization_id == User.organization_id) & (UserRole.user_id == User.id),
            )
            .join(
                RolePermission,
                (RolePermission.organization_id == UserRole.organization_id)
                & (RolePermission.role_id == UserRole.role_id),
            )
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                User.organization_id == organization_id,
                User.id == user_id,
                User.is_active.is_(True),
                Permission.code.in_(("bookings.approve", "bookings.manage")),
            )
        )
    ).first()


async def request_approval(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payload: BookingApprovalRequest,
    context: MutationContext,
) -> BookingView:
    await expire_due_documents(db, organization_id)
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    if booking.status != BookingStatus.VERIFICATION:
        raise AppError(
            status_code=409,
            code="BOOKING_NOT_IN_VERIFICATION",
            message="Booking must be in verification before approval",
        )
    if not await _has_verified_kyc(db, organization_id, booking.customer_id):
        raise AppError(status_code=409, code="KYC_NOT_VERIFIED", message="Verified KYC is required")
    verified_amount = await _payment_total(
        db, organization_id, booking.id, (PaymentStatus.COMPLETED,)
    )
    if verified_amount < booking.booking_amount:
        raise AppError(
            status_code=409,
            code="BOOKING_AMOUNT_NOT_VERIFIED",
            message="Verified payments must cover the booking amount",
        )
    financing = await _financing_view(db, organization_id, booking.id)
    if financing and financing.status not in {
        FinancingStatus.NOT_REQUIRED,
        FinancingStatus.SANCTIONED,
        FinancingStatus.DISBURSED,
    }:
        raise AppError(
            status_code=409,
            code="FINANCING_NOT_READY",
            message="Financing must be sanctioned before booking approval",
        )
    if context.actor_user_id in payload.approver_user_ids:
        raise AppError(
            status_code=403,
            code="SELF_APPROVAL_NOT_ALLOWED",
            message="Booking requester cannot approve the same booking",
        )
    for approver_id in payload.approver_user_ids:
        if await _eligible_approver(db, organization_id, approver_id) is None:
            raise AppError(
                status_code=422,
                code="INVALID_BOOKING_APPROVER",
                message="Every approver must be active and hold booking approval permission",
            )
    existing_count = int(
        await db.scalar(
            select(func.count(BookingApproval.id)).where(
                BookingApproval.organization_id == organization_id,
                BookingApproval.booking_id == booking.id,
            )
        )
        or 0
    )
    if existing_count:
        raise AppError(
            status_code=409,
            code="APPROVAL_ALREADY_REQUESTED",
            message="Booking approval has already been requested",
        )
    db.add_all(
        [
            BookingApproval(
                organization_id=organization_id,
                booking_id=booking.id,
                requested_by_user_id=context.actor_user_id,
                approver_user_id=approver_id,
                step_number=step,
                status=ApprovalStatus.PENDING,
                comments=payload.comments,
            )
            for step, approver_id in enumerate(payload.approver_user_ids, start=1)
        ]
    )
    booking.status = BookingStatus.APPROVAL
    booking.verified_by_user_id = context.actor_user_id
    booking.verification_completed_at = _now()
    booking.approval_requested_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "booking.approval.requested",
            "booking",
            booking.id,
            {"status": BookingStatus.VERIFICATION.value},
            {
                "status": BookingStatus.APPROVAL.value,
                "approver_user_ids": payload.approver_user_ids,
            },
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids=payload.approver_user_ids,
        event_type=NotificationEventType.BOOKING_STATUS_CHANGED,
        title="Booking approval requested",
        body=booking.booking_number,
        related_entity_type="booking",
        related_entity_id=booking.id,
        action_url=f"/bookings/{booking.id}",
        data={"status": booking.status.value, "requested_by_user_id": context.actor_user_id},
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def decide_approval(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    approval_id: str,
    payload: BookingApprovalDecision,
    context: MutationContext,
) -> BookingView:
    booking_ref = await _entity(db, Booking, organization_id, booking_id)
    unit = await _entity(db, Unit, organization_id, booking_ref.unit_id, lock=True)
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    approval = await _entity(db, BookingApproval, organization_id, approval_id, lock=True)
    if approval.booking_id != booking.id:
        raise _not_found()
    if booking.status != BookingStatus.APPROVAL or approval.status != ApprovalStatus.PENDING:
        raise AppError(
            status_code=409, code="APPROVAL_FINALIZED", message="Approval is already finalized"
        )
    if approval.approver_user_id != context.actor_user_id:
        raise AppError(
            status_code=403,
            code="APPROVER_MISMATCH",
            message="Only the assigned approver can decide this step",
        )
    approval.status = ApprovalStatus(payload.status)
    approval.comments = payload.comments.strip()
    approval.decided_at = _now()
    if approval.status == ApprovalStatus.REJECTED:
        booking.status = BookingStatus.REJECTED
        booking.rejected_at = _now()
        booking.rejection_reason = approval.comments
        booking.active_unit_key = None
        unit.status = UnitStatus.CANCELLED_RELEASED
        await db.execute(
            update(BookingApproval)
            .where(
                BookingApproval.organization_id == organization_id,
                BookingApproval.booking_id == booking.id,
                BookingApproval.id != approval.id,
                BookingApproval.status == ApprovalStatus.PENDING,
            )
            .values(status=ApprovalStatus.CANCELLED, decided_at=_now())
        )
    else:
        await db.flush()
        pending = int(
            await db.scalar(
                select(func.count(BookingApproval.id)).where(
                    BookingApproval.organization_id == organization_id,
                    BookingApproval.booking_id == booking.id,
                    BookingApproval.status == ApprovalStatus.PENDING,
                )
            )
            or 0
        )
        if pending == 0:
            if booking.active_unit_key != unit.id or unit.status != UnitStatus.BOOKING_INITIATED:
                raise AppError(
                    status_code=409,
                    code="UNIT_BOOKING_LOCK_LOST",
                    message="Unit booking lock is no longer valid",
                )
            booking.status = BookingStatus.CONFIRMED
            booking.confirmed_by_user_id = context.actor_user_id
            booking.booked_at = _now()
            unit.status = UnitStatus.BOOKED
            from app.services.partners import accrue_booking_commission

            await accrue_booking_commission(db, organization_id, booking, context)
    db.add(
        _audit(
            organization_id,
            context,
            "booking.approval.decided",
            "booking_approval",
            approval.id,
            {"status": ApprovalStatus.PENDING.value},
            {"status": approval.status.value, "booking_status": booking.status.value},
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=organization_id,
        recipient_user_ids={booking.booked_by_user_id, booking.salesperson_user_id or ""},
        event_type=NotificationEventType.BOOKING_STATUS_CHANGED,
        title="Booking approval updated",
        body=f"{booking.booking_number}: {booking.status.value}",
        related_entity_type="booking",
        related_entity_id=booking.id,
        action_url=f"/bookings/{booking.id}",
        data={"approval_status": approval.status.value, "booking_status": booking.status.value},
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def cancel_booking(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    payload: BookingCancel,
    context: MutationContext,
) -> BookingView:
    booking, unit = await _booking_and_unit(db, organization_id, booking_id)
    if booking.status in FINAL_STATUSES:
        raise AppError(
            status_code=409, code="BOOKING_FINALIZED", message="Booking is already finalized"
        )
    before = booking.status.value
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = _now()
    booking.rejection_reason = payload.reason.strip()
    booking.active_unit_key = None
    unit.status = UnitStatus.CANCELLED_RELEASED
    await db.execute(
        update(BookingApproval)
        .where(
            BookingApproval.organization_id == organization_id,
            BookingApproval.booking_id == booking.id,
            BookingApproval.status == ApprovalStatus.PENDING,
        )
        .values(status=ApprovalStatus.CANCELLED, decided_at=_now())
    )
    db.add(
        _audit(
            organization_id,
            context,
            "booking.cancelled",
            "booking",
            booking.id,
            {"status": before},
            {"status": BookingStatus.CANCELLED.value, "reason": booking.rejection_reason},
        )
    )
    await db.commit()
    await db.refresh(booking)
    return await _booking_view(db, organization_id, booking)


async def booking_stats(db: AsyncSession, organization_id: str) -> BookingStats:
    rows = (
        await db.execute(
            select(Booking.status, func.count(Booking.id))
            .where(Booking.organization_id == organization_id)
            .group_by(Booking.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    return BookingStats(
        total=sum(counts.values()),
        documentation_pending=counts.get(BookingStatus.DOCUMENTATION_PENDING, 0),
        payment_pending=counts.get(BookingStatus.PAYMENT_PENDING, 0),
        verification=counts.get(BookingStatus.VERIFICATION, 0),
        approval=counts.get(BookingStatus.APPROVAL, 0),
        confirmed=counts.get(BookingStatus.CONFIRMED, 0),
        rejected=counts.get(BookingStatus.REJECTED, 0),
        cancelled=counts.get(BookingStatus.CANCELLED, 0),
    )


async def booking_options(
    db: AsyncSession, organization_id: str, actor_user_id: str
) -> BookingOptions:
    await expire_due_documents(db, organization_id)
    quotations = list(
        await db.scalars(
            select(Quotation)
            .where(
                Quotation.organization_id == organization_id,
                Quotation.status == QuotationStatus.ACCEPTED,
                Quotation.customer_id.is_not(None),
                Quotation.unit_id.is_not(None),
            )
            .order_by(Quotation.updated_at.desc())
            .limit(500)
        )
    )
    eligible: list[EligibleQuotationOption] = []
    for quote in quotations:
        if quote.customer_id is None or quote.unit_id is None or quote.booking_amount is None:
            continue
        if not await _has_verified_kyc(db, organization_id, quote.customer_id):
            continue
        hold = (
            await db.scalars(
                select(UnitHold).where(
                    UnitHold.organization_id == organization_id,
                    UnitHold.unit_id == quote.unit_id,
                    UnitHold.customer_id == quote.customer_id,
                    UnitHold.status == HoldStatus.ACTIVE,
                    UnitHold.expires_at > _now(),
                )
            )
        ).first()
        if hold is None:
            continue
        if await db.scalar(
            select(Booking.id).where(
                Booking.organization_id == organization_id,
                Booking.active_unit_key == quote.unit_id,
            )
        ):
            continue
        customer = await _entity(db, Customer, organization_id, quote.customer_id)
        unit = await _entity(db, Unit, organization_id, quote.unit_id)
        eligible.append(
            EligibleQuotationOption(
                id=quote.id,
                quotation_number=quote.quotation_number,
                version=quote.version,
                customer_id=customer.id,
                customer_name=customer.full_name,
                unit_id=unit.id,
                unit_number=unit.unit_number,
                agreed_price=quote.final_agreed_value or quote.total,
                discount_amount=quote.discount_amount,
                booking_amount=quote.booking_amount,
                currency=quote.currency,
                hold_id=hold.id,
            )
        )
    salespeople = list(
        await db.scalars(
            select(User)
            .where(User.organization_id == organization_id, User.is_active.is_(True))
            .order_by(User.full_name)
            .limit(500)
        )
    )
    brokers = list(
        await db.scalars(
            select(ChannelPartner)
            .where(
                ChannelPartner.organization_id == organization_id,
                ChannelPartner.status == PartnerStatus.ACTIVE,
            )
            .order_by(ChannelPartner.name)
            .limit(500)
        )
    )
    approvers = list(
        await db.scalars(
            select(User)
            .join(
                UserRole,
                (UserRole.organization_id == User.organization_id) & (UserRole.user_id == User.id),
            )
            .join(
                RolePermission,
                (RolePermission.organization_id == UserRole.organization_id)
                & (RolePermission.role_id == UserRole.role_id),
            )
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                User.id != actor_user_id,
                Permission.code.in_(("bookings.approve", "bookings.manage")),
            )
            .distinct()
            .order_by(User.full_name)
        )
    )
    return BookingOptions(
        quotations=eligible,
        salespeople=[BookingOption(id=item.id, label=item.full_name) for item in salespeople],
        brokers=[BookingOption(id=item.id, label=item.name) for item in brokers],
        approvers=[BookingOption(id=item.id, label=item.full_name) for item in approvers],
    )
