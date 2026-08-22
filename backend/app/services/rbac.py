from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import ROLE_TEMPLATE_BY_NAME, permission_is_granted
from app.core.errors import AppError
from app.models.entities import AuditLog, Permission, Role, RolePermission, User, UserRole
from app.schemas.rbac import (
    PermissionView,
    RoleCreate,
    RoleUpdate,
    RoleView,
    UserAccessView,
    UserRoleView,
)


def _db_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def list_permissions(db: AsyncSession, organization_id: str) -> list[PermissionView]:
    permissions = (
        await db.scalars(
            select(Permission)
            .where(Permission.organization_id == organization_id)
            .order_by(Permission.code)
        )
    ).all()
    return [
        PermissionView(
            id=permission.id,
            code=permission.code,
            description=permission.description,
        )
        for permission in permissions
    ]


async def list_roles(db: AsyncSession, organization_id: str) -> list[RoleView]:
    roles = (
        await db.scalars(
            select(Role).where(Role.organization_id == organization_id).order_by(Role.name)
        )
    ).all()
    return await _role_views(db, organization_id, roles)


async def get_role(db: AsyncSession, organization_id: str, role_id: str) -> RoleView:
    role = await _tenant_role(db, organization_id, role_id)
    return (await _role_views(db, organization_id, [role]))[0]


async def list_user_access(db: AsyncSession, organization_id: str) -> list[UserAccessView]:
    users = (
        await db.scalars(
            select(User).where(User.organization_id == organization_id).order_by(User.full_name)
        )
    ).all()
    assignments = (
        await db.execute(
            select(UserRole.user_id, Role.id, Role.name)
            .join(
                Role,
                (Role.organization_id == UserRole.organization_id) & (Role.id == UserRole.role_id),
            )
            .where(UserRole.organization_id == organization_id)
            .order_by(Role.name)
        )
    ).all()
    role_ids: dict[str, list[str]] = {user.id: [] for user in users}
    role_names: dict[str, list[str]] = {user.id: [] for user in users}
    for user_id, role_id, role_name in assignments:
        role_ids[user_id].append(role_id)
        role_names[user_id].append(role_name)
    return [
        UserAccessView(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            role_ids=role_ids[user.id],
            role_names=role_names[user.id],
        )
        for user in users
    ]


async def create_role(
    db: AsyncSession,
    organization_id: str,
    actor_user_id: str,
    payload: RoleCreate,
    actor_permissions: frozenset[str],
    *,
    request_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    device_metadata: dict[str, str] | None,
) -> RoleView:
    permissions = await _permissions_by_code(db, organization_id, payload.permission_codes)
    _ensure_can_grant(actor_permissions, payload.permission_codes)
    role = Role(
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    db.add(role)
    try:
        await db.flush()
        db.add_all(
            [
                RolePermission(
                    organization_id=organization_id,
                    role_id=role.id,
                    permission_id=permission.id,
                )
                for permission in permissions
            ]
        )
        db.add(
            _audit_log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="role.created",
                role_id=role.id,
                previous_value=None,
                new_value=_role_snapshot(role, payload.permission_codes),
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                device_metadata=device_metadata,
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="ROLE_NAME_EXISTS",
            message="A role with that name already exists",
        ) from exc
    await db.refresh(role)
    return (await _role_views(db, organization_id, [role]))[0]


async def update_role(
    db: AsyncSession,
    organization_id: str,
    actor_user_id: str,
    role_id: str,
    payload: RoleUpdate,
    actor_permissions: frozenset[str],
    *,
    request_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    device_metadata: dict[str, str] | None,
) -> RoleView:
    role = await _tenant_role(db, organization_id, role_id, lock=True)
    administrator_name = "Organization Administrator"
    if role.is_system and role.name == administrator_name:
        raise AppError(
            status_code=409,
            code="SYSTEM_ROLE_IMMUTABLE",
            message="The Organization Administrator role cannot be changed",
        )
    if role.is_system and "name" in payload.model_fields_set and payload.name != role.name:
        raise AppError(
            status_code=409,
            code="SYSTEM_ROLE_NAME_IMMUTABLE",
            message="Built-in role names cannot be changed",
        )

    current_permissions = await _permission_codes_for_roles(db, organization_id, [role.id])
    previous_value = _role_snapshot(role, current_permissions.get(role.id, []))
    next_permission_codes = (
        payload.permission_codes
        if payload.permission_codes is not None
        else current_permissions.get(role.id, [])
    )
    permissions = await _permissions_by_code(db, organization_id, next_permission_codes)
    if payload.permission_codes is not None:
        _ensure_can_grant(actor_permissions, next_permission_codes)

    if "name" in payload.model_fields_set and payload.name is not None:
        role.name = payload.name
    if "description" in payload.model_fields_set:
        role.description = payload.description
    if payload.permission_codes is not None:
        await db.execute(
            delete(RolePermission).where(
                RolePermission.organization_id == organization_id,
                RolePermission.role_id == role.id,
            )
        )
        db.add_all(
            [
                RolePermission(
                    organization_id=organization_id,
                    role_id=role.id,
                    permission_id=permission.id,
                )
                for permission in permissions
            ]
        )
    role.updated_at = _db_now()

    db.add(
        _audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="role.updated",
            role_id=role.id,
            previous_value=previous_value,
            new_value=_role_snapshot(role, next_permission_codes),
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_metadata=device_metadata,
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="ROLE_NAME_EXISTS",
            message="A role with that name already exists",
        ) from exc
    await db.refresh(role)
    return (await _role_views(db, organization_id, [role]))[0]


async def delete_role(
    db: AsyncSession,
    organization_id: str,
    actor_user_id: str,
    role_id: str,
    *,
    request_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    device_metadata: dict[str, str] | None,
) -> None:
    role = await _tenant_role(db, organization_id, role_id, lock=True)
    if role.is_system:
        raise AppError(
            status_code=409,
            code="SYSTEM_ROLE_IMMUTABLE",
            message="System roles cannot be deleted",
        )
    assignment_count = int(
        (
            await db.scalar(
                select(func.count())
                .select_from(UserRole)
                .where(
                    UserRole.organization_id == organization_id,
                    UserRole.role_id == role.id,
                )
            )
        )
        or 0
    )
    if assignment_count:
        raise AppError(
            status_code=409,
            code="ROLE_IN_USE",
            message="Remove this role from all users before deleting it",
        )
    permission_codes = await _permission_codes_for_roles(db, organization_id, [role.id])
    db.add(
        _audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="role.deleted",
            role_id=role.id,
            previous_value=_role_snapshot(role, permission_codes.get(role.id, [])),
            new_value=None,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_metadata=device_metadata,
        )
    )
    await db.execute(
        delete(RolePermission).where(
            RolePermission.organization_id == organization_id,
            RolePermission.role_id == role.id,
        )
    )
    await db.delete(role)
    await db.commit()


async def replace_user_roles(
    db: AsyncSession,
    organization_id: str,
    actor_user_id: str,
    user_id: str,
    role_ids: list[str],
    actor_permissions: frozenset[str],
    *,
    request_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    device_metadata: dict[str, str] | None,
) -> UserRoleView:
    if user_id == actor_user_id:
        raise AppError(
            status_code=409,
            code="SELF_ROLE_CHANGE_NOT_ALLOWED",
            message="You cannot change your own role assignments",
        )
    user = (
        await db.scalars(
            select(User)
            .where(User.organization_id == organization_id, User.id == user_id)
            .with_for_update()
        )
    ).first()
    if user is None:
        raise _not_found()

    roles = (
        await db.scalars(
            select(Role).where(Role.organization_id == organization_id, Role.id.in_(role_ids))
        )
    ).all()
    if len(roles) != len(role_ids):
        raise AppError(
            status_code=400,
            code="INVALID_ROLE_IDS",
            message="One or more roles are not available in this organization",
        )
    selected_permissions = await _permission_codes_for_roles(db, organization_id, role_ids)
    _ensure_can_grant(
        actor_permissions,
        [code for codes in selected_permissions.values() for code in codes],
    )
    previous_role_ids = list(
        (
            await db.scalars(
                select(UserRole.role_id).where(
                    UserRole.organization_id == organization_id,
                    UserRole.user_id == user.id,
                )
            )
        ).all()
    )
    previous_permissions = await _permission_codes_for_roles(db, organization_id, previous_role_ids)
    _ensure_can_grant(
        actor_permissions,
        [code for codes in previous_permissions.values() for code in codes],
    )
    await _protect_last_administrator(
        db,
        organization_id,
        user,
        previous_role_ids=previous_role_ids,
        next_role_ids=role_ids,
    )
    await db.execute(
        delete(UserRole).where(
            UserRole.organization_id == organization_id,
            UserRole.user_id == user.id,
        )
    )
    db.add_all(
        [
            UserRole(organization_id=organization_id, user_id=user.id, role_id=role.id)
            for role in roles
        ]
    )
    user.auth_version += 1
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="user.roles_updated",
            entity_type="user",
            entity_id=user.id,
            previous_value={"role_ids": sorted(previous_role_ids)},
            new_value={"role_ids": sorted(role_ids)},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_metadata=device_metadata,
            created_at=_db_now(),
        )
    )
    await db.commit()
    return UserRoleView(user_id=user.id, role_ids=sorted(role_ids))


