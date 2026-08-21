from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Branch,
    Customer,
    Lead,
    LeadActivity,
    LeadAssignment,
    LeadImportBatch,
    LeadNote,
    LeadScoreRule,
    LeadSource,
    LostLeadReason,
    Project,
    SiteVisit,
    User,
)
from app.models.enums import ActivityType, CustomerStatus, LeadStatus
from app.schemas.leads import (
    AgeingBucket,
    AssigneeView,
    BulkAssignmentPayload,
    CompleteFollowUpPayload,
    DuplicateCheckPayload,
    DuplicateGroup,
    DuplicateMatch,
    DuplicateResolutionPayload,
    ImportBatchView,
    ImportLeadRow,
    ImportPreview,
    ImportRequest,
    ImportRowResult,
    KanbanColumn,
    LeadActivityPayload,
    LeadActivityView,
    LeadAssignmentPayload,
    LeadConversionPayload,
    LeadConversionView,
    LeadCreate,
    LeadNotePayload,
    LeadNoteView,
    LeadSourcePayload,
    LeadSourceView,
    LeadStats,
    LeadUpdate,
    LeadView,
    LostLeadPayload,
    LostReasonPayload,
    LostReasonView,
    QualificationPayload,
    ScoreRulePayload,
    ScoreRuleView,
    StatusTransitionPayload,
    TimelineItem,
)
from app.schemas.organization import Page
from app.services.organization import MutationContext

ACTIVE_LEAD_STATUSES = (
    LeadStatus.NEW,
    LeadStatus.ASSIGNED,
    LeadStatus.ATTEMPTED,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
)
STATUS_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset(
        {
            LeadStatus.ASSIGNED,
            LeadStatus.ATTEMPTED,
            LeadStatus.CONTACTED,
            LeadStatus.QUALIFIED,
            LeadStatus.DISQUALIFIED,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.ASSIGNED: frozenset(
        {
            LeadStatus.ATTEMPTED,
            LeadStatus.CONTACTED,
            LeadStatus.QUALIFIED,
            LeadStatus.DISQUALIFIED,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.ATTEMPTED: frozenset(
        {
            LeadStatus.CONTACTED,
            LeadStatus.QUALIFIED,
            LeadStatus.DISQUALIFIED,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.CONTACTED: frozenset(
        {LeadStatus.QUALIFIED, LeadStatus.DISQUALIFIED, LeadStatus.LOST}
    ),
    LeadStatus.QUALIFIED: frozenset(
        {LeadStatus.CONTACTED, LeadStatus.DISQUALIFIED, LeadStatus.LOST, LeadStatus.CONVERTED}
    ),
    LeadStatus.DISQUALIFIED: frozenset({LeadStatus.CONTACTED, LeadStatus.LOST}),
    LeadStatus.LOST: frozenset({LeadStatus.CONTACTED}),
    LeadStatus.CONVERTED: frozenset(),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _db_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _normalize_email(value: str | None) -> str | None:
    return value.strip().lower() if value and value.strip() else None


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return digits or None


def _page[T](items: list[T], total: int, page: int, page_size: int) -> Page[T]:
    return Page(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested resource was not found",
    )


async def _tenant_entity[T](
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
    entity = (await db.scalars(statement)).first()
    if entity is None:
        raise _not_found()
    return entity


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
        created_at=_now(),
    )


async def _commit_conflict(db: AsyncSession, code: str, message: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(status_code=409, code=code, message=message) from exc


async def _flush_conflict(db: AsyncSession, code: str, message: str) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(status_code=409, code=code, message=message) from exc


def _lead_snapshot(lead: Lead) -> dict[str, Any]:
    return {
        "full_name": lead.full_name,
        "email": lead.email,
        "phone": lead.phone,
        "source_id": lead.source_id,
        "owner_user_id": lead.owner_user_id,
        "branch_id": lead.branch_id,
        "status": lead.status.value,
        "score": lead.score,
        "budget_min": str(lead.budget_min) if lead.budget_min is not None else None,
        "budget_max": str(lead.budget_max) if lead.budget_max is not None else None,
        "lost_reason_id": lead.lost_reason_id,
        "duplicate_of_lead_id": lead.duplicate_of_lead_id,
    }


async def _validate_lead_references(
    db: AsyncSession,
    organization_id: str,
    *,
    source_id: str | None,
    branch_id: str | None,
) -> None:
    if source_id:
        source = await _tenant_entity(db, LeadSource, organization_id, source_id)
        if not source.is_active:
            raise AppError(
                status_code=400,
                code="LEAD_SOURCE_INACTIVE",
                message="The selected lead source is inactive",
            )
    if branch_id:
        branch = await _tenant_entity(db, Branch, organization_id, branch_id)
        if not branch.is_active:
            raise AppError(
                status_code=400,
                code="BRANCH_INACTIVE",
                message="The selected branch is inactive",
            )


async def list_sources(db: AsyncSession, organization_id: str) -> list[LeadSourceView]:
    count_query = (
        select(func.count(Lead.id))
        .where(Lead.organization_id == LeadSource.organization_id, Lead.source_id == LeadSource.id)
        .correlate(LeadSource)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(LeadSource, count_query)
            .where(LeadSource.organization_id == organization_id)
            .order_by(LeadSource.name)
        )
    ).all()
    return [
        LeadSourceView(
            id=source.id,
            name=source.name,
            code=source.code,
            is_active=source.is_active,
            lead_count=int(count),
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        for source, count in rows
    ]


async def create_source(
    db: AsyncSession,
    organization_id: str,
    payload: LeadSourcePayload,
    context: MutationContext,
) -> LeadSourceView:
    source = LeadSource(organization_id=organization_id, **payload.model_dump())
    db.add(source)
    await _flush_conflict(db, "LEAD_SOURCE_EXISTS", "A lead source with this code already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "lead_source.created",
            "lead_source",
            source.id,
            None,
            {"name": source.name, "code": source.code, "is_active": source.is_active},
        )
    )
    await _commit_conflict(db, "LEAD_SOURCE_EXISTS", "A lead source with this code already exists")
    await db.refresh(source)
    return LeadSourceView(
        id=source.id,
        name=source.name,
        code=source.code,
        is_active=source.is_active,
        lead_count=0,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def update_source(
    db: AsyncSession,
    organization_id: str,
    source_id: str,
    payload: LeadSourcePayload,
    context: MutationContext,
) -> LeadSourceView:
    source = await _tenant_entity(db, LeadSource, organization_id, source_id, lock=True)
    before = {"name": source.name, "code": source.code, "is_active": source.is_active}
    for field, value in payload.model_dump().items():
        setattr(source, field, value)
    source.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_source.updated",
            "lead_source",
            source.id,
            before,
            {"name": source.name, "code": source.code, "is_active": source.is_active},
        )
    )
    await _commit_conflict(db, "LEAD_SOURCE_EXISTS", "A lead source with this code already exists")
    count = int(
        await db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.organization_id == organization_id, Lead.source_id == source.id)
        )
        or 0
    )
    return LeadSourceView(
        id=source.id,
        name=source.name,
        code=source.code,
        is_active=source.is_active,
        lead_count=count,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def delete_source(
    db: AsyncSession, organization_id: str, source_id: str, context: MutationContext
) -> None:
    source = await _tenant_entity(db, LeadSource, organization_id, source_id, lock=True)
    in_use = int(
        await db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.organization_id == organization_id, Lead.source_id == source.id)
        )
        or 0
    )
    if in_use:
        raise AppError(
            status_code=409,
            code="RESOURCE_IN_USE",
            message="Deactivate this source instead because existing leads reference it",
        )
    db.add(
        _audit(
            organization_id,
            context,
            "lead_source.deleted",
            "lead_source",
            source.id,
            {"name": source.name, "code": source.code},
            None,
        )
    )
    await db.delete(source)
    await db.commit()


async def list_lost_reasons(db: AsyncSession, organization_id: str) -> list[LostReasonView]:
    count_query = (
        select(func.count(Lead.id))
        .where(
            Lead.organization_id == LostLeadReason.organization_id,
            Lead.lost_reason_id == LostLeadReason.id,
        )
        .correlate(LostLeadReason)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(LostLeadReason, count_query)
            .where(LostLeadReason.organization_id == organization_id)
            .order_by(LostLeadReason.name)
        )
    ).all()
    return [
        LostReasonView(
            id=reason.id,
            name=reason.name,
            code=reason.code,
            is_active=reason.is_active,
            lead_count=int(count),
            created_at=reason.created_at,
            updated_at=reason.updated_at,
        )
        for reason, count in rows
    ]


async def create_lost_reason(
    db: AsyncSession,
    organization_id: str,
    payload: LostReasonPayload,
    context: MutationContext,
) -> LostReasonView:
    reason = LostLeadReason(organization_id=organization_id, **payload.model_dump())
    db.add(reason)
    await _flush_conflict(db, "LOST_REASON_EXISTS", "A lost reason with this code already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "lost_reason.created",
            "lost_reason",
            reason.id,
            None,
            {"name": reason.name, "code": reason.code, "is_active": reason.is_active},
        )
    )
    await _commit_conflict(db, "LOST_REASON_EXISTS", "A lost reason with this code already exists")
    await db.refresh(reason)
    return LostReasonView(
        id=reason.id,
        name=reason.name,
        code=reason.code,
        is_active=reason.is_active,
        lead_count=0,
        created_at=reason.created_at,
        updated_at=reason.updated_at,
    )


