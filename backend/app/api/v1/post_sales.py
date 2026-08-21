from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.entities import Cancellation, UnitTransfer
from app.models.enums import WorkflowStatus
from app.schemas.organization import Page
from app.schemas.post_sales import (
    CancellationCreate,
    CancellationReview,
    CancellationView,
    PostSalesOptions,
    PostSalesStats,
    UnitTransferCreate,
    UnitTransferReview,
    UnitTransferView,
    WorkflowDecision,
)
from app.services import post_sales as service
from app.services.organization import MutationContext

router = APIRouter(prefix="/post-sales", tags=["cancellations refunds and unit transfers"])

Reader = Annotated[
    SecurityContext,
    Depends(require_permissions("bookings.view", "collections.view", any_of=True)),
]
Requester = Annotated[
    SecurityContext,
    Depends(require_permissions("bookings.update", "bookings.manage", any_of=True)),
]
Reviewer = Annotated[
    SecurityContext,
    Depends(
        require_permissions("bookings.update", "collections.update", "bookings.manage", any_of=True)
    ),
]
Approver = Annotated[
    SecurityContext,
    Depends(
        require_permissions(
            "bookings.approve", "collections.approve", "bookings.manage", any_of=True
        )
    ),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/stats", response_model=PostSalesStats)
async def stats(db: DbSession, context: Reader) -> PostSalesStats:
    return await service.stats(db, context.organization_id)


@router.get("/options", response_model=PostSalesOptions)
async def options(db: DbSession, context: Requester) -> PostSalesOptions:
    return await service.options(db, context.organization_id)


@router.get("/cancellations", response_model=Page[CancellationView])
async def cancellations(
    db: DbSession,
    context: Reader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: WorkflowStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CancellationView]:
    return await service.list_cancellations(
        db,
        context.organization_id,
        q=q,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/bookings/{booking_id}/cancellations",
    response_model=CancellationView,
    status_code=201,
)
async def request_cancellation(
    booking_id: str,
    payload: CancellationCreate,
    request: Request,
    db: DbSession,
    context: Requester,
) -> CancellationView:
    return await service.request_cancellation(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.get("/cancellations/{cancellation_id}", response_model=CancellationView)
async def cancellation(cancellation_id: str, db: DbSession, context: Reader) -> CancellationView:
    item = await service._entity(db, Cancellation, context.organization_id, cancellation_id)
    return await service.cancellation_view(db, context.organization_id, item)


@router.post("/cancellations/{cancellation_id}/review", response_model=CancellationView)
async def review_cancellation(
    cancellation_id: str,
    payload: CancellationReview,
    request: Request,
    db: DbSession,
    context: Reviewer,
) -> CancellationView:
    return await service.review_cancellation(
        db, context.organization_id, cancellation_id, payload, _context(request, context)
    )


@router.post("/cancellations/{cancellation_id}/decision", response_model=CancellationView)
async def decide_cancellation(
    cancellation_id: str,
    payload: WorkflowDecision,
    request: Request,
    db: DbSession,
    context: Approver,
) -> CancellationView:
    return await service.decide_cancellation(
        db, context.organization_id, cancellation_id, payload, _context(request, context)
    )


@router.post("/cancellations/{cancellation_id}/complete", response_model=CancellationView)
async def complete_cancellation(
    cancellation_id: str, request: Request, db: DbSession, context: Approver
) -> CancellationView:
    return await service.complete_cancellation(
        db, context.organization_id, cancellation_id, _context(request, context)
    )


@router.get("/cancellations/{cancellation_id}/document")
async def cancellation_document(
    cancellation_id: str, db: DbSession, context: Reader
) -> FileResponse:
    path, filename = await service.document_path(
        db, context.organization_id, "cancellations", cancellation_id
    )
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/transfers", response_model=Page[UnitTransferView])
async def transfers(
    db: DbSession,
    context: Reader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: WorkflowStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[UnitTransferView]:
    return await service.list_transfers(
        db,
        context.organization_id,
        q=q,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/bookings/{booking_id}/transfers", response_model=UnitTransferView, status_code=201)
async def request_transfer(
    booking_id: str,
    payload: UnitTransferCreate,
    request: Request,
    db: DbSession,
    context: Requester,
) -> UnitTransferView:
    return await service.request_transfer(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.get("/transfers/{transfer_id}", response_model=UnitTransferView)
async def transfer(transfer_id: str, db: DbSession, context: Reader) -> UnitTransferView:
    item = await service._entity(db, UnitTransfer, context.organization_id, transfer_id)
    return await service.transfer_view(db, context.organization_id, item)


@router.post("/transfers/{transfer_id}/review", response_model=UnitTransferView)
async def review_transfer(
    transfer_id: str,
    payload: UnitTransferReview,
    request: Request,
    db: DbSession,
    context: Reviewer,
) -> UnitTransferView:
    return await service.review_transfer(
        db, context.organization_id, transfer_id, payload, _context(request, context)
    )


@router.post("/transfers/{transfer_id}/decision", response_model=UnitTransferView)
async def decide_transfer(
    transfer_id: str,
    payload: WorkflowDecision,
    request: Request,
    db: DbSession,
    context: Approver,
) -> UnitTransferView:
    return await service.decide_transfer(
        db, context.organization_id, transfer_id, payload, _context(request, context)
    )


@router.post("/transfers/{transfer_id}/complete", response_model=UnitTransferView)
async def complete_transfer(
    transfer_id: str, request: Request, db: DbSession, context: Approver
) -> UnitTransferView:
    return await service.complete_transfer(
        db, context.organization_id, transfer_id, _context(request, context)
    )


@router.get("/transfers/{transfer_id}/document")
async def transfer_document(transfer_id: str, db: DbSession, context: Reader) -> FileResponse:
    path, filename = await service.document_path(
        db, context.organization_id, "transfers", transfer_id
    )
    return FileResponse(path, media_type="application/pdf", filename=filename)
