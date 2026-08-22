import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.documents.workflow_pdf import WorkflowPdfDocument, WorkflowPdfRenderer
from app.models.entities import (
    Agreement,
    AuditLog,
    Booking,
    ConstructionUpdate,
    Customer,
    CustomerDocument,
    CustomerLedger,
    DemandLetter,
    Handover,
    HandoverDocument,
    Installment,
    NoDuesCertificate,
    Organization,
    Payment,
    PaymentPlan,
    Possession,
    PossessionOverrideRequest,
    PostBookingCase,
    Project,
    SnagItem,
    Tower,
    Unit,
    User,
)
from app.models.enums import (
    AgreementStatus,
    BookingStatus,
    DocumentStatus,
    InstallmentStatus,
    LedgerEntryType,
    NotificationEventType,
    PaymentStatus,
    PossessionStatus,
    PostBookingStage,
    ProgressStatus,
    RecordStatus,
    SnagStatus,
    WorkflowStatus,
)
from app.schemas.organization import Page
from app.schemas.property_lifecycle import (
    AcknowledgementCreate,
    AgreementCreate,
    AgreementTransition,
    AgreementView,
    BookingOption,
    CaseDetail,
    CaseSummary,
    ConstructionCreate,
    ConstructionView,
    DemandView,
    FinalDemandCreate,
    HandoverDocumentCreate,
    HandoverDocumentView,
    HandoverView,
    LifecycleStats,
    NoDuesView,
    OverrideCreate,
    OverrideDecision,
    OverrideView,
    PossessionAction,
    PossessionView,
    ReadinessCondition,
    ReadinessView,
    SnagCreate,
    SnagDecision,
    SnagView,
)
from app.services import notifications as notification_service
from app.services.documents import _prepare_file
from app.services.organization import MutationContext
from app.storage import StoredFile, get_storage

ZERO = Decimal("0.00")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
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
        raise _error("RESOURCE_NOT_FOUND", "Post-booking record not found", 404)
    return item


async def _case(db: AsyncSession, org: str, case_id: str, *, lock: bool = False) -> PostBookingCase:
    return await _entity(db, PostBookingCase, org, case_id, lock=lock)


async def _name(db: AsyncSession, org: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = await db.scalar(
        select(User.full_name).where(User.organization_id == org, User.id == user_id)
    )
    return str(value) if value is not None else None


async def _context_rows(
    db: AsyncSession, org: str, case: PostBookingCase
) -> tuple[Booking, Customer, Unit, Project]:
    booking = await _entity(db, Booking, org, case.booking_id)
    customer = await _entity(db, Customer, org, booking.customer_id)
    unit = await _entity(db, Unit, org, booking.unit_id)
    project = await _entity(db, Project, org, unit.project_id)
    return booking, customer, unit, project


async def readiness(db: AsyncSession, org: str, case: PostBookingCase) -> ReadinessView:
    booking, _, unit, _ = await _context_rows(db, org, case)
    agreement = (
        await db.scalars(
            select(Agreement).where(
                Agreement.organization_id == org, Agreement.booking_id == booking.id
            )
        )
    ).first()
    verified_kyc = bool(
        await db.scalar(
            select(CustomerDocument.id).where(
                CustomerDocument.organization_id == org,
                CustomerDocument.customer_id == booking.customer_id,
                CustomerDocument.is_current.is_(True),
                CustomerDocument.status == DocumentStatus.VERIFIED,
                or_(
                    CustomerDocument.booking_id == booking.id, CustomerDocument.booking_id.is_(None)
                ),
            )
        )
    )
    latest_progress = await db.scalar(
        select(ConstructionUpdate.progress_percent)
        .where(
            ConstructionUpdate.organization_id == org,
            ConstructionUpdate.project_id == unit.project_id,
            ConstructionUpdate.status == ProgressStatus.PUBLISHED,
            or_(
                ConstructionUpdate.tower_id == unit.tower_id, ConstructionUpdate.tower_id.is_(None)
            ),
        )
        .order_by(ConstructionUpdate.update_date.desc(), ConstructionUpdate.created_at.desc())
    )
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
    outstanding = max(Decimal(debits) - Decimal(credits), ZERO)
    plan_ids = list(
        await db.scalars(
            select(PaymentPlan.id).where(
                PaymentPlan.organization_id == org, PaymentPlan.booking_id == booking.id
            )
        )
    )
    open_installments = int(
        await db.scalar(
            select(func.count(Installment.id)).where(
                Installment.organization_id == org,
                Installment.payment_plan_id.in_(plan_ids or [""]),
                Installment.status.not_in((InstallmentStatus.PAID, InstallmentStatus.WAIVED)),
            )
        )
        or 0
    )
    pending_payments = int(
        await db.scalar(
            select(func.count(Payment.id)).where(
                Payment.organization_id == org,
                Payment.booking_id == booking.id,
                Payment.status.in_((PaymentStatus.PENDING, PaymentStatus.PROCESSING)),
            )
        )
        or 0
    )
    open_snags = int(
        await db.scalar(
            select(func.count(SnagItem.id)).where(
                SnagItem.organization_id == org,
                SnagItem.post_booking_case_id == case.id,
                SnagItem.status.in_((SnagStatus.OPEN, SnagStatus.IN_PROGRESS, SnagStatus.RESOLVED)),
            )
        )
        or 0
    )
    no_dues = bool(
        await db.scalar(
            select(NoDuesCertificate.id).where(
                NoDuesCertificate.organization_id == org,
                NoDuesCertificate.post_booking_case_id == case.id,
                NoDuesCertificate.status == RecordStatus.ACTIVE,
            )
        )
    )
    final_demand = case.final_demand_letter_id is not None
    conditions = [
        ReadinessCondition(
            code="BOOKING_CONFIRMED",
            label="Booking confirmed",
            complete=booking.status == BookingStatus.CONFIRMED,
        ),
        ReadinessCondition(
            code="AGREEMENT_REGISTERED",
            label="Agreement registered",
            complete=bool(
                agreement
                and agreement.status == AgreementStatus.REGISTERED
                and agreement.storage_key
            ),
            detail=agreement.status.value if agreement else "Missing",
        ),
        ReadinessCondition(
            code="KYC_VERIFIED", label="Current KYC verified", complete=verified_kyc
        ),
        ReadinessCondition(
            code="CONSTRUCTION_COMPLETE",
            label="Construction at 100%",
            complete=latest_progress is not None and latest_progress >= Decimal("100"),
            detail=f"{latest_progress or ZERO}%",
        ),
        ReadinessCondition(
            code="FINAL_DEMAND_ISSUED", label="Final demand issued", complete=final_demand
        ),
        ReadinessCondition(
            code="NO_OUTSTANDING",
            label="Final payment cleared",
            complete=outstanding <= ZERO,
            detail=f"{booking.currency} {outstanding}",
        ),
        ReadinessCondition(
            code="INSTALLMENTS_CLOSED",
            label="All installments closed",
            complete=open_installments == 0,
            detail=f"{open_installments} open",
        ),
        ReadinessCondition(
            code="PAYMENTS_RECONCILED",
            label="No pending payments",
            complete=pending_payments == 0,
            detail=f"{pending_payments} pending",
        ),
        ReadinessCondition(
            code="NO_DUES_ISSUED", label="No-dues certificate issued", complete=no_dues
        ),
        ReadinessCondition(
            code="SNAGGING_CLOSED",
            label="Snagging closed",
            complete=open_snags == 0,
            detail=f"{open_snags} open",
        ),
    ]
    approved = (
        await db.scalars(
            select(PossessionOverrideRequest)
            .where(
                PossessionOverrideRequest.organization_id == org,
                PossessionOverrideRequest.post_booking_case_id == case.id,
                PossessionOverrideRequest.status == WorkflowStatus.APPROVED,
            )
            .order_by(PossessionOverrideRequest.decided_at.desc())
        )
    ).first()
    return ReadinessView(
        ready=all(item.complete for item in conditions if item.blocking),
        financially_ready=outstanding <= ZERO and open_installments == 0 and pending_payments == 0,
        documents_ready=bool(
            agreement and agreement.status == AgreementStatus.REGISTERED and agreement.storage_key
        )
        and verified_kyc,
        outstanding_amount=outstanding,
        currency=booking.currency,
        conditions=conditions,
        active_override_id=approved.id if approved else None,
    )


async def _sync_stage(db: AsyncSession, org: str, case: PostBookingCase) -> None:
    agreement = await db.scalar(
        select(Agreement.status).where(
            Agreement.organization_id == org, Agreement.booking_id == case.booking_id
        )
    )
    no_dues = await db.scalar(
        select(NoDuesCertificate.id).where(
            NoDuesCertificate.organization_id == org,
            NoDuesCertificate.post_booking_case_id == case.id,
        )
    )
    possession = (
        await db.scalars(
            select(Possession).where(
                Possession.organization_id == org, Possession.post_booking_case_id == case.id
            )
        )
    ).first()
    handover = None
    if possession:
        handover = (
            await db.scalars(
                select(Handover).where(
                    Handover.organization_id == org, Handover.possession_id == possession.id
                )
            )
        ).first()
    state = await readiness(db, org, case)
    if handover and handover.status == WorkflowStatus.COMPLETED:
        case.status = PostBookingStage.COMPLETED
    elif possession and possession.status == PossessionStatus.COMPLETED:
        case.status = PostBookingStage.HANDOVER
    elif possession:
        case.status = PostBookingStage.POSSESSION
    elif no_dues:
        case.status = (
            PostBookingStage.SNAGGING if not state.ready else PostBookingStage.POSSESSION_READINESS
        )
    elif case.final_demand_letter_id and not state.financially_ready:
        case.status = PostBookingStage.FINAL_PAYMENT
    elif case.final_demand_letter_id:
        case.status = PostBookingStage.NO_DUES
    elif any(item.code == "CONSTRUCTION_COMPLETE" and item.complete for item in state.conditions):
        case.status = PostBookingStage.FINAL_DEMAND
    elif agreement == AgreementStatus.REGISTERED:
        case.status = PostBookingStage.CONSTRUCTION
    else:
        case.status = PostBookingStage.AGREEMENT_PENDING
    case.readiness_snapshot = state.model_dump(mode="json")


async def _views(db: AsyncSession, org: str, case: PostBookingCase) -> CaseDetail:
    await _sync_stage(db, org, case)
    booking, customer, unit, project = await _context_rows(db, org, case)
    state = await readiness(db, org, case)
    agreement = (
        await db.scalars(
            select(Agreement).where(
                Agreement.organization_id == org, Agreement.booking_id == booking.id
            )
        )
    ).first()
    updates = list(
        await db.scalars(
            select(ConstructionUpdate)
            .where(
                ConstructionUpdate.organization_id == org,
                ConstructionUpdate.project_id == project.id,
                or_(
                    ConstructionUpdate.tower_id == unit.tower_id,
                    ConstructionUpdate.tower_id.is_(None),
                ),
            )
            .order_by(ConstructionUpdate.update_date.desc())
        )
    )
    demand = (
        await _entity(db, DemandLetter, org, case.final_demand_letter_id)
        if case.final_demand_letter_id
        else None
    )
    certificate = (
        await db.scalars(
            select(NoDuesCertificate).where(
                NoDuesCertificate.organization_id == org,
                NoDuesCertificate.post_booking_case_id == case.id,
            )
        )
    ).first()
    snags = list(
        await db.scalars(
            select(SnagItem)
            .where(SnagItem.organization_id == org, SnagItem.post_booking_case_id == case.id)
            .order_by(SnagItem.reported_at.desc())
        )
    )
    overrides = list(
        await db.scalars(
            select(PossessionOverrideRequest)
            .where(
                PossessionOverrideRequest.organization_id == org,
                PossessionOverrideRequest.post_booking_case_id == case.id,
            )
            .order_by(PossessionOverrideRequest.requested_at.desc())
        )
    )
    possession = (
        await db.scalars(
            select(Possession).where(
                Possession.organization_id == org, Possession.post_booking_case_id == case.id
            )
        )
    ).first()
    handover = None
    documents: list[HandoverDocument] = []
    if possession:
        handover = (
            await db.scalars(
                select(Handover).where(
                    Handover.organization_id == org, Handover.possession_id == possession.id
                )
            )
        ).first()
        if handover:
            documents = list(
                await db.scalars(
                    select(HandoverDocument)
                    .where(
                        HandoverDocument.organization_id == org,
                        HandoverDocument.handover_id == handover.id,
                    )
                    .order_by(HandoverDocument.document_type)
                )
            )
    summary = CaseSummary(
        id=case.id,
        booking_id=booking.id,
        booking_number=booking.booking_number,
        customer_name=customer.full_name,
        project_name=project.name,
        unit_number=unit.unit_number,
        stage=case.status,
        readiness=state,
        updated_at=case.updated_at,
    )
    return CaseDetail(
        case=summary,
        agreement=AgreementView.model_validate(agreement, from_attributes=True)
        if agreement
        else None,
        construction_updates=[
            ConstructionView.model_validate(item, from_attributes=True) for item in updates
        ],
        final_demand=DemandView(
            id=demand.id,
            demand_number=demand.demand_number,
            issue_date=demand.issue_date,
            due_date=demand.due_date,
            amount=demand.amount,
            currency=demand.currency,
            status=demand.status.value,
        )
        if demand
        else None,
        no_dues=NoDuesView.model_validate(certificate, from_attributes=True)
        if certificate
        else None,
        snags=[SnagView.model_validate(item, from_attributes=True) for item in snags],
        overrides=[
            OverrideView(
                id=item.id,
                status=item.status,
                reason=item.reason,
                missing_conditions=item.missing_conditions,
                requested_by_name=await _name(db, org, item.requested_by_user_id) or "Unknown",
                decided_by_name=await _name(db, org, item.decided_by_user_id),
                decision_notes=item.decision_notes,
                requested_at=item.requested_at,
                decided_at=item.decided_at,
            )
            for item in overrides
        ],
        possession=PossessionView.model_validate(possession, from_attributes=True)
        if possession
        else None,
        handover=HandoverView(
            id=handover.id,
            status=handover.status,
            handover_at=handover.handover_at,
            notes=handover.notes,
            customer_acknowledgement_name=handover.customer_acknowledgement_name,
            customer_acknowledgement_notes=handover.customer_acknowledgement_notes,
            customer_acknowledged_at=handover.customer_acknowledged_at,
            documents=[
                HandoverDocumentView.model_validate(item, from_attributes=True)
                for item in documents
            ],
        )
        if handover
        else None,
    )


async def create_case(
    db: AsyncSession, org: str, booking_id: str, context: MutationContext
) -> CaseDetail:
    booking = await _entity(db, Booking, org, booking_id, lock=True)
    if booking.status != BookingStatus.CONFIRMED:
        raise _error(
            "BOOKING_NOT_CONFIRMED", "Only confirmed bookings enter post-booking lifecycle"
        )
    existing = (
        await db.scalars(
            select(PostBookingCase).where(
                PostBookingCase.organization_id == org, PostBookingCase.booking_id == booking.id
            )
        )
    ).first()
    if existing:
        return await _views(db, org, existing)
    case = PostBookingCase(
        organization_id=org,
        booking_id=booking.id,
        created_by_user_id=context.actor_user_id,
        status=PostBookingStage.AGREEMENT_PENDING,
    )
    db.add(case)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("POST_BOOKING_CASE_EXISTS", "Booking already has a lifecycle record") from exc
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.created",
            "post_booking_case",
            case.id,
            None,
            {"booking_id": booking.id},
        )
    )
    await db.commit()
    await db.refresh(case)
    return await _views(db, org, case)