async def update_lost_reason(
    db: AsyncSession,
    organization_id: str,
    reason_id: str,
    payload: LostReasonPayload,
    context: MutationContext,
) -> LostReasonView:
    reason = await _tenant_entity(db, LostLeadReason, organization_id, reason_id, lock=True)
    before = {"name": reason.name, "code": reason.code, "is_active": reason.is_active}
    for field, value in payload.model_dump().items():
        setattr(reason, field, value)
    reason.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "lost_reason.updated",
            "lost_reason",
            reason.id,
            before,
            {"name": reason.name, "code": reason.code, "is_active": reason.is_active},
        )
    )
    await _commit_conflict(db, "LOST_REASON_EXISTS", "A lost reason with this code already exists")
    count = int(
        await db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.organization_id == organization_id, Lead.lost_reason_id == reason.id)
        )
        or 0
    )
    return LostReasonView(
        id=reason.id,
        name=reason.name,
        code=reason.code,
        is_active=reason.is_active,
        lead_count=count,
        created_at=reason.created_at,
        updated_at=reason.updated_at,
    )


async def delete_lost_reason(
    db: AsyncSession, organization_id: str, reason_id: str, context: MutationContext
) -> None:
    reason = await _tenant_entity(db, LostLeadReason, organization_id, reason_id, lock=True)
    in_use = int(
        await db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.organization_id == organization_id, Lead.lost_reason_id == reason.id)
        )
        or 0
    )
    if in_use:
        raise AppError(
            status_code=409,
            code="RESOURCE_IN_USE",
            message="Deactivate this reason instead because existing leads reference it",
        )
    db.add(
        _audit(
            organization_id,
            context,
            "lost_reason.deleted",
            "lost_reason",
            reason.id,
            {"name": reason.name, "code": reason.code},
            None,
        )
    )
    await db.delete(reason)
    await db.commit()


async def _lead_views(db: AsyncSession, organization_id: str, leads: list[Lead]) -> list[LeadView]:
    if not leads:
        return []
    source_ids = {lead.source_id for lead in leads if lead.source_id}
    user_ids = {lead.owner_user_id for lead in leads if lead.owner_user_id}
    branch_ids = {lead.branch_id for lead in leads if lead.branch_id}
    reason_ids = {lead.lost_reason_id for lead in leads if lead.lost_reason_id}
    sources = {
        source.id: source.name
        for source in (
            await db.scalars(
                select(LeadSource).where(
                    LeadSource.organization_id == organization_id, LeadSource.id.in_(source_ids)
                )
            )
        ).all()
    }
    users = {
        user.id: user.full_name
        for user in (
            await db.scalars(
                select(User).where(User.organization_id == organization_id, User.id.in_(user_ids))
            )
        ).all()
    }
    branches = {
        branch.id: branch.name
        for branch in (
            await db.scalars(
                select(Branch).where(
                    Branch.organization_id == organization_id, Branch.id.in_(branch_ids)
                )
            )
        ).all()
    }
    reasons = {
        reason.id: reason.name
        for reason in (
            await db.scalars(
                select(LostLeadReason).where(
                    LostLeadReason.organization_id == organization_id,
                    LostLeadReason.id.in_(reason_ids),
                )
            )
        ).all()
    }
    lead_ids = [lead.id for lead in leads]
    activity_counts = {
        lead_id: int(count)
        for lead_id, count in (
            await db.execute(
                select(LeadActivity.lead_id, func.count(LeadActivity.id))
                .where(
                    LeadActivity.organization_id == organization_id,
                    LeadActivity.lead_id.in_(lead_ids),
                )
                .group_by(LeadActivity.lead_id)
            )
        ).all()
    }
    return [
        LeadView(
            id=lead.id,
            full_name=lead.full_name,
            email=lead.email,
            phone=lead.phone,
            alternate_phone=lead.alternate_phone,
            company_name=lead.company_name,
            source_id=lead.source_id,
            source_name=sources.get(lead.source_id) if lead.source_id else None,
            owner_user_id=lead.owner_user_id,
            owner_name=users.get(lead.owner_user_id) if lead.owner_user_id else None,
            branch_id=lead.branch_id,
            branch_name=branches.get(lead.branch_id) if lead.branch_id else None,
            preferred_location=lead.preferred_location,
            requirements=lead.requirements,
            budget_min=lead.budget_min,
            budget_max=lead.budget_max,
            status=lead.status,
            score=lead.score,
            score_breakdown=lead.score_breakdown,
            qualification_notes=lead.qualification_notes,
            lost_reason_id=lead.lost_reason_id,
            lost_reason_name=reasons.get(lead.lost_reason_id) if lead.lost_reason_id else None,
            lost_notes=lead.lost_notes,
            duplicate_of_lead_id=lead.duplicate_of_lead_id,
            qualified_at=lead.qualified_at,
            converted_at=lead.converted_at,
            last_activity_at=lead.last_activity_at,
            next_follow_up_at=lead.next_follow_up_at,
            metadata_json=lead.metadata_json,
            activity_count=activity_counts.get(lead.id, 0),
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )
        for lead in leads
    ]


