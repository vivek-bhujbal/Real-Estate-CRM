from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.schemas.notifications import (
    DueNotificationResult,
    NotificationMarkAllResult,
    NotificationUnreadCount,
    NotificationView,
)
from app.schemas.organization import Page
from app.services import notifications as service

router = APIRouter(prefix="/notifications", tags=["Notifications"])

Reader = Annotated[SecurityContext, Depends(require_permissions("notifications.view"))]
Updater = Annotated[SecurityContext, Depends(require_permissions("notifications.update"))]
Manager = Annotated[SecurityContext, Depends(require_permissions("notifications.manage"))]


@router.get("", response_model=Page[NotificationView])
async def notifications(
    db: DbSession,
    context: Reader,
    q: str | None = Query(default=None, max_length=100),
    event_type: str | None = Query(default=None, max_length=80),
    unread_only: bool = False,
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationView]:
    return await service.list_notifications(
        db,
        context.organization_id,
        context.user.id,
        q=q,
        event_type=event_type,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=NotificationUnreadCount)
async def notification_unread_count(
    db: DbSession, context: Reader
) -> NotificationUnreadCount:
    return await service.unread_count(db, context.organization_id, context.user.id)


@router.patch("/{notification_id}/read", response_model=NotificationView)
async def read_notification(
    notification_id: str, db: DbSession, context: Updater
) -> NotificationView:
    return await service.mark_read(
        db, context.organization_id, context.user.id, notification_id
    )


@router.post("/read-all", response_model=NotificationMarkAllResult)
async def read_all_notifications(
    db: DbSession, context: Updater
) -> NotificationMarkAllResult:
    marked = await service.mark_all_read(db, context.organization_id, context.user.id)
    return NotificationMarkAllResult(marked_read=marked)


@router.post("/process-due", response_model=DueNotificationResult)
async def process_due_notifications(
    db: DbSession, context: Manager
) -> DueNotificationResult:
    return await service.process_due_events(db, context.organization_id)
