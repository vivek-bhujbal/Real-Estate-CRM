from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import Any

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.entities import (
    AuditLog,
    Branch,
    Department,
    Organization,
    RefreshToken,
    Role,
    Team,
    TeamMember,
    Territory,
    User,
    UserRole,
)
from app.schemas.organization import (
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


@dataclass(frozen=True, slots=True)
class MutationContext:
    actor_user_id: str
    permissions: frozenset[str]
    request_id: str | None
    ip_address: str | None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_permission(context: MutationContext, permission: str) -> None:
    if not permission_is_granted(context.permissions, permission):
        raise AppError(
            status_code=403,
            code="PERMISSION_DENIED",
            message="You do not have permission to perform this assignment",
        )


def _organization_view(organization: Organization) -> OrganizationManagementView:
    return OrganizationManagementView(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        legal_name=organization.legal_name,
        contact_email=organization.contact_email,
        contact_phone=organization.contact_phone,
        timezone=organization.timezone,
        currency=organization.currency,
        date_format=organization.date_format,
        is_active=organization.is_active,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


async def get_organization(db: AsyncSession, organization_id: str) -> OrganizationManagementView:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise _not_found()
    return _organization_view(organization)


async def update_organization(
    db: AsyncSession,
    organization_id: str,
    payload: OrganizationUpdate,
    context: MutationContext,
) -> OrganizationManagementView:
    organization = (
        await db.scalars(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
    ).first()
    if organization is None:
        raise _not_found()
    before = _organization_snapshot(organization)
    for field in payload.model_fields_set:
        setattr(organization, field, getattr(payload, field))
    organization.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "organization.updated",
            "organization",
            organization.id,
            before,
            _organization_snapshot(organization),
        )
    )
    await db.commit()
    await db.refresh(organization)
    return _organization_view(organization)


async def list_branches(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    is_active: bool | None,
    page: int,
    page_size: int,
) -> Page[BranchView]:
    filters: list[Any] = [Branch.organization_id == organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Branch.name.ilike(pattern), Branch.code.ilike(pattern)))
    if is_active is not None:
        filters.append(Branch.is_active == is_active)
    total = await _count(db, Branch, filters)
    department_count = (
        select(func.count(Department.id))
        .where(
            Department.organization_id == Branch.organization_id,
            Department.branch_id == Branch.id,
        )
        .correlate(Branch)
        .scalar_subquery()
    )
    user_count = (
        select(func.count(User.id))
        .where(User.organization_id == Branch.organization_id, User.branch_id == Branch.id)
        .correlate(Branch)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Branch, department_count, user_count)
            .where(*filters)
            .order_by(Branch.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        BranchView(
            id=branch.id,
            name=branch.name,
            code=branch.code,
            is_active=branch.is_active,
            department_count=int(departments),
            user_count=int(users),
            created_at=branch.created_at,
            updated_at=branch.updated_at,
        )
        for branch, departments, users in rows
    ]
    return _page(items, total, page, page_size)


async def create_branch(
    db: AsyncSession,
    organization_id: str,
    payload: BranchCreate,
    context: MutationContext,
) -> BranchView:
    branch = Branch(organization_id=organization_id, **payload.model_dump())
    db.add(branch)
    await _flush_conflict(db, "BRANCH_CODE_EXISTS", "A branch with that code already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "branch.created",
            "branch",
            branch.id,
            None,
            _branch_snapshot(branch),
        )
    )
    await _commit_conflict(db, "BRANCH_CODE_EXISTS", "A branch with that code already exists")
    await db.refresh(branch)
    return _branch_view(branch)


async def update_branch(
    db: AsyncSession,
    organization_id: str,
    branch_id: str,
    payload: BranchUpdate,
    context: MutationContext,
) -> BranchView:
    branch = await _tenant_entity(db, Branch, organization_id, branch_id, lock=True)
    before = _branch_snapshot(branch)
    for field, value in payload.model_dump().items():
        setattr(branch, field, value)
    branch.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "branch.updated",
            "branch",
            branch.id,
            before,
            _branch_snapshot(branch),
        )
    )
    await _commit_conflict(db, "BRANCH_CODE_EXISTS", "A branch with that code already exists")
    await db.refresh(branch)
    return _branch_view(branch)