async def list_leads(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: LeadStatus | None,
    source_id: str | None,
    owner_user_id: str | None,
    branch_id: str | None,
    min_score: int | None,
    max_score: int | None,
    created_from: datetime | None,
    created_to: datetime | None,
    unattended_days: int | None,
    unassigned_only: bool,
    minimum_age_days: int | None,
    maximum_age_days: int | None,
    include_linked_duplicates: bool,
    page: int,
    page_size: int,
) -> Page[LeadView]:
    filters: list[Any] = [Lead.organization_id == organization_id]
    if not include_linked_duplicates:
        filters.append(Lead.duplicate_of_lead_id.is_(None))
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Lead.full_name.ilike(pattern),
                Lead.email.ilike(pattern),
                Lead.phone.ilike(pattern),
                Lead.company_name.ilike(pattern),
            )
        )
    if status:
        filters.append(Lead.status == status)
    if source_id:
        filters.append(Lead.source_id == source_id)
    if owner_user_id:
        filters.append(Lead.owner_user_id == owner_user_id)
    if branch_id:
        filters.append(Lead.branch_id == branch_id)
    if min_score is not None:
        filters.append(Lead.score >= min_score)
    if max_score is not None:
        filters.append(Lead.score <= max_score)
    if created_from:
        filters.append(Lead.created_at >= _db_datetime(created_from))
    if created_to:
        filters.append(Lead.created_at <= _db_datetime(created_to))
    if unattended_days is not None:
        cutoff = _now() - timedelta(days=unattended_days)
        filters.extend(
            [
                Lead.status.in_(ACTIVE_LEAD_STATUSES),
                or_(Lead.last_activity_at.is_(None), Lead.last_activity_at <= cutoff),
            ]
        )
    if unassigned_only:
        filters.extend([Lead.owner_user_id.is_(None), Lead.status.in_(ACTIVE_LEAD_STATUSES)])
    if minimum_age_days is not None:
        filters.append(Lead.created_at <= _now() - timedelta(days=minimum_age_days))
    if maximum_age_days is not None:
        filters.append(Lead.created_at > _now() - timedelta(days=maximum_age_days + 1))
    if minimum_age_days is not None or maximum_age_days is not None:
        filters.append(Lead.status.in_(ACTIVE_LEAD_STATUSES))
    total = int(await db.scalar(select(func.count()).select_from(Lead).where(*filters)) or 0)
    leads = list(
        (
            await db.scalars(
                select(Lead)
                .where(*filters)
                .order_by(Lead.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return _page(await _lead_views(db, organization_id, leads), total, page, page_size)


async def lead_stats(db: AsyncSession, organization_id: str) -> LeadStats:
    now = _now()
    total, active, unassigned, follow_ups, converted, average = (
        await db.execute(
            select(
                func.count(Lead.id),
                func.sum(Lead.status.in_(ACTIVE_LEAD_STATUSES)),
                func.sum(Lead.owner_user_id.is_(None) & Lead.status.in_(ACTIVE_LEAD_STATUSES)),
                func.sum(
                    Lead.next_follow_up_at.is_not(None)
                    & (Lead.next_follow_up_at <= now)
                    & Lead.status.in_(ACTIVE_LEAD_STATUSES)
                ),
                func.sum(Lead.status == LeadStatus.CONVERTED),
                func.avg(Lead.score),
            ).where(Lead.organization_id == organization_id)
        )
    ).one()
    return LeadStats(
        total=int(total or 0),
        active=int(active or 0),
        unassigned=int(unassigned or 0),
        follow_ups_due=int(follow_ups or 0),
        converted=int(converted or 0),
        average_score=round(float(average or 0), 1),
    )


async def get_lead(db: AsyncSession, organization_id: str, lead_id: str) -> LeadView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def _duplicate_matches(
    db: AsyncSession,
    organization_id: str,
    *,
    email: str | None,
    phone: str | None,
    exclude_lead_id: str | None = None,
) -> list[tuple[Lead, list[str]]]:
    normalized_email = _normalize_email(email)
    normalized_phone = _normalize_phone(phone)
    conditions: list[Any] = []
    if normalized_email:
        conditions.append(Lead.normalized_email == normalized_email)
    if normalized_phone:
        conditions.append(Lead.normalized_phone == normalized_phone)
    if not conditions:
        return []
    filters: list[Any] = [
        Lead.organization_id == organization_id,
        Lead.duplicate_of_lead_id.is_(None),
        or_(*conditions),
    ]
    if exclude_lead_id:
        filters.append(Lead.id != exclude_lead_id)
    leads = list((await db.scalars(select(Lead).where(*filters).limit(100))).all())
    return [
        (
            lead,
            [
                match
                for match, is_match in (
                    ("email", bool(normalized_email and lead.normalized_email == normalized_email)),
                    ("phone", bool(normalized_phone and lead.normalized_phone == normalized_phone)),
                )
                if is_match
            ],
        )
        for lead in leads
    ]


async def check_duplicates(
    db: AsyncSession, organization_id: str, payload: DuplicateCheckPayload
) -> list[DuplicateMatch]:
    matches = await _duplicate_matches(
        db,
        organization_id,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        exclude_lead_id=payload.exclude_lead_id,
    )
    views = {
        view.id: view
        for view in await _lead_views(db, organization_id, [lead for lead, _ in matches])
    }
    return [
        DuplicateMatch(lead=views[lead.id], matched_on=matched_on) for lead, matched_on in matches
    ]


async def create_lead(
    db: AsyncSession,
    organization_id: str,
    payload: LeadCreate,
    context: MutationContext,
) -> LeadView:
    await _validate_lead_references(
        db,
        organization_id,
        source_id=payload.source_id,
        branch_id=payload.branch_id,
    )
    if payload.owner_user_id:
        if not permission_is_granted(context.permissions, "leads.assign"):
            raise AppError(
                status_code=403,
                code="PERMISSION_DENIED",
                message="Lead assignment permission is required",
            )
        await _active_user(db, organization_id, payload.owner_user_id)
    matches = await _duplicate_matches(
        db,
        organization_id,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
    )
    if matches and not payload.duplicate_override:
        raise AppError(
            status_code=409,
            code="POTENTIAL_DUPLICATE",
            message="A lead with the same email or phone already exists",
            details={"lead_ids": [lead.id for lead, _ in matches]},
        )
    if payload.duplicate_override and not permission_is_granted(
        context.permissions, "leads.approve"
    ):
        raise AppError(
            status_code=403,
            code="PERMISSION_DENIED",
            message="Duplicate override approval is required",
        )
    values = payload.model_dump(exclude={"duplicate_override"})
    values["email"] = str(payload.email) if payload.email else None
    lead = Lead(
        organization_id=organization_id,
        normalized_email=_normalize_email(values["email"]),
        normalized_phone=_normalize_phone(payload.phone),
        status=LeadStatus.ASSIGNED if payload.owner_user_id else LeadStatus.NEW,
        **values,
    )
    db.add(lead)
    await db.flush()
    if payload.owner_user_id:
        db.add(
            LeadAssignment(
                organization_id=organization_id,
                lead_id=lead.id,
                assigned_user_id=payload.owner_user_id,
                assigned_by_user_id=context.actor_user_id,
                assigned_at=_now(),
                is_active=True,
                active_lead_key=lead.id,
            )
        )
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.created",
            "lead",
            lead.id,
            None,
            _lead_snapshot(lead),
        )
    )
    await db.commit()
    await db.refresh(lead)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def update_lead(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: LeadUpdate,
    context: MutationContext,
) -> LeadView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    if lead.status == LeadStatus.CONVERTED:
        raise AppError(
            status_code=409,
            code="LEAD_CONVERTED",
            message="Converted leads cannot be edited",
        )
    values = payload.model_dump(exclude_unset=True)
    source_id = values.get("source_id", lead.source_id)
    branch_id = values.get("branch_id", lead.branch_id)
    await _validate_lead_references(
        db,
        organization_id,
        source_id=source_id,
        branch_id=branch_id,
    )
    next_email = (
        str(values.get("email"))
        if values.get("email")
        else (None if "email" in values else lead.email)
    )
    next_phone = values.get("phone", lead.phone)
    if not next_email and not next_phone:
        raise AppError(
            status_code=400,
            code="CONTACT_REQUIRED",
            message="Email or phone is required",
        )
    matches = await _duplicate_matches(
        db,
        organization_id,
        email=next_email,
        phone=next_phone,
        exclude_lead_id=lead.id,
    )
    if matches:
        raise AppError(
            status_code=409,
            code="POTENTIAL_DUPLICATE",
            message="Another lead has the same email or phone",
            details={"lead_ids": [item.id for item, _ in matches]},
        )
    next_min = values.get("budget_min", lead.budget_min)
    next_max = values.get("budget_max", lead.budget_max)
    if next_min is not None and next_max is not None and next_min > next_max:
        raise AppError(
            status_code=400,
            code="INVALID_BUDGET_RANGE",
            message="Minimum budget cannot exceed maximum budget",
        )
    before = _lead_snapshot(lead)
    for field, value in values.items():
        setattr(lead, field, str(value) if field == "email" and value is not None else value)
    lead.normalized_email = _normalize_email(lead.email)
    lead.normalized_phone = _normalize_phone(lead.phone)
    lead.updated_at = _now()
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.updated",
            "lead",
            lead.id,
            before,
            _lead_snapshot(lead),
        )
    )
    await db.commit()
    await db.refresh(lead)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def delete_lead(
    db: AsyncSession, organization_id: str, lead_id: str, context: MutationContext
) -> None:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    if lead.status == LeadStatus.CONVERTED:
        raise AppError(
            status_code=409,
            code="LEAD_CONVERTED",
            message="Converted leads cannot be deleted",
        )
    snapshot = _lead_snapshot(lead)
    await db.execute(
        update(Lead)
        .where(
            Lead.organization_id == organization_id,
            Lead.duplicate_of_lead_id == lead.id,
        )
        .values(duplicate_of_lead_id=None)
    )
    db.add(
        _audit(
            organization_id,
            context,
            "lead.deleted",
            "lead",
            lead.id,
            snapshot,
            None,
        )
    )
    await db.delete(lead)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="RESOURCE_IN_USE",
            message="This lead is referenced by another business record",
        ) from exc


