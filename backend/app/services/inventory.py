from datetime import UTC, datetime
from math import ceil
from typing import Any

from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Booking,
    Customer,
    Floor,
    Lead,
    Project,
    Quotation,
    Tower,
    Unit,
    UnitHold,
    User,
)
from app.models.enums import (
    BookingStatus,
    HoldStatus,
    HoldType,
    NotificationEventType,
    ProjectStatus,
    UnitStatus,
)
from app.schemas.inventory import (
    BookingInitiate,
    FloorCreate,
    FloorUpdate,
    FloorView,
    HoldApprovalDecision,
    HoldSalespersonOption,
    HoldStats,
    InventoryBookingView,
    InventoryStats,
    ProjectCreate,
    ProjectUpdate,
    ProjectView,
    TowerCreate,
    TowerUpdate,
    TowerView,
    UnitCreate,
    UnitHoldCreate,
    UnitHoldView,
    UnitUpdate,
    UnitView,
)
from app.schemas.organization import Page
from app.services.notifications import queue_in_app
from app.services.organization import MutationContext

RESERVING_HOLD_STATUSES = (HoldStatus.PENDING_APPROVAL, HoldStatus.ACTIVE)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested resource was not found",
    )


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


def _system_audit(
    organization_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    previous_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=previous_value,
        new_value=new_value,
        request_id=None,
        ip_address=None,
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
    entity = (await db.scalars(statement)).first()
    if entity is None:
        raise _not_found()
    return entity


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


def _project_snapshot(item: Project) -> dict[str, Any]:
    return {
        "name": item.name,
        "code": item.code,
        "status": item.status.value,
        "project_type": item.project_type,
        "default_currency": item.default_currency,
        "rera_number": item.rera_number,
    }


def _unit_snapshot(item: Unit) -> dict[str, Any]:
    return {
        "project_id": item.project_id,
        "tower_id": item.tower_id,
        "floor_id": item.floor_id,
        "unit_number": item.unit_number,
        "unit_type": item.unit_type,
        "area_sqft": str(item.area_sqft) if item.area_sqft is not None else None,
        "base_price": str(item.base_price) if item.base_price is not None else None,
        "currency": item.currency,
        "status": item.status.value,
    }


async def _project_views(
    db: AsyncSession, organization_id: str, projects: list[Project]
) -> list[ProjectView]:
    if not projects:
        return []
    await expire_due_holds(db, organization_id=organization_id)
    ids = [item.id for item in projects]
    tower_counts: dict[str, int] = {
        project_id: count
        for project_id, count in (
            await db.execute(
                select(Tower.project_id, func.count(Tower.id))
                .where(Tower.organization_id == organization_id, Tower.project_id.in_(ids))
                .group_by(Tower.project_id)
            )
        ).all()
    }
    unit_counts: dict[str, int] = {
        project_id: count
        for project_id, count in (
            await db.execute(
                select(Unit.project_id, func.count(Unit.id))
                .where(Unit.organization_id == organization_id, Unit.project_id.in_(ids))
                .group_by(Unit.project_id)
            )
        ).all()
    }
    available_counts: dict[str, int] = {
        project_id: count
        for project_id, count in (
            await db.execute(
                select(Unit.project_id, func.count(Unit.id))
                .where(
                    Unit.organization_id == organization_id,
                    Unit.project_id.in_(ids),
                    Unit.status == UnitStatus.AVAILABLE,
                    ~exists(
                        select(UnitHold.id).where(
                            UnitHold.organization_id == organization_id,
                            UnitHold.unit_id == Unit.id,
                            UnitHold.status.in_(RESERVING_HOLD_STATUSES),
                            UnitHold.expires_at > _now(),
                        )
                    ),
                )
                .group_by(Unit.project_id)
            )
        ).all()
    }
    return [
        ProjectView(
            id=item.id,
            name=item.name,
            code=item.code,
            description=item.description,
            project_type=item.project_type,
            address_line1=item.address_line1,
            address_line2=item.address_line2,
            city=item.city,
            state=item.state,
            postal_code=item.postal_code,
            country=item.country,
            rera_number=item.rera_number,
            launch_date=item.launch_date,
            expected_possession_date=item.expected_possession_date,
            default_currency=item.default_currency,
            amenities=item.amenities,
            configuration=item.configuration,
            status=item.status,
            tower_count=tower_counts.get(item.id, 0),
            unit_count=unit_counts.get(item.id, 0),
            available_unit_count=available_counts.get(item.id, 0),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in projects
    ]


async def list_projects(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: ProjectStatus | None,
    page: int,
    page_size: int,
) -> Page[ProjectView]:
    filters = [Project.organization_id == organization_id]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(Project.name.ilike(term), Project.code.ilike(term), Project.city.ilike(term))
        )
    if status:
        filters.append(Project.status == status)
    total = int(await db.scalar(select(func.count(Project.id)).where(*filters)) or 0)
    records = list(
        (
            await db.scalars(
                select(Project)
                .where(*filters)
                .order_by(Project.updated_at.desc(), Project.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=await _project_views(db, organization_id, records),
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def create_project(
    db: AsyncSession,
    organization_id: str,
    payload: ProjectCreate,
    context: MutationContext,
) -> ProjectView:
    project = Project(organization_id=organization_id, **payload.model_dump())
    db.add(project)
    await _flush_conflict(db, "DUPLICATE_PROJECT_CODE", "Project code already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "project.created",
            "project",
            project.id,
            None,
            _project_snapshot(project),
        )
    )
    await _commit_conflict(db, "DUPLICATE_PROJECT_CODE", "Project code already exists")
    await db.refresh(project)
    return (await _project_views(db, organization_id, [project]))[0]


async def get_project(db: AsyncSession, organization_id: str, project_id: str) -> ProjectView:
    project = await _entity(db, Project, organization_id, project_id)
    return (await _project_views(db, organization_id, [project]))[0]


async def update_project(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    payload: ProjectUpdate,
    context: MutationContext,
) -> ProjectView:
    project = await _entity(db, Project, organization_id, project_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    launch = changes.get("launch_date", project.launch_date)
    possession = changes.get("expected_possession_date", project.expected_possession_date)
    if launch and possession and possession < launch:
        raise AppError(
            status_code=400,
            code="INVALID_PROJECT_DATES",
            message="Expected possession cannot be before launch",
        )
    before = _project_snapshot(project)
    for field, value in changes.items():
        setattr(project, field, value)
    project.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "project.updated",
            "project",
            project.id,
            before,
            _project_snapshot(project),
        )
    )
    await db.commit()
    await db.refresh(project)
    return (await _project_views(db, organization_id, [project]))[0]


async def delete_project(
    db: AsyncSession, organization_id: str, project_id: str, context: MutationContext
) -> None:
    project = await _entity(db, Project, organization_id, project_id, lock=True)
    db.add(
        _audit(
            organization_id,
            context,
            "project.deleted",
            "project",
            project.id,
            _project_snapshot(project),
            None,
        )
    )
    await db.delete(project)
    await _commit_conflict(
        db, "PROJECT_IN_USE", "Project cannot be deleted while linked transactional records exist"
    )


async def list_towers(db: AsyncSession, organization_id: str, project_id: str) -> list[TowerView]:
    await _entity(db, Project, organization_id, project_id)
    towers = list(
        (
            await db.scalars(
                select(Tower)
                .where(Tower.organization_id == organization_id, Tower.project_id == project_id)
                .order_by(Tower.name, Tower.id)
            )
        ).all()
    )
    if not towers:
        return []
    ids = [item.id for item in towers]
    floor_counts: dict[str, int] = {
        tower_id: count
        for tower_id, count in (
            await db.execute(
                select(Floor.tower_id, func.count(Floor.id))
                .where(Floor.organization_id == organization_id, Floor.tower_id.in_(ids))
                .group_by(Floor.tower_id)
            )
        ).all()
    }
    unit_counts: dict[str, int] = {
        tower_id: count
        for tower_id, count in (
            await db.execute(
                select(Unit.tower_id, func.count(Unit.id))
                .where(Unit.organization_id == organization_id, Unit.tower_id.in_(ids))
                .group_by(Unit.tower_id)
            )
        ).all()
        if tower_id is not None
    }
    return [
        TowerView(
            id=item.id,
            project_id=item.project_id,
            name=item.name,
            code=item.code,
            is_active=item.is_active,
            floor_count=floor_counts.get(item.id, 0),
            unit_count=unit_counts.get(item.id, 0),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in towers
    ]


async def create_tower(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    payload: TowerCreate,
    context: MutationContext,
) -> TowerView:
    await _entity(db, Project, organization_id, project_id)
    tower = Tower(organization_id=organization_id, project_id=project_id, **payload.model_dump())
    db.add(tower)
    await _flush_conflict(db, "DUPLICATE_TOWER_CODE", "Tower code already exists in this project")
    db.add(
        _audit(
            organization_id,
            context,
            "tower.created",
            "tower",
            tower.id,
            None,
            {"project_id": project_id, "name": tower.name, "code": tower.code},
        )
    )
    await _commit_conflict(db, "DUPLICATE_TOWER_CODE", "Tower code already exists in this project")
    return next(
        item for item in await list_towers(db, organization_id, project_id) if item.id == tower.id
    )


async def update_tower(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    tower_id: str,
    payload: TowerUpdate,
    context: MutationContext,
) -> TowerView:
    tower = await _entity(db, Tower, organization_id, tower_id, lock=True)
    if tower.project_id != project_id:
        raise _not_found()
    before = {"name": tower.name, "code": tower.code, "is_active": tower.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tower, field, value)
    tower.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "tower.updated",
            "tower",
            tower.id,
            before,
            {"name": tower.name, "code": tower.code, "is_active": tower.is_active},
        )
    )
    await _commit_conflict(db, "DUPLICATE_TOWER_CODE", "Tower code already exists in this project")
    return next(
        item for item in await list_towers(db, organization_id, project_id) if item.id == tower.id
    )


async def delete_tower(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    tower_id: str,
    context: MutationContext,
) -> None:
    tower = await _entity(db, Tower, organization_id, tower_id, lock=True)
    if tower.project_id != project_id:
        raise _not_found()
    db.add(
        _audit(
            organization_id,
            context,
            "tower.deleted",
            "tower",
            tower.id,
            {"project_id": project_id, "name": tower.name},
            None,
        )
    )
    await db.delete(tower)
    await _commit_conflict(db, "TOWER_IN_USE", "Tower cannot be deleted while units are linked")


async def list_floors(
    db: AsyncSession, organization_id: str, project_id: str, tower_id: str | None = None
) -> list[FloorView]:
    await _entity(db, Project, organization_id, project_id)
    statement = (
        select(Floor, Tower)
        .join(
            Tower,
            (Tower.organization_id == Floor.organization_id) & (Tower.id == Floor.tower_id),
        )
        .where(Floor.organization_id == organization_id, Tower.project_id == project_id)
    )
    if tower_id:
        statement = statement.where(Floor.tower_id == tower_id)
    rows = (await db.execute(statement.order_by(Tower.name, Floor.floor_number))).all()
    floor_ids = [floor.id for floor, _tower in rows]
    counts: dict[str, int] = (
        {
            floor_id: count
            for floor_id, count in (
                await db.execute(
                    select(Unit.floor_id, func.count(Unit.id))
                    .where(Unit.organization_id == organization_id, Unit.floor_id.in_(floor_ids))
                    .group_by(Unit.floor_id)
                )
            ).all()
            if floor_id is not None
        }
        if floor_ids
        else {}
    )
    return [
        FloorView(
            id=floor.id,
            project_id=project_id,
            tower_id=floor.tower_id,
            tower_name=tower.name,
            name=floor.name,
            floor_number=floor.floor_number,
            is_active=floor.is_active,
            unit_count=counts.get(floor.id, 0),
            created_at=floor.created_at,
            updated_at=floor.updated_at,
        )
        for floor, tower in rows
    ]


async def _validate_floor(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    tower_id: str | None,
    floor_id: str | None,
) -> None:
    if tower_id is None:
        if floor_id is not None:
            raise AppError(
                status_code=400, code="INVALID_HIERARCHY", message="Floor requires a tower"
            )
        return
    tower = await _entity(db, Tower, organization_id, tower_id)
    if tower.project_id != project_id:
        raise AppError(
            status_code=400, code="INVALID_TOWER", message="Tower is not in this project"
        )
    if floor_id:
        floor = await _entity(db, Floor, organization_id, floor_id)
        if floor.tower_id != tower_id:
            raise AppError(
                status_code=400, code="INVALID_FLOOR", message="Floor is not in the selected tower"
            )


async def create_floor(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    payload: FloorCreate,
    context: MutationContext,
) -> FloorView:
    await _validate_floor(db, organization_id, project_id, payload.tower_id, None)
    floor = Floor(organization_id=organization_id, **payload.model_dump())
    db.add(floor)
    await _flush_conflict(db, "DUPLICATE_FLOOR", "Floor number already exists in this tower")
    db.add(
        _audit(
            organization_id,
            context,
            "floor.created",
            "floor",
            floor.id,
            None,
            {"tower_id": floor.tower_id, "name": floor.name, "floor_number": floor.floor_number},
        )
    )
    await _commit_conflict(db, "DUPLICATE_FLOOR", "Floor number already exists in this tower")
    return next(
        item for item in await list_floors(db, organization_id, project_id) if item.id == floor.id
    )


async def update_floor(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    floor_id: str,
    payload: FloorUpdate,
    context: MutationContext,
) -> FloorView:
    floor = await _entity(db, Floor, organization_id, floor_id, lock=True)
    tower = await _entity(db, Tower, organization_id, floor.tower_id)
    if tower.project_id != project_id:
        raise _not_found()
    before = {"name": floor.name, "floor_number": floor.floor_number, "is_active": floor.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(floor, field, value)
    floor.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "floor.updated",
            "floor",
            floor.id,
            before,
            {"name": floor.name, "floor_number": floor.floor_number, "is_active": floor.is_active},
        )
    )
    await _commit_conflict(db, "DUPLICATE_FLOOR", "Floor number already exists in this tower")
    return next(
        item for item in await list_floors(db, organization_id, project_id) if item.id == floor.id
    )


async def delete_floor(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    floor_id: str,
    context: MutationContext,
) -> None:
    floor = await _entity(db, Floor, organization_id, floor_id, lock=True)
    tower = await _entity(db, Tower, organization_id, floor.tower_id)
    if tower.project_id != project_id:
        raise _not_found()
    db.add(
        _audit(
            organization_id,
            context,
            "floor.deleted",
            "floor",
            floor.id,
            {"tower_id": floor.tower_id, "name": floor.name},
            None,
        )
    )
    await db.delete(floor)
    await _commit_conflict(db, "FLOOR_IN_USE", "Floor cannot be deleted while units are linked")


def _effective_unit_status(unit: Unit, hold: UnitHold | None) -> UnitStatus:
    if hold is not None and hold.hold_type is not None:
        return UnitStatus(hold.hold_type.value)
    return unit.status


async def _unit_views(db: AsyncSession, organization_id: str, units: list[Unit]) -> list[UnitView]:
    if not units:
        return []
    await expire_due_holds(db, organization_id=organization_id)
    project_ids = {item.project_id for item in units}
    tower_ids = {item.tower_id for item in units if item.tower_id}
    floor_ids = {item.floor_id for item in units if item.floor_id}
    projects = {
        item.id: item.name
        for item in (
            await db.scalars(
                select(Project).where(
                    Project.organization_id == organization_id, Project.id.in_(project_ids)
                )
            )
        ).all()
    }
    towers = (
        {
            item.id: item.name
            for item in (
                await db.scalars(
                    select(Tower).where(
                        Tower.organization_id == organization_id, Tower.id.in_(tower_ids)
                    )
                )
            ).all()
        }
        if tower_ids
        else {}
    )
    floors = (
        {
            item.id: (item.name, item.floor_number)
            for item in (
                await db.scalars(
                    select(Floor).where(
                        Floor.organization_id == organization_id, Floor.id.in_(floor_ids)
                    )
                )
            ).all()
        }
        if floor_ids
        else {}
    )
    active_holds = {
        item.unit_id: item
        for item in (
            await db.scalars(
                select(UnitHold).where(
                    UnitHold.organization_id == organization_id,
                    UnitHold.unit_id.in_([unit.id for unit in units]),
                    UnitHold.status.in_(RESERVING_HOLD_STATUSES),
                    UnitHold.expires_at > _now(),
                )
            )
        ).all()
    }
    return [
        UnitView(
            id=item.id,
            project_id=item.project_id,
            project_name=projects[item.project_id],
            tower_id=item.tower_id,
            tower_name=towers.get(item.tower_id) if item.tower_id else None,
            floor_id=item.floor_id,
            floor_name=floors[item.floor_id][0] if item.floor_id in floors else None,
            floor_number=floors[item.floor_id][1] if item.floor_id in floors else None,
            unit_number=item.unit_number,
            unit_type=item.unit_type,
            area_sqft=item.area_sqft,
            carpet_area_sqft=item.carpet_area_sqft,
            built_up_area_sqft=item.built_up_area_sqft,
            facing=item.facing,
            bedrooms=item.bedrooms,
            bathrooms=item.bathrooms,
            balconies=item.balconies,
            status=_effective_unit_status(item, active_holds.get(item.id)),
            base_price=item.base_price,
            currency=item.currency,
            amenities=item.amenities,
            price_components=item.price_components,
            configuration=item.configuration,
            active_hold_id=(active_holds[item.id].id if item.id in active_holds else None),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in units
    ]


async def search_units(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    project_id: str | None,
    tower_id: str | None,
    floor_id: str | None,
    status: UnitStatus | None,
    unit_type: str | None,
    facing: str | None,
    bedrooms: int | None,
    min_area: float | None,
    max_area: float | None,
    min_price: float | None,
    max_price: float | None,
    amenity: str | None,
    page: int,
    page_size: int,
) -> Page[UnitView]:
    await expire_due_holds(db, organization_id=organization_id)
    filters = [Unit.organization_id == organization_id]
    if q:
        term = f"%{q.strip()}%"
        filters.append(or_(Unit.unit_number.ilike(term), Unit.unit_type.ilike(term)))
    if project_id:
        filters.append(Unit.project_id == project_id)
    if tower_id:
        filters.append(Unit.tower_id == tower_id)
    if floor_id:
        filters.append(Unit.floor_id == floor_id)
    if status:
        filters.append(Unit.status == status)
        if status == UnitStatus.AVAILABLE:
            filters.append(
                ~exists(
                    select(UnitHold.id).where(
                        UnitHold.organization_id == organization_id,
                        UnitHold.unit_id == Unit.id,
                        UnitHold.status.in_(RESERVING_HOLD_STATUSES),
                        UnitHold.expires_at > _now(),
                    )
                )
            )
    if unit_type:
        filters.append(Unit.unit_type == unit_type)
    if facing:
        filters.append(Unit.facing == facing)
    if bedrooms is not None:
        filters.append(Unit.bedrooms == bedrooms)
    if min_area is not None:
        filters.append(Unit.area_sqft >= min_area)
    if max_area is not None:
        filters.append(Unit.area_sqft <= max_area)
    if min_price is not None:
        filters.append(Unit.base_price >= min_price)
    if max_price is not None:
        filters.append(Unit.base_price <= max_price)
    if amenity:
        filters.append(cast(Unit.amenities, String).ilike(f'%"{amenity.strip()}"%'))
    total = int(await db.scalar(select(func.count(Unit.id)).where(*filters)) or 0)
    records = list(
        (
            await db.scalars(
                select(Unit)
                .where(*filters)
                .order_by(Unit.project_id, Unit.tower_id, Unit.floor_id, Unit.unit_number)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=await _unit_views(db, organization_id, records),
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def inventory_stats(db: AsyncSession, organization_id: str) -> InventoryStats:
    await expire_due_holds(db, organization_id=organization_id)
    rows = (
        await db.execute(
            select(Unit.status, func.count(Unit.id))
            .where(Unit.organization_id == organization_id)
            .group_by(Unit.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    available = int(
        await db.scalar(
            select(func.count(Unit.id)).where(
                Unit.organization_id == organization_id,
                Unit.status == UnitStatus.AVAILABLE,
                ~exists(
                    select(UnitHold.id).where(
                        UnitHold.organization_id == organization_id,
                        UnitHold.unit_id == Unit.id,
                        UnitHold.status.in_(RESERVING_HOLD_STATUSES),
                        UnitHold.expires_at > _now(),
                    )
                ),
            )
        )
        or 0
    )
    held = int(
        await db.scalar(
            select(func.count(UnitHold.id)).where(
                UnitHold.organization_id == organization_id,
                UnitHold.status.in_(RESERVING_HOLD_STATUSES),
                UnitHold.expires_at > _now(),
            )
        )
        or 0
    )
    return InventoryStats(
        total=sum(counts.values()),
        available=available,
        held=held,
        booking_initiated=counts.get(UnitStatus.BOOKING_INITIATED, 0),
        booked=counts.get(UnitStatus.BOOKED, 0),
        sold=counts.get(UnitStatus.SOLD, 0),
    )


async def create_unit(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    payload: UnitCreate,
    context: MutationContext,
) -> UnitView:
    project = await _entity(db, Project, organization_id, project_id)
    await _validate_floor(db, organization_id, project_id, payload.tower_id, payload.floor_id)
    values = payload.model_dump()
    if values["base_price"] is not None and values["currency"] is None:
        values["currency"] = project.default_currency
    unit = Unit(
        organization_id=organization_id,
        project_id=project_id,
        status=UnitStatus.AVAILABLE,
        **values,
    )
    db.add(unit)
    await _flush_conflict(db, "DUPLICATE_UNIT", "Unit number already exists in this project")
    db.add(
        _audit(
            organization_id,
            context,
            "unit.created",
            "unit",
            unit.id,
            None,
            _unit_snapshot(unit),
        )
    )
    await _commit_conflict(db, "DUPLICATE_UNIT", "Unit number already exists in this project")
    await db.refresh(unit)
    return (await _unit_views(db, organization_id, [unit]))[0]


async def get_unit(db: AsyncSession, organization_id: str, unit_id: str) -> UnitView:
    unit = await _entity(db, Unit, organization_id, unit_id)
    return (await _unit_views(db, organization_id, [unit]))[0]


async def update_unit(
    db: AsyncSession,
    organization_id: str,
    unit_id: str,
    payload: UnitUpdate,
    context: MutationContext,
) -> UnitView:
    unit = await _entity(db, Unit, organization_id, unit_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    tower_id = changes.get("tower_id", unit.tower_id)
    floor_id = changes.get("floor_id", unit.floor_id)
    if "tower_id" in changes and "floor_id" not in changes and tower_id != unit.tower_id:
        floor_id = None
        changes["floor_id"] = None
    await _validate_floor(db, organization_id, unit.project_id, tower_id, floor_id)
    price = changes.get("base_price", unit.base_price)
    currency = changes.get("currency", unit.currency)
    if (price is None) != (currency is None):
        raise AppError(
            status_code=400,
            code="INVALID_PRICE",
            message="Price and currency must be provided together",
        )
    before = _unit_snapshot(unit)
    for field, value in changes.items():
        setattr(unit, field, value)
    unit.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "unit.updated",
            "unit",
            unit.id,
            before,
            _unit_snapshot(unit),
        )
    )
    await _commit_conflict(db, "DUPLICATE_UNIT", "Unit number already exists in this project")
    await db.refresh(unit)
    return (await _unit_views(db, organization_id, [unit]))[0]


async def delete_unit(
    db: AsyncSession, organization_id: str, unit_id: str, context: MutationContext
) -> None:
    unit = await _entity(db, Unit, organization_id, unit_id, lock=True)
    if unit.status not in {UnitStatus.AVAILABLE, UnitStatus.CANCELLED_RELEASED}:
        raise AppError(
            status_code=409,
            code="UNIT_NOT_DELETABLE",
            message="Only available or released units can be deleted",
        )
    db.add(
        _audit(
            organization_id,
            context,
            "unit.deleted",
            "unit",
            unit.id,
            _unit_snapshot(unit),
            None,
        )
    )
    await db.delete(unit)
    await _commit_conflict(db, "UNIT_IN_USE", "Unit cannot be deleted while linked records exist")


async def transition_unit_status(
    db: AsyncSession,
    organization_id: str,
    unit_id: str,
    target: UnitStatus,
    context: MutationContext,
) -> UnitView:
    unit = await _entity(db, Unit, organization_id, unit_id, lock=True)
    allowed = {
        UnitStatus.CANCELLED_RELEASED: {UnitStatus.AVAILABLE},
        UnitStatus.BOOKED: {UnitStatus.SOLD},
    }
    if target not in allowed.get(unit.status, set()):
        raise AppError(
            status_code=409,
            code="INVALID_UNIT_STATUS_TRANSITION",
            message=f"Cannot move unit from {unit.status.value} to {target.value}",
        )
    before = _unit_snapshot(unit)
    unit.status = target
    unit.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "unit.status.changed",
            "unit",
            unit.id,
            before,
            _unit_snapshot(unit),
        )
    )
    await db.commit()
    await db.refresh(unit)
    return (await _unit_views(db, organization_id, [unit]))[0]


async def _hold_view(db: AsyncSession, organization_id: str, hold: UnitHold) -> UnitHoldView:
    unit = await _entity(db, Unit, organization_id, hold.unit_id)
    project = await _entity(db, Project, organization_id, unit.project_id)
    customer = (
        await _entity(db, Customer, organization_id, hold.customer_id) if hold.customer_id else None
    )
    salesperson = await _entity(db, User, organization_id, hold.held_by_user_id)
    approver = (
        await _entity(db, User, organization_id, hold.approved_by_user_id)
        if hold.approved_by_user_id
        else None
    )
    hold_type = hold.hold_type
    if hold_type is None and unit.status in {UnitStatus.SOFT_HOLD, UnitStatus.HARD_HOLD}:
        hold_type = HoldType(unit.status.value)
    return UnitHoldView(
        id=hold.id,
        unit_id=unit.id,
        unit_number=unit.unit_number,
        project_id=project.id,
        project_name=project.name,
        hold_type=hold_type,
        hold_reason=hold.hold_reason,
        customer_id=customer.id if customer else None,
        customer_name=customer.full_name if customer else None,
        lead_id=hold.lead_id,
        held_by_user_id=salesperson.id,
        salesperson_name=salesperson.full_name,
        approved_by_user_id=approver.id if approver else None,
        approver_name=approver.full_name if approver else None,
        status=hold.status,
        starts_at=hold.starts_at,
        expires_at=hold.expires_at,
        released_at=hold.released_at,
        approved_at=hold.approved_at,
        rejected_at=hold.rejected_at,
        approval_notes=hold.approval_notes,
        release_reason=hold.release_reason,
        created_at=hold.created_at,
        updated_at=hold.updated_at,
    )


def _mark_hold_expired(
    db: AsyncSession,
    unit: Unit,
    hold: UnitHold,
    context: MutationContext | None,
) -> None:
    previous = {
        "status": hold.status.value,
        "unit_status": unit.status.value,
        "expires_at": hold.expires_at.isoformat(),
    }
    hold.status = HoldStatus.EXPIRED
    hold.active_unit_key = None
    hold.released_at = _now()
    hold.release_reason = "Expired automatically"
    if unit.status in {UnitStatus.SOFT_HOLD, UnitStatus.HARD_HOLD}:
        unit.status = UnitStatus.AVAILABLE
    audit = (
        _audit(
            unit.organization_id,
            context,
            "unit.hold.expired",
            "unit_hold",
            hold.id,
            previous,
            {"status": HoldStatus.EXPIRED.value, "unit_status": unit.status.value},
        )
        if context
        else _system_audit(
            unit.organization_id,
            "unit.hold.expired",
            "unit_hold",
            hold.id,
            previous,
            {"status": HoldStatus.EXPIRED.value, "unit_status": unit.status.value},
        )
    )
    db.add(audit)
    queue_in_app(
        db,
        organization_id=unit.organization_id,
        recipient_user_ids=[hold.held_by_user_id],
        event_type=NotificationEventType.UNIT_HOLD_EXPIRED,
        title="Unit hold expired",
        body="The unit has been released back to available inventory.",
        related_entity_type="unit_hold",
        related_entity_id=hold.id,
        action_url="/inventory/holds",
        data={"unit_id": unit.id, "expired_at": hold.released_at.isoformat()},
    )


async def _expire_hold(
    db: AsyncSession, unit: Unit, context: MutationContext | None = None
) -> UnitHold | None:
    hold = (
        await db.scalars(
            select(UnitHold)
            .where(
                UnitHold.organization_id == unit.organization_id,
                UnitHold.unit_id == unit.id,
                UnitHold.status.in_(RESERVING_HOLD_STATUSES),
            )
            .with_for_update()
        )
    ).first()
    if hold and hold.expires_at <= _now():
        _mark_hold_expired(db, unit, hold, context)
        await db.flush()
        return None
    return hold


async def expire_due_holds(
    db: AsyncSession,
    *,
    organization_id: str | None = None,
    limit: int = 200,
    context: MutationContext | None = None,
) -> int:
    conditions: list[Any] = [
        UnitHold.status.in_(RESERVING_HOLD_STATUSES),
        UnitHold.expires_at <= _now(),
    ]
    if organization_id:
        conditions.append(UnitHold.organization_id == organization_id)
    candidates = list(
        await db.scalars(
            select(UnitHold.id).where(*conditions).order_by(UnitHold.expires_at).limit(limit)
        )
    )
    expired = 0
    for hold_id in candidates:
        candidate = await db.scalar(select(UnitHold).where(UnitHold.id == hold_id))
        if candidate is None:
            continue
        unit = await _entity(db, Unit, candidate.organization_id, candidate.unit_id, lock=True)
        hold = (
            await db.scalars(
                select(UnitHold)
                .where(
                    UnitHold.organization_id == candidate.organization_id,
                    UnitHold.id == hold_id,
                    UnitHold.status.in_(RESERVING_HOLD_STATUSES),
                    UnitHold.expires_at <= _now(),
                )
                .with_for_update()
            )
        ).first()
        if hold is None:
            continue
        _mark_hold_expired(db, unit, hold, context)
        expired += 1
    if expired:
        await db.commit()
    return expired


async def list_holds(
    db: AsyncSession,
    organization_id: str,
    *,
    status: HoldStatus | None,
    hold_type: HoldType | None,
    project_id: str | None,
    customer_id: str | None,
    salesperson_user_id: str | None,
    page: int,
    page_size: int,
) -> Page[UnitHoldView]:
    await expire_due_holds(db, organization_id=organization_id)
    conditions: list[Any] = [UnitHold.organization_id == organization_id]
    if status:
        conditions.append(UnitHold.status == status)
    if hold_type:
        conditions.append(UnitHold.hold_type == hold_type)
    if customer_id:
        conditions.append(UnitHold.customer_id == customer_id)
    if salesperson_user_id:
        conditions.append(UnitHold.held_by_user_id == salesperson_user_id)
    if project_id:
        conditions.append(
            UnitHold.unit_id.in_(
                select(Unit.id).where(
                    Unit.organization_id == organization_id,
                    Unit.project_id == project_id,
                )
            )
        )
    total = int(await db.scalar(select(func.count(UnitHold.id)).where(*conditions)) or 0)
    holds = list(
        await db.scalars(
            select(UnitHold)
            .where(*conditions)
            .order_by(UnitHold.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _hold_view(db, organization_id, item) for item in holds],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def hold_salespeople(db: AsyncSession, organization_id: str) -> list[HoldSalespersonOption]:
    users = list(
        await db.scalars(
            select(User)
            .where(User.organization_id == organization_id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )
    return [
        HoldSalespersonOption(id=item.id, full_name=item.full_name, email=item.email)
        for item in users
    ]


async def hold_history(db: AsyncSession, organization_id: str, unit_id: str) -> list[UnitHoldView]:
    await _entity(db, Unit, organization_id, unit_id)
    await expire_due_holds(db, organization_id=organization_id)
    holds = list(
        await db.scalars(
            select(UnitHold)
            .where(
                UnitHold.organization_id == organization_id,
                UnitHold.unit_id == unit_id,
            )
            .order_by(UnitHold.created_at.desc())
        )
    )
    return [await _hold_view(db, organization_id, item) for item in holds]


async def hold_stats(db: AsyncSession, organization_id: str) -> HoldStats:
    await expire_due_holds(db, organization_id=organization_id)
    rows = (
        await db.execute(
            select(UnitHold.status, func.count(UnitHold.id))
            .where(UnitHold.organization_id == organization_id)
            .group_by(UnitHold.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    return HoldStats(
        total=sum(counts.values()),
        pending_approval=counts.get(HoldStatus.PENDING_APPROVAL, 0),
        active=counts.get(HoldStatus.ACTIVE, 0),
        released=counts.get(HoldStatus.RELEASED, 0),
        expired=counts.get(HoldStatus.EXPIRED, 0),
        rejected=counts.get(HoldStatus.REJECTED, 0),
        converted=counts.get(HoldStatus.CONVERTED, 0),
    )


async def create_hold(
    db: AsyncSession,
    organization_id: str,
    unit_id: str,
    payload: UnitHoldCreate,
    context: MutationContext,
) -> UnitHoldView:
    unit = await _entity(db, Unit, organization_id, unit_id, lock=True)
    active = await _expire_hold(db, unit, context)
    if active or unit.status != UnitStatus.AVAILABLE:
        raise AppError(status_code=409, code="UNIT_UNAVAILABLE", message="Unit is not available")
    if payload.expires_at.replace(tzinfo=None) <= _now():
        raise AppError(
            status_code=400, code="INVALID_EXPIRY", message="Hold expiry must be in the future"
        )
    await _entity(db, Customer, organization_id, payload.customer_id)
    if payload.lead_id:
        await _entity(db, Lead, organization_id, payload.lead_id)
    salesperson_id = payload.salesperson_user_id or context.actor_user_id
    salesperson = await _entity(db, User, organization_id, salesperson_id)
    if not salesperson.is_active:
        raise AppError(
            status_code=400,
            code="INVALID_SALESPERSON",
            message="The selected salesperson is inactive",
        )
    hold = UnitHold(
        organization_id=organization_id,
        unit_id=unit.id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        held_by_user_id=salesperson.id,
        hold_type=HoldType(payload.hold_type),
        hold_reason=payload.hold_reason,
        status=HoldStatus.PENDING_APPROVAL,
        starts_at=_now(),
        expires_at=payload.expires_at.replace(tzinfo=None),
        active_unit_key=unit.id,
    )
    db.add(hold)
    unit.status = UnitStatus(payload.hold_type)
    await _flush_conflict(db, "UNIT_UNAVAILABLE", "Unit already has an active hold")
    db.add(
        _audit(
            organization_id,
            context,
            "unit.hold.created",
            "unit_hold",
            hold.id,
            None,
            {
                "unit_id": unit.id,
                "hold_type": payload.hold_type,
                "status": HoldStatus.PENDING_APPROVAL.value,
                "customer_id": payload.customer_id,
                "salesperson_user_id": salesperson.id,
                "reason": payload.hold_reason,
                "expires_at": hold.expires_at.isoformat(),
            },
        )
    )
    await _commit_conflict(db, "UNIT_UNAVAILABLE", "Unit already has an active hold")
    await db.refresh(hold)
    return await _hold_view(db, organization_id, hold)


async def decide_hold(
    db: AsyncSession,
    organization_id: str,
    hold_id: str,
    payload: HoldApprovalDecision,
    context: MutationContext,
) -> UnitHoldView:
    candidate = await _entity(db, UnitHold, organization_id, hold_id)
    unit = await _entity(db, Unit, organization_id, candidate.unit_id, lock=True)
    hold = await _expire_hold(db, unit, context)
    if hold is None or hold.id != hold_id or hold.status != HoldStatus.PENDING_APPROVAL:
        await db.commit()
        raise AppError(
            status_code=409,
            code="HOLD_APPROVAL_NOT_PENDING",
            message="This hold has no pending approval",
        )
    if hold.held_by_user_id == context.actor_user_id:
        raise AppError(
            status_code=403,
            code="SELF_APPROVAL_NOT_ALLOWED",
            message="The hold salesperson cannot approve their own request",
        )
    previous = {"status": hold.status.value, "unit_status": unit.status.value}
    expected_unit_status = UnitStatus(hold.hold_type.value) if hold.hold_type else unit.status
    if unit.status != expected_unit_status:
        raise AppError(
            status_code=409,
            code="HOLD_UNIT_STATE_MISMATCH",
            message="The unit no longer matches the requested hold state",
        )
    hold.approved_by_user_id = context.actor_user_id
    hold.approval_notes = payload.notes
    if payload.status == "APPROVED":
        hold.status = HoldStatus.ACTIVE
        hold.approved_at = _now()
    else:
        hold.status = HoldStatus.REJECTED
        hold.rejected_at = _now()
        hold.released_at = hold.rejected_at
        hold.active_unit_key = None
        unit.status = UnitStatus.AVAILABLE
    db.add(
        _audit(
            organization_id,
            context,
            "unit.hold.approved" if payload.status == "APPROVED" else "unit.hold.rejected",
            "unit_hold",
            hold.id,
            previous,
            {
                "status": hold.status.value,
                "unit_status": unit.status.value,
                "approver_user_id": context.actor_user_id,
                "notes": payload.notes,
            },
        )
    )
    await db.commit()
    await db.refresh(hold)
    return await _hold_view(db, organization_id, hold)


async def release_hold(
    db: AsyncSession,
    organization_id: str,
    unit_id: str,
    reason: str,
    context: MutationContext,
) -> UnitView:
    unit = await _entity(db, Unit, organization_id, unit_id, lock=True)
    hold = await _expire_hold(db, unit, context)
    if hold is None:
        await db.commit()
        raise AppError(status_code=409, code="NO_ACTIVE_HOLD", message="Unit has no active hold")
    previous = {"status": hold.status.value, "unit_status": unit.status.value}
    hold.status = HoldStatus.RELEASED
    hold.active_unit_key = None
    hold.released_at = _now()
    hold.release_reason = reason
    unit.status = UnitStatus.AVAILABLE
    db.add(
        _audit(
            organization_id,
            context,
            "unit.hold.released",
            "unit_hold",
            hold.id,
            previous,
            {"unit_id": unit.id, "status": "RELEASED", "reason": reason},
        )
    )
    await db.commit()
    await db.refresh(unit)
    return (await _unit_views(db, organization_id, [unit]))[0]


def _booking_view(booking: Booking, unit: Unit) -> InventoryBookingView:
    return InventoryBookingView(
        id=booking.id,
        unit_id=booking.unit_id,
        unit_number=unit.unit_number,
        customer_id=booking.customer_id,
        lead_id=booking.lead_id,
        quotation_id=booking.quotation_id,
        booked_by_user_id=booking.booked_by_user_id,
        booking_number=booking.booking_number,
        booking_amount=booking.booking_amount,
        currency=booking.currency,
        status=booking.status,
        booked_at=booking.booked_at,
        created_at=booking.created_at,
    )


async def initiate_booking(
    db: AsyncSession,
    organization_id: str,
    unit_id: str,
    payload: BookingInitiate,
    context: MutationContext,
) -> InventoryBookingView:
    unit = await _entity(db, Unit, organization_id, unit_id, lock=True)
    hold = await _expire_hold(db, unit, context)
    existing = await db.scalar(
        select(Booking.id).where(
            Booking.organization_id == organization_id,
            Booking.active_unit_key == unit.id,
        )
    )
    if existing or unit.status not in {
        UnitStatus.AVAILABLE,
        UnitStatus.SOFT_HOLD,
        UnitStatus.HARD_HOLD,
    }:
        raise AppError(status_code=409, code="UNIT_ALREADY_BOOKED", message="Unit is not bookable")
    if hold and hold.status == HoldStatus.PENDING_APPROVAL:
        raise AppError(
            status_code=409,
            code="HOLD_APPROVAL_PENDING",
            message="The unit hold must be approved before booking",
        )
    await _entity(db, Customer, organization_id, payload.customer_id)
    if payload.lead_id:
        await _entity(db, Lead, organization_id, payload.lead_id)
    if payload.quotation_id:
        quotation = await _entity(db, Quotation, organization_id, payload.quotation_id)
        if (
            quotation.customer_id not in {None, payload.customer_id}
            or quotation.project_id != unit.project_id
        ):
            raise AppError(
                status_code=400,
                code="INVALID_QUOTATION",
                message="Quotation does not match this booking",
            )
    if hold and hold.customer_id not in {None, payload.customer_id}:
        raise AppError(
            status_code=409, code="HOLD_OWNER_MISMATCH", message="Unit is held for another customer"
        )
    if hold and payload.lead_id and hold.lead_id not in {None, payload.lead_id}:
        raise AppError(
            status_code=409, code="HOLD_OWNER_MISMATCH", message="Unit is held for another lead"
        )
    if hold:
        previous_hold_status = hold.status.value
        hold.status = HoldStatus.CONVERTED
        hold.active_unit_key = None
        hold.released_at = _now()
        db.add(
            _audit(
                organization_id,
                context,
                "unit.hold.converted",
                "unit_hold",
                hold.id,
                {"status": previous_hold_status},
                {"status": HoldStatus.CONVERTED.value, "booking_number": payload.booking_number},
            )
        )
    booking = Booking(
        organization_id=organization_id,
        unit_id=unit.id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        quotation_id=payload.quotation_id,
        booked_by_user_id=context.actor_user_id,
        booking_number=payload.booking_number,
        status=BookingStatus.DRAFT,
        booking_amount=payload.booking_amount,
        currency=payload.currency,
        active_unit_key=unit.id,
    )
    db.add(booking)
    unit.status = UnitStatus.BOOKING_INITIATED
    await _flush_conflict(db, "UNIT_ALREADY_BOOKED", "Unit already has an active booking")
    db.add(
        _audit(
            organization_id,
            context,
            "booking.initiated",
            "booking",
            booking.id,
            None,
            {
                "unit_id": unit.id,
                "customer_id": payload.customer_id,
                "booking_number": booking.booking_number,
            },
        )
    )
    await _commit_conflict(db, "UNIT_ALREADY_BOOKED", "Unit already has an active booking")
    await db.refresh(booking)
    return _booking_view(booking, unit)


async def transition_booking(
    db: AsyncSession,
    organization_id: str,
    booking_id: str,
    target: BookingStatus,
    context: MutationContext,
) -> InventoryBookingView:
    booking = await _entity(db, Booking, organization_id, booking_id, lock=True)
    unit = await _entity(db, Unit, organization_id, booking.unit_id, lock=True)
    if booking.status in {BookingStatus.CONFIRMED, BookingStatus.CANCELLED}:
        raise AppError(
            status_code=409, code="BOOKING_FINALIZED", message="Booking is already finalized"
        )
    before = {"status": booking.status.value, "unit_status": unit.status.value}
    if target == BookingStatus.CONFIRMED:
        if booking.active_unit_key != unit.id or unit.status != UnitStatus.BOOKING_INITIATED:
            raise AppError(
                status_code=409,
                code="UNIT_ALREADY_BOOKED",
                message="Unit booking lock is not active",
            )
        booking.status = BookingStatus.CONFIRMED
        booking.booked_at = _now()
        unit.status = UnitStatus.BOOKED
    elif target == BookingStatus.CANCELLED:
        booking.status = BookingStatus.CANCELLED
        booking.active_unit_key = None
        unit.status = UnitStatus.CANCELLED_RELEASED
    else:
        raise AppError(
            status_code=400, code="INVALID_BOOKING_STATUS", message="Unsupported booking status"
        )
    db.add(
        _audit(
            organization_id,
            context,
            "booking.status.changed",
            "booking",
            booking.id,
            before,
            {"status": booking.status.value, "unit_status": unit.status.value},
        )
    )
    await db.commit()
    await db.refresh(booking)
    await db.refresh(unit)
    return _booking_view(booking, unit)
