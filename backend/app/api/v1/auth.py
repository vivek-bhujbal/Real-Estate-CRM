from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app.api.dependencies import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.schemas.auth import (
    CurrentUserView,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OrganizationRegistration,
    PasswordChangeRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services import auth as auth_service
from app.services.email import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_rate_limit = rate_limit(requests=10, window_seconds=60)
forgot_password_rate_limit = rate_limit(requests=5, window_seconds=3600)
reset_password_rate_limit = rate_limit(requests=10, window_seconds=3600)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, value: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=value,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=f"{settings.api_v1_prefix}/auth",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    _set_no_store(response)


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=f"{settings.api_v1_prefix}/auth",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    _set_no_store(response)


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(get_settings().refresh_cookie_name)


def _validate_cookie_origin(request: Request) -> None:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise AppError(status_code=403, code="ORIGIN_NOT_ALLOWED", message="Request rejected")
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer:
            parsed = urlsplit(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    allowed_origins = {allowed.rstrip("/") for allowed in get_settings().cors_origins}
    if origin is not None and origin.rstrip("/") not in allowed_origins:
        raise AppError(status_code=403, code="ORIGIN_NOT_ALLOWED", message="Request rejected")


def _token_response(result: auth_service.SessionResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=result.user,
    )


@router.post(
    "/register-organization",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(auth_rate_limit)],
)
async def register_organization(
    payload: OrganizationRegistration,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    result = await auth_service.register_organization(
        db,
        payload,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
        request_id=request.state.request_id,
    )
    _set_refresh_cookie(response, result.refresh_token)
    return _token_response(result)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    result = await auth_service.login(
        db,
        payload,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, result.refresh_token)
    return _token_response(result)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    _validate_cookie_origin(request)
    refresh_token = _refresh_cookie(request)
    if not refresh_token:
        raise AppError(status_code=401, code="REFRESH_TOKEN_REQUIRED", message="Session expired")
    result = await auth_service.rotate_refresh_token(
        db,
        refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, result.refresh_token)
    return _token_response(result)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
) -> None:
    _validate_cookie_origin(request)
    refresh_token = _refresh_cookie(request)
    if refresh_token:
        await auth_service.revoke_refresh_token(db, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=CurrentUserView)
async def me(response: Response, db: DbSession, user: CurrentUser) -> CurrentUserView:
    _set_no_store(response)
    return await auth_service.current_user_view(db, user)


@router.post("/change-password", status_code=204, dependencies=[Depends(auth_rate_limit)])
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: DbSession,
    user: CurrentUser,
) -> None:
    await auth_service.change_password(
        db,
        user,
        payload,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )
    _clear_refresh_cookie(response)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=202,
    dependencies=[Depends(forgot_password_rate_limit)],
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> MessageResponse:
    dispatch = await auth_service.request_password_reset(
        db,
        payload,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )
    if dispatch is not None:
        background_tasks.add_task(
            send_password_reset_email,
            recipient=dispatch.recipient,
            full_name=dispatch.full_name,
            token=dispatch.token,
        )
    _set_no_store(response)
    return MessageResponse(
        message="If that account exists, password reset instructions have been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(reset_password_rate_limit)],
)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> MessageResponse:
    await auth_service.reset_password(
        db,
        payload,
        request_id=request.state.request_id,
        ip_address=_client_ip(request),
    )
    _clear_refresh_cookie(response)
    return MessageResponse(message="Your password has been reset. You can now sign in.")
