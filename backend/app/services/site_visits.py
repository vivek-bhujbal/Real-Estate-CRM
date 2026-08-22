from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Customer,
    CustomerActivity,
    Floor,
    Lead,
    LeadActivity,
    Project,
    SiteVisit,
    SiteVisitUnit,
    Tower,
    Unit,
    User,
)
from app.models.enums import ActivityType, NotificationEventType, VisitStatus
from app.schemas.organization import Page
from app.schemas.site_visits import (
    CheckInPayload,
    CheckOutPayload,
    InterestedUnitView,
    SalespersonOption,
    SiteVisitCreate,
    SiteVisitStats,
    SiteVisitUpdate,
    SiteVisitView,
    VisitStatusPayload,
)
from app.services.notifications import queue_in_app
from app.services.organization import MutationContext


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _optional_as_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested site visit was not found",
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
    visit_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type="site_visit",
        entity_id=visit_id,
        previous_value=before,
        new_value=after,
        request_id=context.request_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
        created_at=_now(),
    )


def _snapshot(item: SiteVisit) -> dict[str, Any]:
    return {
        "lead_id": item.lead_id,
        "customer_id": item.customer_id,
        "project_id": item.project_id,
        "assigned_user_id": item.assigned_user_id,
        "scheduled_at": item.scheduled_at.isoformat(),
        "status": item.status.value,
        "check_in_at": item.check_in_at.isoformat() if item.check_in_at else None,
        "check_out_at": item.check_out_at.isoformat() if item.check_out_at else None,
        "outcome": item.outcome,
        "next_follow_up_at": (
            item.next_follow_up_at.isoformat() if item.next_follow_up_at else None
        ),
    }


async def _validate_contact_project_units(
    db: AsyncSession,
    organization_id: str,
    lead_id: str | None,
    customer_id: str | None,
    project_id: str,
    unit_ids: list[str],
) -> None:
    if not lead_id and not customer_id:
        raise AppError(
            status_code=400, code="CONTACT_REQUIRED", message="A lead or customer is required"
        )
    if lead_id:
        await _entity(db, Lead, organization_id, lead_id)
    if customer_id:
        await _entity(db, Customer, organization_id, customer_id)
    await _entity(db, Project, organization_id, project_id)
    if not unit_ids:
        return
    units = list(
        (
            await db.scalars(
                select(Unit).where(
                    Unit.organization_id == organization_id,
                    Unit.id.in_(unit_ids),
                )
            )
        ).all()
    )
    if len(units) != len(unit_ids) or any(item.project_id != project_id for item in units):
        raise AppError(
            status_code=400,
            code="INVALID_INTERESTED_UNITS",
            message="Every interested unit must belong to the selected project",
        )


async def _validate_assignee(
    db: AsyncSession,
    organization_id: str,
    user_id: str,
) -> User:
    user = await _entity(db, User, organization_id, user_id)
    if not user.is_active:
        raise AppError(
            status_code=400,
            code="INACTIVE_ASSIGNEE",
            message="Assigned salesperson must be active",
        )
    return user


async def _replace_units(
    db: AsyncSession,
    organization_id: str,
    visit: SiteVisit,
    unit_ids: list[str],
) -> None:
    await db.execute(
        delete(SiteVisitUnit).where(
            SiteVisitUnit.organization_id == organization_id,
            SiteVisitUnit.site_visit_id == visit.id,
        )
    )
    for sequence, unit_id in enumerate(unit_ids, start=1):
        db.add(
            SiteVisitUnit(
                organization_id=organization_id,
                site_visit_id=visit.id,
                unit_id=unit_id,
                sequence=sequence,
            )
        )
    visit.unit_id = unit_ids[0] if unit_ids else None