async def _active_user(db: AsyncSession, organization_id: str, user_id: str) -> User:
    user = await _tenant_entity(db, User, organization_id, user_id)
    if not user.is_active:
        raise AppError(
            status_code=400,
            code="ASSIGNEE_INACTIVE",
            message="The selected assignee is inactive",
        )
    return user


async def list_assignees(db: AsyncSession, organization_id: str) -> list[AssigneeView]:
    users = list(
        (
            await db.scalars(
                select(User)
                .where(User.organization_id == organization_id, User.is_active.is_(True))
                .order_by(User.full_name)
            )
        ).all()
    )
    return [
        AssigneeView(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            branch_id=user.branch_id,
        )
        for user in users
    ]


async def assign_lead(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: LeadAssignmentPayload,
    context: MutationContext,
) -> LeadView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    if lead.status == LeadStatus.CONVERTED:
        raise AppError(
            status_code=409,
            code="LEAD_CONVERTED",
            message="Converted leads cannot be reassigned",
        )
    if payload.assigned_user_id:
        await _active_user(db, organization_id, payload.assigned_user_id)
    before = _lead_snapshot(lead)
    await _set_assignment(
        db,
        lead,
        payload.assigned_user_id,
        context.actor_user_id,
    )
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.assigned" if payload.assigned_user_id else "lead.unassigned",
            "lead",
            lead.id,
            before,
            _lead_snapshot(lead),
        )
    )
    await db.commit()
    await db.refresh(lead)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def _set_assignment(
    db: AsyncSession,
    lead: Lead,
    assigned_user_id: str | None,
    actor_user_id: str,
) -> None:
    now = _now()
    await db.execute(
        update(LeadAssignment)
        .where(
            LeadAssignment.organization_id == lead.organization_id,
            LeadAssignment.lead_id == lead.id,
            LeadAssignment.is_active.is_(True),
        )
        .values(is_active=False, active_lead_key=None, unassigned_at=now, updated_at=now)
    )
    lead.owner_user_id = assigned_user_id
    if assigned_user_id:
        if lead.status == LeadStatus.NEW:
            lead.status = LeadStatus.ASSIGNED
        db.add(
            LeadAssignment(
                organization_id=lead.organization_id,
                lead_id=lead.id,
                assigned_user_id=assigned_user_id,
                assigned_by_user_id=actor_user_id,
                assigned_at=now,
                is_active=True,
                active_lead_key=lead.id,
            )
        )
    lead.updated_at = now


async def bulk_assign(
    db: AsyncSession,
    organization_id: str,
    payload: BulkAssignmentPayload,
    context: MutationContext,
) -> list[LeadView]:
    await _active_user(db, organization_id, payload.assigned_user_id)
    leads = list(
        (
            await db.scalars(
                select(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.id.in_(payload.lead_ids),
                )
                .with_for_update()
            )
        ).all()
    )
    if len(leads) != len(payload.lead_ids):
        raise _not_found()
    if any(lead.status == LeadStatus.CONVERTED for lead in leads):
        raise AppError(
            status_code=409,
            code="LEAD_CONVERTED",
            message="Converted leads cannot be reassigned",
        )
    for lead in leads:
        before = _lead_snapshot(lead)
        await _set_assignment(db, lead, payload.assigned_user_id, context.actor_user_id)
        await _recompute_score(db, lead)
        db.add(
            _audit(
                organization_id,
                context,
                "lead.assigned",
                "lead",
                lead.id,
                before,
                _lead_snapshot(lead),
            )
        )
    await db.commit()
    return await _lead_views(db, organization_id, leads)


def _ensure_transition(current: LeadStatus, target: LeadStatus) -> None:
    if target == current:
        return
    if target not in STATUS_TRANSITIONS[current]:
        raise AppError(
            status_code=409,
            code="INVALID_LEAD_TRANSITION",
            message=f"Lead cannot move from {current.value} to {target.value}",
        )


async def transition_status(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: StatusTransitionPayload,
    context: MutationContext,
) -> LeadView:
    if payload.status in {LeadStatus.QUALIFIED, LeadStatus.LOST, LeadStatus.CONVERTED}:
        raise AppError(
            status_code=400,
            code="SPECIALIZED_WORKFLOW_REQUIRED",
            message="Use the qualification, lost, or conversion workflow for this status",
        )
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    _ensure_transition(lead.status, payload.status)
    before = _lead_snapshot(lead)
    previous_status = lead.status
    lead.status = payload.status
    lead.updated_at = _now()
    await _add_status_activity(db, lead, context.actor_user_id, previous_status, payload.notes)
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.status_changed",
            "lead",
            lead.id,
            before,
            _lead_snapshot(lead),
        )
    )
    await db.commit()
    await db.refresh(lead)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def _add_status_activity(
    db: AsyncSession,
    lead: Lead,
    actor_user_id: str,
    previous_status: LeadStatus,
    notes: str | None,
) -> None:
    now = _now()
    db.add(
        LeadActivity(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            performed_by_user_id=actor_user_id,
            activity_type=ActivityType.STATUS_CHANGE,
            subject=f"Status changed from {previous_status.value} to {lead.status.value}",
            notes=notes,
            occurred_at=now,
            completed_at=now,
            is_completed=True,
        )
    )
    lead.last_activity_at = now


async def qualify_lead(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: QualificationPayload,
    context: MutationContext,
) -> LeadView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    _ensure_transition(lead.status, LeadStatus.QUALIFIED)
    before = _lead_snapshot(lead)
    previous_status = lead.status
    lead.status = LeadStatus.QUALIFIED
    lead.qualification_notes = payload.notes
    lead.qualified_at = _now()
    lead.lost_reason_id = None
    lead.lost_notes = None
    lead.updated_at = _now()
    await _add_status_activity(db, lead, context.actor_user_id, previous_status, payload.notes)
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.qualified",
            "lead",
            lead.id,
            before,
            _lead_snapshot(lead),
        )
    )
    await db.commit()
    await db.refresh(lead)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def mark_lead_lost(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: LostLeadPayload,
    context: MutationContext,
) -> LeadView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    _ensure_transition(lead.status, LeadStatus.LOST)
    reason = await _tenant_entity(db, LostLeadReason, organization_id, payload.reason_id)
    if not reason.is_active:
        raise AppError(
            status_code=400,
            code="LOST_REASON_INACTIVE",
            message="The selected lost reason is inactive",
        )
    before = _lead_snapshot(lead)
    previous_status = lead.status
    lead.status = LeadStatus.LOST
    lead.lost_reason_id = reason.id
    lead.lost_notes = payload.notes
    lead.updated_at = _now()
    await _add_status_activity(
        db,
        lead,
        context.actor_user_id,
        previous_status,
        f"{reason.name}: {payload.notes}" if payload.notes else reason.name,
    )
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.lost",
            "lead",
            lead.id,
            before,
            _lead_snapshot(lead),
        )
    )
    await db.commit()
    await db.refresh(lead)
    return (await _lead_views(db, organization_id, [lead]))[0]


async def convert_lead(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: LeadConversionPayload,
    context: MutationContext,
) -> LeadConversionView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    if lead.status != LeadStatus.QUALIFIED:
        raise AppError(
            status_code=409,
            code="LEAD_NOT_QUALIFIED",
            message="Only qualified leads can be converted",
        )
    existing = await db.scalar(
        select(Customer.id).where(
            Customer.organization_id == organization_id,
            Customer.converted_from_lead_id == lead.id,
        )
    )
    if existing:
        raise AppError(
            status_code=409,
            code="LEAD_ALREADY_CONVERTED",
            message="This lead is already linked to a customer",
        )
    full_name = payload.full_name or lead.full_name
    email = str(payload.email) if payload.email else lead.email
    phone = payload.phone or lead.phone
    if not email and not phone:
        raise AppError(
            status_code=400,
            code="CONTACT_REQUIRED",
            message="A customer requires an email or phone",
        )
    customer = Customer(
        organization_id=organization_id,
        converted_from_lead_id=lead.id,
        owner_user_id=lead.owner_user_id,
        branch_id=lead.branch_id,
        full_name=full_name,
        email=email,
        phone=phone,
        alternate_phone=lead.alternate_phone,
        normalized_email=_normalize_email(email),
        normalized_phone=_normalize_phone(phone),
        company_name=lead.company_name,
        preferred_location=lead.preferred_location,
        requirements=lead.requirements,
        budget_min=lead.budget_min,
        budget_max=lead.budget_max,
        status=CustomerStatus.PROSPECT,
    )
    db.add(customer)
    await db.flush()
    before = _lead_snapshot(lead)
    previous_status = lead.status
    lead.status = LeadStatus.CONVERTED
    lead.converted_at = _now()
    lead.updated_at = _now()
    await _add_status_activity(db, lead, context.actor_user_id, previous_status, None)
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead.converted",
            "lead",
            lead.id,
            before,
            {**_lead_snapshot(lead), "customer_id": customer.id},
        )
    )
    await _commit_conflict(
        db,
        "LEAD_ALREADY_CONVERTED",
        "This lead is already linked to a customer",
    )
    await db.refresh(lead)
    return LeadConversionView(
        lead=(await _lead_views(db, organization_id, [lead]))[0],
        customer_id=customer.id,
    )


async def list_activities(
    db: AsyncSession, organization_id: str, lead_id: str
) -> list[LeadActivityView]:
    await _tenant_entity(db, Lead, organization_id, lead_id)
    activities = list(
        (
            await db.scalars(
                select(LeadActivity)
                .where(
                    LeadActivity.organization_id == organization_id,
                    LeadActivity.lead_id == lead_id,
                )
                .order_by(LeadActivity.occurred_at.desc())
            )
        ).all()
    )
    user_ids = {item.performed_by_user_id for item in activities if item.performed_by_user_id}
    users = {
        user.id: user.full_name
        for user in (
            await db.scalars(
                select(User).where(User.organization_id == organization_id, User.id.in_(user_ids))
            )
        ).all()
    }
    return [
        LeadActivityView(
            id=item.id,
            lead_id=item.lead_id,
            performed_by_user_id=item.performed_by_user_id,
            performed_by_name=(
                users.get(item.performed_by_user_id) if item.performed_by_user_id else None
            ),
            activity_type=item.activity_type,
            subject=item.subject,
            notes=item.notes,
            occurred_at=item.occurred_at,
            due_at=item.due_at,
            outcome=item.outcome,
            is_completed=item.is_completed,
            completed_at=item.completed_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in activities
    ]


async def create_activity(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: LeadActivityPayload,
    context: MutationContext,
) -> LeadActivityView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    if lead.status == LeadStatus.CONVERTED and payload.activity_type == ActivityType.FOLLOW_UP:
        raise AppError(
            status_code=409,
            code="LEAD_CONVERTED",
            message="Follow-ups cannot be scheduled for a converted lead",
        )
    occurred_at = _db_datetime(payload.occurred_at)
    due_at = _db_datetime(payload.due_at) if payload.due_at else None
    now = _now()
    activity = LeadActivity(
        organization_id=organization_id,
        lead_id=lead.id,
        performed_by_user_id=context.actor_user_id,
        activity_type=payload.activity_type,
        subject=payload.subject,
        notes=payload.notes,
        occurred_at=occurred_at,
        due_at=due_at,
        outcome=payload.outcome,
        is_completed=payload.is_completed,
        completed_at=now if payload.is_completed else None,
    )
    db.add(activity)
    await db.flush()
    lead.last_activity_at = max(lead.last_activity_at or occurred_at, occurred_at)
    await _refresh_next_follow_up(db, lead)
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead_activity.created",
            "lead",
            lead.id,
            None,
            {"activity_id": activity.id, "type": activity.activity_type.value},
        )
    )
    await db.commit()
    await db.refresh(activity)
    return next(
        item
        for item in await list_activities(db, organization_id, lead.id)
        if item.id == activity.id
    )


async def update_activity(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    activity_id: str,
    payload: LeadActivityPayload,
    context: MutationContext,
) -> LeadActivityView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    activity = await _tenant_entity(db, LeadActivity, organization_id, activity_id, lock=True)
    if activity.lead_id != lead.id:
        raise _not_found()
    before = {
        "subject": activity.subject,
        "type": activity.activity_type.value,
        "due_at": activity.due_at.isoformat() if activity.due_at else None,
        "is_completed": activity.is_completed,
    }
    activity.activity_type = payload.activity_type
    activity.subject = payload.subject
    activity.notes = payload.notes
    activity.occurred_at = _db_datetime(payload.occurred_at)
    activity.due_at = _db_datetime(payload.due_at) if payload.due_at else None
    activity.outcome = payload.outcome
    activity.is_completed = payload.is_completed
    activity.completed_at = _now() if payload.is_completed else None
    activity.updated_at = _now()
    await _refresh_next_follow_up(db, lead)
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead_activity.updated",
            "lead",
            lead.id,
            before,
            {
                "activity_id": activity.id,
                "subject": activity.subject,
                "type": activity.activity_type.value,
                "is_completed": activity.is_completed,
            },
        )
    )
    await db.commit()
    return next(
        item
        for item in await list_activities(db, organization_id, lead.id)
        if item.id == activity.id
    )


async def complete_follow_up(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    activity_id: str,
    payload: CompleteFollowUpPayload,
    context: MutationContext,
) -> LeadActivityView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    activity = await _tenant_entity(db, LeadActivity, organization_id, activity_id, lock=True)
    if activity.lead_id != lead.id or activity.activity_type != ActivityType.FOLLOW_UP:
        raise _not_found()
    if activity.is_completed:
        raise AppError(
            status_code=409,
            code="FOLLOW_UP_COMPLETED",
            message="This follow-up is already complete",
        )
    activity.is_completed = True
    activity.outcome = payload.outcome
    activity.completed_at = _now()
    activity.updated_at = _now()
    lead.last_activity_at = _now()
    await _refresh_next_follow_up(db, lead)
    await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead_follow_up.completed",
            "lead",
            lead.id,
            {"activity_id": activity.id, "is_completed": False},
            {"activity_id": activity.id, "is_completed": True, "outcome": payload.outcome},
        )
    )
    await db.commit()
    return next(
        item
        for item in await list_activities(db, organization_id, lead.id)
        if item.id == activity.id
    )


async def delete_activity(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    activity_id: str,
    context: MutationContext,
) -> None:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    activity = await _tenant_entity(db, LeadActivity, organization_id, activity_id, lock=True)
    if activity.lead_id != lead.id:
        raise _not_found()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_activity.deleted",
            "lead",
            lead.id,
            {"activity_id": activity.id, "subject": activity.subject},
            None,
        )
    )
    await db.delete(activity)
    await db.flush()
    await _refresh_next_follow_up(db, lead)
    await _recompute_score(db, lead)
    await db.commit()


async def _refresh_next_follow_up(db: AsyncSession, lead: Lead) -> None:
    await db.flush()
    lead.next_follow_up_at = await db.scalar(
        select(func.min(LeadActivity.due_at)).where(
            LeadActivity.organization_id == lead.organization_id,
            LeadActivity.lead_id == lead.id,
            LeadActivity.activity_type == ActivityType.FOLLOW_UP,
            LeadActivity.is_completed.is_(False),
            LeadActivity.due_at.is_not(None),
        )
    )
    lead.updated_at = _now()


async def list_notes(db: AsyncSession, organization_id: str, lead_id: str) -> list[LeadNoteView]:
    await _tenant_entity(db, Lead, organization_id, lead_id)
    notes = list(
        (
            await db.scalars(
                select(LeadNote)
                .where(LeadNote.organization_id == organization_id, LeadNote.lead_id == lead_id)
                .order_by(LeadNote.is_pinned.desc(), LeadNote.created_at.desc())
            )
        ).all()
    )
    user_ids = {note.created_by_user_id for note in notes if note.created_by_user_id}
    users = {
        user.id: user.full_name
        for user in (
            await db.scalars(
                select(User).where(User.organization_id == organization_id, User.id.in_(user_ids))
            )
        ).all()
    }
    return [
        LeadNoteView(
            id=note.id,
            lead_id=note.lead_id,
            created_by_user_id=note.created_by_user_id,
            created_by_name=(
                users.get(note.created_by_user_id) if note.created_by_user_id else None
            ),
            body=note.body,
            is_pinned=note.is_pinned,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )
        for note in notes
    ]


async def create_note(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    payload: LeadNotePayload,
    context: MutationContext,
) -> LeadNoteView:
    lead = await _tenant_entity(db, Lead, organization_id, lead_id, lock=True)
    note = LeadNote(
        organization_id=organization_id,
        lead_id=lead.id,
        created_by_user_id=context.actor_user_id,
        **payload.model_dump(),
    )
    db.add(note)
    await db.flush()
    lead.last_activity_at = _now()
    lead.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_note.created",
            "lead",
            lead.id,
            None,
            {"note_id": note.id, "is_pinned": note.is_pinned},
        )
    )
    await db.commit()
    return next(
        item for item in await list_notes(db, organization_id, lead.id) if item.id == note.id
    )


async def update_note(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    note_id: str,
    payload: LeadNotePayload,
    context: MutationContext,
) -> LeadNoteView:
    await _tenant_entity(db, Lead, organization_id, lead_id)
    note = await _tenant_entity(db, LeadNote, organization_id, note_id, lock=True)
    if note.lead_id != lead_id:
        raise _not_found()
    before = {"body": note.body, "is_pinned": note.is_pinned}
    note.body = payload.body
    note.is_pinned = payload.is_pinned
    note.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_note.updated",
            "lead",
            lead_id,
            before,
            {"note_id": note.id, "body": note.body, "is_pinned": note.is_pinned},
        )
    )
    await db.commit()
    return next(
        item for item in await list_notes(db, organization_id, lead_id) if item.id == note.id
    )


async def delete_note(
    db: AsyncSession,
    organization_id: str,
    lead_id: str,
    note_id: str,
    context: MutationContext,
) -> None:
    await _tenant_entity(db, Lead, organization_id, lead_id)
    note = await _tenant_entity(db, LeadNote, organization_id, note_id, lock=True)
    if note.lead_id != lead_id:
        raise _not_found()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_note.deleted",
            "lead",
            lead_id,
            {"note_id": note.id, "body": note.body},
            None,
        )
    )
    await db.delete(note)
    await db.commit()


async def timeline(db: AsyncSession, organization_id: str, lead_id: str) -> list[TimelineItem]:
    await _tenant_entity(db, Lead, organization_id, lead_id)
    users = {
        user.id: user.full_name
        for user in (
            await db.scalars(select(User).where(User.organization_id == organization_id))
        ).all()
    }
    activities = list(
        (
            await db.scalars(
                select(LeadActivity).where(
                    LeadActivity.organization_id == organization_id,
                    LeadActivity.lead_id == lead_id,
                )
            )
        ).all()
    )
    assignments = list(
        (
            await db.scalars(
                select(LeadAssignment).where(
                    LeadAssignment.organization_id == organization_id,
                    LeadAssignment.lead_id == lead_id,
                )
            )
        ).all()
    )
    notes = list(
        (
            await db.scalars(
                select(LeadNote).where(
                    LeadNote.organization_id == organization_id,
                    LeadNote.lead_id == lead_id,
                )
            )
        ).all()
    )
    audits = list(
        (
            await db.scalars(
                select(AuditLog).where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.entity_type == "lead",
                    AuditLog.entity_id == lead_id,
                )
            )
        ).all()
    )
    visits = list(
        (
            await db.scalars(
                select(SiteVisit).where(
                    SiteVisit.organization_id == organization_id,
                    SiteVisit.lead_id == lead_id,
                )
            )
        ).all()
    )
    project_ids = {visit.project_id for visit in visits}
    projects = {
        project.id: project.name
        for project in (
            await db.scalars(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.id.in_(project_ids),
                )
            )
        ).all()
    }
    items = [
        TimelineItem(
            id=activity.id,
            kind="activity",
            title=activity.subject,
            detail=activity.notes or activity.outcome,
            actor_name=(
                users.get(activity.performed_by_user_id) if activity.performed_by_user_id else None
            ),
            occurred_at=activity.occurred_at,
        )
        for activity in activities
    ]
    items.extend(
        TimelineItem(
            id=visit.id,
            kind="site_visit",
            title=f"Site visit · {visit.status.value.replace('_', ' ').title()}",
            detail=projects.get(visit.project_id),
            actor_name=(users.get(visit.assigned_user_id) if visit.assigned_user_id else None),
            occurred_at=visit.scheduled_at,
        )
        for visit in visits
    )
    items.extend(
        TimelineItem(
            id=assignment.id,
            kind="assignment",
            title=f"Assigned to {users.get(assignment.assigned_user_id, 'user')}",
            detail="Active assignment" if assignment.is_active else "Previous assignment",
            actor_name=(
                users.get(assignment.assigned_by_user_id)
                if assignment.assigned_by_user_id
                else None
            ),
            occurred_at=assignment.assigned_at,
        )
        for assignment in assignments
    )
    items.extend(
        TimelineItem(
            id=note.id,
            kind="note",
            title="Pinned note" if note.is_pinned else "Note added",
            detail=note.body,
            actor_name=(users.get(note.created_by_user_id) if note.created_by_user_id else None),
            occurred_at=note.created_at,
        )
        for note in notes
    )
    items.extend(
        TimelineItem(
            id=audit.id,
            kind="audit",
            title=audit.action.replace(".", " ").title(),
            detail=None,
            actor_name=users.get(audit.actor_user_id) if audit.actor_user_id else None,
            occurred_at=audit.created_at,
        )
        for audit in audits
        if audit.action not in {"lead_activity.created", "lead_note.created", "lead.assigned"}
    )
    return sorted(items, key=lambda item: item.occurred_at, reverse=True)[:300]


async def duplicate_groups(db: AsyncSession, organization_id: str) -> list[DuplicateGroup]:
    groups: list[DuplicateGroup] = []
    for field, label in (
        (Lead.normalized_email, "email"),
        (Lead.normalized_phone, "phone"),
    ):
        duplicate_values = list(
            (
                await db.scalars(
                    select(field)
                    .where(
                        Lead.organization_id == organization_id,
                        field.is_not(None),
                        Lead.duplicate_of_lead_id.is_(None),
                    )
                    .group_by(field)
                    .having(func.count(Lead.id) > 1)
                    .limit(50)
                )
            ).all()
        )
        for value in duplicate_values:
            leads = list(
                (
                    await db.scalars(
                        select(Lead)
                        .where(
                            Lead.organization_id == organization_id,
                            field == value,
                            Lead.duplicate_of_lead_id.is_(None),
                        )
                        .order_by(Lead.created_at)
                    )
                ).all()
            )
            groups.append(
                DuplicateGroup(
                    key=str(value),
                    matched_on=label,
                    leads=await _lead_views(db, organization_id, leads),
                )
            )
    return groups


