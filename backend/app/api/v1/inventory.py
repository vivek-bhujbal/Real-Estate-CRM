from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DbSession, SecurityContext, mutation_context, require_permissions
from app.core.errors import AppError
from app.models.enums import BookingStatus, HoldStatus, HoldType, ProjectStatus, UnitStatus
from app.schemas.inventory import (
    BookingInitiate,
    BookingStatusPayload,
    FloorCreate,
    FloorUpdate,
    FloorView,
    HoldApprovalDecision,
    HoldExpiryResult,
    HoldReleasePayload,
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
    UnitStatusPayload,
    UnitUpdate,
    UnitView,
)
from app.schemas.organization import Page
from app.services import inventory as inventory_service
from app.services.organization import MutationContext

router = APIRouter(tags=["project-inventory"])

ProjectsReader = Annotated[SecurityContext, Depends(require_permissions("projects.view"))]
ProjectsCreator = Annotated[SecurityContext, Depends(require_permissions("projects.create"))]
ProjectsUpdater = Annotated[SecurityContext, Depends(require_permissions("projects.update"))]
ProjectsDeleter = Annotated[SecurityContext, Depends(require_permissions("projects.delete"))]
InventoryReader = Annotated[SecurityContext, Depends(require_permissions("inventory.view"))]
InventoryCreator = Annotated[SecurityContext, Depends(require_permissions("inventory.create"))]
InventoryUpdater = Annotated[SecurityContext, Depends(require_permissions("inventory.update"))]
InventoryDeleter = Annotated[SecurityContext, Depends(require_permissions("inventory.delete"))]
InventoryApprover = Annotated[SecurityContext, Depends(require_permissions("inventory.approve"))]
InventoryAssigner = Annotated[SecurityContext, Depends(require_permissions("inventory.assign"))]
InventoryManager = Annotated[SecurityContext, Depends(require_permissions("inventory.manage"))]
BookingCreator = Annotated[
    SecurityContext, Depends(require_permissions("bookings.create", "inventory.update"))
]
BookingUpdater = Annotated[
    SecurityContext, Depends(require_permissions("bookings.update", "inventory.update"))
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return mutation_context(request, security)


@router.get("/projects", response_model=Page[ProjectView])
async def projects(
    db: DbSession,
    context: ProjectsReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: ProjectStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ProjectView]:
    return await inventory_service.list_projects(
        db, context.organization_id, q=q, status=status, page=page, page_size=page_size
    )


@router.post("/projects", response_model=ProjectView, status_code=201)
async def create_project(
    payload: ProjectCreate, request: Request, db: DbSession, context: ProjectsCreator
) -> ProjectView:
    return await inventory_service.create_project(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/projects/{project_id}", response_model=ProjectView)
async def project(project_id: str, db: DbSession, context: ProjectsReader) -> ProjectView:
    return await inventory_service.get_project(db, context.organization_id, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectView)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    db: DbSession,
    context: ProjectsUpdater,
) -> ProjectView:
    return await inventory_service.update_project(
        db, context.organization_id, project_id, payload, _context(request, context)
    )


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str, request: Request, db: DbSession, context: ProjectsDeleter
) -> None:
    await inventory_service.delete_project(
        db, context.organization_id, project_id, _context(request, context)
    )


@router.get("/projects/{project_id}/towers", response_model=list[TowerView])
async def towers(project_id: str, db: DbSession, context: ProjectsReader) -> list[TowerView]:
    return await inventory_service.list_towers(db, context.organization_id, project_id)


@router.post("/projects/{project_id}/towers", response_model=TowerView, status_code=201)
async def create_tower(
    project_id: str,
    payload: TowerCreate,
    request: Request,
    db: DbSession,
    context: ProjectsCreator,
) -> TowerView:
    return await inventory_service.create_tower(
        db, context.organization_id, project_id, payload, _context(request, context)
    )


@router.patch("/projects/{project_id}/towers/{tower_id}", response_model=TowerView)
async def update_tower(
    project_id: str,
    tower_id: str,
    payload: TowerUpdate,
    request: Request,
    db: DbSession,
    context: ProjectsUpdater,
) -> TowerView:
    return await inventory_service.update_tower(
        db,
        context.organization_id,
        project_id,
        tower_id,
        payload,
        _context(request, context),
    )