async def _protect_last_administrator(
    db: AsyncSession,
    organization_id: str,
    user: User,
    *,
    previous_role_ids: list[str],
    next_role_ids: list[str],
) -> None:
    administrator_role = (
        await db.scalars(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.name == ROLE_TEMPLATE_BY_NAME["Organization Administrator"].name,
                Role.is_system.is_(True),
            )
        )
    ).first()
    if (
        administrator_role is None
        or administrator_role.id not in previous_role_ids
        or administrator_role.id in next_role_ids
    ):
        return
    other_administrators = int(
        (
            await db.scalar(
                select(func.count(func.distinct(UserRole.user_id)))
                .join(
                    User,
                    (User.organization_id == UserRole.organization_id)
                    & (User.id == UserRole.user_id),
                )
                .where(
                    UserRole.organization_id == organization_id,
                    UserRole.role_id == administrator_role.id,
                    UserRole.user_id != user.id,
                    User.is_active.is_(True),
                )
            )
        )
        or 0
    )
    if other_administrators == 0:
        raise AppError(
            status_code=409,
            code="LAST_ADMINISTRATOR_REQUIRED",
            message="At least one active Organization Administrator is required",
        )


async def _tenant_role(
    db: AsyncSession, organization_id: str, role_id: str, *, lock: bool = False
) -> Role:
    statement = select(Role).where(Role.organization_id == organization_id, Role.id == role_id)
    if lock:
        statement = statement.with_for_update()
    role = (await db.scalars(statement)).first()
    if role is None:
        raise _not_found()
    return role


async def _permissions_by_code(
    db: AsyncSession, organization_id: str, permission_codes: Sequence[str]
) -> list[Permission]:
    if not permission_codes:
        return []
    permissions = list(
        (
            await db.scalars(
                select(Permission).where(
                    Permission.organization_id == organization_id,
                    Permission.code.in_(permission_codes),
                )
            )
        ).all()
    )
    if len(permissions) != len(permission_codes):
        found = {permission.code for permission in permissions}
        invalid = sorted(set(permission_codes) - found)
        raise AppError(
            status_code=400,
            code="INVALID_PERMISSION_CODES",
            message="One or more permissions are not available in this organization",
            details={"permission_codes": invalid},
        )
    return permissions


async def _role_views(
    db: AsyncSession, organization_id: str, roles: Sequence[Role]
) -> list[RoleView]:
    if not roles:
        return []
    role_ids = [role.id for role in roles]
    permissions = await _permission_codes_for_roles(db, organization_id, role_ids)
    count_rows = (
        await db.execute(
            select(UserRole.role_id, func.count(UserRole.id))
            .where(
                UserRole.organization_id == organization_id,
                UserRole.role_id.in_(role_ids),
            )
            .group_by(UserRole.role_id)
        )
    ).all()
    counts: dict[str, int] = {
        role_id: int(assignment_count) for role_id, assignment_count in count_rows
    }
    return [
        RoleView(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            permission_codes=permissions.get(role.id, []),
            user_count=int(counts.get(role.id, 0)),
            created_at=role.created_at,
            updated_at=role.updated_at,
        )
        for role in roles
    ]


async def _permission_codes_for_roles(
    db: AsyncSession, organization_id: str, role_ids: Sequence[str]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {role_id: [] for role_id in role_ids}
    if not role_ids:
        return result
    rows = (
        await db.execute(
            select(RolePermission.role_id, Permission.code)
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                RolePermission.organization_id == organization_id,
                RolePermission.role_id.in_(role_ids),
            )
            .order_by(Permission.code)
        )
    ).all()
    for role_id, code in rows:
        result[role_id].append(code)
    return result


def _role_snapshot(role: Role, permission_codes: Sequence[str]) -> dict[str, object]:
    return {
        "name": role.name,
        "description": role.description,
        "permission_codes": sorted(permission_codes),
    }


def _ensure_can_grant(actor_permissions: frozenset[str], permission_codes: Sequence[str]) -> None:
    forbidden = sorted(
        code for code in set(permission_codes) if not permission_is_granted(actor_permissions, code)
    )
    if forbidden:
        raise AppError(
            status_code=403,
            code="PERMISSION_GRANT_NOT_ALLOWED",
            message="You cannot grant permissions that you do not hold",
            details={"permission_codes": forbidden},
        )


def _audit_log(
    *,
    organization_id: str,
    actor_user_id: str,
    action: str,
    role_id: str,
    previous_value: dict[str, object] | None,
    new_value: dict[str, object] | None,
    request_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    device_metadata: dict[str, str] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type="role",
        entity_id=role_id,
        previous_value=previous_value,
        new_value=new_value,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        device_metadata=device_metadata,
        created_at=_db_now(),
    )


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested resource was not found",
    )
