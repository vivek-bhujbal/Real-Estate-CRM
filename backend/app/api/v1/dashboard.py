from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import ColumnElement, func, select

from app.api.dependencies import DbSession, require_permission
from app.models.entities import Booking, Lead, Project, Unit, UnitStatus, User
from app.schemas.dashboard import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    db: DbSession,
    user: Annotated[User, Depends(require_permission("dashboard.read"))],
) -> DashboardSummary:
    organization_id = user.organization_id

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
