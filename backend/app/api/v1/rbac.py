from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.schemas.rbac import (
    PermissionView,
    RoleCreate,
    RoleUpdate,
    RoleView,
    UserAccessView,
    UserRoleAssignment,
    UserRoleView,
)
from app.services import rbac as rbac_service

router = APIRouter(prefix="/rbac", tags=["Roles and permissions"])

RolesReader = Annotated[SecurityContext, Depends(require_permissions("roles.view"))]
RolesCreator = Annotated[SecurityContext, Depends(require_permissions("roles.create"))]
RolesUpdater = Annotated[SecurityContext, Depends(require_permissions("roles.update"))]
RolesDeleter = Annotated[SecurityContext, Depends(require_permissions("roles.delete"))]
AssignmentManager = Annotated[
    SecurityContext,
    Depends(require_permissions("roles.assign", "users.assign")),
]
UsersReader = Annotated[SecurityContext, Depends(require_permissions("users.view"))]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/permissions", response_model=list[PermissionView])
async def permissions(db: DbSession, context: RolesReader) -> list[PermissionView]:
    return await rbac_service.list_permissions(db, context.organization_id)


@router.get("/roles", response_model=list[RoleView])
async def roles(db: DbSession, context: RolesReader) -> list[RoleView]:
    return await rbac_service.list_roles(db, context.organization_id)


@router.get("/roles/{role_id}", response_model=RoleView)
async def role(role_id: str, db: DbSession, context: RolesReader) -> RoleView:
    return await rbac_service.get_role(db, context.organization_id, role_id)


@router.get("/users", response_model=list[UserAccessView])
async def users(db: DbSession, context: UsersReader) -> list[UserAccessView]:
    return await rbac_service.list_user_access(db, context.organization_id)


@router.post("/roles", response_model=RoleView, status_code=201)
async def create_role(
    payload: RoleCreate,
    request: Request,
    db: DbSession,
    context: RolesCreator,
) -> RoleView:
    return await rbac_service.create_role(
        db,
        context.organization_id,
        context.user.id,
        payload,
        context.permissions,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )


@router.patch("/roles/{role_id}", response_model=RoleView)
async def update_role(
    role_id: str,
    payload: RoleUpdate,
    request: Request,
    db: DbSession,
    context: RolesUpdater,
) -> RoleView:
    return await rbac_service.update_role(
        db,
        context.organization_id,
        context.user.id,
        role_id,
        payload,
        context.permissions,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: str,
    request: Request,
    db: DbSession,
    context: RolesDeleter,
) -> None:
    await rbac_service.delete_role(
        db,
        context.organization_id,
        context.user.id,
        role_id,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )


@router.put("/users/{user_id}/roles", response_model=UserRoleView)
async def replace_user_roles(
    user_id: str,
    payload: UserRoleAssignment,
    request: Request,
    db: DbSession,
    context: AssignmentManager,
) -> UserRoleView:
    return await rbac_service.replace_user_roles(
        db,
        context.organization_id,
        context.user.id,
        user_id,
        payload.role_ids,
        context.permissions,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )
