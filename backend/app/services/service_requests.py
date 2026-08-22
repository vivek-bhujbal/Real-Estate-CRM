import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from fastapi import UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Customer,
    Permission,
    Project,
    RolePermission,
    ServiceRequest,
    ServiceRequestAttachment,
    ServiceRequestCategory,
    ServiceRequestComment,
    ServiceRequestEscalation,
    ServiceRequestFeedback,
    ServiceSLAPolicy,
    Tenant,
    Unit,
    User,
    UserRole,
)
from app.models.enums import (
    EscalationStatus,
    NotificationEventType,
    ServicePriority,
    TicketStatus,
)
from app.schemas.organization import Page
from app.schemas.service_requests import (
    AssignmentCreate,
    AttachmentView,
    CategoryCreate,
    CategoryUpdate,
    CategoryView,
    CommentCreate,
    CommentView,
    EscalationCreate,
    EscalationDecision,
    EscalationView,
    FeedbackCreate,
    FeedbackView,
    SLAPolicyCreate,
    SLAPolicyUpdate,
    SLAPolicyView,
    SLAView,
    StatusTransition,
    TicketCreate,
    TicketDetail,
    TicketOptions,
    TicketStats,
    TicketSummary,
    TicketUpdate,
)
from app.services import notifications as notification_service
from app.services.documents import _prepare_file
from app.services.organization import MutationContext
from app.storage import StoredFile, get_storage


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _error(code: str, message: str, status: int = 409) -> AppError:
    return AppError(status_code=status, code=code, message=message)


def _is_agent(context: MutationContext) -> bool:
    return any(
        permission_is_granted(context.permissions, permission)
        for permission in (
            "service_requests.assign",
            "service_requests.approve",
            "service_requests.manage",
        )
    )


def _can_manage(context: MutationContext) -> bool:
    return permission_is_granted(context.permissions, "service_requests.manage")


async def _service_agent(
    db: AsyncSession, org: str, user_id: str, *, error_code: str = "INVALID_ASSIGNEE"
) -> User:
    user = (
        await db.scalars(
            select(User)
            .join(
                UserRole,
                and_(
                    UserRole.organization_id == User.organization_id,
                    UserRole.user_id == User.id,
                ),
            )
            .join(
                RolePermission,
                and_(
                    RolePermission.organization_id == UserRole.organization_id,
                    RolePermission.role_id == UserRole.role_id,
                ),
            )
            .join(
                Permission,
                and_(
                    Permission.organization_id == RolePermission.organization_id,
                    Permission.id == RolePermission.permission_id,
                ),
            )
            .where(
                User.organization_id == org,
                User.id == user_id,
                User.is_active.is_(True),
                Permission.code.in_(
                    ("service_requests.assign", "service_requests.manage")
                ),
            )
            .distinct()
        )
    ).first()
    if user is None:
        raise _error(
            error_code,
            "Select an active user authorized to manage service requests",
            422,
        )
    return user


def _audit(
    org: str,
    context: MutationContext,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=org,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=before,
        new_value=after,
        request_id=context.request_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
        created_at=_now(),
    )


async def _entity[T](
    db: AsyncSession, model: type[T], org: str, entity_id: str, *, lock: bool = False
) -> T:
    statement = select(model).where(model.organization_id == org, model.id == entity_id)  # type: ignore[attr-defined]
    if lock:
        statement = statement.with_for_update()
    item = (await db.scalars(statement)).first()
    if item is None:
        raise _error("RESOURCE_NOT_FOUND", "Service request record not found", 404)
    return item


async def _actor_tenant(db: AsyncSession, org: str, user_id: str) -> Tenant | None:
    return (
        await db.scalars(
            select(Tenant).where(Tenant.organization_id == org, Tenant.user_id == user_id)
        )
    ).first()


async def _ticket(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    context: MutationContext,
    *,
    lock: bool = False,
) -> ServiceRequest:
    item = await _entity(db, ServiceRequest, org, ticket_id, lock=lock)
    if _is_agent(context) or item.opened_by_user_id == context.actor_user_id:
        return item
    tenant = await _actor_tenant(db, org, context.actor_user_id)
    if tenant and item.tenant_id == tenant.id:
        return item
    raise _error("RESOURCE_NOT_FOUND", "Service request record not found", 404)


async def _name(db: AsyncSession, org: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = await db.scalar(
        select(User.full_name).where(User.organization_id == org, User.id == user_id)
    )
    return str(value) if value is not None else None


async def _category_view(db: AsyncSession, org: str, item: ServiceRequestCategory) -> CategoryView:
    policy_count = int(
        await db.scalar(
            select(func.count(ServiceSLAPolicy.id)).where(
                ServiceSLAPolicy.organization_id == org,
                ServiceSLAPolicy.category_id == item.id,
            )
        )
        or 0
    )
    ticket_count = int(
        await db.scalar(
            select(func.count(ServiceRequest.id)).where(
                ServiceRequest.organization_id == org,
                ServiceRequest.category_id == item.id,
            )
        )
        or 0
    )
    return CategoryView(
        id=item.id,
        code=item.code,
        name=item.name,
        description=item.description,
        is_active=item.is_active,
        policy_count=policy_count,
        ticket_count=ticket_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def list_categories(db: AsyncSession, org: str) -> list[CategoryView]:
    items = list(
        await db.scalars(
            select(ServiceRequestCategory)
            .where(ServiceRequestCategory.organization_id == org)
            .order_by(ServiceRequestCategory.name)
        )
    )
    return [await _category_view(db, org, item) for item in items]


async def create_category(
    db: AsyncSession, org: str, payload: CategoryCreate, context: MutationContext
) -> CategoryView:
    item = ServiceRequestCategory(
        organization_id=org,
        code=payload.code.strip().upper(),
        name=" ".join(payload.name.split()),
        description=payload.description,
        is_active=True,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("SERVICE_CATEGORY_EXISTS", "Service category code already exists") from exc
    db.add(
        _audit(
            org,
            context,
            "service.category.created",
            "service_request_category",
            item.id,
            None,
            {"code": item.code, "name": item.name},
        )
    )
    await db.commit()
    await db.refresh(item)
    return await _category_view(db, org, item)


async def update_category(
    db: AsyncSession,
    org: str,
    category_id: str,
    payload: CategoryUpdate,
    context: MutationContext,
) -> CategoryView:
    item = await _entity(db, ServiceRequestCategory, org, category_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise _error("NO_CHANGES", "Provide at least one category change", 422)
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, " ".join(value.split()) if key == "name" and value else value)
    db.add(
        _audit(
            org,
            context,
            "service.category.updated",
            "service_request_category",
            item.id,
            {key: str(value) for key, value in before.items()},
            {key: str(value) for key, value in changes.items()},
        )
    )
    await db.commit()
    return await _category_view(db, org, item)


async def _policy_view(db: AsyncSession, org: str, item: ServiceSLAPolicy) -> SLAPolicyView:
    category = await _entity(db, ServiceRequestCategory, org, item.category_id)
    return SLAPolicyView(
        id=item.id,
        category_id=item.category_id,
        category_name=category.name,
        priority=item.priority,
        first_response_minutes=item.first_response_minutes,
        escalation_minutes=item.escalation_minutes,
        resolution_minutes=item.resolution_minutes,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def list_policies(db: AsyncSession, org: str) -> list[SLAPolicyView]:
    items = list(
        await db.scalars(
            select(ServiceSLAPolicy)
            .where(ServiceSLAPolicy.organization_id == org)
            .order_by(ServiceSLAPolicy.category_id, ServiceSLAPolicy.priority)
        )
    )
    return [await _policy_view(db, org, item) for item in items]


async def create_policy(
    db: AsyncSession, org: str, payload: SLAPolicyCreate, context: MutationContext
) -> SLAPolicyView:
    category = await _entity(db, ServiceRequestCategory, org, payload.category_id)
    if not category.is_active:
        raise _error("CATEGORY_INACTIVE", "SLA policy requires an active category", 422)
    item = ServiceSLAPolicy(
        organization_id=org,
        category_id=category.id,
        priority=payload.priority,
        first_response_minutes=payload.first_response_minutes,
        escalation_minutes=payload.escalation_minutes,
        resolution_minutes=payload.resolution_minutes,
        is_active=True,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(
            "SLA_POLICY_EXISTS", "An SLA policy already exists for this category and priority"
        ) from exc
    db.add(
        _audit(
            org,
            context,
            "service.sla_policy.created",
            "service_sla_policy",
            item.id,
            None,
            {
                "category_id": item.category_id,
                "priority": item.priority.value,
                "resolution_minutes": item.resolution_minutes,
            },
        )
    )
    await db.commit()
    await db.refresh(item)
    return await _policy_view(db, org, item)


async def update_policy(
    db: AsyncSession,
    org: str,
    policy_id: str,
    payload: SLAPolicyUpdate,
    context: MutationContext,
) -> SLAPolicyView:
    item = await _entity(db, ServiceSLAPolicy, org, policy_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise _error("NO_CHANGES", "Provide at least one SLA policy change", 422)
    response = changes.get("first_response_minutes", item.first_response_minutes)
    escalation = changes.get("escalation_minutes", item.escalation_minutes)
    resolution = changes.get("resolution_minutes", item.resolution_minutes)
    if not response <= escalation <= resolution:
        raise _error("INVALID_SLA_ORDER", "SLA deadlines must be in chronological order", 422)
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    db.add(
        _audit(
            org,
            context,
            "service.sla_policy.updated",
            "service_sla_policy",
            item.id,
            {key: str(value) for key, value in before.items()},
            {key: str(value) for key, value in changes.items()},
        )
    )
    await db.commit()
    return await _policy_view(db, org, item)


async def _sla_policy(
    db: AsyncSession, org: str, category_id: str, priority: ServicePriority
) -> ServiceSLAPolicy | None:
    return (
        await db.scalars(
            select(ServiceSLAPolicy).where(
                ServiceSLAPolicy.organization_id == org,
                ServiceSLAPolicy.category_id == category_id,
                ServiceSLAPolicy.priority == priority,
                ServiceSLAPolicy.is_active.is_(True),
            )
        )
    ).first()


def _apply_sla(item: ServiceRequest, policy: ServiceSLAPolicy | None) -> None:
    item.sla_policy_id = policy.id if policy else None
    item.response_due_at = (
        item.opened_at + timedelta(minutes=policy.first_response_minutes) if policy else None
    )
    item.escalation_due_at = (
        item.opened_at + timedelta(minutes=policy.escalation_minutes) if policy else None
    )
    item.resolution_due_at = (
        item.opened_at + timedelta(minutes=policy.resolution_minutes) if policy else None
    )


def _deadline_state(
    due: datetime | None, completed: datetime | None, *, still_open: bool
) -> tuple[str, int | None]:
    if due is None:
        return "NOT_CONFIGURED", None
    reference = completed or _now()
    remaining = int((due - reference).total_seconds() // 60)
    if completed:
        return ("MET" if completed <= due else "BREACHED"), remaining
    return ("BREACHED" if still_open and reference > due else "ON_TRACK"), remaining


def _sla_view(item: ServiceRequest) -> SLAView:
    response_state, response_remaining = _deadline_state(
        item.response_due_at,
        item.first_responded_at,
        still_open=item.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED),
    )
    resolution_state, resolution_remaining = _deadline_state(
        item.resolution_due_at,
        item.resolved_at,
        still_open=item.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED),
    )
    return SLAView(
        configured=item.sla_policy_id is not None,
        response_state=response_state,
        resolution_state=resolution_state,
        response_due_at=item.response_due_at,
        resolution_due_at=item.resolution_due_at,
        escalation_due_at=item.escalation_due_at,
        first_responded_at=item.first_responded_at,
        response_remaining_minutes=response_remaining,
        resolution_remaining_minutes=resolution_remaining,
        escalation_due=bool(
            item.escalation_due_at
            and item.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)
            and _now() > item.escalation_due_at
        ),
    )


def _sla_breached_condition(now: datetime) -> Any:
    return or_(
        and_(
            ServiceRequest.response_due_at.is_not(None),
            or_(
                and_(
                    ServiceRequest.first_responded_at.is_(None),
                    ServiceRequest.response_due_at < now,
                ),
                ServiceRequest.first_responded_at > ServiceRequest.response_due_at,
            ),
        ),
        and_(
            ServiceRequest.resolution_due_at.is_not(None),
            or_(
                and_(
                    ServiceRequest.resolved_at.is_(None),
                    ServiceRequest.resolution_due_at < now,
                ),
                ServiceRequest.resolved_at > ServiceRequest.resolution_due_at,
            ),
        ),
    )


async def _requester(db: AsyncSession, org: str, item: ServiceRequest) -> tuple[str, str]:
    if item.customer_id:
        customer = await _entity(db, Customer, org, item.customer_id)
        return customer.full_name, "CUSTOMER"
    if item.tenant_id:
        tenant = await _entity(db, Tenant, org, item.tenant_id)
        return tenant.full_name, "TENANT"
    return (await _name(db, org, item.opened_by_user_id) or "Portal user"), "PORTAL_USER"


async def _summary(db: AsyncSession, org: str, item: ServiceRequest) -> TicketSummary:
    requester_name, requester_type = await _requester(db, org, item)
    return TicketSummary(
        id=item.id,
        request_number=item.request_number,
        subject=item.subject,
        category_id=item.category_id,
        category_name=item.category,
        priority=item.priority,
        status=item.status,
        requester_name=requester_name,
        requester_type=requester_type,
        assigned_user_id=item.assigned_user_id,
        assigned_user_name=await _name(db, org, item.assigned_user_id),
        is_escalated=item.is_escalated,
        sla=_sla_view(item),
        opened_at=item.opened_at,
        updated_at=item.updated_at,
        resolved_at=item.resolved_at,
        closed_at=item.closed_at,
    )


async def list_tickets(
    db: AsyncSession,
    org: str,
    context: MutationContext,
    *,
    q: str | None,
    status: TicketStatus | None,
    priority: ServicePriority | None,
    category_id: str | None,
    assigned_user_id: str | None,
    sla_breached: bool | None,
    page: int,
    page_size: int,
) -> Page[TicketSummary]:
    conditions: list[Any] = [ServiceRequest.organization_id == org]
    if not _is_agent(context):
        tenant = await _actor_tenant(db, org, context.actor_user_id)
        own = [ServiceRequest.opened_by_user_id == context.actor_user_id]
        if tenant:
            own.append(ServiceRequest.tenant_id == tenant.id)
        conditions.append(or_(*own))
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                ServiceRequest.request_number.ilike(pattern),
                ServiceRequest.subject.ilike(pattern),
                ServiceRequest.category.ilike(pattern),
            )
        )
    if status:
        conditions.append(ServiceRequest.status == status)
    if priority:
        conditions.append(ServiceRequest.priority == priority)
    if category_id:
        conditions.append(ServiceRequest.category_id == category_id)
    if assigned_user_id:
        conditions.append(ServiceRequest.assigned_user_id == assigned_user_id)
    if sla_breached is not None:
        breached = _sla_breached_condition(_now())
        conditions.append(breached if sla_breached else ~breached)
    total = int(await db.scalar(select(func.count(ServiceRequest.id)).where(*conditions)) or 0)
    items = list(
        await db.scalars(
            select(ServiceRequest)
            .where(*conditions)
            .order_by(ServiceRequest.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _summary(db, org, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def create_ticket(
    db: AsyncSession, org: str, payload: TicketCreate, context: MutationContext
) -> TicketDetail:
    category = await _entity(db, ServiceRequestCategory, org, payload.category_id)
    if not category.is_active:
        raise _error("CATEGORY_INACTIVE", "Select an active service category", 422)
    is_agent = _is_agent(context)
    if payload.customer_id and payload.tenant_id:
        raise _error("MULTIPLE_REQUESTERS", "Choose a customer or tenant, not both", 422)
    customer_id = payload.customer_id if is_agent else None
    tenant_id = payload.tenant_id if is_agent else None
    project_id = payload.project_id if is_agent else None
    unit_id = payload.unit_id if is_agent else None
    assigned_user_id = payload.assigned_user_id if is_agent else None
    if customer_id:
        await _entity(db, Customer, org, customer_id)
    if tenant_id:
        await _entity(db, Tenant, org, tenant_id)
    if not is_agent:
        actor_tenant = await _actor_tenant(db, org, context.actor_user_id)
        tenant_id = actor_tenant.id if actor_tenant else None
    if project_id:
        await _entity(db, Project, org, project_id)
    if unit_id:
        unit = await _entity(db, Unit, org, unit_id)
        if project_id and unit.project_id != project_id:
            raise _error(
                "UNIT_PROJECT_MISMATCH", "Unit does not belong to the selected project", 422
            )
        project_id = project_id or unit.project_id
    if assigned_user_id:
        await _service_agent(db, org, assigned_user_id)
    opened = _now()
    policy = await _sla_policy(db, org, category.id, payload.priority)
    item = ServiceRequest(
        organization_id=org,
        customer_id=customer_id,
        tenant_id=tenant_id,
        project_id=project_id,
        unit_id=unit_id,
        category_id=category.id,
        opened_by_user_id=context.actor_user_id,
        assigned_user_id=assigned_user_id,
        assigned_by_user_id=context.actor_user_id if assigned_user_id else None,
        request_number=f"SR-{opened:%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        category=category.name,
        priority=payload.priority,
        status=TicketStatus.ASSIGNED if assigned_user_id else TicketStatus.OPEN,
        subject=" ".join(payload.subject.split()),
        description=payload.description.strip(),
        opened_at=opened,
        is_escalated=False,
    )
    _apply_sla(item, policy)
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "service.ticket.created",
            "service_request",
            item.id,
            None,
            {
                "request_number": item.request_number,
                "category_id": item.category_id,
                "priority": item.priority.value,
                "sla_policy_id": item.sla_policy_id,
            },
        )
    )
    ticket_recipients = {item.assigned_user_id} if item.assigned_user_id else set()
    if not ticket_recipients:
        ticket_recipients = await notification_service.recipients_for_permission(
            db, org, "service_requests.assign"
        )
    notification_service.queue_in_app(
        db,
        organization_id=org,
        recipient_user_ids={recipient for recipient in ticket_recipients if recipient},
        event_type=NotificationEventType.SERVICE_REQUEST_CREATED,
        title="Service request created",
        body=f"{item.request_number} · {item.subject}",
        related_entity_type="service_request",
        related_entity_id=item.id,
        action_url=f"/service-requests/{item.id}",
        data={"priority": item.priority.value, "status": item.status.value},
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def ticket_detail(
    db: AsyncSession, org: str, ticket_id: str, context: MutationContext
) -> TicketDetail:
    item = await _ticket(db, org, ticket_id, context)
    is_agent = _is_agent(context)
    comments_query = select(ServiceRequestComment).where(
        ServiceRequestComment.organization_id == org,
        ServiceRequestComment.service_request_id == item.id,
    )
    if not is_agent:
        comments_query = comments_query.where(ServiceRequestComment.is_internal.is_(False))
    comments = list(
        await db.scalars(comments_query.order_by(ServiceRequestComment.created_at.asc()))
    )
    attachments = list(
        await db.scalars(
            select(ServiceRequestAttachment)
            .where(
                ServiceRequestAttachment.organization_id == org,
                ServiceRequestAttachment.service_request_id == item.id,
                ServiceRequestAttachment.comment_id.in_([comment.id for comment in comments])
                | ServiceRequestAttachment.comment_id.is_(None),
            )
            .order_by(ServiceRequestAttachment.created_at)
        )
    )
    escalations = list(
        await db.scalars(
            select(ServiceRequestEscalation)
            .where(
                ServiceRequestEscalation.organization_id == org,
                ServiceRequestEscalation.service_request_id == item.id,
            )
            .order_by(ServiceRequestEscalation.escalated_at.desc())
        )
    )
    feedback = (
        await db.scalars(
            select(ServiceRequestFeedback).where(
                ServiceRequestFeedback.organization_id == org,
                ServiceRequestFeedback.service_request_id == item.id,
            )
        )
    ).first()
    project_name = (
        await db.scalar(
            select(Project.name).where(
                Project.organization_id == org, Project.id == item.project_id
            )
        )
        if item.project_id
        else None
    )
    unit_number = (
        await db.scalar(
            select(Unit.unit_number).where(Unit.organization_id == org, Unit.id == item.unit_id)
        )
        if item.unit_id
        else None
    )
    return TicketDetail(
        ticket=await _summary(db, org, item),
        description=item.description,
        customer_id=item.customer_id,
        tenant_id=item.tenant_id,
        project_id=item.project_id,
        project_name=str(project_name) if project_name else None,
        unit_id=item.unit_id,
        unit_number=str(unit_number) if unit_number else None,
        resolution_summary=item.resolution_summary,
        closure_notes=item.closure_notes,
        comments=[
            CommentView(
                id=comment.id,
                author_user_id=comment.author_user_id,
                author_name=await _name(db, org, comment.author_user_id) or "User",
                body=comment.body,
                is_internal=comment.is_internal,
                created_at=comment.created_at,
            )
            for comment in comments
        ],
        attachments=[
            AttachmentView(
                id=attachment.id,
                comment_id=attachment.comment_id,
                file_name=attachment.file_name,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                uploaded_by_name=await _name(db, org, attachment.uploaded_by_user_id) or "User",
                created_at=attachment.created_at,
            )
            for attachment in attachments
        ],
        escalations=[
            EscalationView(
                id=escalation.id,
                status=escalation.status,
                from_user_name=await _name(db, org, escalation.from_user_id),
                to_user_id=escalation.to_user_id,
                to_user_name=await _name(db, org, escalation.to_user_id) or "User",
                escalated_by_name=await _name(db, org, escalation.escalated_by_user_id),
                acknowledged_by_name=await _name(db, org, escalation.acknowledged_by_user_id),
                reason=escalation.reason,
                escalated_at=escalation.escalated_at,
                acknowledged_at=escalation.acknowledged_at,
                resolved_at=escalation.resolved_at,
            )
            for escalation in escalations
        ],
        feedback=(
            FeedbackView(
                id=feedback.id,
                rating=feedback.rating,
                comments=feedback.comments,
                submitted_by_name=await _name(db, org, feedback.submitted_by_user_id) or "Customer",
                submitted_at=feedback.submitted_at,
            )
            if feedback
            else None
        ),
    )


async def update_ticket(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    payload: TicketUpdate,
    context: MutationContext,
) -> TicketDetail:
    item = await _ticket(db, org, ticket_id, context, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise _error("NO_CHANGES", "Provide at least one ticket change", 422)
    if not _is_agent(context):
        if item.status != TicketStatus.OPEN or set(changes) - {"subject", "description"}:
            raise _error("PERMISSION_DENIED", "Requester can only edit an open ticket", 403)
    before = {key: getattr(item, key) for key in changes}
    category = None
    if "category_id" in changes:
        category = await _entity(db, ServiceRequestCategory, org, changes["category_id"])
        if not category.is_active:
            raise _error("CATEGORY_INACTIVE", "Select an active service category", 422)
        item.category_id = category.id
        item.category = category.name
    if "priority" in changes:
        item.priority = changes["priority"]
    if "subject" in changes:
        item.subject = " ".join(changes["subject"].split())
    if "description" in changes:
        item.description = changes["description"].strip()
    if category or "priority" in changes:
        if not item.category_id:
            raise _error("CATEGORY_REQUIRED", "Ticket category is required", 422)
        policy = await _sla_policy(db, org, item.category_id, item.priority)
        _apply_sla(item, policy)
    db.add(
        _audit(
            org,
            context,
            "service.ticket.updated",
            "service_request",
            item.id,
            {key: str(value) for key, value in before.items()},
            {key: str(value) for key, value in changes.items()},
        )
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def assign_ticket(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    payload: AssignmentCreate,
    context: MutationContext,
) -> TicketDetail:
    if not _is_agent(context):
        raise _error("PERMISSION_DENIED", "Only service agents can assign tickets", 403)
    item = await _ticket(db, org, ticket_id, context, lock=True)
    if item.status == TicketStatus.CLOSED:
        raise _error("TICKET_CLOSED", "Closed tickets cannot be reassigned")
    assignee = await _service_agent(db, org, payload.assigned_user_id)
    before = item.assigned_user_id
    item.assigned_user_id = assignee.id
    item.assigned_by_user_id = context.actor_user_id
    if item.status == TicketStatus.OPEN:
        item.status = TicketStatus.ASSIGNED
    if payload.notes:
        db.add(
            ServiceRequestComment(
                organization_id=org,
                service_request_id=item.id,
                author_user_id=context.actor_user_id,
                body=payload.notes.strip(),
                is_internal=True,
            )
        )
    db.add(
        _audit(
            org,
            context,
            "service.ticket.assigned",
            "service_request",
            item.id,
            {"assigned_user_id": before},
            {"assigned_user_id": item.assigned_user_id, "status": item.status.value},
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=org,
        recipient_user_ids=[assignee.id],
        event_type=NotificationEventType.SERVICE_REQUEST_ASSIGNED,
        title="Service request assigned to you",
        body=f"{item.request_number} · {item.subject}",
        related_entity_type="service_request",
        related_entity_id=item.id,
        action_url=f"/service-requests/{item.id}",
        data={"priority": item.priority.value, "status": item.status.value},
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def transition_ticket(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    payload: StatusTransition,
    context: MutationContext,
) -> TicketDetail:
    item = await _ticket(db, org, ticket_id, context, lock=True)
    target = TicketStatus(payload.status)
    agent = _is_agent(context)
    if not agent:
        if not (item.status == TicketStatus.RESOLVED and target == TicketStatus.CLOSED):
            raise _error("PERMISSION_DENIED", "Requester can only close a resolved ticket", 403)
    allowed = {
        TicketStatus.ASSIGNED: {TicketStatus.IN_PROGRESS},
        TicketStatus.IN_PROGRESS: {
            TicketStatus.WAITING_FOR_CUSTOMER,
            TicketStatus.RESOLVED,
        },
        TicketStatus.WAITING_FOR_CUSTOMER: {
            TicketStatus.IN_PROGRESS,
            TicketStatus.RESOLVED,
        },
        TicketStatus.RESOLVED: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    }
    if target not in allowed.get(item.status, set()):
        raise _error(
            "INVALID_TICKET_TRANSITION",
            f"Ticket cannot move from {item.status.value} to {target.value}",
        )
    before = item.status
    now = _now()
    item.status = target
    if agent and target == TicketStatus.IN_PROGRESS and item.first_responded_at is None:
        item.first_responded_at = now
    if target == TicketStatus.RESOLVED:
        item.resolution_summary = payload.resolution_summary
        item.resolved_by_user_id = context.actor_user_id
        item.resolved_at = now
        active_escalations = list(
            await db.scalars(
                select(ServiceRequestEscalation).where(
                    ServiceRequestEscalation.organization_id == org,
                    ServiceRequestEscalation.service_request_id == item.id,
                    ServiceRequestEscalation.status != EscalationStatus.RESOLVED,
                )
            )
        )
        for escalation in active_escalations:
            escalation.status = EscalationStatus.RESOLVED
            escalation.resolved_at = now
        item.is_escalated = False
    elif target == TicketStatus.CLOSED:
        item.closure_notes = payload.notes
        item.closed_by_user_id = context.actor_user_id
        item.closed_at = now
    elif before == TicketStatus.RESOLVED and target == TicketStatus.IN_PROGRESS:
        item.resolved_at = None
        item.resolved_by_user_id = None
    db.add(
        ServiceRequestComment(
            organization_id=org,
            service_request_id=item.id,
            author_user_id=context.actor_user_id,
            body=payload.notes.strip(),
            is_internal=agent,
        )
    )
    db.add(
        _audit(
            org,
            context,
            "service.ticket.status_changed",
            "service_request",
            item.id,
            {"status": before.value},
            {"status": target.value, "resolution_summary": payload.resolution_summary},
        )
    )
    notification_service.queue_in_app(
        db,
        organization_id=org,
        recipient_user_ids={
            recipient
            for recipient in (item.assigned_user_id, item.opened_by_user_id)
            if recipient
        },
        event_type=NotificationEventType.SERVICE_REQUEST_STATUS_CHANGED,
        title="Service request status updated",
        body=f"{item.request_number}: {before.value} → {target.value}",
        related_entity_type="service_request",
        related_entity_id=item.id,
        action_url=f"/service-requests/{item.id}",
        data={"previous_status": before.value, "status": target.value},
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def add_comment(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    payload: CommentCreate,
    context: MutationContext,
) -> TicketDetail:
    item = await _ticket(db, org, ticket_id, context, lock=True)
    if item.status == TicketStatus.CLOSED:
        raise _error("TICKET_CLOSED", "Comments cannot be added to a closed ticket")
    agent = _is_agent(context)
    if payload.is_internal and not agent:
        raise _error("PERMISSION_DENIED", "Only agents can add internal notes", 403)
    now = _now()
    comment = ServiceRequestComment(
        organization_id=org,
        service_request_id=item.id,
        author_user_id=context.actor_user_id,
        body=payload.body.strip(),
        is_internal=payload.is_internal,
    )
    db.add(comment)
    await db.flush()
    if agent:
        item.last_agent_reply_at = now
        if not payload.is_internal and item.first_responded_at is None:
            item.first_responded_at = now
    else:
        item.last_customer_reply_at = now
        if item.status == TicketStatus.WAITING_FOR_CUSTOMER:
            item.status = TicketStatus.IN_PROGRESS
    db.add(
        _audit(
            org,
            context,
            "service.comment.added",
            "service_request_comment",
            comment.id,
            None,
            {"ticket_id": item.id, "is_internal": comment.is_internal},
        )
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def upload_attachment(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    comment_id: str | None,
    upload: UploadFile,
    context: MutationContext,
) -> TicketDetail:
    item = await _ticket(db, org, ticket_id, context)
    if comment_id:
        comment = await _entity(db, ServiceRequestComment, org, comment_id)
        if comment.service_request_id != item.id:
            raise _error("RESOURCE_NOT_FOUND", "Ticket comment not found", 404)
        if comment.is_internal and not _is_agent(context):
            raise _error("RESOURCE_NOT_FOUND", "Ticket comment not found", 404)
    prepared = await _prepare_file(upload)
    storage = get_storage()
    attachment_id = str(uuid.uuid4())
    key = f"service-requests/a/{org}/{attachment_id}/{uuid.uuid4().hex[:16]}.private"
    try:
        await storage.save(key=key, source=prepared.path)
        attachment = ServiceRequestAttachment(
            organization_id=org,
            id=attachment_id,
            service_request_id=item.id,
            comment_id=comment_id,
            uploaded_by_user_id=context.actor_user_id,
            file_name=prepared.file_name,
            storage_key=key,
            content_type=prepared.content_type,
            size_bytes=prepared.size_bytes,
            checksum_sha256=prepared.checksum_sha256,
        )
        db.add(attachment)
        db.add(
            _audit(
                org,
                context,
                "service.attachment.uploaded",
                "service_request_attachment",
                attachment.id,
                None,
                {"ticket_id": item.id, "file_name": attachment.file_name},
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        await storage.delete(key=key)
        raise
    finally:
        if await asyncio.to_thread(prepared.path.exists):
            await asyncio.to_thread(prepared.path.unlink)
    return await ticket_detail(db, org, item.id, context)


async def attachment_download(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    attachment_id: str,
    context: MutationContext,
) -> tuple[StoredFile, str, str]:
    item = await _ticket(db, org, ticket_id, context)
    attachment = await _entity(db, ServiceRequestAttachment, org, attachment_id)
    if attachment.service_request_id != item.id:
        raise _error("RESOURCE_NOT_FOUND", "Ticket attachment not found", 404)
    if attachment.comment_id and not _is_agent(context):
        comment = await _entity(db, ServiceRequestComment, org, attachment.comment_id)
        if comment.is_internal:
            raise _error("RESOURCE_NOT_FOUND", "Ticket attachment not found", 404)
    path = await get_storage().path_for_read(key=attachment.storage_key)
    return path, attachment.file_name, attachment.content_type


async def escalate_ticket(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    payload: EscalationCreate,
    context: MutationContext,
) -> TicketDetail:
    if not _is_agent(context):
        raise _error("PERMISSION_DENIED", "Only service agents can escalate tickets", 403)
    item = await _ticket(db, org, ticket_id, context, lock=True)
    if item.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        raise _error("TICKET_FINALIZED", "Resolved or closed tickets cannot be escalated")
    if await db.scalar(
        select(ServiceRequestEscalation.id).where(
            ServiceRequestEscalation.organization_id == org,
            ServiceRequestEscalation.service_request_id == item.id,
            ServiceRequestEscalation.status.in_(
                (EscalationStatus.OPEN, EscalationStatus.ACKNOWLEDGED)
            ),
        )
    ):
        raise _error("ESCALATION_ACTIVE", "This ticket already has an active escalation")
    target = await _service_agent(
        db, org, payload.to_user_id, error_code="INVALID_ESCALATION_TARGET"
    )
    if target.id == item.assigned_user_id:
        raise _error(
            "INVALID_ESCALATION_TARGET",
            "Escalation target must be an active user different from the current assignee",
            422,
        )
    escalation = ServiceRequestEscalation(
        organization_id=org,
        service_request_id=item.id,
        escalated_by_user_id=context.actor_user_id,
        from_user_id=item.assigned_user_id,
        to_user_id=target.id,
        status=EscalationStatus.OPEN,
        reason=payload.reason.strip(),
        escalated_at=_now(),
    )
    db.add(escalation)
    item.assigned_user_id = target.id
    item.assigned_by_user_id = context.actor_user_id
    item.is_escalated = True
    if item.status == TicketStatus.OPEN:
        item.status = TicketStatus.ASSIGNED
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "service.ticket.escalated",
            "service_request_escalation",
            escalation.id,
            None,
            {"ticket_id": item.id, "to_user_id": target.id, "reason": escalation.reason},
        )
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def decide_escalation(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    escalation_id: str,
    payload: EscalationDecision,
    context: MutationContext,
) -> TicketDetail:
    if not _is_agent(context):
        raise _error("PERMISSION_DENIED", "Only service agents can update escalations", 403)
    item = await _ticket(db, org, ticket_id, context, lock=True)
    escalation = await _entity(db, ServiceRequestEscalation, org, escalation_id, lock=True)
    if escalation.service_request_id != item.id:
        raise _error("RESOURCE_NOT_FOUND", "Ticket escalation not found", 404)
    if escalation.to_user_id != context.actor_user_id and not _can_manage(context):
        raise _error("PERMISSION_DENIED", "Only the escalation target can acknowledge it", 403)
    now = _now()
    before = escalation.status
    if payload.action == "ACKNOWLEDGE":
        if escalation.status != EscalationStatus.OPEN:
            raise _error("ESCALATION_FINALIZED", "Escalation is not awaiting acknowledgement")
        escalation.status = EscalationStatus.ACKNOWLEDGED
        escalation.acknowledged_by_user_id = context.actor_user_id
        escalation.acknowledged_at = now
    else:
        if escalation.status not in (EscalationStatus.OPEN, EscalationStatus.ACKNOWLEDGED):
            raise _error("ESCALATION_FINALIZED", "Escalation is already resolved")
        escalation.status = EscalationStatus.RESOLVED
        escalation.resolved_at = now
        item.is_escalated = False
    if payload.notes:
        db.add(
            ServiceRequestComment(
                organization_id=org,
                service_request_id=item.id,
                author_user_id=context.actor_user_id,
                body=payload.notes.strip(),
                is_internal=True,
            )
        )
    db.add(
        _audit(
            org,
            context,
            "service.escalation.updated",
            "service_request_escalation",
            escalation.id,
            {"status": before.value},
            {"status": escalation.status.value},
        )
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def submit_feedback(
    db: AsyncSession,
    org: str,
    ticket_id: str,
    payload: FeedbackCreate,
    context: MutationContext,
) -> TicketDetail:
    item = await _ticket(db, org, ticket_id, context, lock=True)
    if _is_agent(context):
        raise _error("PERMISSION_DENIED", "Service agents cannot submit customer feedback", 403)
    if item.status != TicketStatus.CLOSED:
        raise _error("TICKET_NOT_CLOSED", "Feedback is available after ticket closure")
    feedback = ServiceRequestFeedback(
        organization_id=org,
        service_request_id=item.id,
        submitted_by_user_id=context.actor_user_id,
        rating=payload.rating,
        comments=payload.comments,
        submitted_at=_now(),
    )
    db.add(feedback)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("FEEDBACK_EXISTS", "Feedback has already been submitted") from exc
    db.add(
        _audit(
            org,
            context,
            "service.feedback.submitted",
            "service_request_feedback",
            feedback.id,
            None,
            {"ticket_id": item.id, "rating": feedback.rating},
        )
    )
    await db.commit()
    return await ticket_detail(db, org, item.id, context)


async def stats(db: AsyncSession, org: str, context: MutationContext) -> TicketStats:
    conditions: list[Any] = [ServiceRequest.organization_id == org]
    if not _is_agent(context):
        tenant = await _actor_tenant(db, org, context.actor_user_id)
        own = [ServiceRequest.opened_by_user_id == context.actor_user_id]
        if tenant:
            own.append(ServiceRequest.tenant_id == tenant.id)
        conditions.append(or_(*own))
    open_statuses = (
        TicketStatus.OPEN,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_FOR_CUSTOMER,
    )

    async def count(*extra: Any) -> int:
        return int(
            await db.scalar(select(func.count(ServiceRequest.id)).where(*conditions, *extra)) or 0
        )

    breached = _sla_breached_condition(_now())
    feedback_average = await db.scalar(
        select(func.avg(ServiceRequestFeedback.rating))
        .join(
            ServiceRequest,
            and_(
                ServiceRequest.organization_id == ServiceRequestFeedback.organization_id,
                ServiceRequest.id == ServiceRequestFeedback.service_request_id,
            ),
        )
        .where(*conditions)
    )
    return TicketStats(
        total_open=await count(ServiceRequest.status.in_(open_statuses)),
        unassigned=await count(
            ServiceRequest.status.in_(open_statuses), ServiceRequest.assigned_user_id.is_(None)
        ),
        in_progress=await count(ServiceRequest.status == TicketStatus.IN_PROGRESS),
        waiting_for_customer=await count(
            ServiceRequest.status == TicketStatus.WAITING_FOR_CUSTOMER
        ),
        resolved=await count(ServiceRequest.status == TicketStatus.RESOLVED),
        sla_breached=await count(breached),
        escalated=await count(ServiceRequest.is_escalated.is_(True)),
        average_feedback=float(feedback_average) if feedback_average is not None else None,
    )


async def options(db: AsyncSession, org: str, context: MutationContext) -> TicketOptions:
    categories = [item for item in await list_categories(db, org) if item.is_active]
    if not _is_agent(context):
        return TicketOptions(
            categories=categories,
            agents=[],
            customers=[],
            tenants=[],
            projects=[],
            units=[],
        )
    users = list(
        await db.scalars(
            select(User)
            .join(
                UserRole,
                and_(
                    UserRole.organization_id == User.organization_id,
                    UserRole.user_id == User.id,
                ),
            )
            .join(
                RolePermission,
                and_(
                    RolePermission.organization_id == UserRole.organization_id,
                    RolePermission.role_id == UserRole.role_id,
                ),
            )
            .join(
                Permission,
                and_(
                    Permission.organization_id == RolePermission.organization_id,
                    Permission.id == RolePermission.permission_id,
                ),
            )
            .where(
                User.organization_id == org,
                User.is_active.is_(True),
                Permission.code.in_(
                    ("service_requests.assign", "service_requests.manage")
                ),
            )
            .distinct()
            .order_by(User.full_name)
            .limit(500)
        )
    )
    customers = list(
        await db.scalars(
            select(Customer)
            .where(Customer.organization_id == org)
            .order_by(Customer.full_name)
            .limit(500)
        )
    )
    tenants = list(
        await db.scalars(
            select(Tenant)
            .where(Tenant.organization_id == org)
            .order_by(Tenant.full_name)
            .limit(500)
        )
    )
    projects = list(
        await db.scalars(
            select(Project).where(Project.organization_id == org).order_by(Project.name).limit(500)
        )
    )
    units = list(
        await db.scalars(
            select(Unit).where(Unit.organization_id == org).order_by(Unit.unit_number).limit(1000)
        )
    )
    return TicketOptions(
        categories=categories,
        agents=[{"id": item.id, "label": item.full_name} for item in users],
        customers=[
            {"id": item.id, "label": item.full_name, "secondary": item.email or item.phone}
            for item in customers
        ],
        tenants=[
            {"id": item.id, "label": item.full_name, "secondary": item.email or item.phone}
            for item in tenants
        ],
        projects=[{"id": item.id, "label": item.name} for item in projects],
        units=[
            {"id": item.id, "label": item.unit_number, "project_id": item.project_id}
            for item in units
        ],
    )