async def delete_branch(
    db: AsyncSession, organization_id: str, branch_id: str, context: MutationContext
) -> None:
    branch = await _tenant_entity(db, Branch, organization_id, branch_id, lock=True)
    db.add(
        _audit(
            organization_id,
            context,
            "branch.deleted",
            "branch",
            branch.id,
            _branch_snapshot(branch),
            None,
        )
    )
    await db.delete(branch)
    await _commit_in_use(db, "Branch")


async def list_departments(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    is_active: bool | None,
    branch_id: str | None,
    page: int,
    page_size: int,
) -> Page[DepartmentView]:
    filters: list[Any] = [Department.organization_id == organization_id]
    if q:
        filters.append(Department.name.ilike(f"%{q.strip()}%"))
    if is_active is not None:
        filters.append(Department.is_active == is_active)
    if branch_id:
        filters.append(Department.branch_id == branch_id)
    total = await _count(db, Department, filters)
    user_count = (
        select(func.count(User.id))
        .where(
            User.organization_id == Department.organization_id,
            User.department_id == Department.id,
        )
        .correlate(Department)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Department, Branch.name, user_count)
            .outerjoin(
                Branch,
                (Branch.organization_id == Department.organization_id)
                & (Branch.id == Department.branch_id),
            )
            .where(*filters)
            .order_by(Department.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        DepartmentView(
            id=department.id,
            name=department.name,
            branch_id=department.branch_id,
            branch_name=branch_name,
            is_active=department.is_active,
            user_count=int(users),
            created_at=department.created_at,
            updated_at=department.updated_at,
        )
        for department, branch_name, users in rows
    ]
    return _page(items, total, page, page_size)


async def create_department(
    db: AsyncSession,
    organization_id: str,
    payload: DepartmentCreate,
    context: MutationContext,
) -> DepartmentView:
    if payload.branch_id:
        _require_permission(context, "departments.assign")
    await _validate_branch(db, organization_id, payload.branch_id)
    department = Department(organization_id=organization_id, **payload.model_dump())
    db.add(department)
    await _flush_conflict(
        db, "DEPARTMENT_EXISTS", "A department with that name already exists in the branch"
    )
    db.add(
        _audit(
            organization_id,
            context,
            "department.created",
            "department",
            department.id,
            None,
            _department_snapshot(department),
        )
    )
    await _commit_conflict(
        db, "DEPARTMENT_EXISTS", "A department with that name already exists in the branch"
    )
    await db.refresh(department)
    return await _department_view(db, department)


async def update_department(
    db: AsyncSession,
    organization_id: str,
    department_id: str,
    payload: DepartmentUpdate,
    context: MutationContext,
) -> DepartmentView:
    department = await _tenant_entity(db, Department, organization_id, department_id, lock=True)
    if payload.branch_id != department.branch_id:
        _require_permission(context, "departments.assign")
    await _validate_branch(db, organization_id, payload.branch_id)
    before = _department_snapshot(department)
    for field, value in payload.model_dump().items():
        setattr(department, field, value)
    department.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "department.updated",
            "department",
            department.id,
            before,
            _department_snapshot(department),
        )
    )
    await _commit_conflict(
        db, "DEPARTMENT_EXISTS", "A department with that name already exists in the branch"
    )
    await db.refresh(department)
    return await _department_view(db, department)


async def delete_department(
    db: AsyncSession, organization_id: str, department_id: str, context: MutationContext
) -> None:
    department = await _tenant_entity(db, Department, organization_id, department_id, lock=True)
    db.add(
        _audit(
            organization_id,
            context,
            "department.deleted",
            "department",
            department.id,
            _department_snapshot(department),
            None,
        )
    )
    await db.delete(department)
    await _commit_in_use(db, "Department")