@router.delete("/projects/{project_id}/towers/{tower_id}", status_code=204)
async def delete_tower(
    project_id: str,
    tower_id: str,
    request: Request,
    db: DbSession,
    context: ProjectsDeleter,
) -> None:
    await inventory_service.delete_tower(
        db, context.organization_id, project_id, tower_id, _context(request, context)
    )


@router.get("/projects/{project_id}/floors", response_model=list[FloorView])
async def floors(
    project_id: str,
    db: DbSession,
    context: ProjectsReader,
    tower_id: str | None = None,
) -> list[FloorView]:
    return await inventory_service.list_floors(db, context.organization_id, project_id, tower_id)


@router.post("/projects/{project_id}/floors", response_model=FloorView, status_code=201)
async def create_floor(
    project_id: str,
    payload: FloorCreate,
    request: Request,
    db: DbSession,
    context: ProjectsCreator,
) -> FloorView:
    return await inventory_service.create_floor(
        db, context.organization_id, project_id, payload, _context(request, context)
    )


@router.patch("/projects/{project_id}/floors/{floor_id}", response_model=FloorView)
async def update_floor(
    project_id: str,
    floor_id: str,
    payload: FloorUpdate,
    request: Request,
    db: DbSession,
    context: ProjectsUpdater,
) -> FloorView:
    return await inventory_service.update_floor(
        db,
        context.organization_id,
        project_id,
        floor_id,
        payload,
        _context(request, context),
    )


@router.delete("/projects/{project_id}/floors/{floor_id}", status_code=204)
async def delete_floor(
    project_id: str,
    floor_id: str,
    request: Request,
    db: DbSession,
    context: ProjectsDeleter,
) -> None:
    await inventory_service.delete_floor(
        db, context.organization_id, project_id, floor_id, _context(request, context)
    )


@router.post("/projects/{project_id}/units", response_model=UnitView, status_code=201)
async def create_unit(
    project_id: str,
    payload: UnitCreate,
    request: Request,
    db: DbSession,
    context: InventoryCreator,
) -> UnitView:
    return await inventory_service.create_unit(
        db, context.organization_id, project_id, payload, _context(request, context)
    )


@router.get("/inventory/stats", response_model=InventoryStats)
async def stats(db: DbSession, context: InventoryReader) -> InventoryStats:
    return await inventory_service.inventory_stats(db, context.organization_id)


@router.get("/inventory/holds/stats", response_model=HoldStats)
async def hold_stats(db: DbSession, context: InventoryReader) -> HoldStats:
    return await inventory_service.hold_stats(db, context.organization_id)