async def _views(
    db: AsyncSession, organization_id: str, visits: list[SiteVisit]
) -> list[SiteVisitView]:
    if not visits:
        return []
    visit_ids = [item.id for item in visits]
    lead_ids = {item.lead_id for item in visits if item.lead_id}
    customer_ids = {item.customer_id for item in visits if item.customer_id}
    project_ids = {item.project_id for item in visits}
    user_ids = {
        value
        for item in visits
        for value in (item.assigned_user_id, item.created_by_user_id)
        if value
    }
    leads = {
        item.id: item.full_name
        for item in (
            await db.scalars(
                select(Lead).where(Lead.organization_id == organization_id, Lead.id.in_(lead_ids))
            )
        ).all()
    }
    customers = {
        item.id: item.full_name
        for item in (
            await db.scalars(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.id.in_(customer_ids),
                )
            )
        ).all()
    }
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
    users = {
        item.id: item.full_name
        for item in (
            await db.scalars(
                select(User).where(User.organization_id == organization_id, User.id.in_(user_ids))
            )
        ).all()
    }
    rows = (
        await db.execute(
            select(SiteVisitUnit, Unit, Tower.name, Floor.name)
            .join(
                Unit,
                (Unit.organization_id == SiteVisitUnit.organization_id)
                & (Unit.id == SiteVisitUnit.unit_id),
            )
            .outerjoin(
                Tower,
                (Tower.organization_id == Unit.organization_id) & (Tower.id == Unit.tower_id),
            )
            .outerjoin(
                Floor,
                (Floor.organization_id == Unit.organization_id) & (Floor.id == Unit.floor_id),
            )
            .where(
                SiteVisitUnit.organization_id == organization_id,
                SiteVisitUnit.site_visit_id.in_(visit_ids),
            )
            .order_by(SiteVisitUnit.sequence)
        )
    ).all()
    units: dict[str, list[InterestedUnitView]] = {visit_id: [] for visit_id in visit_ids}
    for relation, unit, tower_name, floor_name in rows:
        units[relation.site_visit_id].append(
            InterestedUnitView(
                id=unit.id,
                unit_number=unit.unit_number,
                unit_type=unit.unit_type,
                status=unit.status.value,
                tower_name=tower_name,
                floor_name=floor_name,
            )
        )
    legacy_units = {item.id: item.unit_id for item in visits if item.unit_id and not units[item.id]}
    if legacy_units:
        legacy_rows = (
            await db.execute(
                select(Unit, Tower.name, Floor.name)
                .outerjoin(
                    Tower,
                    (Tower.organization_id == Unit.organization_id) & (Tower.id == Unit.tower_id),
                )
                .outerjoin(
                    Floor,
                    (Floor.organization_id == Unit.organization_id) & (Floor.id == Unit.floor_id),
                )
                .where(
                    Unit.organization_id == organization_id,
                    Unit.id.in_(legacy_units.values()),
                )
            )
        ).all()
        legacy_views = {
            unit.id: InterestedUnitView(
                id=unit.id,
                unit_number=unit.unit_number,
                unit_type=unit.unit_type,
                status=unit.status.value,
                tower_name=tower_name,
                floor_name=floor_name,
            )
            for unit, tower_name, floor_name in legacy_rows
        }
        for visit_id, unit_id in legacy_units.items():
            if unit_id in legacy_views:
                units[visit_id].append(legacy_views[unit_id])
    return [
        SiteVisitView(
            id=item.id,
            lead_id=item.lead_id,
            lead_name=leads.get(item.lead_id) if item.lead_id else None,
            customer_id=item.customer_id,
            customer_name=customers.get(item.customer_id) if item.customer_id else None,
            project_id=item.project_id,
            project_name=projects[item.project_id],
            interested_units=units[item.id],
            assigned_user_id=item.assigned_user_id,
            assigned_user_name=(
                users.get(item.assigned_user_id) if item.assigned_user_id else None
            ),
            created_by_user_id=item.created_by_user_id,
            created_by_user_name=(
                users.get(item.created_by_user_id) if item.created_by_user_id else None
            ),
            scheduled_at=_as_utc(item.scheduled_at),
            check_in_at=_optional_as_utc(item.check_in_at),
            check_out_at=_optional_as_utc(item.check_out_at),
            completed_at=_optional_as_utc(item.completed_at),
            status=item.status,
            attendees=item.attendees or [],
            notes=item.notes,
            feedback=item.feedback,
            outcome=item.outcome,
            next_follow_up_at=_optional_as_utc(item.next_follow_up_at),
            created_at=_as_utc(item.created_at),
            updated_at=_as_utc(item.updated_at),
        )
        for item in visits
    ]


async def list_visits(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: VisitStatus | None,
    project_id: str | None,
    assigned_user_id: str | None,
    lead_id: str | None,
    customer_id: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    page: int,
    page_size: int,
) -> Page[SiteVisitView]:
    if date_from and date_to and _naive_utc(date_to) < _naive_utc(date_from):
        raise AppError(
            status_code=400,
            code="INVALID_DATE_RANGE",
            message="Date to must be on or after date from",
        )
    conditions: list[Any] = [SiteVisit.organization_id == organization_id]
    if status:
        conditions.append(SiteVisit.status == status)
    if project_id:
        conditions.append(SiteVisit.project_id == project_id)
    if assigned_user_id:
        conditions.append(SiteVisit.assigned_user_id == assigned_user_id)
    if lead_id:
        conditions.append(SiteVisit.lead_id == lead_id)
    if customer_id:
        conditions.append(SiteVisit.customer_id == customer_id)
    if date_from:
        conditions.append(SiteVisit.scheduled_at >= _naive_utc(date_from))
    if date_to:
        conditions.append(SiteVisit.scheduled_at <= _naive_utc(date_to))
    statement = (
        select(SiteVisit)
        .outerjoin(
            Lead,
            (Lead.organization_id == SiteVisit.organization_id) & (Lead.id == SiteVisit.lead_id),
        )
        .outerjoin(
            Customer,
            (Customer.organization_id == SiteVisit.organization_id)
            & (Customer.id == SiteVisit.customer_id),
        )
        .join(
            Project,
            (Project.organization_id == SiteVisit.organization_id)
            & (Project.id == SiteVisit.project_id),
        )
        .where(*conditions)
    )
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Lead.full_name.ilike(pattern),
                Customer.full_name.ilike(pattern),
                Project.name.ilike(pattern),
                SiteVisit.outcome.ilike(pattern),
            )
        )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    visits = list(
        (
            await db.scalars(
                statement.order_by(SiteVisit.scheduled_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=await _views(db, organization_id, visits),
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def get_visit(db: AsyncSession, organization_id: str, visit_id: str) -> SiteVisitView:
    visit = await _entity(db, SiteVisit, organization_id, visit_id)
    return (await _views(db, organization_id, [visit]))[0]


async def create_visit(
    db: AsyncSession,
    organization_id: str,
    payload: SiteVisitCreate,
    context: MutationContext,
) -> SiteVisitView:
    scheduled_at = _naive_utc(payload.scheduled_at)
    if scheduled_at <= _now():
        raise AppError(
            status_code=400,
            code="INVALID_SCHEDULE",
            message="Visit date and time must be in the future",
        )
    assignee_id = payload.assigned_user_id or context.actor_user_id
    if assignee_id != context.actor_user_id and not permission_is_granted(
        context.permissions, "visits.assign"
    ):
        raise AppError(
            status_code=403,
            code="PERMISSION_DENIED",
            message="Visit assignment permission is required",
        )
    await _validate_assignee(db, organization_id, assignee_id)
    await _validate_contact_project_units(
        db,
        organization_id,
        payload.lead_id,
        payload.customer_id,
        payload.project_id,
        payload.interested_unit_ids,
    )
    visit = SiteVisit(
        organization_id=organization_id,
        lead_id=payload.lead_id,
        customer_id=payload.customer_id,
        project_id=payload.project_id,
        unit_id=payload.interested_unit_ids[0] if payload.interested_unit_ids else None,
        assigned_user_id=assignee_id,
        created_by_user_id=context.actor_user_id,
        scheduled_at=scheduled_at,
        status=VisitStatus.SCHEDULED,
        attendees=payload.attendees or None,
        notes=payload.notes,
    )
    db.add(visit)
    await db.flush()
    await _replace_units(db, organization_id, visit, payload.interested_unit_ids)
    db.add(_audit(organization_id, context, "site_visit.created", visit.id, None, _snapshot(visit)))
    if visit.assigned_user_id:
        queue_in_app(
            db,
            organization_id=organization_id,
            recipient_user_ids=[visit.assigned_user_id],
            event_type=NotificationEventType.SITE_VISIT_SCHEDULED,
            title="Site visit scheduled",
            body=f"Visit scheduled for {visit.scheduled_at.isoformat()}",
            related_entity_type="site_visit",
            related_entity_id=visit.id,
            action_url=f"/site-visits/{visit.id}",
            data={"scheduled_at": visit.scheduled_at.isoformat(), "project_id": visit.project_id},
        )
    await db.commit()
    await db.refresh(visit)
    return (await _views(db, organization_id, [visit]))[0]


async def update_visit(
    db: AsyncSession,
    organization_id: str,
    visit_id: str,
    payload: SiteVisitUpdate,
    context: MutationContext,
) -> SiteVisitView:
    visit = await _entity(db, SiteVisit, organization_id, visit_id, lock=True)
    if visit.status not in {VisitStatus.SCHEDULED, VisitStatus.CONFIRMED}:
        raise AppError(
            status_code=409,
            code="VISIT_NOT_EDITABLE",
            message="This visit can no longer be edited",
        )
    changes = payload.model_dump(exclude_unset=True)
    lead_id = changes.get("lead_id", visit.lead_id)
    customer_id = changes.get("customer_id", visit.customer_id)
    project_id = changes.get("project_id", visit.project_id)
    unit_ids = changes.pop("interested_unit_ids", None)
    if unit_ids is None:
        unit_ids = list(
            (
                await db.scalars(
                    select(SiteVisitUnit.unit_id)
                    .where(
                        SiteVisitUnit.organization_id == organization_id,
                        SiteVisitUnit.site_visit_id == visit.id,
                    )
                    .order_by(SiteVisitUnit.sequence)
                )
            ).all()
        )
    await _validate_contact_project_units(
        db, organization_id, lead_id, customer_id, project_id, unit_ids
    )
    if "assigned_user_id" in changes:
        assigned_user_id = changes["assigned_user_id"] or context.actor_user_id
        if assigned_user_id != visit.assigned_user_id and not permission_is_granted(
            context.permissions, "visits.assign"
        ):
            raise AppError(
                status_code=403,
                code="PERMISSION_DENIED",
                message="Visit assignment permission is required",
            )
        await _validate_assignee(db, organization_id, assigned_user_id)
        changes["assigned_user_id"] = assigned_user_id
    if "scheduled_at" in changes:
        if changes["scheduled_at"] is None:
            raise AppError(
                status_code=400,
                code="INVALID_SCHEDULE",
                message="Visit date and time is required",
            )
        changes["scheduled_at"] = _naive_utc(changes["scheduled_at"])
        if changes["scheduled_at"] <= _now():
            raise AppError(
                status_code=400,
                code="INVALID_SCHEDULE",
                message="Visit date and time must be in the future",
            )
    before = _snapshot(visit)
    for field, value in changes.items():
        setattr(visit, field, value)
    await _replace_units(db, organization_id, visit, unit_ids)
    db.add(
        _audit(organization_id, context, "site_visit.updated", visit.id, before, _snapshot(visit))
    )
    if visit.assigned_user_id:
        queue_in_app(
            db,
            organization_id=organization_id,
            recipient_user_ids=[visit.assigned_user_id],
            event_type=NotificationEventType.SITE_VISIT_UPDATED,
            title="Site visit updated",
            body=f"Visit is scheduled for {visit.scheduled_at.isoformat()}",
            related_entity_type="site_visit",
            related_entity_id=visit.id,
            action_url=f"/site-visits/{visit.id}",
            data={"scheduled_at": visit.scheduled_at.isoformat(), "status": visit.status.value},
        )
    await db.commit()
    await db.refresh(visit)
    return (await _views(db, organization_id, [visit]))[0]


async def change_status(
    db: AsyncSession,
    organization_id: str,
    visit_id: str,
    payload: VisitStatusPayload,
    context: MutationContext,
) -> SiteVisitView:
    visit = await _entity(db, SiteVisit, organization_id, visit_id, lock=True)
    target = VisitStatus(payload.status)
    allowed = {
        VisitStatus.SCHEDULED: {
            VisitStatus.CONFIRMED,
            VisitStatus.CANCELLED,
            VisitStatus.NO_SHOW,
        },
        VisitStatus.CONFIRMED: {VisitStatus.CANCELLED, VisitStatus.NO_SHOW},
    }
    if target not in allowed.get(visit.status, set()):
        raise AppError(
            status_code=409,
            code="INVALID_VISIT_TRANSITION",
            message=f"Cannot move visit from {visit.status.value} to {target.value}",
        )
    if target == VisitStatus.NO_SHOW and visit.scheduled_at > _now():
        raise AppError(
            status_code=409,
            code="VISIT_NOT_DUE",
            message="A future visit cannot be marked no-show",
        )
    before = _snapshot(visit)
    visit.status = target
    if target == VisitStatus.CANCELLED and payload.reason:
        visit.notes = (
            f"{visit.notes}\n\nCancellation: {payload.reason}" if visit.notes else payload.reason
        )
    db.add(
        _audit(
            organization_id,
            context,
            "site_visit.status.changed",
            visit.id,
            before,
            _snapshot(visit),
        )
    )
    await db.commit()
    await db.refresh(visit)
    return (await _views(db, organization_id, [visit]))[0]


async def check_in(
    db: AsyncSession,
    organization_id: str,
    visit_id: str,
    payload: CheckInPayload,
    context: MutationContext,
) -> SiteVisitView:
    visit = await _entity(db, SiteVisit, organization_id, visit_id, lock=True)
    if visit.status not in {VisitStatus.SCHEDULED, VisitStatus.CONFIRMED}:
        raise AppError(
            status_code=409,
            code="INVALID_VISIT_TRANSITION",
            message="Only an upcoming visit can check in",
        )
    before = _snapshot(visit)
    visit.status = VisitStatus.CHECKED_IN
    visit.check_in_at = _now()
    if payload.attendees is not None:
        visit.attendees = payload.attendees or None
    db.add(
        _audit(
            organization_id,
            context,
            "site_visit.checked_in",
            visit.id,
            before,
            _snapshot(visit),
        )
    )
    await db.commit()
    await db.refresh(visit)
    return (await _views(db, organization_id, [visit]))[0]


async def check_out(
    db: AsyncSession,
    organization_id: str,
    visit_id: str,
    payload: CheckOutPayload,
    context: MutationContext,
) -> SiteVisitView:
    visit = await _entity(db, SiteVisit, organization_id, visit_id, lock=True)
    if visit.status != VisitStatus.CHECKED_IN:
        raise AppError(
            status_code=409,
            code="INVALID_VISIT_TRANSITION",
            message="Visit must be checked in first",
        )
    follow_up = _naive_utc(payload.next_follow_up_at) if payload.next_follow_up_at else None
    if follow_up and follow_up <= _now():
        raise AppError(
            status_code=400,
            code="INVALID_FOLLOW_UP",
            message="Next follow-up must be in the future",
        )
    before = _snapshot(visit)
    occurred_at = _now()
    visit.status = VisitStatus.COMPLETED
    visit.check_out_at = occurred_at
    visit.completed_at = occurred_at
    visit.feedback = payload.feedback
    visit.outcome = payload.outcome
    visit.next_follow_up_at = follow_up
    if visit.lead_id:
        lead = await _entity(db, Lead, organization_id, visit.lead_id, lock=True)
        lead.last_activity_at = occurred_at
        lead.next_follow_up_at = follow_up
        db.add(
            LeadActivity(
                organization_id=organization_id,
                lead_id=lead.id,
                performed_by_user_id=context.actor_user_id,
                activity_type=ActivityType.MEETING,
                subject="Site visit completed",
                notes=payload.feedback,
                occurred_at=occurred_at,
                completed_at=occurred_at,
                outcome=payload.outcome,
                is_completed=True,
            )
        )
        if follow_up:
            db.add(
                LeadActivity(
                    organization_id=organization_id,
                    lead_id=lead.id,
                    performed_by_user_id=context.actor_user_id,
                    activity_type=ActivityType.FOLLOW_UP,
                    subject="Site visit follow-up",
                    occurred_at=occurred_at,
                    due_at=follow_up,
                    is_completed=False,
                )
            )
    if visit.customer_id:
        db.add(
            CustomerActivity(
                organization_id=organization_id,
                customer_id=visit.customer_id,
                performed_by_user_id=context.actor_user_id,
                activity_type=ActivityType.MEETING,
                subject="Site visit completed",
                notes=payload.feedback or payload.outcome,
                channel="IN_PERSON",
                direction="OUTBOUND",
                occurred_at=occurred_at,
            )
        )
    db.add(
        _audit(
            organization_id,
            context,
            "site_visit.checked_out",
            visit.id,
            before,
            _snapshot(visit),
        )
    )
    await db.commit()
    await db.refresh(visit)
    return (await _views(db, organization_id, [visit]))[0]


async def delete_visit(
    db: AsyncSession,
    organization_id: str,
    visit_id: str,
    context: MutationContext,
) -> None:
    visit = await _entity(db, SiteVisit, organization_id, visit_id, lock=True)
    if visit.status not in {VisitStatus.SCHEDULED, VisitStatus.CANCELLED}:
        raise AppError(
            status_code=409,
            code="VISIT_NOT_DELETABLE",
            message="Only scheduled or cancelled visits can be deleted",
        )
    db.add(_audit(organization_id, context, "site_visit.deleted", visit.id, _snapshot(visit), None))
    await db.delete(visit)
    await db.commit()


async def stats(db: AsyncSession, organization_id: str) -> SiteVisitStats:
    now = _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    rows = (
        await db.execute(
            select(SiteVisit.status, func.count(SiteVisit.id))
            .where(SiteVisit.organization_id == organization_id)
            .group_by(SiteVisit.status)
        )
    ).all()
    counts: dict[VisitStatus, int] = {status: count for status, count in rows}
    total = sum(counts.values())
    upcoming = (
        await db.scalar(
            select(func.count(SiteVisit.id)).where(
                SiteVisit.organization_id == organization_id,
                SiteVisit.scheduled_at >= now,
                SiteVisit.status.in_([VisitStatus.SCHEDULED, VisitStatus.CONFIRMED]),
            )
        )
        or 0
    )
    today_count = (
        await db.scalar(
            select(func.count(SiteVisit.id)).where(
                SiteVisit.organization_id == organization_id,
                SiteVisit.scheduled_at >= today,
                SiteVisit.scheduled_at < tomorrow,
            )
        )
        or 0
    )
    return SiteVisitStats(
        total=total,
        upcoming=upcoming,
        today=today_count,
        checked_in=counts.get(VisitStatus.CHECKED_IN, 0),
        completed=counts.get(VisitStatus.COMPLETED, 0),
    )


async def salesperson_options(db: AsyncSession, organization_id: str) -> list[SalespersonOption]:
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
        SalespersonOption(id=item.id, full_name=item.full_name, email=item.email) for item in users
    ]


async def calendar_visits(
    db: AsyncSession,
    organization_id: str,
    date_from: datetime,
    date_to: datetime,
    assigned_user_id: str | None,
) -> list[SiteVisitView]:
    start = _naive_utc(date_from)
    end = _naive_utc(date_to)
    if end < start or end - start > timedelta(days=370):
        raise AppError(
            status_code=400,
            code="INVALID_DATE_RANGE",
            message="Calendar range must be ordered and no longer than 370 days",
        )
    conditions: list[Any] = [
        SiteVisit.organization_id == organization_id,
        SiteVisit.scheduled_at >= start,
        SiteVisit.scheduled_at <= end,
    ]
    if assigned_user_id:
        conditions.append(SiteVisit.assigned_user_id == assigned_user_id)
    visits = list(
        (
            await db.scalars(select(SiteVisit).where(*conditions).order_by(SiteVisit.scheduled_at))
        ).all()
    )
    return await _views(db, organization_id, visits)