async def list_users(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    is_active: bool | None,
    branch_id: str | None,
    department_id: str | None,
    page: int,
    page_size: int,
) -> Page[UserManagementView]:
    filters: list[Any] = [User.organization_id == organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    if is_active is not None:
        filters.append(User.is_active == is_active)
    if branch_id:
        filters.append(User.branch_id == branch_id)
    if department_id:
        filters.append(User.department_id == department_id)
    total = await _count(db, User, filters)
    users = list(
        (
            await db.scalars(
                select(User)
                .where(*filters)
                .order_by(User.full_name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return _page(await _user_views(db, organization_id, users), total, page, page_size)


async def create_user(
    db: AsyncSession,
    organization_id: str,
    payload: UserCreate,
    context: MutationContext,
) -> UserManagementView:
    if payload.branch_id or payload.department_id:
        _require_permission(context, "users.assign")
    await _validate_user_structure(db, organization_id, payload.branch_id, payload.department_id)
    values = payload.model_dump(exclude={"password"})
    user = User(
        organization_id=organization_id,
        password_hash=hash_password(payload.password),
        **values,
    )
    db.add(user)
    await _flush_conflict(db, "USER_EMAIL_EXISTS", "A user with that email already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "user.created",
            "user",
            user.id,
            None,
            _user_snapshot(user),
        )
    )
    await _commit_conflict(db, "USER_EMAIL_EXISTS", "A user with that email already exists")
    await db.refresh(user)
    return (await _user_views(db, organization_id, [user]))[0]


async def update_user(
    db: AsyncSession,
    organization_id: str,
    user_id: str,
    payload: UserUpdate,
    context: MutationContext,
) -> UserManagementView:
    user = await _tenant_entity(db, User, organization_id, user_id, lock=True)
    if user.id == context.actor_user_id and not payload.is_active:
        raise AppError(
            status_code=409,
            code="SELF_DEACTIVATION_NOT_ALLOWED",
            message="You cannot deactivate your own account",
        )
    if payload.branch_id != user.branch_id or payload.department_id != user.department_id:
        _require_permission(context, "users.assign")
    await _validate_user_structure(db, organization_id, payload.branch_id, payload.department_id)
    before = _user_snapshot(user)
    for field, value in payload.model_dump().items():
        setattr(user, field, value)
    if before["is_active"] and not user.is_active:
        user.auth_version += 1
        await _revoke_sessions(db, organization_id, user.id)
    user.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "user.updated",
            "user",
            user.id,
            before,
            _user_snapshot(user),
        )
    )
    await _commit_conflict(db, "USER_EMAIL_EXISTS", "A user with that email already exists")
    await db.refresh(user)
    return (await _user_views(db, organization_id, [user]))[0]


async def deactivate_user(
    db: AsyncSession, organization_id: str, user_id: str, context: MutationContext
) -> None:
    user = await _tenant_entity(db, User, organization_id, user_id, lock=True)
    if user.id == context.actor_user_id:
        raise AppError(
            status_code=409,
            code="SELF_DEACTIVATION_NOT_ALLOWED",
            message="You cannot deactivate your own account",
        )
    before = _user_snapshot(user)
    user.is_active = False
    user.auth_version += 1
    user.updated_at = _now()
    await _revoke_sessions(db, organization_id, user.id)
    db.add(
        _audit(
            organization_id,
            context,
            "user.deactivated",
            "user",
            user.id,
            before,
            _user_snapshot(user),
        )
    )
    await db.commit()


async def list_teams(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    is_active: bool | None,
    branch_id: str | None,
    page: int,
    page_size: int,
) -> Page[TeamView]:
    filters: list[Any] = [Team.organization_id == organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Team.name.ilike(pattern), Team.code.ilike(pattern)))
    if is_active is not None:
        filters.append(Team.is_active == is_active)
    if branch_id:
        filters.append(Team.branch_id == branch_id)
    total = await _count(db, Team, filters)
    teams = list(
        (
            await db.scalars(
                select(Team)
                .where(*filters)
                .order_by(Team.name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return _page(await _team_views(db, organization_id, teams), total, page, page_size)


async def create_team(
    db: AsyncSession,
    organization_id: str,
    payload: TeamCreate,
    context: MutationContext,
) -> TeamView:
    if payload.branch_id or payload.manager_user_id or payload.member_ids:
        _require_permission(context, "teams.assign")
    await _validate_branch(db, organization_id, payload.branch_id)
    await _validate_users(db, organization_id, payload.member_ids, payload.manager_user_id)
    values = payload.model_dump(exclude={"member_ids"})
    team = Team(organization_id=organization_id, **values)
    db.add(team)
    await _flush_conflict(db, "TEAM_CODE_EXISTS", "A team with that code already exists")
    db.add_all(
        [
            TeamMember(organization_id=organization_id, team_id=team.id, user_id=user_id)
            for user_id in payload.member_ids
        ]
    )
    db.add(
        _audit(
            organization_id,
            context,
            "team.created",
            "team",
            team.id,
            None,
            _team_snapshot(team, payload.member_ids),
        )
    )
    await _commit_conflict(db, "TEAM_CODE_EXISTS", "A team with that code already exists")
    await db.refresh(team)
    return (await _team_views(db, organization_id, [team]))[0]


async def update_team(
    db: AsyncSession,
    organization_id: str,
    team_id: str,
    payload: TeamUpdate,
    context: MutationContext,
) -> TeamView:
    team = await _tenant_entity(db, Team, organization_id, team_id, lock=True)
    await _validate_branch(db, organization_id, payload.branch_id)
    await _validate_users(db, organization_id, payload.member_ids, payload.manager_user_id)
    current_members = list(
        (
            await db.scalars(
                select(TeamMember.user_id).where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id == team.id,
                )
            )
        ).all()
    )
    if (
        payload.branch_id != team.branch_id
        or payload.manager_user_id != team.manager_user_id
        or set(payload.member_ids) != set(current_members)
    ):
        _require_permission(context, "teams.assign")
    before = _team_snapshot(team, current_members)
    for field, value in payload.model_dump(exclude={"member_ids"}).items():
        setattr(team, field, value)
    team.updated_at = _now()
    await db.execute(
        delete(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.team_id == team.id,
        )
    )
    db.add_all(
        [
            TeamMember(organization_id=organization_id, team_id=team.id, user_id=user_id)
            for user_id in payload.member_ids
        ]
    )
    db.add(
        _audit(
            organization_id,
            context,
            "team.updated",
            "team",
            team.id,
            before,
            _team_snapshot(team, payload.member_ids),
        )
    )
    await _commit_conflict(db, "TEAM_CODE_EXISTS", "A team with that code already exists")
    await db.refresh(team)
    return (await _team_views(db, organization_id, [team]))[0]


async def delete_team(
    db: AsyncSession, organization_id: str, team_id: str, context: MutationContext
) -> None:
    team = await _tenant_entity(db, Team, organization_id, team_id, lock=True)
    members = list(
        (
            await db.scalars(
                select(TeamMember.user_id).where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id == team.id,
                )
            )
        ).all()
    )
    db.add(
        _audit(
            organization_id,
            context,
            "team.deleted",
            "team",
            team.id,
            _team_snapshot(team, members),
            None,
        )
    )
    await db.execute(
        delete(TeamMember).where(
            TeamMember.organization_id == organization_id, TeamMember.team_id == team.id
        )
    )
    await db.delete(team)
    await db.commit()


async def list_territories(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    is_active: bool | None,
    branch_id: str | None,
    page: int,
    page_size: int,
) -> Page[TerritoryView]:
    filters: list[Any] = [Territory.organization_id == organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Territory.name.ilike(pattern), Territory.code.ilike(pattern)))
    if is_active is not None:
        filters.append(Territory.is_active == is_active)
    if branch_id:
        filters.append(Territory.branch_id == branch_id)
    total = await _count(db, Territory, filters)
    territories = list(
        (
            await db.scalars(
                select(Territory)
                .where(*filters)
                .order_by(Territory.name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return _page(await _territory_views(db, organization_id, territories), total, page, page_size)


async def create_territory(
    db: AsyncSession,
    organization_id: str,
    payload: TerritoryCreate,
    context: MutationContext,
) -> TerritoryView:
    if payload.branch_id or payload.manager_user_id:
        _require_permission(context, "territories.assign")
    await _validate_branch(db, organization_id, payload.branch_id)
    await _validate_users(db, organization_id, [], payload.manager_user_id)
    if payload.parent_id:
        await _tenant_entity(db, Territory, organization_id, payload.parent_id)
    territory = Territory(organization_id=organization_id, **payload.model_dump())
    db.add(territory)
    await _flush_conflict(db, "TERRITORY_CODE_EXISTS", "A territory with that code already exists")
    db.add(
        _audit(
            organization_id,
            context,
            "territory.created",
            "territory",
            territory.id,
            None,
            _territory_snapshot(territory),
        )
    )
    await _commit_conflict(db, "TERRITORY_CODE_EXISTS", "A territory with that code already exists")
    await db.refresh(territory)
    return (await _territory_views(db, organization_id, [territory]))[0]


async def update_territory(
    db: AsyncSession,
    organization_id: str,
    territory_id: str,
    payload: TerritoryUpdate,
    context: MutationContext,
) -> TerritoryView:
    territory = await _tenant_entity(db, Territory, organization_id, territory_id, lock=True)
    if (
        payload.branch_id != territory.branch_id
        or payload.manager_user_id != territory.manager_user_id
    ):
        _require_permission(context, "territories.assign")
    await _validate_branch(db, organization_id, payload.branch_id)
    await _validate_users(db, organization_id, [], payload.manager_user_id)
    await _validate_territory_parent(db, organization_id, territory.id, payload.parent_id)
    before = _territory_snapshot(territory)
    for field, value in payload.model_dump().items():
        setattr(territory, field, value)
    territory.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "territory.updated",
            "territory",
            territory.id,
            before,
            _territory_snapshot(territory),
        )
    )
    await _commit_conflict(db, "TERRITORY_CODE_EXISTS", "A territory with that code already exists")
    await db.refresh(territory)
    return (await _territory_views(db, organization_id, [territory]))[0]


async def delete_territory(
    db: AsyncSession, organization_id: str, territory_id: str, context: MutationContext
) -> None:
    territory = await _tenant_entity(db, Territory, organization_id, territory_id, lock=True)
    db.add(
        _audit(
            organization_id,
            context,
            "territory.deleted",
            "territory",
            territory.id,
            _territory_snapshot(territory),
            None,
        )
    )
    await db.delete(territory)
    await _commit_in_use(db, "Territory")


async def list_audit_logs(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    action: str | None,
    entity_type: str | None,
    page: int,
    page_size: int,
) -> Page[AuditLogView]:
    filters: list[Any] = [AuditLog.organization_id == organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                AuditLog.action.ilike(pattern),
                AuditLog.entity_type.ilike(pattern),
                AuditLog.entity_id.ilike(pattern),
            )
        )
    if action:
        filters.append(AuditLog.action == action)
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    total = await _count(db, AuditLog, filters)
    rows = (
        await db.execute(
            select(AuditLog, User.full_name)
            .outerjoin(
                User,
                (User.organization_id == AuditLog.organization_id)
                & (User.id == AuditLog.actor_user_id),
            )
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        AuditLogView(
            id=audit.id,
            actor_user_id=audit.actor_user_id,
            actor_name=actor_name,
            action=audit.action,
            entity_type=audit.entity_type,
            entity_id=audit.entity_id,
            previous_value=audit.previous_value,
            new_value=audit.new_value,
            request_id=audit.request_id,
            ip_address=audit.ip_address,
            created_at=audit.created_at,
        )
        for audit, actor_name in rows
    ]
    return _page(items, total, page, page_size)


async def _count(db: AsyncSession, model: type[Any], filters: list[Any]) -> int:
    return int((await db.scalar(select(func.count()).select_from(model).where(*filters))) or 0)


def _page[ModelT](items: list[ModelT], total: int, page: int, page_size: int) -> Page[ModelT]:
    return Page[ModelT](
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def _tenant_entity[ModelT](
    db: AsyncSession,
    model: type[ModelT],
    organization_id: str,
    entity_id: str,
    *,
    lock: bool = False,
) -> ModelT:
    statement: Select[tuple[ModelT]] = select(model).where(
        model.organization_id == organization_id,  # type: ignore[attr-defined]
        model.id == entity_id,  # type: ignore[attr-defined]
    )
    if lock:
        statement = statement.with_for_update()
    entity = (await db.scalars(statement)).first()
    if entity is None:
        raise _not_found()
    return entity


async def _validate_branch(db: AsyncSession, organization_id: str, branch_id: str | None) -> None:
    if branch_id:
        await _tenant_entity(db, Branch, organization_id, branch_id)


async def _validate_user_structure(
    db: AsyncSession,
    organization_id: str,
    branch_id: str | None,
    department_id: str | None,
) -> None:
    await _validate_branch(db, organization_id, branch_id)
    if not department_id:
        return
    department = await _tenant_entity(db, Department, organization_id, department_id)
    if department.branch_id is not None and department.branch_id != branch_id:
        raise AppError(
            status_code=400,
            code="DEPARTMENT_BRANCH_MISMATCH",
            message="The selected department does not belong to the selected branch",
        )


async def _validate_users(
    db: AsyncSession,
    organization_id: str,
    member_ids: list[str],
    manager_user_id: str | None,
) -> None:
    user_ids = set(member_ids)
    if manager_user_id:
        user_ids.add(manager_user_id)
    if not user_ids:
        return
    found = set(
        (
            await db.scalars(
                select(User.id).where(
                    User.organization_id == organization_id,
                    User.id.in_(user_ids),
                    User.is_active.is_(True),
                )
            )
        ).all()
    )
    if found != user_ids:
        raise AppError(
            status_code=400,
            code="INVALID_USER_IDS",
            message="One or more selected users are unavailable",
        )


async def _validate_territory_parent(
    db: AsyncSession,
    organization_id: str,
    territory_id: str,
    parent_id: str | None,
) -> None:
    if parent_id is None:
        return
    if parent_id == territory_id:
        raise _territory_cycle()
    seen = {territory_id}
    current_id: str | None = parent_id
    while current_id is not None:
        if current_id in seen:
            raise _territory_cycle()
        seen.add(current_id)
        current = await _tenant_entity(db, Territory, organization_id, current_id)
        current_id = current.parent_id


async def _department_view(db: AsyncSession, department: Department) -> DepartmentView:
    branch_name = None
    if department.branch_id:
        branch_name = await db.scalar(
            select(Branch.name).where(
                Branch.organization_id == department.organization_id,
                Branch.id == department.branch_id,
            )
        )
    users = int(
        (
            await db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.organization_id == department.organization_id,
                    User.department_id == department.id,
                )
            )
        )
        or 0
    )
    return DepartmentView(
        id=department.id,
        name=department.name,
        branch_id=department.branch_id,
        branch_name=branch_name,
        is_active=department.is_active,
        user_count=users,
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


async def _user_views(
    db: AsyncSession, organization_id: str, users: list[User]
) -> list[UserManagementView]:
    if not users:
        return []
    user_ids = [user.id for user in users]
    branch_ids = {user.branch_id for user in users if user.branch_id}
    department_ids = {user.department_id for user in users if user.department_id}
    branch_rows = (
        await db.execute(
            select(Branch.id, Branch.name).where(
                Branch.organization_id == organization_id, Branch.id.in_(branch_ids)
            )
        )
    ).all()
    branches: dict[str, str] = {branch_id: name for branch_id, name in branch_rows}
    department_rows = (
        await db.execute(
            select(Department.id, Department.name).where(
                Department.organization_id == organization_id,
                Department.id.in_(department_ids),
            )
        )
    ).all()
    departments: dict[str, str] = {department_id: name for department_id, name in department_rows}
    role_rows = (
        await db.execute(
            select(UserRole.user_id, Role.name)
            .join(
                Role,
                (Role.organization_id == UserRole.organization_id) & (Role.id == UserRole.role_id),
            )
            .where(UserRole.organization_id == organization_id, UserRole.user_id.in_(user_ids))
            .order_by(Role.name)
        )
    ).all()
    role_names: dict[str, list[str]] = {user_id: [] for user_id in user_ids}
    for user_id, role_name in role_rows:
        role_names[user_id].append(role_name)
    return [
        UserManagementView(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            branch_id=user.branch_id,
            branch_name=branches.get(user.branch_id) if user.branch_id else None,
            department_id=user.department_id,
            department_name=departments.get(user.department_id) if user.department_id else None,
            is_active=user.is_active,
            role_names=role_names[user.id],
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )
        for user in users
    ]


async def _team_views(db: AsyncSession, organization_id: str, teams: list[Team]) -> list[TeamView]:
    if not teams:
        return []
    team_ids = [team.id for team in teams]
    user_rows = (
        await db.execute(
            select(User.id, User.full_name).where(User.organization_id == organization_id)
        )
    ).all()
    users: dict[str, str] = {user_id: name for user_id, name in user_rows}
    branch_rows = (
        await db.execute(
            select(Branch.id, Branch.name).where(Branch.organization_id == organization_id)
        )
    ).all()
    branches: dict[str, str] = {branch_id: name for branch_id, name in branch_rows}
    member_rows = (
        await db.execute(
            select(TeamMember.team_id, TeamMember.user_id).where(
                TeamMember.organization_id == organization_id,
                TeamMember.team_id.in_(team_ids),
            )
        )
    ).all()
    member_ids: dict[str, list[str]] = {team_id: [] for team_id in team_ids}
    for team_id, user_id in member_rows:
        member_ids[team_id].append(user_id)
    return [
        TeamView(
            id=team.id,
            name=team.name,
            code=team.code,
            description=team.description,
            branch_id=team.branch_id,
            branch_name=branches.get(team.branch_id) if team.branch_id else None,
            manager_user_id=team.manager_user_id,
            manager_name=users.get(team.manager_user_id) if team.manager_user_id else None,
            member_ids=member_ids[team.id],
            member_names=sorted(
                users[user_id] for user_id in member_ids[team.id] if user_id in users
            ),
            is_active=team.is_active,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )
        for team in teams
    ]


async def _territory_views(
    db: AsyncSession, organization_id: str, territories: list[Territory]
) -> list[TerritoryView]:
    if not territories:
        return []
    branch_rows = (
        await db.execute(
            select(Branch.id, Branch.name).where(Branch.organization_id == organization_id)
        )
    ).all()
    branches: dict[str, str] = {branch_id: name for branch_id, name in branch_rows}
    user_rows = (
        await db.execute(
            select(User.id, User.full_name).where(User.organization_id == organization_id)
        )
    ).all()
    users: dict[str, str] = {user_id: name for user_id, name in user_rows}
    name_rows = (
        await db.execute(
            select(Territory.id, Territory.name).where(Territory.organization_id == organization_id)
        )
    ).all()
    names: dict[str, str] = {territory_id: name for territory_id, name in name_rows}
    return [
        TerritoryView(
            id=territory.id,
            name=territory.name,
            code=territory.code,
            description=territory.description,
            branch_id=territory.branch_id,
            branch_name=branches.get(territory.branch_id) if territory.branch_id else None,
            parent_id=territory.parent_id,
            parent_name=names.get(territory.parent_id) if territory.parent_id else None,
            manager_user_id=territory.manager_user_id,
            manager_name=users.get(territory.manager_user_id)
            if territory.manager_user_id
            else None,
            is_active=territory.is_active,
            created_at=territory.created_at,
            updated_at=territory.updated_at,
        )
        for territory in territories
    ]


async def _revoke_sessions(db: AsyncSession, organization_id: str, user_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.organization_id == organization_id,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
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


async def _commit_in_use(db: AsyncSession, label: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="RESOURCE_IN_USE",
            message=f"{label} cannot be deleted while related records exist",
        ) from exc


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


def _organization_snapshot(organization: Organization) -> dict[str, Any]:
    return {
        "name": organization.name,
        "legal_name": organization.legal_name,
        "contact_email": organization.contact_email,
        "contact_phone": organization.contact_phone,
        "timezone": organization.timezone,
        "currency": organization.currency,
        "date_format": organization.date_format,
    }


def _branch_snapshot(branch: Branch) -> dict[str, Any]:
    return {"name": branch.name, "code": branch.code, "is_active": branch.is_active}


def _branch_view(branch: Branch) -> BranchView:
    return BranchView(
        id=branch.id,
        name=branch.name,
        code=branch.code,
        is_active=branch.is_active,
        created_at=branch.created_at,
        updated_at=branch.updated_at,
    )


def _department_snapshot(department: Department) -> dict[str, Any]:
    return {
        "name": department.name,
        "branch_id": department.branch_id,
        "is_active": department.is_active,
    }


def _user_snapshot(user: User) -> dict[str, Any]:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "branch_id": user.branch_id,
        "department_id": user.department_id,
        "is_active": user.is_active,
        "auth_version": user.auth_version,
    }


def _team_snapshot(team: Team, member_ids: list[str]) -> dict[str, Any]:
    return {
        "name": team.name,
        "code": team.code,
        "description": team.description,
        "branch_id": team.branch_id,
        "manager_user_id": team.manager_user_id,
        "member_ids": sorted(member_ids),
        "is_active": team.is_active,
    }


def _territory_snapshot(territory: Territory) -> dict[str, Any]:
    return {
        "name": territory.name,
        "code": territory.code,
        "description": territory.description,
        "branch_id": territory.branch_id,
        "parent_id": territory.parent_id,
        "manager_user_id": territory.manager_user_id,
        "is_active": territory.is_active,
    }


def _territory_cycle() -> AppError:
    return AppError(
        status_code=400,
        code="TERRITORY_CYCLE",
        message="A territory cannot be its own ancestor",
    )


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested resource was not found",
    )