@router.get("/inventory/holds", response_model=Page[UnitHoldView])
async def holds(
    db: DbSession,
    context: InventoryReader,
    status: HoldStatus | None = None,
    hold_type: HoldType | None = None,
    project_id: str | None = None,
    customer_id: str | None = None,
    salesperson_user_id: str | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[UnitHoldView]:
    return await inventory_service.list_holds(
        db,
        context.organization_id,
        status=status,
        hold_type=hold_type,
        project_id=project_id,
        customer_id=customer_id,
        salesperson_user_id=salesperson_user_id,
        page=page,
        page_size=page_size,
    )


@router.get("/inventory/hold-salespeople", response_model=list[HoldSalespersonOption])
async def hold_salespeople(
    db: DbSession, context: InventoryAssigner
) -> list[HoldSalespersonOption]:
    return await inventory_service.hold_salespeople(db, context.organization_id)


@router.post("/inventory/holds/expire-due", response_model=HoldExpiryResult)
async def expire_holds(db: DbSession, context: InventoryManager) -> HoldExpiryResult:
    count = await inventory_service.expire_due_holds(
        db,
        organization_id=context.organization_id,
        context=None,
    )
    return HoldExpiryResult(expired_count=count, processed_at=datetime.now(UTC))


@router.post("/inventory/holds/{hold_id}/approval", response_model=UnitHoldView)
async def decide_hold(
    hold_id: str,
    payload: HoldApprovalDecision,
    request: Request,
    db: DbSession,
    context: InventoryApprover,
) -> UnitHoldView:
    return await inventory_service.decide_hold(
        db,
        context.organization_id,
        hold_id,
        payload,
        _context(request, context),
    )


@router.get("/inventory/units", response_model=Page[UnitView])
async def units(
    db: DbSession,
    context: InventoryReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    project_id: str | None = None,
    tower_id: str | None = None,
    floor_id: str | None = None,
    status: UnitStatus | None = None,
    unit_type: Annotated[str | None, Query(max_length=80)] = None,
    facing: Annotated[str | None, Query(max_length=40)] = None,
    bedrooms: Annotated[int | None, Query(ge=0, le=100)] = None,
    min_area: Annotated[float | None, Query(gt=0)] = None,
    max_area: Annotated[float | None, Query(gt=0)] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    amenity: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[UnitView]:
    return await inventory_service.search_units(
        db,
        context.organization_id,
        q=q,
        project_id=project_id,
        tower_id=tower_id,
        floor_id=floor_id,
        status=status,
        unit_type=unit_type,
        facing=facing,
        bedrooms=bedrooms,
        min_area=min_area,
        max_area=max_area,
        min_price=min_price,
        max_price=max_price,
        amenity=amenity,
        page=page,
        page_size=page_size,
    )


@router.get("/inventory/units/{unit_id}", response_model=UnitView)
async def unit(unit_id: str, db: DbSession, context: InventoryReader) -> UnitView:
    return await inventory_service.get_unit(db, context.organization_id, unit_id)


@router.get("/inventory/units/{unit_id}/holds", response_model=list[UnitHoldView])
async def unit_hold_history(
    unit_id: str, db: DbSession, context: InventoryReader
) -> list[UnitHoldView]:
    return await inventory_service.hold_history(db, context.organization_id, unit_id)


@router.patch("/inventory/units/{unit_id}", response_model=UnitView)
async def update_unit(
    unit_id: str,
    payload: UnitUpdate,
    request: Request,
    db: DbSession,
    context: InventoryUpdater,
) -> UnitView:
    return await inventory_service.update_unit(
        db, context.organization_id, unit_id, payload, _context(request, context)
    )


@router.delete("/inventory/units/{unit_id}", status_code=204)
async def delete_unit(
    unit_id: str, request: Request, db: DbSession, context: InventoryDeleter
) -> None:
    await inventory_service.delete_unit(
        db, context.organization_id, unit_id, _context(request, context)
    )


@router.post("/inventory/units/{unit_id}/status", response_model=UnitView)
async def transition_unit_status(
    unit_id: str,
    payload: UnitStatusPayload,
    request: Request,
    db: DbSession,
    context: InventoryApprover,
) -> UnitView:
    return await inventory_service.transition_unit_status(
        db, context.organization_id, unit_id, payload.status, _context(request, context)
    )


@router.post("/inventory/units/{unit_id}/hold", response_model=UnitHoldView, status_code=201)
async def create_hold(
    unit_id: str,
    payload: UnitHoldCreate,
    request: Request,
    db: DbSession,
    context: InventoryAssigner,
) -> UnitHoldView:
    return await inventory_service.create_hold(
        db, context.organization_id, unit_id, payload, _context(request, context)
    )


@router.post("/inventory/units/{unit_id}/hold/release", response_model=UnitView)
async def release_hold(
    unit_id: str,
    payload: HoldReleasePayload,
    request: Request,
    db: DbSession,
    context: InventoryAssigner,
) -> UnitView:
    return await inventory_service.release_hold(
        db,
        context.organization_id,
        unit_id,
        payload.reason,
        _context(request, context),
    )


@router.post(
    "/inventory/units/{unit_id}/booking",
    response_model=InventoryBookingView,
    status_code=201,
)
async def initiate_booking(
    unit_id: str,
    payload: BookingInitiate,
    request: Request,
    db: DbSession,
    context: BookingCreator,
) -> InventoryBookingView:
    return await inventory_service.initiate_booking(
        db, context.organization_id, unit_id, payload, _context(request, context)
    )


@router.post("/inventory/bookings/{booking_id}/status", response_model=InventoryBookingView)
async def transition_booking(
    booking_id: str,
    payload: BookingStatusPayload,
    request: Request,
    db: DbSession,
    context: BookingUpdater,
) -> InventoryBookingView:
    if payload.status == "CONFIRMED":
        raise AppError(
            status_code=409,
            code="BOOKING_APPROVAL_REQUIRED",
            message="Bookings can only be confirmed by the complete approval workflow",
        )
    return await inventory_service.transition_booking(
        db,
        context.organization_id,
        booking_id,
        BookingStatus(payload.status),
        _context(request, context),
    )
