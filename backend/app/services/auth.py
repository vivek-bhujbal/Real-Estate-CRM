import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import PERMISSION_CATALOG, ROLE_TEMPLATES
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_password_reset_token,
    new_refresh_token,
    verify_and_update_password,
    verify_password,
)
from app.models.entities import (
    AuditLog,
    Organization,
    PasswordResetToken,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.schemas.auth import (
    CurrentUserView,
    ForgotPasswordRequest,
    LoginRequest,
    OrganizationRegistration,
    OrganizationView,
    PasswordChangeRequest,
    ResetPasswordRequest,
)


@dataclass(slots=True)
class SessionResult:
    access_token: str
    expires_in: int
    refresh_token: str
    user: CurrentUserView


@dataclass(slots=True)
class PasswordResetDispatch:
    recipient: str
    full_name: str
    token: str


def _db_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def permission_codes(db: AsyncSession, user: User) -> list[str]:
    statement = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user.id,
            UserRole.organization_id == user.organization_id,
            RolePermission.organization_id == user.organization_id,
            Permission.organization_id == user.organization_id,
        )
        .distinct()
        .order_by(Permission.code)
    )
    return list((await db.scalars(statement)).all())


async def current_user_view(db: AsyncSession, user: User) -> CurrentUserView:
    organization = user.organization
    return CurrentUserView(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        organization_id=user.organization_id,
        branch_id=user.branch_id,
        department_id=user.department_id,
        is_active=user.is_active,
        created_at=user.created_at,
        organization=OrganizationView.model_validate(organization),
        permissions=await permission_codes(db, user),
    )


async def register_organization(
    db: AsyncSession,
    payload: OrganizationRegistration,
    *,
    user_agent: str | None,
    ip_address: str | None,
    request_id: str | None,
) -> SessionResult:
    if not get_settings().allow_organization_registration:
        raise AppError(
            status_code=403, code="REGISTRATION_DISABLED", message="Registration is disabled"
        )

    organization = Organization(name=payload.organization_name, slug=payload.organization_slug)
    db.add(organization)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="ORGANIZATION_EXISTS",
            message="That organization slug is already registered",
        ) from exc

    user = User(
        organization_id=organization.id,
        email=str(payload.admin_email),
        full_name=payload.admin_full_name,
        password_hash=hash_password(payload.password),
    )
    permissions = [
        Permission(organization_id=organization.id, code=code, description=description)
        for code, description in PERMISSION_CATALOG.items()
    ]
    roles = [
        Role(
            organization_id=organization.id,
            name=template.name,
            description=template.description,
            is_system=True,
        )
        for template in ROLE_TEMPLATES
    ]
    db.add_all([user, *permissions, *roles])
    await db.flush()
    permission_by_code = {permission.code: permission for permission in permissions}
    role_by_name = {role.name: role for role in roles}
    administrator_role = role_by_name["Organization Administrator"]
    db.add(
        UserRole(
            organization_id=organization.id,
            user_id=user.id,
            role_id=administrator_role.id,
        )
    )
    db.add_all(
        [
            RolePermission(
                organization_id=organization.id,
                role_id=role_by_name[template.name].id,
                permission_id=permission_by_code[code].id,
            )
            for template in ROLE_TEMPLATES
            for code in template.permissions
        ]
    )
    db.add(
        AuditLog(
            organization_id=organization.id,
            actor_user_id=user.id,
            action="organization.created",
            entity_type="organization",
            entity_id=organization.id,
            previous_value=None,
            new_value={"name": organization.name, "slug": organization.slug},
            request_id=request_id,
            ip_address=ip_address,
            created_at=_db_now(),
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="ORGANIZATION_EXISTS",
            message="That organization slug is already registered",
        ) from exc
    await db.refresh(user, attribute_names=["organization"])
    return await _create_session(db, user, user_agent=user_agent, ip_address=ip_address)


async def login(
    db: AsyncSession, payload: LoginRequest, *, user_agent: str | None, ip_address: str | None
) -> SessionResult:
    statement = (
        select(User)
        .join(Organization)
        .options(selectinload(User.organization))
        .where(Organization.slug == payload.organization_slug, User.email == str(payload.email))
    )
    user = (await db.scalars(statement)).first()
    if user is None:
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise AppError(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid organization, email, or password",
        )

    password_valid, updated_hash = verify_and_update_password(payload.password, user.password_hash)
    if not password_valid or not user.is_active or not user.organization.is_active:
        raise AppError(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid organization, email, or password",
        )
    if updated_hash is not None:
        user.password_hash = updated_hash
    user.last_login_at = _db_now()
    return await _create_session(db, user, user_agent=user_agent, ip_address=ip_address)


async def _create_session(
    db: AsyncSession,
    user: User,
    *,
    user_agent: str | None,
    ip_address: str | None,
    family_id: str | None = None,
) -> SessionResult:
    settings = get_settings()
    now = _db_now()
    absolute_expires_at = now + timedelta(days=settings.refresh_token_ttl_days)
    expires_at = min(now + timedelta(days=settings.refresh_token_idle_days), absolute_expires_at)
    session_id = family_id or str(uuid.uuid4())
    raw_refresh, token_digest = new_refresh_token()
    refresh = RefreshToken(
        organization_id=user.organization_id,
        user_id=user.id,
        token_hash=token_digest,
        family_id=session_id,
        expires_at=expires_at,
        absolute_expires_at=absolute_expires_at,
        user_agent=(user_agent or "")[:255] or None,
        ip_address=ip_address,
    )
    db.add(refresh)
    await db.commit()
    access, expires_in = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        session_id=session_id,
        auth_version=user.auth_version,
    )
    return SessionResult(
        access_token=access,
        expires_in=expires_in,
        refresh_token=raw_refresh,
        user=await current_user_view(db, user),
    )


async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
    *,
    user_agent: str | None,
    ip_address: str | None,
) -> SessionResult:
    statement = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    stored = (await db.scalars(statement)).first()
    if stored is None:
        raise AppError(status_code=401, code="INVALID_REFRESH_TOKEN", message="Session expired")
    if stored.revoked_at is not None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_db_now())
        )
        await db.commit()
        raise AppError(status_code=401, code="REFRESH_TOKEN_REUSED", message="Session expired")
    now = _db_now()
    if stored.expires_at <= now or stored.absolute_expires_at <= now:
        stored.revoked_at = _db_now()
        await db.commit()
        raise AppError(status_code=401, code="REFRESH_TOKEN_EXPIRED", message="Session expired")

    user = (
        await db.scalars(
            select(User)
            .options(selectinload(User.organization))
            .where(User.id == stored.user_id, User.organization_id == stored.organization_id)
        )
    ).first()
    if user is None or not user.is_active or not user.organization.is_active:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_db_now())
        )
        await db.commit()
        raise AppError(status_code=401, code="ACCOUNT_DISABLED", message="Session expired")

    raw_refresh, token_digest = new_refresh_token()
    replacement_expires_at = min(
        now + timedelta(days=get_settings().refresh_token_idle_days),
        stored.absolute_expires_at,
    )
    replacement = RefreshToken(
        organization_id=user.organization_id,
        user_id=user.id,
        token_hash=token_digest,
        family_id=stored.family_id,
        expires_at=replacement_expires_at,
        absolute_expires_at=stored.absolute_expires_at,
        user_agent=(user_agent or "")[:255] or None,
        ip_address=ip_address,
    )
    db.add(replacement)
    await db.flush()
    stored.revoked_at = _db_now()
    stored.replaced_by_id = replacement.id
    await db.commit()
    access, expires_in = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        session_id=stored.family_id,
        auth_version=user.auth_version,
    )
    return SessionResult(
        access_token=access,
        expires_in=expires_in,
        refresh_token=raw_refresh,
        user=await current_user_view(db, user),
    )


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    stored = (
        await db.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        )
    ).first()
    if stored is not None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_db_now())
        )
        await db.commit()


async def session_is_active(
    db: AsyncSession, *, organization_id: str, user_id: str, family_id: str
) -> bool:
    now = _db_now()
    statement = (
        select(RefreshToken.id)
        .where(
            RefreshToken.organization_id == organization_id,
            RefreshToken.user_id == user_id,
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
            RefreshToken.absolute_expires_at > now,
        )
        .limit(1)
    )
    return (await db.scalar(statement)) is not None


async def change_password(
    db: AsyncSession,
    user: User,
    payload: PasswordChangeRequest,
    *,
    request_id: str | None,
    ip_address: str | None,
) -> None:
    locked_user = (
        await db.scalars(
            select(User)
            .where(User.id == user.id, User.organization_id == user.organization_id)
            .with_for_update()
        )
    ).first()
    if locked_user is None or not locked_user.is_active:
        raise AppError(status_code=401, code="SESSION_REVOKED", message="Sign in required")
    if not verify_password(payload.current_password, locked_user.password_hash):
        raise AppError(
            status_code=400,
            code="CURRENT_PASSWORD_INVALID",
            message="The current password is incorrect",
        )
    if verify_password(payload.new_password, locked_user.password_hash):
        raise AppError(
            status_code=400,
            code="PASSWORD_REUSE_NOT_ALLOWED",
            message="Choose a password that is different from your current password",
        )

    now = _db_now()
    locked_user.password_hash = hash_password(payload.new_password)
    locked_user.auth_version += 1
    await _revoke_user_sessions(db, locked_user, now=now)
    await _consume_password_reset_tokens(db, locked_user, now=now)
    db.add(
        _security_audit(
            locked_user,
            action="authentication.password_changed",
            request_id=request_id,
            ip_address=ip_address,
        )
    )
    await db.commit()


async def request_password_reset(
    db: AsyncSession,
    payload: ForgotPasswordRequest,
    *,
    request_id: str | None,
    ip_address: str | None,
) -> PasswordResetDispatch | None:
    user = (
        await db.scalars(
            select(User)
            .join(Organization)
            .where(
                Organization.slug == payload.organization_slug,
                Organization.is_active.is_(True),
                User.email == str(payload.email),
                User.is_active.is_(True),
            )
        )
    ).first()
    raw_token, token_hash = new_password_reset_token()
    if user is None:
        # Perform the same entropy and digest work without revealing account existence.
        return None

    now = _db_now()
    await _consume_password_reset_tokens(db, user, now=now)
    db.add(
        PasswordResetToken(
            organization_id=user.organization_id,
            user_id=user.id,
            token_hash=token_hash,
            expires_at=now + timedelta(minutes=get_settings().password_reset_ttl_minutes),
            requested_ip=ip_address,
        )
    )
    db.add(
        _security_audit(
            user,
            action="authentication.password_reset_requested",
            request_id=request_id,
            ip_address=ip_address,
            actor_user_id=None,
        )
    )
    await db.commit()
    return PasswordResetDispatch(
        recipient=user.email,
        full_name=user.full_name,
        token=raw_token,
    )


async def reset_password(
    db: AsyncSession,
    payload: ResetPasswordRequest,
    *,
    request_id: str | None,
    ip_address: str | None,
) -> None:
    token_hash = hash_refresh_token(payload.token)
    result = (
        await db.execute(
            select(PasswordResetToken, User, Organization)
            .join(
                User,
                (User.organization_id == PasswordResetToken.organization_id)
                & (User.id == PasswordResetToken.user_id),
            )
            .join(Organization, Organization.id == PasswordResetToken.organization_id)
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        )
    ).first()
    now = _db_now()
    if result is None:
        raise _invalid_reset_token_error()

    stored, user, organization = result
    if (
        stored.consumed_at is not None
        or stored.expires_at <= now
        or not user.is_active
        or not organization.is_active
    ):
        raise _invalid_reset_token_error()
    if verify_password(payload.new_password, user.password_hash):
        raise AppError(
            status_code=400,
            code="PASSWORD_REUSE_NOT_ALLOWED",
            message="Choose a password that is different from your current password",
        )

    user.password_hash = hash_password(payload.new_password)
    user.auth_version += 1
    await _revoke_user_sessions(db, user, now=now)
    await _consume_password_reset_tokens(db, user, now=now)
    db.add(
        _security_audit(
            user,
            action="authentication.password_reset_completed",
            request_id=request_id,
            ip_address=ip_address,
            actor_user_id=None,
        )
    )
    await db.commit()


async def _revoke_user_sessions(db: AsyncSession, user: User, *, now: datetime) -> None:
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.organization_id == user.organization_id,
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


async def _consume_password_reset_tokens(db: AsyncSession, user: User, *, now: datetime) -> None:
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.organization_id == user.organization_id,
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )


def _security_audit(
    user: User,
    *,
    action: str,
    request_id: str | None,
    ip_address: str | None,
    actor_user_id: str | None = "self",
) -> AuditLog:
    return AuditLog(
        organization_id=user.organization_id,
        actor_user_id=user.id if actor_user_id == "self" else actor_user_id,
        action=action,
        entity_type="user",
        entity_id=user.id,
        previous_value=None,
        new_value={"auth_version": user.auth_version},
        request_id=request_id,
        ip_address=ip_address,
        created_at=_db_now(),
    )


def _invalid_reset_token_error() -> AppError:
    return AppError(
        status_code=400,
        code="INVALID_RESET_TOKEN",
        message="This password reset link is invalid or has expired",
    )