async def resolve_duplicates(
    db: AsyncSession,
    organization_id: str,
    payload: DuplicateResolutionPayload,
    context: MutationContext,
) -> None:
    primary = await _tenant_entity(db, Lead, organization_id, payload.primary_lead_id)
    duplicates = list(
        (
            await db.scalars(
                select(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.id.in_(payload.duplicate_lead_ids),
                )
                .with_for_update()
            )
        ).all()
    )
    if len(duplicates) != len(payload.duplicate_lead_ids):
        raise _not_found()
    primary_keys = {primary.normalized_email, primary.normalized_phone} - {None}
    for duplicate in duplicates:
        duplicate_keys = {duplicate.normalized_email, duplicate.normalized_phone} - {None}
        if not primary_keys.intersection(duplicate_keys):
            raise AppError(
                status_code=400,
                code="NOT_A_DUPLICATE",
                message="Selected leads do not share an email or phone",
            )
        duplicate.duplicate_of_lead_id = primary.id
        duplicate.updated_at = _now()
        db.add(
            _audit(
                organization_id,
                context,
                "lead.duplicate_linked",
                "lead",
                duplicate.id,
                {"duplicate_of_lead_id": None},
                {"duplicate_of_lead_id": primary.id},
            )
        )
    await db.commit()


async def list_score_rules(db: AsyncSession, organization_id: str) -> list[ScoreRuleView]:
    rules = list(
        (
            await db.scalars(
                select(LeadScoreRule)
                .where(LeadScoreRule.organization_id == organization_id)
                .order_by(LeadScoreRule.priority, LeadScoreRule.name)
            )
        ).all()
    )
    return [_score_rule_view(rule) for rule in rules]


def _score_rule_view(rule: LeadScoreRule) -> ScoreRuleView:
    return ScoreRuleView(
        id=rule.id,
        name=rule.name,
        field=rule.field,
        operator=rule.operator,
        comparison_value=rule.comparison_value,
        points=rule.points,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def create_score_rule(
    db: AsyncSession,
    organization_id: str,
    payload: ScoreRulePayload,
    context: MutationContext,
) -> ScoreRuleView:
    rule = LeadScoreRule(organization_id=organization_id, **payload.model_dump())
    db.add(rule)
    await _flush_conflict(db, "SCORE_RULE_EXISTS", "A scoring rule with this name already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "lead_score_rule.created",
            "lead_score_rule",
            rule.id,
            None,
            payload.model_dump(),
        )
    )
    await _commit_conflict(db, "SCORE_RULE_EXISTS", "A scoring rule with this name already exists")
    await db.refresh(rule)
    return _score_rule_view(rule)


async def update_score_rule(
    db: AsyncSession,
    organization_id: str,
    rule_id: str,
    payload: ScoreRulePayload,
    context: MutationContext,
) -> ScoreRuleView:
    rule = await _tenant_entity(db, LeadScoreRule, organization_id, rule_id, lock=True)
    before = {
        "name": rule.name,
        "field": rule.field,
        "operator": rule.operator,
        "comparison_value": rule.comparison_value,
        "points": rule.points,
        "priority": rule.priority,
        "is_active": rule.is_active,
    }
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    rule.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_score_rule.updated",
            "lead_score_rule",
            rule.id,
            before,
            payload.model_dump(),
        )
    )
    await _commit_conflict(db, "SCORE_RULE_EXISTS", "A scoring rule with this name already exists")
    return _score_rule_view(rule)


async def delete_score_rule(
    db: AsyncSession, organization_id: str, rule_id: str, context: MutationContext
) -> None:
    rule = await _tenant_entity(db, LeadScoreRule, organization_id, rule_id, lock=True)
    db.add(
        _audit(
            organization_id,
            context,
            "lead_score_rule.deleted",
            "lead_score_rule",
            rule.id,
            {"name": rule.name},
            None,
        )
    )
    await db.delete(rule)
    await db.commit()


async def recompute_all_scores(
    db: AsyncSession, organization_id: str, context: MutationContext
) -> int:
    leads = list(
        (await db.scalars(select(Lead).where(Lead.organization_id == organization_id))).all()
    )
    for lead in leads:
        await _recompute_score(db, lead)
    db.add(
        _audit(
            organization_id,
            context,
            "lead_scores.recomputed",
            "lead_score_rule",
            organization_id,
            None,
            {"lead_count": len(leads)},
        )
    )
    await db.commit()
    return len(leads)


async def _recompute_score(db: AsyncSession, lead: Lead) -> None:
    activity_count = int(
        await db.scalar(
            select(func.count())
            .select_from(LeadActivity)
            .where(
                LeadActivity.organization_id == lead.organization_id,
                LeadActivity.lead_id == lead.id,
            )
        )
        or 0
    )
    base_items: list[tuple[str, int]] = []
    if lead.email:
        base_items.append(("email provided", 10))
    if lead.phone:
        base_items.append(("phone provided", 15))
    if lead.budget_min is not None or lead.budget_max is not None:
        base_items.append(("budget captured", 10))
    if lead.owner_user_id:
        base_items.append(("assigned", 5))
    if lead.status == LeadStatus.QUALIFIED:
        base_items.append(("qualified", 20))
    if lead.status == LeadStatus.CONVERTED:
        base_items.append(("converted", 30))
    if activity_count:
        base_items.append(("engagement", min(activity_count * 3, 15)))
    rules = list(
        (
            await db.scalars(
                select(LeadScoreRule)
                .where(
                    LeadScoreRule.organization_id == lead.organization_id,
                    LeadScoreRule.is_active.is_(True),
                )
                .order_by(LeadScoreRule.priority)
            )
        ).all()
    )
    source_code = None
    if lead.source_id:
        source_code = await db.scalar(
            select(LeadSource.code).where(
                LeadSource.organization_id == lead.organization_id,
                LeadSource.id == lead.source_id,
            )
        )
    custom_items = [
        (rule.name, rule.points)
        for rule in rules
        if _rule_matches(rule, lead, activity_count, source_code)
    ]
    raw_score = sum(points for _, points in [*base_items, *custom_items])
    lead.score = max(0, min(100, raw_score))
    lead.score_breakdown = {
        "base": [{"label": label, "points": points} for label, points in base_items],
        "rules": [{"label": label, "points": points} for label, points in custom_items],
        "raw_score": raw_score,
    }


def _rule_matches(
    rule: LeadScoreRule,
    lead: Lead,
    activity_count: int,
    source_code: str | None,
) -> bool:
    values: dict[str, Any] = {
        "email_present": bool(lead.email),
        "phone_present": bool(lead.phone),
        "source_code": source_code,
        "budget_min": lead.budget_min,
        "budget_max": lead.budget_max,
        "status": lead.status.value,
        "activity_count": activity_count,
        "days_since_created": max((_now() - _db_datetime(lead.created_at)).days, 0),
        "assigned": bool(lead.owner_user_id),
    }
    value = values.get(rule.field)
    comparison = rule.comparison_value
    if rule.operator == "present":
        return value not in {None, "", False}
    if comparison is None:
        return False
    if isinstance(value, bool):
        target: Any = comparison.lower() in {"true", "1", "yes"}
    elif isinstance(value, (int, Decimal)):
        try:
            target = Decimal(comparison)
        except InvalidOperation:
            return False
    else:
        target = comparison
    if rule.operator == "eq":
        return bool(value == target)
    if rule.operator == "neq":
        return bool(value != target)
    if rule.operator == "contains":
        return str(target).lower() in str(value or "").lower()
    if rule.operator == "gte":
        try:
            return bool(value is not None and value >= target)
        except TypeError:
            return False
    if rule.operator == "lte":
        try:
            return bool(value is not None and value <= target)
        except TypeError:
            return False
    return False


async def preview_import(
    db: AsyncSession, organization_id: str, payload: ImportRequest
) -> ImportPreview:
    results, _ = await _validate_import_rows(db, organization_id, payload.rows)
    return ImportPreview(
        total_rows=len(payload.rows),
        ready_rows=sum(item.status == "ready" for item in results),
        duplicate_rows=sum(item.status == "duplicate" for item in results),
        error_rows=sum(item.status == "error" for item in results),
        rows=results,
    )


