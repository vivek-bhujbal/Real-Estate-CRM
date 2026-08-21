from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.schemas.finance import (
    ChargeCreate,
    ChargeWaive,
    CollectionAccount,
    CollectionAccountDetail,
    CollectionPaymentCreate,
    DemandCreate,
    FinanceSummary,
    PaymentAllocationRequest,
    ReconciliationCreate,
    RefundCreate,
    RefundDecision,
    RefundProcess,
)
from app.schemas.organization import Page
from app.services import finance as finance_service
from app.services.organization import MutationContext

router = APIRouter(prefix="/collections", tags=["finance and collections"])

FinanceReader = Annotated[SecurityContext, Depends(require_permissions("collections.view"))]
CollectionCreator = Annotated[
    SecurityContext,
    Depends(require_permissions("collections.create", "collections.manage", any_of=True)),
]
PaymentCreator = Annotated[
    SecurityContext, Depends(require_permissions("payments.create", "payments.manage", any_of=True))
]
PaymentApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("payments.approve", "payments.manage", any_of=True)),
]
CollectionApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("collections.approve", "collections.manage", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/summary", response_model=FinanceSummary)
async def summary(db: DbSession, context: FinanceReader) -> FinanceSummary:
    return await finance_service.summary(db, context.organization_id)


@router.get("/accounts", response_model=Page[CollectionAccount])
async def accounts(
    db: DbSession,
    context: FinanceReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    overdue_only: bool = False,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CollectionAccount]:
    return await finance_service.list_accounts(
        db, context.organization_id, q=q, overdue_only=overdue_only, page=page, page_size=page_size
    )


@router.get("/bookings/{booking_id}", response_model=CollectionAccountDetail)
async def account(
    booking_id: str, db: DbSession, context: FinanceReader
) -> CollectionAccountDetail:
    return await finance_service.detail(db, context.organization_id, booking_id)


@router.post(
    "/bookings/{booking_id}/demands", response_model=CollectionAccountDetail, status_code=201
)
async def create_demand(
    booking_id: str,
    payload: DemandCreate,
    request: Request,
    db: DbSession,
    context: CollectionCreator,
) -> CollectionAccountDetail:
    return await finance_service.create_demand(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.post(
    "/bookings/{booking_id}/payments", response_model=CollectionAccountDetail, status_code=201
)
async def create_payment(
    booking_id: str,
    payload: CollectionPaymentCreate,
    request: Request,
    db: DbSession,
    context: PaymentCreator,
) -> CollectionAccountDetail:
    return await finance_service.create_payment(
        db, context.organization_id, booking_id, payload, _context(request, context)
    )


@router.post(
    "/payments/{payment_id}/reconciliations",
    response_model=CollectionAccountDetail,
    status_code=201,
)
async def reconcile(
    payment_id: str,
    payload: ReconciliationCreate,
    request: Request,
    db: DbSession,
    context: PaymentApprover,
) -> CollectionAccountDetail:
    return await finance_service.reconcile_payment(
        db, context.organization_id, payment_id, payload, _context(request, context)
    )


@router.post("/payments/{payment_id}/allocate", response_model=CollectionAccountDetail)
async def allocate(
    payment_id: str,
    payload: PaymentAllocationRequest,
    request: Request,
    db: DbSession,
    context: PaymentApprover,
) -> CollectionAccountDetail:
    return await finance_service.allocate_payment(
        db, context.organization_id, payment_id, payload, _context(request, context)
    )


@router.post(
    "/installments/{installment_id}/charges",
    response_model=CollectionAccountDetail,
    status_code=201,
)
async def charge(
    installment_id: str,
    payload: ChargeCreate,
    request: Request,
    db: DbSession,
    context: CollectionCreator,
) -> CollectionAccountDetail:
    return await finance_service.create_charge(
        db, context.organization_id, installment_id, payload, _context(request, context)
    )


@router.post("/charges/{charge_id}/waive", response_model=CollectionAccountDetail)
async def waive(
    charge_id: str,
    payload: ChargeWaive,
    request: Request,
    db: DbSession,
    context: CollectionApprover,
) -> CollectionAccountDetail:
    return await finance_service.waive_charge(
        db, context.organization_id, charge_id, payload, _context(request, context)
    )


@router.post(
    "/payments/{payment_id}/refunds", response_model=CollectionAccountDetail, status_code=201
)
async def refund(
    payment_id: str, payload: RefundCreate, request: Request, db: DbSession, context: PaymentCreator
) -> CollectionAccountDetail:
    return await finance_service.request_refund(
        db, context.organization_id, payment_id, payload, _context(request, context)
    )


@router.post("/refunds/{refund_id}/decision", response_model=CollectionAccountDetail)
async def refund_decision(
    refund_id: str,
    payload: RefundDecision,
    request: Request,
    db: DbSession,
    context: PaymentApprover,
) -> CollectionAccountDetail:
    return await finance_service.decide_refund(
        db, context.organization_id, refund_id, payload, _context(request, context)
    )


@router.post("/refunds/{refund_id}/process", response_model=CollectionAccountDetail)
async def process_refund(
    refund_id: str,
    payload: RefundProcess,
    request: Request,
    db: DbSession,
    context: PaymentApprover,
) -> CollectionAccountDetail:
    return await finance_service.process_refund(
        db, context.organization_id, refund_id, payload, _context(request, context)
    )
