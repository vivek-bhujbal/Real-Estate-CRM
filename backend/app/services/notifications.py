from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import (
    Booking,
    Installment,
    Lead,
    LeadActivity,
    Notification,
    Organization,
    PaymentPlan,
    Permission,
    RolePermission,
    SiteVisit,
    UnitHold,
    User,
    UserRole,
)
from app.models.enums import (
    ExternalNotificationChannel,
    HoldStatus,
    InstallmentStatus,
    NotificationChannel,
    NotificationEventType,
    NotificationStatus,
)
from app.schemas.notifications import (
    DueNotificationResult,
    NotificationUnreadCount,
    NotificationView,
)
from app.schemas.organization import Page


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class OutboundNotification:
    organization_id: str
    event_type: NotificationEventType
    recipient: str
    title: str
    body: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    provider_message_id: str
    accepted_at: datetime


class NotificationTransport(Protocol):
    channel: ExternalNotificationChannel

    async def send(self, message: OutboundNotification) -> DeliveryReceipt: ...


class NotificationTransportRegistry:
    """Provider-neutral registry for future email, SMS, and WhatsApp adapters."""

    def __init__(self) -> None:
        self._transports: dict[ExternalNotificationChannel, NotificationTransport] = {}

    def register(self, transport: NotificationTransport) -> None:
        self._transports[transport.channel] = transport

    async def send(
        self, channel: ExternalNotificationChannel, message: OutboundNotification
    ) -> DeliveryReceipt:
        transport = self._transports.get(channel)
        if transport is None:
            raise RuntimeError(f"No {channel.value} notification transport is configured")
        return await transport.send(message)


external_transports = NotificationTransportRegistry()


def queue_in_app(
    db: AsyncSession,
    *,
    organization_id: str,
    recipient_user_ids: list[str] | tuple[str, ...] | set[str],
    event_type: NotificationEventType,
    title: str,
    body: str,
    related_entity_type: str,
    related_entity_id: str,
    action_url: str,
    data: dict[str, Any] | None = None,
    deduplication_key: str | None = None,
    scheduled_for: datetime | None = None,
) -> list[Notification]:
    if not action_url.startswith("/"):
        raise ValueError("In-app notification action URLs must be application-relative")
    sent_at = _now()
    notifications = [
        Notification(
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.DELIVERED,
            event_type=event_type.value,
            title=title[:200],
            body=body,
            action_url=action_url[:500],
            data=data,
            deduplication_key=deduplication_key,
            scheduled_for=scheduled_for,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            sent_at=sent_at,
        )
        for recipient_user_id in sorted(set(recipient_user_ids))
        if recipient_user_id
    ]
    db.add_all(notifications)
    return notifications


async def recipients_for_permission(
    db: AsyncSession, organization_id: str, permission: str
) -> set[str]:
    module = permission.partition(".")[0]
    accepted = {permission, f"{module}.manage"}
    return set(
        await db.scalars(
            select(User.id)
            .join(
                UserRole,
                (UserRole.organization_id == User.organization_id)
                & (UserRole.user_id == User.id),
            )
            .join(
                RolePermission,
                (RolePermission.organization_id == UserRole.organization_id)
                & (RolePermission.role_id == UserRole.role_id),
            )
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Permission.code.in_(accepted),
            )
            .distinct()
        )
    )


async def recipients_for_roles(
    db: AsyncSession, organization_id: str, role_ids: list[str]
) -> set[str]:
    if not role_ids:
        return set()
    return set(
        await db.scalars(
            select(User.id)
            .join(
                UserRole,
                (UserRole.organization_id == User.organization_id)
                & (UserRole.user_id == User.id),
            )
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                UserRole.role_id.in_(role_ids),
            )
            .distinct()
        )
    )


