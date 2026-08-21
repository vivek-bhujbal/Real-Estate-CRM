from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.entities import User
from app.services.auth import permission_codes, session_is_active

DbSession = Annotated[AsyncSession, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise AppError(
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
            message="Sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(credentials.credentials)
        if claims["type"] != "access":
            raise jwt.InvalidTokenError
    except jwt.ExpiredSignatureError as exc:
        raise AppError(
            status_code=401,
            code="ACCESS_TOKEN_EXPIRED",
            message="Session refresh required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.PyJWTError as exc:
        raise AppError(
            status_code=401,
            code="INVALID_ACCESS_TOKEN",
            message="Sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = (
        await db.scalars(
            select(User)
            .options(selectinload(User.organization))
            .where(User.id == claims["sub"], User.organization_id == claims["org"])
        )
    ).first()
    if (
        user is None
        or not user.is_active
        or not user.organization.is_active
        or not isinstance(claims.get("av"), int)
        or user.auth_version != claims["av"]
        or not isinstance(claims.get("sid"), str)
        or not await session_is_active(
            db,
            organization_id=user.organization_id,
            user_id=user.id,
            family_id=claims["sid"],
        )
    ):
        raise AppError(
            status_code=401,
            code="SESSION_REVOKED",
            message="Sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True, slots=True)
class SecurityContext:
    user: User
    permissions: frozenset[str]

    @property
    def organization_id(self) -> str:
        return self.user.organization_id

    def has_permission(self, permission: str) -> bool:
        return permission_is_granted(self.permissions, permission)


async def get_security_context(db: DbSession, user: CurrentUser) -> SecurityContext:
    return SecurityContext(user=user, permissions=frozenset(await permission_codes(db, user)))


CurrentSecurityContext = Annotated[SecurityContext, Depends(get_security_context)]


def require_permission(
    permission: str,
) -> Callable[[DbSession, CurrentUser], Coroutine[Any, Any, User]]:
    async def dependency(db: DbSession, user: CurrentUser) -> User:
        if not permission_is_granted(set(await permission_codes(db, user)), permission):
            raise AppError(
                status_code=403,
                code="PERMISSION_DENIED",
                message="You do not have permission to perform this action",
            )
        return user

    return dependency


def require_permissions(
    *required: str, any_of: bool = False
) -> Callable[[CurrentSecurityContext], Coroutine[Any, Any, SecurityContext]]:
    if not required:
        raise ValueError("At least one permission is required")

    async def dependency(context: CurrentSecurityContext) -> SecurityContext:
        matches = [context.has_permission(permission) for permission in required]
        allowed = any(matches) if any_of else all(matches)
        if not allowed:
            raise AppError(
                status_code=403,
                code="PERMISSION_DENIED",
                message="You do not have permission to perform this action",
            )
        return context

    return dependency


def enforce_organization_scope(context: SecurityContext, organization_id: str) -> None:
    if context.organization_id != organization_id:
        raise AppError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="The requested resource was not found",
        )
