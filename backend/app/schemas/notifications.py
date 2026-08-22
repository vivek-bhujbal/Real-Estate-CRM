from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import NotificationStatus


class NotificationView(BaseModel):
    id: str
    event_type: str
    title: str
    body: str
    status: NotificationStatus
    action_url: str | None
    data: dict[str, Any] | None
    related_entity_type: str | None
    related_entity_id: str | None
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class NotificationUnreadCount(BaseModel):
    unread: int


class NotificationMarkAllResult(BaseModel):
    marked_read: int


class DueNotificationResult(BaseModel):
    follow_up_reminders: int
    hold_expiry_reminders: int
    installment_due_reminders: int
    overdue_reminders: int

    @property
    def total(self) -> int:
        return (
            self.follow_up_reminders
            + self.hold_expiry_reminders
            + self.installment_due_reminders
            + self.overdue_reminders
        )