async def list_notifications(
    db: AsyncSession,
    organization_id: str,
    user_id: str,
    *,
    q: str | None,
    event_type: str | None,
    unread_only: bool,
    page: int,
    page_size: int,
) -> Page[NotificationView]:
    filters: list[Any] = [
        Notification.organization_id == organization_id,
        Notification.recipient_user_id == user_id,
        Notification.channel == NotificationChannel.IN_APP,
    ]
    if q and (term := q.strip()):
        pattern = f"%{term}%"
        filters.append(or_(Notification.title.ilike(pattern), Notification.body.ilike(pattern)))
    if event_type:
        filters.append(Notification.event_type == event_type)
    if unread_only:
        filters.append(Notification.read_at.is_(None))
    total = int(
        await db.scalar(select(func.count()).select_from(Notification).where(*filters)) or 0
    )
    rows = list(
        await db.scalars(
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[_view(item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=(total + page_size - 1) // page_size if total else 0,
    )


async def unread_count(
    db: AsyncSession, organization_id: str, user_id: str
) -> NotificationUnreadCount:
    count = int(
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.recipient_user_id == user_id,
                Notification.channel == NotificationChannel.IN_APP,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )
    return NotificationUnreadCount(unread=count)


async def mark_read(
    db: AsyncSession, organization_id: str, user_id: str, notification_id: str
) -> NotificationView:
    item = (
        await db.scalars(
            select(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
                Notification.channel == NotificationChannel.IN_APP,
            )
            .with_for_update()
        )
    ).first()
    if item is None:
        raise AppError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="The requested notification was not found",
        )
    if item.read_at is None:
        item.read_at = _now()
        item.status = NotificationStatus.READ
        await db.commit()
        await db.refresh(item)
    return _view(item)


async def mark_all_read(db: AsyncSession, organization_id: str, user_id: str) -> int:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == user_id,
            Notification.channel == NotificationChannel.IN_APP,
            Notification.read_at.is_(None),
        )
        .values(read_at=_now(), status=NotificationStatus.READ)
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def process_due_events(
    db: AsyncSession, organization_id: str, *, now: datetime | None = None
) -> DueNotificationResult:
    current = now or _now()
    await db.scalar(
        select(Organization.id)
        .where(Organization.id == organization_id)
        .with_for_update()
    )
    existing_keys = set(
        await db.scalars(
            select(Notification.deduplication_key).where(
                Notification.organization_id == organization_id,
                Notification.deduplication_key.is_not(None),
            )
        )
    )
    counts = {"follow_up": 0, "hold": 0, "due": 0, "overdue": 0}

    follow_ups = (
        await db.execute(
            select(LeadActivity, Lead.owner_user_id)
            .join(
                Lead,
                (Lead.organization_id == LeadActivity.organization_id)
                & (Lead.id == LeadActivity.lead_id),
            )
            .where(
                LeadActivity.organization_id == organization_id,
                LeadActivity.due_at.is_not(None),
                LeadActivity.due_at <= current,
                LeadActivity.is_completed.is_(False),
            )
        )
    ).all()
    for activity, owner_user_id in follow_ups:
        recipient = owner_user_id or activity.performed_by_user_id
        key = f"follow-up:{activity.id}:due"
        if recipient and key not in existing_keys:
            queue_in_app(
                db,
                organization_id=organization_id,
                recipient_user_ids=[recipient],
                event_type=NotificationEventType.FOLLOW_UP_REMINDER,
                title="Follow-up is due",
                body=activity.subject,
                related_entity_type="lead_activity",
                related_entity_id=activity.id,
                action_url=f"/leads/{activity.lead_id}",
                data={"lead_id": activity.lead_id, "due_at": activity.due_at.isoformat()},
                deduplication_key=key,
                scheduled_for=activity.due_at,
            )
            existing_keys.add(key)
            counts["follow_up"] += 1

    visit_follow_ups = list(
        await db.scalars(
            select(SiteVisit).where(
                SiteVisit.organization_id == organization_id,
                SiteVisit.next_follow_up_at.is_not(None),
                SiteVisit.next_follow_up_at <= current,
                SiteVisit.assigned_user_id.is_not(None),
            )
        )
    )
    for visit in visit_follow_ups:
        follow_up_at = visit.next_follow_up_at
        key = f"site-visit:{visit.id}:follow-up"
        if visit.assigned_user_id and follow_up_at and key not in existing_keys:
            queue_in_app(
                db,
                organization_id=organization_id,
                recipient_user_ids=[visit.assigned_user_id],
                event_type=NotificationEventType.FOLLOW_UP_REMINDER,
                title="Site visit follow-up is due",
                body="Record the visit outcome and next action.",
                related_entity_type="site_visit",
                related_entity_id=visit.id,
                action_url=f"/site-visits/{visit.id}",
                data={"next_follow_up_at": follow_up_at.isoformat()},
                deduplication_key=key,
                scheduled_for=follow_up_at,
            )
            existing_keys.add(key)
            counts["follow_up"] += 1

    expiring_holds = list(
        await db.scalars(
            select(UnitHold).where(
                UnitHold.organization_id == organization_id,
                UnitHold.status.in_((HoldStatus.ACTIVE, HoldStatus.PENDING_APPROVAL)),
                UnitHold.expires_at > current,
                UnitHold.expires_at <= current + timedelta(hours=24),
            )
        )
    )
    for hold in expiring_holds:
        key = f"unit-hold:{hold.id}:expiring"
        if key not in existing_keys:
            queue_in_app(
                db,
                organization_id=organization_id,
                recipient_user_ids=[hold.held_by_user_id],
                event_type=NotificationEventType.UNIT_HOLD_EXPIRING,
                title="Unit hold expires soon",
                body="Review or release this unit hold before it expires.",
                related_entity_type="unit_hold",
                related_entity_id=hold.id,
                action_url="/inventory/holds",
                data={"unit_id": hold.unit_id, "expires_at": hold.expires_at.isoformat()},
                deduplication_key=key,
                scheduled_for=hold.expires_at,
            )
            existing_keys.add(key)
            counts["hold"] += 1

    finance_users = await recipients_for_permission(db, organization_id, "collections.approve")
    installments = (
        await db.execute(
            select(Installment, Booking)
            .join(
                PaymentPlan,
                (PaymentPlan.organization_id == Installment.organization_id)
                & (PaymentPlan.id == Installment.payment_plan_id),
            )
            .join(
                Booking,
                (Booking.organization_id == PaymentPlan.organization_id)
                & (Booking.id == PaymentPlan.booking_id),
            )
            .where(
                Installment.organization_id == organization_id,
                Installment.due_date <= current.date(),
                Installment.status.in_(
                    (
                        InstallmentStatus.SCHEDULED,
                        InstallmentStatus.DUE,
                        InstallmentStatus.PARTIALLY_PAID,
                        InstallmentStatus.OVERDUE,
                    )
                ),
            )
        )
    ).all()
    for installment, booking in installments:
        overdue = installment.due_date < current.date()
        event = (
            NotificationEventType.INSTALLMENT_OVERDUE
            if overdue
            else NotificationEventType.INSTALLMENT_DUE
        )
        key = f"installment:{installment.id}:{event.value.lower()}"
        recipients = set(finance_users)
        if booking.salesperson_user_id:
            recipients.add(booking.salesperson_user_id)
        if key not in existing_keys and recipients:
            queue_in_app(
                db,
                organization_id=organization_id,
                recipient_user_ids=recipients,
                event_type=event,
                title="Installment overdue" if overdue else "Installment due today",
                body=f"{installment.name}: {booking.currency} {installment.amount}",
                related_entity_type="installment",
                related_entity_id=installment.id,
                action_url=f"/collections/{booking.id}",
                data={
                    "booking_id": booking.id,
                    "due_date": installment.due_date.isoformat(),
                    "amount": str(installment.amount),
                    "paid_amount": str(installment.paid_amount),
                },
                deduplication_key=key,
            )
            existing_keys.add(key)
            counts["overdue" if overdue else "due"] += len(recipients)

    await db.commit()
    return DueNotificationResult(
        follow_up_reminders=counts["follow_up"],
        hold_expiry_reminders=counts["hold"],
        installment_due_reminders=counts["due"],
        overdue_reminders=counts["overdue"],
    )


def _view(item: Notification) -> NotificationView:
    return NotificationView(
        id=item.id,
        event_type=item.event_type or "LEGACY",
        title=item.title,
        body=item.body,
        status=item.status,
        action_url=item.action_url,
        data=item.data,
        related_entity_type=item.related_entity_type,
        related_entity_id=item.related_entity_id,
        sent_at=item.sent_at,
        read_at=item.read_at,
        created_at=item.created_at,
    )
