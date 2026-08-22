from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import ColumnElement, func, select

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.entities import Booking, Lead, Project, Unit, UnitStatus
from app.schemas.dashboard import DashboardCatalog, DashboardKind, DashboardSummary, DashboardView
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
DashboardReader = Annotated[SecurityContext, Depends(require_permissions("dashboard.view"))]
LegacySummaryReader = Annotated[
    SecurityContext,
    Depends(
        require_permissions(
            "dashboard.view",
            "leads.view",
            "projects.view",
            "inventory.view",
            "bookings.view",
        )
    ),
]


@router.get("/summary", response_model=DashboardSummary, deprecated=True)
async def summary(
    db: DbSession,
    context: LegacySummaryReader,
) -> DashboardSummary:
    organization_id = context.organization_id

    async def count(
        model: type[Lead] | type[Project] | type[Unit] | type[Booking],
        *filters: ColumnElement[bool],
    ) -> int:
        statement = (
            select(func.count()).select_from(model).where(model.organization_id == organization_id)
        )
        if filters:
            statement = statement.where(*filters)
        return int((await db.scalar(statement)) or 0)

    return DashboardSummary(
        leads=await count(Lead),
        projects=await count(Project),
        available_units=await count(Unit, Unit.status == UnitStatus.AVAILABLE),
        bookings=await count(Booking),
    )


@router.get("/catalog", response_model=DashboardCatalog)
async def catalog(context: DashboardReader) -> DashboardCatalog:
    return dashboard_service.available_catalog(context.permissions)


@router.get("/{kind}", response_model=DashboardView)
async def dashboard(
    kind: DashboardKind,
    db: DbSession,
    context: DashboardReader,
) -> DashboardView:
    return await dashboard_service.dashboard_view(
        db,
        context.organization_id,
        context.permissions,
        kind,
        context.user.organization.currency,
    )
