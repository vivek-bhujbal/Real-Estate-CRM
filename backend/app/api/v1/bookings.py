from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.enums import BookingStatus
from app.schemas.bookings import (
    BookingAdvance,
    BookingApprovalDecision,
    BookingApprovalRequest,
    BookingCancel,
    BookingCreate,
    BookingOptions,
    BookingPaymentCreate,
    BookingPaymentDecision,
    BookingStats,
    BookingView,
    FinancingInput,
    JointApplicantInput,
    PaymentPlanInput,
)
from app.schemas.organization import Page
from app.services import bookings as booking_service
from app.services.organization import MutationContext

router = APIRouter(prefix="/bookings", tags=["bookings"])

BookingReader = Annotated[SecurityContext, Depends(require_permissions("bookings.view"))]
BookingCreator = Annotated[SecurityContext, Depends(require_permissions("bookings.create"))]
BookingOptionReader = Annotated[
    SecurityContext,
    Depends(require_permissions("bookings.create", "bookings.update", any_of=True)),
]
BookingUpdater = Annotated[SecurityContext, Depends(require_permissions("bookings.update"))]
BookingApprover = Annotated[SecurityContext, Depends(require_permissions("bookings.approve"))]
PaymentCreator = Annotated[
    SecurityContext,
    Depends(require_permissions("payments.create", "bookings.update", any_of=True)),
]
PaymentApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("payments.approve", "bookings.approve", any_of=True)),
]
FinancingUpdater = Annotated[
    SecurityContext,
    Depends(require_permissions("financing.update", "bookings.update", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("", response_model=Page[BookingView])
async def bookings(
    db: DbSession,
    context: BookingReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: BookingStatus | None = None,
    customer_id: str | None = None,
    salesperson_user_id: str | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[BookingView]:
    return await booking_service.list_bookings(
        db,
        context.organization_id,
        q=q,
        status=status,
        customer_id=customer_id,
        salesperson_user_id=salesperson_user_id,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=BookingStats)
async def stats(db: DbSession, context: BookingReader) -> BookingStats:
    return await booking_service.booking_stats(db, context.organization_id)


@router.get("/options", response_model=BookingOptions)
async def options(db: DbSession, context: BookingOptionReader) -> BookingOptions:
    return await booking_service.booking_options(db, context.organization_id, context.user.id)


@router.post("", response_model=BookingView, status_code=201)
async def create_booking(
    payload: BookingCreate,
    request: Request,
    db: DbSession,
    context: BookingCreator,
) -> BookingView:
    return await booking_service.create_booking(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/{booking_id}", response_model=BookingView)
async def booking(booking_id: str, db: DbSession, context: BookingReader) -> BookingView:
    return await booking_service.get_booking(db, context.organization_id, booking_id)


@router.post("/{booking_id}/advance", response_model=BookingView)
async def advance(
    booking_id: str,
    payload: BookingAdvance,
    request: Request,
    db: DbSession,
    context: BookingUpdater,
) -> BookingView:
    return await booking_service.advance_booking(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.put("/{booking_id}/applicants", response_model=BookingView)
async def applicants(
    booking_id: str,
    payload: list[JointApplicantInput],
    request: Request,
    db: DbSession,
    context: BookingUpdater,
) -> BookingView:
    return await booking_service.replace_joint_applicants(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.put("/{booking_id}/payment-plan", response_model=BookingView)
async def payment_plan(
    booking_id: str,
    payload: PaymentPlanInput,
    request: Request,
    db: DbSession,
    context: BookingUpdater,
) -> BookingView:
    return await booking_service.set_payment_plan(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.put("/{booking_id}/financing", response_model=BookingView)
async def financing(
    booking_id: str,
    payload: FinancingInput,
    request: Request,
    db: DbSession,
    context: FinancingUpdater,
) -> BookingView:
    return await booking_service.set_financing(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.post("/{booking_id}/payments", response_model=BookingView, status_code=201)
async def create_payment(
    booking_id: str,
    payload: BookingPaymentCreate,
    request: Request,
    db: DbSession,
    context: PaymentCreator,
) -> BookingView:
    return await booking_service.create_payment(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.post("/{booking_id}/payments/{payment_id}/decision", response_model=BookingView)
async def payment_decision(
    booking_id: str,
    payment_id: str,
    payload: BookingPaymentDecision,
    request: Request,
    db: DbSession,
    context: PaymentApprover,
) -> BookingView:
    return await booking_service.decide_payment(
        db,
        context.organization_id,
        booking_id,
        payment_id,
        payload,
        _context(request, context),
    )


@router.post("/{booking_id}/approval-request", response_model=BookingView)
async def request_approval(
    booking_id: str,
    payload: BookingApprovalRequest,
    request: Request,
    db: DbSession,
    context: BookingUpdater,
) -> BookingView:
    return await booking_service.request_approval(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.post("/{booking_id}/approvals/{approval_id}/decision", response_model=BookingView)
async def approval_decision(
    booking_id: str,
    approval_id: str,
    payload: BookingApprovalDecision,
    request: Request,
    db: DbSession,
    context: BookingApprover,
) -> BookingView:
    return await booking_service.decide_approval(
        db,
        context.organization_id,
        booking_id,
        approval_id,
        payload,
        _context(request, context),
    )


@router.post("/{booking_id}/cancel", response_model=BookingView)
async def cancel(
    booking_id: str,
    payload: BookingCancel,
    request: Request,
    db: DbSession,
    context: BookingUpdater,
) -> BookingView:
    return await booking_service.cancel_booking(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )
