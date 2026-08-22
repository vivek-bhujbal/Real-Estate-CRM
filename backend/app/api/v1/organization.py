import csv
import json
from datetime import datetime
from io import StringIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import DbSession, SecurityContext, mutation_context, require_permissions
from app.core.responses import PRIVATE_FILE_HEADERS
from app.schemas.organization import (
    AuditFilterOptions,
    AuditLogView,
    BranchCreate,
    BranchUpdate,
    BranchView,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentView,
    OrganizationManagementView,
    OrganizationUpdate,
    Page,
    TeamCreate,
    TeamUpdate,
    TeamView,
    TerritoryCreate,
    TerritoryUpdate,
    TerritoryView,
    UserCreate,
    UserManagementView,
    UserUpdate,
)
from app.services import organization as organization_service

router = APIRouter(prefix="/organization", tags=["Organization management"])

OrganizationReader = Annotated[SecurityContext, Depends(require_permissions("organization.view"))]
OrganizationUpdater = Annotated[
    SecurityContext, Depends(require_permissions("organization.update"))
]
BranchesReader = Annotated[SecurityContext, Depends(require_permissions("branches.view"))]
BranchesCreator = Annotated[SecurityContext, Depends(require_permissions("branches.create"))]
BranchesUpdater = Annotated[SecurityContext, Depends(require_permissions("branches.update"))]
BranchesDeleter = Annotated[SecurityContext, Depends(require_permissions("branches.delete"))]
DepartmentsReader = Annotated[SecurityContext, Depends(require_permissions("departments.view"))]
DepartmentsCreator = Annotated[SecurityContext, Depends(require_permissions("departments.create"))]
DepartmentsUpdater = Annotated[SecurityContext, Depends(require_permissions("departments.update"))]
DepartmentsDeleter = Annotated[SecurityContext, Depends(require_permissions("departments.delete"))]
UsersReader = Annotated[SecurityContext, Depends(require_permissions("users.view"))]
UsersCreator = Annotated[SecurityContext, Depends(require_permissions("users.create"))]
UsersUpdater = Annotated[SecurityContext, Depends(require_permissions("users.update"))]
UsersDeleter = Annotated[SecurityContext, Depends(require_permissions("users.delete"))]
TeamsReader = Annotated[SecurityContext, Depends(require_permissions("teams.view"))]
TeamsCreator = Annotated[SecurityContext, Depends(require_permissions("teams.create"))]
TeamsUpdater = Annotated[SecurityContext, Depends(require_permissions("teams.update"))]
TeamsDeleter = Annotated[SecurityContext, Depends(require_permissions("teams.delete"))]
TerritoriesReader = Annotated[SecurityContext, Depends(require_permissions("territories.view"))]
TerritoriesCreator = Annotated[SecurityContext, Depends(require_permissions("territories.create"))]
TerritoriesUpdater = Annotated[SecurityContext, Depends(require_permissions("territories.update"))]
TerritoriesDeleter = Annotated[SecurityContext, Depends(require_permissions("territories.delete"))]
AuditReader = Annotated[SecurityContext, Depends(require_permissions("audit.view"))]
AuditExporter = Annotated[SecurityContext, Depends(require_permissions("audit.export"))]

SearchQuery = Annotated[str | None, Query(max_length=100)]
PageQuery = Annotated[int, Query(ge=1, le=100_000)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]


def _mutation_context(
    request: Request, context: SecurityContext
) -> organization_service.MutationContext:
    return mutation_context(request, context)


@router.get("", response_model=OrganizationManagementView)
async def organization(db: DbSession, context: OrganizationReader) -> OrganizationManagementView:
    return await organization_service.get_organization(db, context.organization_id)


@router.patch("", response_model=OrganizationManagementView)
async def update_organization(
    payload: OrganizationUpdate,
    request: Request,
    db: DbSession,
    context: OrganizationUpdater,
) -> OrganizationManagementView:
    return await organization_service.update_organization(
        db, context.organization_id, payload, _mutation_context(request, context)
    )


