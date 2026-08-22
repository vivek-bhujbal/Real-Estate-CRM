from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, SecurityContext, mutation_context, require_permissions
from app.core.responses import private_file_response
from app.models.enums import ServicePriority, TicketStatus
from app.schemas.organization import Page
from app.schemas.service_requests import (
    AssignmentCreate,
    CategoryCreate,
    CategoryUpdate,
    CategoryView,
    CommentCreate,
    EscalationCreate,
    EscalationDecision,
    FeedbackCreate,
    SLAPolicyCreate,
    SLAPolicyUpdate,
    SLAPolicyView,
    StatusTransition,
    TicketCreate,
    TicketDetail,
    TicketOptions,
    TicketStats,
    TicketSummary,
    TicketUpdate,
)
from app.services import service_requests as service
from app.services.organization import MutationContext

router = APIRouter(prefix="/service-requests", tags=["service request management"])

Reader = Annotated[SecurityContext, Depends(require_permissions("service_requests.view"))]
Creator = Annotated[SecurityContext, Depends(require_permissions("service_requests.create"))]
Updater = Annotated[SecurityContext, Depends(require_permissions("service_requests.update"))]
Assigner = Annotated[
    SecurityContext,
    Depends(require_permissions("service_requests.assign", "service_requests.manage", any_of=True)),
]
Manager = Annotated[SecurityContext, Depends(require_permissions("service_requests.manage"))]
AttachmentWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("service_requests.create", "service_requests.update", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return mutation_context(request, security)


@router.get("/stats", response_model=TicketStats)
async def ticket_stats(request: Request, db: DbSession, context: Reader) -> TicketStats:
    return await service.stats(db, context.organization_id, _context(request, context))


@router.get("/options", response_model=TicketOptions)
async def ticket_options(request: Request, db: DbSession, context: Reader) -> TicketOptions:
    return await service.options(db, context.organization_id, _context(request, context))


@router.get("/categories", response_model=list[CategoryView])
async def categories(db: DbSession, context: Reader) -> list[CategoryView]:
    return await service.list_categories(db, context.organization_id)


@router.post("/categories", response_model=CategoryView, status_code=201)
async def create_category(
    payload: CategoryCreate,
    request: Request,
    db: DbSession,
    context: Manager,
) -> CategoryView:
    return await service.create_category(
        db, context.organization_id, payload, _context(request, context)
    )


@router.patch("/categories/{category_id}", response_model=CategoryView)
async def update_category(
    category_id: str,
    payload: CategoryUpdate,
    request: Request,
    db: DbSession,
    context: Manager,
) -> CategoryView:
    return await service.update_category(
        db,
        context.organization_id,
        category_id,
        payload,
        _context(request, context),
    )


@router.get("/sla-policies", response_model=list[SLAPolicyView])
async def policies(db: DbSession, context: Manager) -> list[SLAPolicyView]:
    return await service.list_policies(db, context.organization_id)


@router.post("/sla-policies", response_model=SLAPolicyView, status_code=201)
async def create_policy(
    payload: SLAPolicyCreate,
    request: Request,
    db: DbSession,
    context: Manager,
) -> SLAPolicyView:
    return await service.create_policy(
        db, context.organization_id, payload, _context(request, context)
    )


@router.patch("/sla-policies/{policy_id}", response_model=SLAPolicyView)
async def update_policy(
    policy_id: str,
    payload: SLAPolicyUpdate,
    request: Request,
    db: DbSession,
    context: Manager,
) -> SLAPolicyView:
    return await service.update_policy(
        db,
        context.organization_id,
        policy_id,
        payload,
        _context(request, context),
    )


@router.get("", response_model=Page[TicketSummary])
async def tickets(
    request: Request,
    db: DbSession,
    context: Reader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: TicketStatus | None = None,
    priority: ServicePriority | None = None,
    category_id: str | None = None,
    assigned_user_id: str | None = None,
    sla_breached: bool | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[TicketSummary]:
    return await service.list_tickets(
        db,
        context.organization_id,
        _context(request, context),
        q=q,
        status=status,
        priority=priority,
        category_id=category_id,
        assigned_user_id=assigned_user_id,
        sla_breached=sla_breached,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TicketDetail, status_code=201)
async def create_ticket(
    payload: TicketCreate,
    request: Request,
    db: DbSession,
    context: Creator,
) -> TicketDetail:
    return await service.create_ticket(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/{ticket_id}", response_model=TicketDetail)
async def ticket(
    ticket_id: str,
    request: Request,
    db: DbSession,
    context: Reader,
) -> TicketDetail:
    return await service.ticket_detail(
        db, context.organization_id, ticket_id, _context(request, context)
    )


@router.patch("/{ticket_id}", response_model=TicketDetail)
async def update_ticket(
    ticket_id: str,
    payload: TicketUpdate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> TicketDetail:
    return await service.update_ticket(
        db, context.organization_id, ticket_id, payload, _context(request, context)
    )


@router.post("/{ticket_id}/assignment", response_model=TicketDetail)
async def assign_ticket(
    ticket_id: str,
    payload: AssignmentCreate,
    request: Request,
    db: DbSession,
    context: Assigner,
) -> TicketDetail:
    return await service.assign_ticket(
        db, context.organization_id, ticket_id, payload, _context(request, context)
    )


@router.post("/{ticket_id}/status", response_model=TicketDetail)
async def transition_ticket(
    ticket_id: str,
    payload: StatusTransition,
    request: Request,
    db: DbSession,
    context: Updater,
) -> TicketDetail:
    return await service.transition_ticket(
        db, context.organization_id, ticket_id, payload, _context(request, context)
    )


@router.post("/{ticket_id}/comments", response_model=TicketDetail, status_code=201)
async def add_comment(
    ticket_id: str,
    payload: CommentCreate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> TicketDetail:
    return await service.add_comment(
        db, context.organization_id, ticket_id, payload, _context(request, context)
    )


@router.post("/{ticket_id}/attachments", response_model=TicketDetail, status_code=201)
async def upload_attachment(
    ticket_id: str,
    request: Request,
    db: DbSession,
    context: AttachmentWriter,
    file: Annotated[UploadFile, File(...)],
    comment_id: Annotated[str | None, Form()] = None,
) -> TicketDetail:
    return await service.upload_attachment(
        db,
        context.organization_id,
        ticket_id,
        comment_id,
        file,
        _context(request, context),
    )


@router.get("/{ticket_id}/attachments/{attachment_id}/download")
async def download_attachment(
    ticket_id: str,
    attachment_id: str,
    request: Request,
    db: DbSession,
    context: Reader,
) -> FileResponse:
    path, filename, content_type = await service.attachment_download(
        db,
        context.organization_id,
        ticket_id,
        attachment_id,
        _context(request, context),
    )
    return private_file_response(path, filename=filename, media_type=content_type)


@router.post("/{ticket_id}/escalations", response_model=TicketDetail, status_code=201)
async def escalate_ticket(
    ticket_id: str,
    payload: EscalationCreate,
    request: Request,
    db: DbSession,
    context: Assigner,
) -> TicketDetail:
    return await service.escalate_ticket(
        db, context.organization_id, ticket_id, payload, _context(request, context)
    )


@router.post("/{ticket_id}/escalations/{escalation_id}", response_model=TicketDetail)
async def decide_escalation(
    ticket_id: str,
    escalation_id: str,
    payload: EscalationDecision,
    request: Request,
    db: DbSession,
    context: Assigner,
) -> TicketDetail:
    return await service.decide_escalation(
        db,
        context.organization_id,
        ticket_id,
        escalation_id,
        payload,
        _context(request, context),
    )


@router.post("/{ticket_id}/feedback", response_model=TicketDetail, status_code=201)
async def submit_feedback(
    ticket_id: str,
    payload: FeedbackCreate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> TicketDetail:
    return await service.submit_feedback(
        db, context.organization_id, ticket_id, payload, _context(request, context)
    )