async def _validate_import_rows(
    db: AsyncSession, organization_id: str, raw_rows: list[dict[str, Any]]
) -> tuple[list[ImportRowResult], list[ImportLeadRow | None]]:
    results: list[ImportRowResult] = []
    parsed: list[ImportLeadRow | None] = []
    seen_contacts: set[tuple[str | None, str | None]] = set()
    for index, raw in enumerate(raw_rows, start=2):
        try:
            row = ImportLeadRow.model_validate(raw)
        except ValidationError as exc:
            results.append(
                ImportRowResult(
                    row_number=index,
                    status="error",
                    message=exc.errors(include_url=False)[0]["msg"],
                )
            )
            parsed.append(None)
            continue
        normalized = (
            _normalize_email(str(row.email) if row.email else None),
            _normalize_phone(row.phone),
        )
        if normalized in seen_contacts:
            results.append(
                ImportRowResult(
                    row_number=index,
                    status="duplicate",
                    message="Duplicate contact appears earlier in this file",
                )
            )
            parsed.append(row)
            continue
        seen_contacts.add(normalized)
        matches = await _duplicate_matches(
            db,
            organization_id,
            email=str(row.email) if row.email else None,
            phone=row.phone,
        )
        if matches:
            results.append(
                ImportRowResult(
                    row_number=index,
                    status="duplicate",
                    message="Existing lead has the same email or phone",
                    duplicate_lead_ids=[lead.id for lead, _ in matches],
                )
            )
        else:
            results.append(ImportRowResult(row_number=index, status="ready"))
        parsed.append(row)
    return results, parsed


async def commit_import(
    db: AsyncSession,
    organization_id: str,
    payload: ImportRequest,
    context: MutationContext,
) -> ImportBatchView:
    results, parsed = await _validate_import_rows(db, organization_id, payload.rows)
    source_by_code = {
        source.code: source
        for source in (
            await db.scalars(
                select(LeadSource).where(
                    LeadSource.organization_id == organization_id,
                    LeadSource.is_active.is_(True),
                )
            )
        ).all()
    }
    user_by_email = {
        user.email.lower(): user
        for user in (
            await db.scalars(
                select(User).where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                )
            )
        ).all()
    }
    batch = LeadImportBatch(
        organization_id=organization_id,
        created_by_user_id=context.actor_user_id,
        filename=payload.filename,
        status="PROCESSING",
        total_rows=len(payload.rows),
        imported_rows=0,
        skipped_rows=0,
        error_rows=0,
        mapping_json={
            "supported_columns": [
                "full_name",
                "email",
                "phone",
                "source_code",
                "owner_email",
                "preferred_location",
                "budget_min",
                "budget_max",
                "requirements",
            ]
        },
    )
    db.add(batch)
    await db.flush()
    errors: list[dict[str, Any]] = []
    imported = 0
    skipped = 0
    for result, row in zip(results, parsed, strict=True):
        if row is None or result.status == "error":
            errors.append({"row": result.row_number, "message": result.message})
            continue
        if result.status == "duplicate" and payload.skip_duplicates:
            skipped += 1
            continue
        source = source_by_code.get(row.source_code) if row.source_code else None
        owner = user_by_email.get(str(row.owner_email).lower()) if row.owner_email else None
        if row.source_code and source is None:
            errors.append({"row": result.row_number, "message": "Unknown or inactive source code"})
            continue
        if row.owner_email and owner is None:
            errors.append({"row": result.row_number, "message": "Unknown or inactive owner email"})
            continue
        lead = Lead(
            organization_id=organization_id,
            import_batch_id=batch.id,
            full_name=row.full_name,
            email=str(row.email) if row.email else None,
            phone=row.phone,
            normalized_email=_normalize_email(str(row.email) if row.email else None),
            normalized_phone=_normalize_phone(row.phone),
            source_id=source.id if source else None,
            owner_user_id=owner.id if owner else None,
            preferred_location=row.preferred_location,
            budget_min=row.budget_min,
            budget_max=row.budget_max,
            requirements=row.requirements,
            status=LeadStatus.ASSIGNED if owner else LeadStatus.NEW,
        )
        db.add(lead)
        await db.flush()
        if owner:
            db.add(
                LeadAssignment(
                    organization_id=organization_id,
                    lead_id=lead.id,
                    assigned_user_id=owner.id,
                    assigned_by_user_id=context.actor_user_id,
                    assigned_at=_now(),
                    is_active=True,
                    active_lead_key=lead.id,
                )
            )
        await _recompute_score(db, lead)
        db.add(
            _audit(
                organization_id,
                context,
                "lead.imported",
                "lead",
                lead.id,
                None,
                {**_lead_snapshot(lead), "import_batch_id": batch.id},
            )
        )
        imported += 1
    batch.imported_rows = imported
    batch.skipped_rows = skipped
    batch.error_rows = len(errors)
    batch.errors_json = errors
    batch.status = "COMPLETED_WITH_ERRORS" if errors else "COMPLETED"
    batch.completed_at = _now()
    batch.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "lead_import.completed",
            "lead_import_batch",
            batch.id,
            None,
            {
                "filename": batch.filename,
                "total_rows": batch.total_rows,
                "imported_rows": imported,
                "skipped_rows": skipped,
                "error_rows": len(errors),
            },
        )
    )
    await db.commit()
    await db.refresh(batch)
    return _import_batch_view(batch)


def _import_batch_view(batch: LeadImportBatch) -> ImportBatchView:
    return ImportBatchView(
        id=batch.id,
        filename=batch.filename,
        status=batch.status,
        total_rows=batch.total_rows,
        imported_rows=batch.imported_rows,
        skipped_rows=batch.skipped_rows,
        error_rows=batch.error_rows,
        errors=batch.errors_json or [],
        completed_at=batch.completed_at,
        created_at=batch.created_at,
    )


async def list_imports(db: AsyncSession, organization_id: str) -> list[ImportBatchView]:
    batches = list(
        (
            await db.scalars(
                select(LeadImportBatch)
                .where(LeadImportBatch.organization_id == organization_id)
                .order_by(LeadImportBatch.created_at.desc())
                .limit(50)
            )
        ).all()
    )
    return [_import_batch_view(batch) for batch in batches]


async def kanban(db: AsyncSession, organization_id: str) -> list[KanbanColumn]:
    columns: list[KanbanColumn] = []
    for status in LeadStatus:
        total = int(
            await db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.status == status,
                    Lead.duplicate_of_lead_id.is_(None),
                )
            )
            or 0
        )
        leads = list(
            (
                await db.scalars(
                    select(Lead)
                    .where(
                        Lead.organization_id == organization_id,
                        Lead.status == status,
                        Lead.duplicate_of_lead_id.is_(None),
                    )
                    .order_by(Lead.score.desc(), Lead.updated_at.desc())
                    .limit(50)
                )
            ).all()
        )
        columns.append(
            KanbanColumn(
                status=status,
                total=total,
                items=await _lead_views(db, organization_id, leads),
            )
        )
    return columns


async def ageing_buckets(db: AsyncSession, organization_id: str) -> list[AgeingBucket]:
    definitions = (
        ("0-7 days", 0, 7),
        ("8-14 days", 8, 14),
        ("15-30 days", 15, 30),
        ("31-60 days", 31, 60),
        ("61+ days", 61, None),
    )
    now = _now()
    buckets: list[AgeingBucket] = []
    for label, minimum, maximum in definitions:
        filters: list[Any] = [
            Lead.organization_id == organization_id,
            Lead.status.in_(ACTIVE_LEAD_STATUSES),
            Lead.duplicate_of_lead_id.is_(None),
            Lead.created_at <= now - timedelta(days=minimum),
        ]
        if maximum is not None:
            filters.append(Lead.created_at > now - timedelta(days=maximum + 1))
        count = int(await db.scalar(select(func.count()).select_from(Lead).where(*filters)) or 0)
        buckets.append(
            AgeingBucket(
                label=label,
                minimum_days=minimum,
                maximum_days=maximum,
                count=count,
            )
        )
    return buckets