@router.get("/branches", response_model=Page[BranchView])
async def branches(
    db: DbSession,
    context: BranchesReader,
    q: SearchQuery = None,
    is_active: bool | None = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[BranchView]:
    return await organization_service.list_branches(
        db,
        context.organization_id,
        q=q,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.post("/branches", response_model=BranchView, status_code=201)
async def create_branch(
    payload: BranchCreate, request: Request, db: DbSession, context: BranchesCreator
) -> BranchView:
    return await organization_service.create_branch(
        db, context.organization_id, payload, _mutation_context(request, context)
    )


@router.put("/branches/{branch_id}", response_model=BranchView)
async def update_branch(
    branch_id: str,
    payload: BranchUpdate,
    request: Request,
    db: DbSession,
    context: BranchesUpdater,
) -> BranchView:
    return await organization_service.update_branch(
        db, context.organization_id, branch_id, payload, _mutation_context(request, context)
    )


@router.delete("/branches/{branch_id}", status_code=204)
async def delete_branch(
    branch_id: str, request: Request, db: DbSession, context: BranchesDeleter
) -> None:
    await organization_service.delete_branch(
        db, context.organization_id, branch_id, _mutation_context(request, context)
    )


@router.get("/departments", response_model=Page[DepartmentView])
async def departments(
    db: DbSession,
    context: DepartmentsReader,
    q: SearchQuery = None,
    is_active: bool | None = None,
    branch_id: str | None = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[DepartmentView]:
    return await organization_service.list_departments(
        db,
        context.organization_id,
        q=q,
        is_active=is_active,
        branch_id=branch_id,
        page=page,
        page_size=page_size,
    )


@router.post("/departments", response_model=DepartmentView, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    db: DbSession,
    context: DepartmentsCreator,
) -> DepartmentView:
    return await organization_service.create_department(
        db, context.organization_id, payload, _mutation_context(request, context)
    )


@router.put("/departments/{department_id}", response_model=DepartmentView)
async def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    request: Request,
    db: DbSession,
    context: DepartmentsUpdater,
) -> DepartmentView:
    return await organization_service.update_department(
        db,
        context.organization_id,
        department_id,
        payload,
        _mutation_context(request, context),
    )


@router.delete("/departments/{department_id}", status_code=204)
async def delete_department(
    department_id: str,
    request: Request,
    db: DbSession,
    context: DepartmentsDeleter,
) -> None:
    await organization_service.delete_department(
        db, context.organization_id, department_id, _mutation_context(request, context)
    )


@router.get("/users", response_model=Page[UserManagementView])
async def users(
    db: DbSession,
    context: UsersReader,
    q: SearchQuery = None,
    is_active: bool | None = None,
    branch_id: str | None = None,
    department_id: str | None = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[UserManagementView]:
    return await organization_service.list_users(
        db,
        context.organization_id,
        q=q,
        is_active=is_active,
        branch_id=branch_id,
        department_id=department_id,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=UserManagementView, status_code=201)
async def create_user(
    payload: UserCreate, request: Request, db: DbSession, context: UsersCreator
) -> UserManagementView:
    return await organization_service.create_user(
        db, context.organization_id, payload, _mutation_context(request, context)
    )


@router.put("/users/{user_id}", response_model=UserManagementView)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    db: DbSession,
    context: UsersUpdater,
) -> UserManagementView:
    return await organization_service.update_user(
        db, context.organization_id, user_id, payload, _mutation_context(request, context)
    )


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str, request: Request, db: DbSession, context: UsersDeleter
) -> None:
    await organization_service.deactivate_user(
        db, context.organization_id, user_id, _mutation_context(request, context)
    )


@router.get("/teams", response_model=Page[TeamView])
async def teams(
    db: DbSession,
    context: TeamsReader,
    q: SearchQuery = None,
    is_active: bool | None = None,
    branch_id: str | None = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[TeamView]:
    return await organization_service.list_teams(
        db,
        context.organization_id,
        q=q,
        is_active=is_active,
        branch_id=branch_id,
        page=page,
        page_size=page_size,
    )


@router.post("/teams", response_model=TeamView, status_code=201)
async def create_team(
    payload: TeamCreate, request: Request, db: DbSession, context: TeamsCreator
) -> TeamView:
    return await organization_service.create_team(
        db, context.organization_id, payload, _mutation_context(request, context)
    )


@router.put("/teams/{team_id}", response_model=TeamView)
async def update_team(
    team_id: str,
    payload: TeamUpdate,
    request: Request,
    db: DbSession,
    context: TeamsUpdater,
) -> TeamView:
    return await organization_service.update_team(
        db, context.organization_id, team_id, payload, _mutation_context(request, context)
    )


@router.delete("/teams/{team_id}", status_code=204)
async def delete_team(team_id: str, request: Request, db: DbSession, context: TeamsDeleter) -> None:
    await organization_service.delete_team(
        db, context.organization_id, team_id, _mutation_context(request, context)
    )


@router.get("/territories", response_model=Page[TerritoryView])
async def territories(
    db: DbSession,
    context: TerritoriesReader,
    q: SearchQuery = None,
    is_active: bool | None = None,
    branch_id: str | None = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[TerritoryView]:
    return await organization_service.list_territories(
        db,
        context.organization_id,
        q=q,
        is_active=is_active,
        branch_id=branch_id,
        page=page,
        page_size=page_size,
    )


@router.post("/territories", response_model=TerritoryView, status_code=201)
async def create_territory(
    payload: TerritoryCreate,
    request: Request,
    db: DbSession,
    context: TerritoriesCreator,
) -> TerritoryView:
    return await organization_service.create_territory(
        db, context.organization_id, payload, _mutation_context(request, context)
    )


@router.put("/territories/{territory_id}", response_model=TerritoryView)
async def update_territory(
    territory_id: str,
    payload: TerritoryUpdate,
    request: Request,
    db: DbSession,
    context: TerritoriesUpdater,
) -> TerritoryView:
    return await organization_service.update_territory(
        db,
        context.organization_id,
        territory_id,
        payload,
        _mutation_context(request, context),
    )


@router.delete("/territories/{territory_id}", status_code=204)
async def delete_territory(
    territory_id: str,
    request: Request,
    db: DbSession,
    context: TerritoriesDeleter,
) -> None:
    await organization_service.delete_territory(
        db, context.organization_id, territory_id, _mutation_context(request, context)
    )


@router.get("/audit-logs/options", response_model=AuditFilterOptions)
async def audit_log_options(db: DbSession, context: AuditReader) -> AuditFilterOptions:
    return await organization_service.audit_filter_options(db, context.organization_id)


@router.get("/audit-logs/export")
async def export_audit_logs(
    db: DbSession,
    context: AuditExporter,
    q: SearchQuery = None,
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    actor_user_id: str | None = Query(default=None, max_length=36),
    entity_id: str | None = Query(default=None, max_length=36),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    rows = await organization_service.audit_export_rows(
        db,
        context.organization_id,
        q=q,
        action=action,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "timestamp",
            "organization_id",
            "organization",
            "actor_user_id",
            "actor",
            "action",
            "entity",
            "entity_id",
            "old_value",
            "new_value",
            "request_id",
            "ip_address",
            "user_agent",
            "device_metadata",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.organization_id,
                _safe_csv(row.organization_name),
                row.actor_user_id,
                _safe_csv(row.actor_name),
                row.action,
                row.entity_type,
                row.entity_id,
                json.dumps(row.old_value, sort_keys=True, default=str),
                json.dumps(row.new_value, sort_keys=True, default=str),
                row.request_id,
                row.ip_address,
                _safe_csv(row.user_agent),
                json.dumps(row.device_metadata, sort_keys=True, default=str),
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            **PRIVATE_FILE_HEADERS,
            "Content-Disposition": 'attachment; filename="audit-log.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/audit-logs", response_model=Page[AuditLogView])
async def audit_logs(
    db: DbSession,
    context: AuditReader,
    q: SearchQuery = None,
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    actor_user_id: str | None = Query(default=None, max_length=36),
    entity_id: str | None = Query(default=None, max_length=36),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> Page[AuditLogView]:
    return await organization_service.list_audit_logs(
        db,
        context.organization_id,
        q=q,
        action=action,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


def _safe_csv(value: str | None) -> str | None:
    if value and value[0] in "=+-@":
        return f"'{value}"
    return value
