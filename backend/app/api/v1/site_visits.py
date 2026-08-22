from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DbSession, SecurityContext, mutation_context, require_permissions
from app.models.enums import VisitStatus
from app.schemas.organization import Page
from app.schemas.site_visits import (
    CheckInPayload,
    CheckOutPayload,
    SalespersonOption,
    SiteVisitCreate,
    SiteVisitStats,
    SiteVisitUpdate,
    SiteVisitView,
    VisitStatusPayload,
)
from app.services import site_visits as visit_service
from app.services.organization import MutationContext

router = APIRouter(prefix="/site-visits", tags=["site-visits"])

VisitsReader = Annotated[SecurityContext, Depends(require_permissions("visits.view"))]
VisitsCreator = Annotated[SecurityContext, Depends(require_permissions("visits.create"))]
VisitsUpdater = Annotated[SecurityContext, Depends(require_permissions("visits.update"))]
VisitsDeleter = Annotated[SecurityContext, Depends(require_permissions("visits.delete"))]
VisitsAssigner = Annotated[SecurityContext, Depends(require_permissions("visits.assign"))]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return mutation_context(request, security)


@router.get("", response_model=Page[SiteVisitView])
async def visits(
    db: DbSession,
    context: VisitsReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: VisitStatus | None = None,
    project_id: str | None = None,
    assigned_user_id: str | None = None,
    lead_id: str | None = None,
    customer_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[SiteVisitView]:
    return await visit_service.list_visits(
        db,
        context.organization_id,
        q=q,
        status=status,
        project_id=project_id,
        assigned_user_id=assigned_user_id,
        lead_id=lead_id,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SiteVisitView, status_code=201)
async def create_visit(
    payload: SiteVisitCreate,
    request: Request,
    db: DbSession,
    context: VisitsCreator,
) -> SiteVisitView:
    return await visit_service.create_visit(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/stats", response_model=SiteVisitStats)
async def stats(db: DbSession, context: VisitsReader) -> SiteVisitStats:
    return await visit_service.stats(db, context.organization_id)


@router.get("/salespeople", response_model=list[SalespersonOption])
async def salespeople(db: DbSession, context: VisitsAssigner) -> list[SalespersonOption]:
    return await visit_service.salesperson_options(db, context.organization_id)


@router.get("/calendar", response_model=list[SiteVisitView])
async def calendar(
    db: DbSession,
    context: VisitsReader,
    date_from: datetime,
    date_to: datetime,
    assigned_user_id: str | None = None,
) -> list[SiteVisitView]:
    return await visit_service.calendar_visits(
        db, context.organization_id, date_from, date_to, assigned_user_id
    )


@router.get("/{visit_id}", response_model=SiteVisitView)
async def visit(visit_id: str, db: DbSession, context: VisitsReader) -> SiteVisitView:
    return await visit_service.get_visit(db, context.organization_id, visit_id)


@router.patch("/{visit_id}", response_model=SiteVisitView)
async def update_visit(
    visit_id: str,
    payload: SiteVisitUpdate,
    request: Request,
    db: DbSession,
    context: VisitsUpdater,
) -> SiteVisitView:
    return await visit_service.update_visit(
        db, context.organization_id, visit_id, payload, _context(request, context)
    )


@router.delete("/{visit_id}", status_code=204)
async def delete_visit(
    visit_id: str,
    request: Request,
    db: DbSession,
    context: VisitsDeleter,
) -> None:
    await visit_service.delete_visit(
        db, context.organization_id, visit_id, _context(request, context)
    )


@router.post("/{visit_id}/status", response_model=SiteVisitView)
async def change_status(
    visit_id: str,
    payload: VisitStatusPayload,
    request: Request,
    db: DbSession,
    context: VisitsUpdater,
) -> SiteVisitView:
    return await visit_service.change_status(
        db, context.organization_id, visit_id, payload, _context(request, context)
    )


@router.post("/{visit_id}/check-in", response_model=SiteVisitView)
async def check_in(
    visit_id: str,
    payload: CheckInPayload,
    request: Request,
    db: DbSession,
    context: VisitsUpdater,
) -> SiteVisitView:
    return await visit_service.check_in(
        db, context.organization_id, visit_id, payload, _context(request, context)
    )


@router.post("/{visit_id}/check-out", response_model=SiteVisitView)
async def check_out(
    visit_id: str,
    payload: CheckOutPayload,
    request: Request,
    db: DbSession,
    context: VisitsUpdater,
) -> SiteVisitView:
    return await visit_service.check_out(
        db, context.organization_id, visit_id, payload, _context(request, context)
    )