async def list_cases(
    db: AsyncSession,
    org: str,
    *,
    q: str | None,
    stage: PostBookingStage | None,
    page: int,
    page_size: int,
) -> Page[CaseSummary]:
    statement = (
        select(PostBookingCase)
        .join(
            Booking,
            (Booking.organization_id == PostBookingCase.organization_id)
            & (Booking.id == PostBookingCase.booking_id),
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
    statement = statement.where(PostBookingCase.organization_id == org)
    if stage:
        statement = statement.where(PostBookingCase.status == stage)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Booking.booking_number.ilike(pattern),
                Customer.full_name.ilike(pattern),
                Unit.unit_number.ilike(pattern),
            )
        )
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = list(
        await db.scalars(
            statement.order_by(PostBookingCase.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    items = [(await _views(db, org, item)).case for item in rows]
    return Page(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def get_case(db: AsyncSession, org: str, case_id: str) -> CaseDetail:
    return await _views(db, org, await _case(db, org, case_id))


async def options(db: AsyncSession, org: str) -> list[BookingOption]:
    existing = select(PostBookingCase.booking_id).where(PostBookingCase.organization_id == org)
    rows = (
        await db.execute(
            select(
                Booking.id,
                Booking.booking_number,
                Customer.full_name,
                Project.name,
                Unit.unit_number,
            )
            .join(
                Customer,
                (Customer.organization_id == Booking.organization_id)
                & (Customer.id == Booking.customer_id),
            )
            .join(
                Unit,
                (Unit.organization_id == Booking.organization_id) & (Unit.id == Booking.unit_id),
            )
            .join(
                Project,
                (Project.organization_id == Unit.organization_id) & (Project.id == Unit.project_id),
            )
            .where(
                Booking.organization_id == org,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.id.not_in(existing),
            )
            .order_by(Booking.updated_at.desc())
            .limit(500)
        )
    ).all()
    return [
        BookingOption(
            id=row[0],
            booking_number=row[1],
            customer_name=row[2],
            project_name=row[3],
            unit_number=row[4],
        )
        for row in rows
    ]


async def stats(db: AsyncSession, org: str) -> LifecycleStats:
    rows = list(
        await db.scalars(select(PostBookingCase).where(PostBookingCase.organization_id == org))
    )
    details = [await _views(db, org, item) for item in rows]
    return LifecycleStats(
        total=len(rows),
        readiness_blocked=sum(not item.case.readiness.ready for item in details),
        ready_for_possession=sum(item.case.readiness.ready for item in details),
        possession_scheduled=sum(
            bool(item.possession and item.possession.status == PossessionStatus.SCHEDULED)
            for item in details
        ),
        handed_over=sum(
            bool(item.handover and item.handover.status == WorkflowStatus.COMPLETED)
            for item in details
        ),
    )


async def create_agreement(
    db: AsyncSession, org: str, case_id: str, payload: AgreementCreate, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    if await db.scalar(
        select(Agreement.id).where(
            Agreement.organization_id == org, Agreement.booking_id == case.booking_id
        )
    ):
        raise _error("AGREEMENT_EXISTS", "Booking already has an agreement")
    item = Agreement(
        organization_id=org,
        booking_id=case.booking_id,
        agreement_number=payload.agreement_number.strip().upper(),
        status=AgreementStatus.DRAFT,
        notes=payload.notes,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("AGREEMENT_NUMBER_EXISTS", "Agreement number already exists") from exc
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.agreement.created",
            "agreement",
            item.id,
            None,
            {"number": item.agreement_number},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def upload_agreement(
    db: AsyncSession, org: str, case_id: str, upload: UploadFile, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id)
    item = (
        await db.scalars(
            select(Agreement).where(
                Agreement.organization_id == org, Agreement.booking_id == case.booking_id
            )
        )
    ).first()
    if not item:
        raise _error("AGREEMENT_REQUIRED", "Create the agreement before uploading", 404)
    prepared = await _prepare_file(upload)
    if prepared.content_type != "application/pdf":
        await asyncio.to_thread(prepared.path.unlink)
        raise _error("AGREEMENT_PDF_REQUIRED", "Agreement must be a genuine PDF", 415)
    storage = get_storage()
    key = f"pbl/a/{org}/{item.id}/{uuid.uuid4().hex[:16]}.private"
    old_key = item.storage_key
    try:
        await storage.save(key=key, source=prepared.path)
        item.storage_key, item.file_name, item.content_type = (
            key,
            prepared.file_name,
            prepared.content_type,
        )
        item.size_bytes, item.checksum_sha256 = prepared.size_bytes, prepared.checksum_sha256
        db.add(
            _audit(
                org,
                context,
                "property_lifecycle.agreement.uploaded",
                "agreement",
                item.id,
                None,
                {"file_name": item.file_name, "checksum": item.checksum_sha256},
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        await storage.delete(key=key)
        raise
    finally:
        if await asyncio.to_thread(prepared.path.exists):
            await asyncio.to_thread(prepared.path.unlink)
    if old_key:
        await storage.delete(key=old_key)
    return await _views(db, org, case)


async def transition_agreement(
    db: AsyncSession, org: str, case_id: str, payload: AgreementTransition, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    item = (
        await db.scalars(
            select(Agreement)
            .where(Agreement.organization_id == org, Agreement.booking_id == case.booking_id)
            .with_for_update()
        )
    ).first()
    if not item:
        raise _error("AGREEMENT_REQUIRED", "Agreement is missing", 404)
    target = AgreementStatus(payload.status)
    allowed = {
        AgreementStatus.DRAFT: AgreementStatus.ISSUED,
        AgreementStatus.ISSUED: AgreementStatus.SIGNED,
        AgreementStatus.SIGNED: AgreementStatus.REGISTERED,
    }
    if allowed.get(item.status) != target:
        raise _error(
            "INVALID_AGREEMENT_TRANSITION",
            f"Cannot move agreement from {item.status.value} to {target.value}",
        )
    if target in (AgreementStatus.SIGNED, AgreementStatus.REGISTERED) and not item.storage_key:
        raise _error("SIGNED_AGREEMENT_REQUIRED", "Upload the signed agreement PDF first")
    before = item.status.value
    item.status, item.notes = target, payload.notes or item.notes
    now = _now()
    if target == AgreementStatus.ISSUED:
        item.issued_at, item.issued_by_user_id = now, context.actor_user_id
    elif target == AgreementStatus.SIGNED:
        item.signed_at, item.signed_by_user_id = now, context.actor_user_id
    else:
        item.registered_at, item.registered_by_user_id = now, context.actor_user_id
        item.registration_number = payload.registration_number
        case.agreement_completed_at = now
    await _sync_stage(db, org, case)
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.agreement.status_changed",
            "agreement",
            item.id,
            {"status": before},
            {"status": target.value, "registration_number": item.registration_number},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def create_construction_update(
    db: AsyncSession, org: str, case_id: str, payload: ConstructionCreate, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id)
    _, _, unit, _ = await _context_rows(db, org, case)
    if payload.tower_id:
        tower = await _entity(db, Tower, org, payload.tower_id)
        if tower.project_id != unit.project_id:
            raise _error(
                "TOWER_PROJECT_MISMATCH", "Tower does not belong to the booking project", 422
            )
    item = ConstructionUpdate(
        organization_id=org,
        project_id=unit.project_id,
        tower_id=payload.tower_id,
        published_by_user_id=None,
        title=payload.title.strip(),
        description=payload.description.strip(),
        progress_percent=payload.progress_percent,
        status=ProgressStatus.DRAFT,
        update_date=payload.update_date,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.construction.created",
            "construction_update",
            item.id,
            None,
            {"progress_percent": str(item.progress_percent)},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def publish_construction_update(
    db: AsyncSession, org: str, case_id: str, update_id: str, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    _, _, unit, _ = await _context_rows(db, org, case)
    item = await _entity(db, ConstructionUpdate, org, update_id, lock=True)
    if item.project_id != unit.project_id or item.status != ProgressStatus.DRAFT:
        raise _error(
            "CONSTRUCTION_UPDATE_NOT_PUBLISHABLE", "Update is not a draft for this project"
        )
    item.status, item.published_by_user_id, item.published_at = (
        ProgressStatus.PUBLISHED,
        context.actor_user_id,
        _now(),
    )
    if item.progress_percent >= Decimal("100"):
        case.construction_ready_at = item.published_at
    await _sync_stage(db, org, case)
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.construction.published",
            "construction_update",
            item.id,
            {"status": "DRAFT"},
            {"status": "PUBLISHED", "progress_percent": str(item.progress_percent)},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def issue_final_demand(
    db: AsyncSession, org: str, case_id: str, payload: FinalDemandCreate, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    booking = await _entity(db, Booking, org, case.booking_id, lock=True)
    if case.final_demand_letter_id:
        raise _error("FINAL_DEMAND_EXISTS", "Final demand has already been issued")
    state = await readiness(db, org, case)
    required = {item.code: item.complete for item in state.conditions}
    if not required["AGREEMENT_REGISTERED"] or not required["CONSTRUCTION_COMPLETE"]:
        raise _error(
            "FINAL_DEMAND_NOT_READY", "Registered agreement and completed construction are required"
        )
    item = DemandLetter(
        organization_id=org,
        booking_id=booking.id,
        customer_id=booking.customer_id,
        installment_id=None,
        demand_number=payload.demand_number.strip().upper(),
        status=RecordStatus.ACTIVE,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        amount=state.outstanding_amount,
        currency=booking.currency,
        is_final=True,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("DEMAND_NUMBER_EXISTS", "Demand number already exists") from exc
    case.final_demand_letter_id, case.final_demand_issued_at = item.id, _now()
    if state.financially_ready:
        case.final_payment_verified_at = _now()
    await _sync_stage(db, org, case)
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.final_demand.issued",
            "demand_letter",
            item.id,
            None,
            {"booking_id": booking.id, "amount": str(item.amount), "server_calculated": True},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def issue_no_dues(
    db: AsyncSession, org: str, case_id: str, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    booking, customer, unit, project = await _context_rows(db, org, case)
    if await db.scalar(
        select(NoDuesCertificate.id).where(
            NoDuesCertificate.organization_id == org, NoDuesCertificate.booking_id == booking.id
        )
    ):
        raise _error("NO_DUES_EXISTS", "No-dues certificate already exists")
    state = await readiness(db, org, case)
    if not case.final_demand_letter_id or not state.financially_ready or not state.documents_ready:
        raise _error(
            "NO_DUES_CONDITIONS_INCOMPLETE",
            "Final demand, cleared finances, registered agreement, and verified KYC are required",
        )
    number = f"NDC-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    organization = await db.get(Organization, org)
    if organization is None:
        raise _error("RESOURCE_NOT_FOUND", "Organization not found", 404)
    pdf = WorkflowPdfRenderer().render(
        WorkflowPdfDocument(
            organization_name=organization.name,
            title="NO-DUES CERTIFICATE",
            document_number=number,
            lines=(
                f"Booking: {booking.booking_number}",
                f"Customer: {customer.full_name}",
                f"Project: {project.name}",
                f"Unit: {unit.unit_number}",
                f"Outstanding: {booking.currency} {state.outstanding_amount}",
                "All recorded installments and reconciled ledger dues are cleared.",
            ),
        )
    )
    key = f"pbl/n/{org}/{case.id}/{uuid.uuid4().hex[:16]}.private"
    storage = get_storage()
    await storage.save_bytes(key=key, content=pdf)
    item = NoDuesCertificate(
        organization_id=org,
        post_booking_case_id=case.id,
        booking_id=booking.id,
        issued_by_user_id=context.actor_user_id,
        certificate_number=number,
        status=RecordStatus.ACTIVE,
        financial_snapshot={
            "outstanding": str(state.outstanding_amount),
            "currency": state.currency,
            "conditions": [entry.model_dump(mode="json") for entry in state.conditions],
        },
        issued_at=_now(),
        storage_key=key,
    )
    db.add(item)
    try:
        await db.flush()
        case.no_dues_issued_at, case.final_payment_verified_at = item.issued_at, item.issued_at
        await _sync_stage(db, org, case)
        db.add(
            _audit(
                org,
                context,
                "property_lifecycle.no_dues.issued",
                "no_dues_certificate",
                item.id,
                None,
                {"number": number, "snapshot": item.financial_snapshot},
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        await storage.delete(key=key)
        raise
    return await _views(db, org, case)


async def create_snag(
    db: AsyncSession, org: str, case_id: str, payload: SnagCreate, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id)
    item = SnagItem(
        organization_id=org,
        post_booking_case_id=case.id,
        reported_by_user_id=context.actor_user_id,
        area=payload.area.strip(),
        description=payload.description.strip(),
        severity=payload.severity,
        status=SnagStatus.OPEN,
        reported_at=_now(),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.snag.created",
            "snag_item",
            item.id,
            None,
            {"area": item.area, "severity": item.severity},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def decide_snag(
    db: AsyncSession,
    org: str,
    case_id: str,
    snag_id: str,
    payload: SnagDecision,
    context: MutationContext,
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    item = await _entity(db, SnagItem, org, snag_id, lock=True)
    if item.post_booking_case_id != case.id:
        raise _error("SNAG_SCOPE_MISMATCH", "Snag does not belong to this lifecycle", 404)
    target = SnagStatus(payload.status)
    allowed = {
        SnagStatus.OPEN: {SnagStatus.IN_PROGRESS, SnagStatus.WAIVED},
        SnagStatus.IN_PROGRESS: {SnagStatus.RESOLVED, SnagStatus.WAIVED},
        SnagStatus.RESOLVED: {SnagStatus.ACCEPTED, SnagStatus.IN_PROGRESS},
    }
    if target not in allowed.get(item.status, set()):
        raise _error(
            "INVALID_SNAG_TRANSITION",
            f"Cannot move snag from {item.status.value} to {target.value}",
        )
    before, now = item.status.value, _now()
    item.status, item.resolution_notes = target, payload.notes.strip()
    if target in (SnagStatus.RESOLVED, SnagStatus.WAIVED):
        item.resolved_at, item.resolved_by_user_id = now, context.actor_user_id
    if target == SnagStatus.ACCEPTED:
        item.accepted_at = now
    open_count = int(
        await db.scalar(
            select(func.count(SnagItem.id)).where(
                SnagItem.organization_id == org,
                SnagItem.post_booking_case_id == case.id,
                SnagItem.id != item.id,
                SnagItem.status.in_((SnagStatus.OPEN, SnagStatus.IN_PROGRESS, SnagStatus.RESOLVED)),
            )
        )
        or 0
    )
    if open_count == 0 and target in (SnagStatus.ACCEPTED, SnagStatus.WAIVED):
        case.snagging_completed_at = now
    await _sync_stage(db, org, case)
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.snag.status_changed",
            "snag_item",
            item.id,
            {"status": before},
            {"status": target.value, "notes": item.resolution_notes},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def request_override(
    db: AsyncSession, org: str, case_id: str, payload: OverrideCreate, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    state = await readiness(db, org, case)
    missing = [item.code for item in state.conditions if item.blocking and not item.complete]
    if not missing:
        raise _error("OVERRIDE_NOT_REQUIRED", "All possession conditions are already complete")
    if await db.scalar(
        select(PossessionOverrideRequest.id).where(
            PossessionOverrideRequest.organization_id == org,
            PossessionOverrideRequest.post_booking_case_id == case.id,
            PossessionOverrideRequest.status == WorkflowStatus.REQUESTED,
        )
    ):
        raise _error("OVERRIDE_PENDING", "An override request is already pending")
    item = PossessionOverrideRequest(
        organization_id=org,
        post_booking_case_id=case.id,
        requested_by_user_id=context.actor_user_id,
        status=WorkflowStatus.REQUESTED,
        reason=payload.reason.strip(),
        missing_conditions=missing,
        requested_at=_now(),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.possession_override.requested",
            "possession_override",
            item.id,
            None,
            {"missing_conditions": missing, "reason": item.reason},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def decide_override(
    db: AsyncSession,
    org: str,
    case_id: str,
    override_id: str,
    payload: OverrideDecision,
    context: MutationContext,
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    item = await _entity(db, PossessionOverrideRequest, org, override_id, lock=True)
    if item.post_booking_case_id != case.id or item.status != WorkflowStatus.REQUESTED:
        raise _error("OVERRIDE_FINALIZED", "Override is not awaiting a decision")
    if item.requested_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Override requester cannot approve it", 403)
    item.status = WorkflowStatus(payload.status)
    item.decided_by_user_id, item.decision_notes, item.decided_at = (
        context.actor_user_id,
        payload.notes.strip(),
        _now(),
    )
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.possession_override.decided",
            "possession_override",
            item.id,
            {"status": "REQUESTED"},
            {"status": item.status.value, "notes": item.decision_notes},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def _authorized_readiness(
    db: AsyncSession, org: str, case: PostBookingCase
) -> tuple[ReadinessView, str | None]:
    state = await readiness(db, org, case)
    if state.ready:
        return state, None
    missing = {item.code for item in state.conditions if item.blocking and not item.complete}
    approved = (
        await db.scalars(
            select(PossessionOverrideRequest)
            .where(
                PossessionOverrideRequest.organization_id == org,
                PossessionOverrideRequest.post_booking_case_id == case.id,
                PossessionOverrideRequest.status == WorkflowStatus.APPROVED,
            )
            .order_by(PossessionOverrideRequest.decided_at.desc())
            .with_for_update()
        )
    ).first()
    if not approved or not missing.issubset(set(approved.missing_conditions)):
        raise _error(
            "POSSESSION_CONDITIONS_INCOMPLETE",
            "Possession is blocked until all readiness conditions pass or an explicit "
            "override is independently approved",
        )
    return state, approved.id


async def possession_action(
    db: AsyncSession,
    org: str,
    case_id: str,
    action: str,
    payload: PossessionAction,
    context: MutationContext,
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    booking = await _entity(db, Booking, org, case.booking_id, lock=True)
    _, override_id = await _authorized_readiness(db, org, case)
    item = (
        await db.scalars(
            select(Possession)
            .where(Possession.organization_id == org, Possession.booking_id == booking.id)
            .with_for_update()
        )
    ).first()
    now = _now()
    if action == "offer":
        if item:
            raise _error("POSSESSION_EXISTS", "Possession workflow already exists")
        item = Possession(
            organization_id=org,
            booking_id=booking.id,
            customer_id=booking.customer_id,
            unit_id=booking.unit_id,
            post_booking_case_id=case.id,
            readiness_override_id=override_id,
            offered_by_user_id=context.actor_user_id,
            status=PossessionStatus.OFFERED,
            offered_at=now,
            notes=payload.notes,
        )
        db.add(item)
        await db.flush()
    elif action == "schedule":
        if not item or item.status != PossessionStatus.OFFERED or not payload.scheduled_at:
            raise _error("POSSESSION_NOT_OFFERED", "Offer possession and provide a schedule first")
        scheduled_at = payload.scheduled_at
        if scheduled_at.tzinfo is not None:
            scheduled_at = scheduled_at.astimezone(UTC).replace(tzinfo=None)
        if scheduled_at <= now:
            raise _error(
                "INVALID_POSSESSION_TIME", "Possession schedule must be in the future", 422
            )
        item.status, item.scheduled_at, item.scheduled_by_user_id = (
            PossessionStatus.SCHEDULED,
            scheduled_at,
            context.actor_user_id,
        )
        item.readiness_override_id, item.notes = override_id, payload.notes or item.notes
    elif action == "complete":
        if not item or item.status != PossessionStatus.SCHEDULED:
            raise _error(
                "POSSESSION_NOT_SCHEDULED", "Possession must be scheduled before completion"
            )
        item.status, item.completed_at, item.completed_by_user_id = (
            PossessionStatus.COMPLETED,
            now,
            context.actor_user_id,
        )
        item.readiness_override_id, item.notes = override_id, payload.notes or item.notes
        case.possession_completed_at = now
    else:
        raise _error("INVALID_POSSESSION_ACTION", "Unknown possession action", 422)
    await _sync_stage(db, org, case)
    db.add(
        _audit(
            org,
            context,
            f"property_lifecycle.possession.{action}",
            "possession",
            item.id,
            None,
            {
                "status": item.status.value,
                "override_id": override_id,
                "readiness_snapshot": case.readiness_snapshot,
            },
        )
    )
    possession_recipients = await notification_service.recipients_for_permission(
        db, org, "possession.update"
    )
    if booking.salesperson_user_id:
        possession_recipients.add(booking.salesperson_user_id)
    notification_service.queue_in_app(
        db,
        organization_id=org,
        recipient_user_ids=possession_recipients,
        event_type=NotificationEventType.POSSESSION_UPDATED,
        title="Possession workflow updated",
        body=f"{booking.booking_number}: {item.status.value}",
        related_entity_type="possession",
        related_entity_id=item.id,
        action_url=f"/property-lifecycle/{case.id}",
        data={"booking_id": booking.id, "status": item.status.value, "action": action},
    )
    await db.commit()
    return await _views(db, org, case)


async def start_handover(
    db: AsyncSession, org: str, case_id: str, payload: PossessionAction, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    possession = (
        await db.scalars(
            select(Possession)
            .where(Possession.organization_id == org, Possession.post_booking_case_id == case.id)
            .with_for_update()
        )
    ).first()
    if not possession or possession.status != PossessionStatus.COMPLETED:
        raise _error("POSSESSION_NOT_COMPLETED", "Complete possession before handover")
    if await db.scalar(
        select(Handover.id).where(
            Handover.organization_id == org, Handover.possession_id == possession.id
        )
    ):
        raise _error("HANDOVER_EXISTS", "Handover workflow already exists")
    item = Handover(
        organization_id=org,
        possession_id=possession.id,
        status=WorkflowStatus.UNDER_REVIEW,
        notes=payload.notes,
    )
    db.add(item)
    await db.flush()
    for document_type in ("POSSESSION_LETTER", "NO_DUES_CERTIFICATE", "HANDOVER_CHECKLIST"):
        db.add(
            HandoverDocument(
                organization_id=org,
                handover_id=item.id,
                document_type=document_type,
                is_required=True,
            )
        )
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.handover.started",
            "handover",
            item.id,
            None,
            {
                "required_documents": [
                    "POSSESSION_LETTER",
                    "NO_DUES_CERTIFICATE",
                    "HANDOVER_CHECKLIST",
                ]
            },
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def add_handover_document(
    db: AsyncSession,
    org: str,
    case_id: str,
    payload: HandoverDocumentCreate,
    context: MutationContext,
) -> CaseDetail:
    case = await _case(db, org, case_id)
    possession = (
        await db.scalars(
            select(Possession).where(
                Possession.organization_id == org, Possession.post_booking_case_id == case.id
            )
        )
    ).first()
    handover = (
        await db.scalars(
            select(Handover).where(
                Handover.organization_id == org,
                Handover.possession_id == (possession.id if possession else ""),
            )
        )
    ).first()
    if not handover:
        raise _error("HANDOVER_REQUIRED", "Start handover first")
    item = HandoverDocument(
        organization_id=org,
        handover_id=handover.id,
        document_type=payload.document_type.strip().upper().replace(" ", "_"),
        is_required=payload.is_required,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("HANDOVER_DOCUMENT_EXISTS", "Document type already exists") from exc
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.handover_document.requested",
            "handover_document",
            item.id,
            None,
            {"document_type": item.document_type, "required": item.is_required},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def upload_handover_document(
    db: AsyncSession,
    org: str,
    case_id: str,
    document_id: str,
    upload: UploadFile,
    context: MutationContext,
) -> CaseDetail:
    case = await _case(db, org, case_id)
    item = await _entity(db, HandoverDocument, org, document_id, lock=True)
    possession = (
        await db.scalars(
            select(Possession).where(
                Possession.organization_id == org, Possession.post_booking_case_id == case.id
            )
        )
    ).first()
    handover = (
        await db.scalars(
            select(Handover).where(
                Handover.organization_id == org,
                Handover.possession_id == (possession.id if possession else ""),
            )
        )
    ).first()
    if not handover or item.handover_id != handover.id:
        raise _error(
            "HANDOVER_DOCUMENT_SCOPE_MISMATCH", "Document does not belong to this handover", 404
        )
    prepared = await _prepare_file(upload)
    storage = get_storage()
    key = f"pbl/h/{org}/{item.id}/{uuid.uuid4().hex[:16]}.private"
    old_key = item.storage_key
    try:
        await storage.save(key=key, source=prepared.path)
        item.uploaded_by_user_id, item.file_name, item.storage_key = (
            context.actor_user_id,
            prepared.file_name,
            key,
        )
        item.content_type, item.size_bytes, item.checksum_sha256, item.uploaded_at = (
            prepared.content_type,
            prepared.size_bytes,
            prepared.checksum_sha256,
            _now(),
        )
        db.add(
            _audit(
                org,
                context,
                "property_lifecycle.handover_document.uploaded",
                "handover_document",
                item.id,
                None,
                {"file_name": item.file_name, "checksum": item.checksum_sha256},
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        await storage.delete(key=key)
        raise
    finally:
        if await asyncio.to_thread(prepared.path.exists):
            await asyncio.to_thread(prepared.path.unlink)
    if old_key:
        await storage.delete(key=old_key)
    return await _views(db, org, case)


async def acknowledge_handover(
    db: AsyncSession,
    org: str,
    case_id: str,
    payload: AcknowledgementCreate,
    context: MutationContext,
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    possession = (
        await db.scalars(
            select(Possession).where(
                Possession.organization_id == org, Possession.post_booking_case_id == case.id
            )
        )
    ).first()
    handover = (
        await db.scalars(
            select(Handover)
            .where(
                Handover.organization_id == org,
                Handover.possession_id == (possession.id if possession else ""),
            )
            .with_for_update()
        )
    ).first()
    if not handover or handover.status != WorkflowStatus.UNDER_REVIEW:
        raise _error("HANDOVER_NOT_ACTIVE", "Handover is not awaiting acknowledgement")
    missing = int(
        await db.scalar(
            select(func.count(HandoverDocument.id)).where(
                HandoverDocument.organization_id == org,
                HandoverDocument.handover_id == handover.id,
                HandoverDocument.is_required.is_(True),
                HandoverDocument.storage_key.is_(None),
            )
        )
        or 0
    )
    if missing:
        raise _error(
            "HANDOVER_DOCUMENTS_INCOMPLETE", f"{missing} required handover documents are missing"
        )
    handover.customer_acknowledgement_name, handover.customer_acknowledgement_notes = (
        payload.customer_name.strip(),
        payload.notes.strip(),
    )
    handover.customer_acknowledged_at, handover.acknowledged_by_user_id = (
        _now(),
        context.actor_user_id,
    )
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.handover.acknowledged",
            "handover",
            handover.id,
            None,
            {
                "customer_name": handover.customer_acknowledgement_name,
                "acknowledged_at": handover.customer_acknowledged_at.isoformat(),
            },
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def complete_handover(
    db: AsyncSession, org: str, case_id: str, context: MutationContext
) -> CaseDetail:
    case = await _case(db, org, case_id, lock=True)
    possession = (
        await db.scalars(
            select(Possession)
            .where(Possession.organization_id == org, Possession.post_booking_case_id == case.id)
            .with_for_update()
        )
    ).first()
    handover = (
        await db.scalars(
            select(Handover)
            .where(
                Handover.organization_id == org,
                Handover.possession_id == (possession.id if possession else ""),
            )
            .with_for_update()
        )
    ).first()
    if (
        not handover
        or handover.status != WorkflowStatus.UNDER_REVIEW
        or not handover.customer_acknowledged_at
    ):
        raise _error(
            "CUSTOMER_ACKNOWLEDGEMENT_REQUIRED",
            "Customer acknowledgement is required before handover",
        )
    handover.status, handover.handover_at, handover.handed_over_by_user_id = (
        WorkflowStatus.COMPLETED,
        _now(),
        context.actor_user_id,
    )
    case.handover_completed_at = handover.handover_at
    await _sync_stage(db, org, case)
    db.add(
        _audit(
            org,
            context,
            "property_lifecycle.handover.completed",
            "handover",
            handover.id,
            {"status": "UNDER_REVIEW"},
            {"status": "COMPLETED", "handover_at": handover.handover_at.isoformat()},
        )
    )
    await db.commit()
    return await _views(db, org, case)


async def agreement_download(
    db: AsyncSession, org: str, case_id: str
) -> tuple[StoredFile, str, str]:
    case = await _case(db, org, case_id)
    item = (
        await db.scalars(
            select(Agreement).where(
                Agreement.organization_id == org, Agreement.booking_id == case.booking_id
            )
        )
    ).first()
    if not item or not item.storage_key or not item.file_name or not item.content_type:
        raise _error("AGREEMENT_FILE_MISSING", "Agreement file is unavailable", 404)
    return (
        await get_storage().path_for_read(key=item.storage_key),
        item.file_name,
        item.content_type,
    )


async def no_dues_download(
    db: AsyncSession, org: str, case_id: str
) -> tuple[StoredFile, str]:
    item = (
        await db.scalars(
            select(NoDuesCertificate).where(
                NoDuesCertificate.organization_id == org,
                NoDuesCertificate.post_booking_case_id == case_id,
            )
        )
    ).first()
    if not item:
        raise _error("NO_DUES_MISSING", "No-dues certificate is unavailable", 404)
    return await get_storage().path_for_read(
        key=item.storage_key
    ), f"{item.certificate_number}.pdf"


async def handover_document_download(
    db: AsyncSession, org: str, case_id: str, document_id: str
) -> tuple[StoredFile, str, str]:
    case = await _case(db, org, case_id)
    item = await _entity(db, HandoverDocument, org, document_id)
    possession = (
        await db.scalars(
            select(Possession).where(
                Possession.organization_id == org, Possession.post_booking_case_id == case.id
            )
        )
    ).first()
    handover_id = await db.scalar(
        select(Handover.id).where(
            Handover.organization_id == org,
            Handover.possession_id == (possession.id if possession else ""),
        )
    )
    if (
        item.handover_id != handover_id
        or not item.storage_key
        or not item.file_name
        or not item.content_type
    ):
        raise _error("HANDOVER_DOCUMENT_MISSING", "Handover document is unavailable", 404)
    return (
        await get_storage().path_for_read(key=item.storage_key),
        item.file_name,
        item.content_type,
    )
