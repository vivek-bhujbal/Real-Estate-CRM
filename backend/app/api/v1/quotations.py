from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.documents.quotation_pdf import (
    BasicQuotationPdfRenderer,
    QuotationPdfDocument,
    QuotationPdfLine,
)
from app.models.enums import CostSheetStatus, QuotationStatus, RecordStatus
from app.schemas.organization import Page
from app.schemas.quotations import (
    ApprovalDecision,
    ApprovalMatrixOptions,
    CostSheetCreate,
    CostSheetView,
    PriceListCreate,
    PriceListStatusPayload,
    PriceListUpdate,
    PriceListView,
    QuotationCreate,
    QuotationStats,
    QuotationStatusPayload,
    QuotationVersionCreate,
    QuotationView,
)
from app.services import quotations as quotation_service
from app.services.organization import MutationContext

router = APIRouter(tags=["quotation-cost-sheets"])

QuotationReader = Annotated[SecurityContext, Depends(require_permissions("quotations.view"))]
QuotationCreator = Annotated[SecurityContext, Depends(require_permissions("quotations.create"))]
QuotationUpdater = Annotated[SecurityContext, Depends(require_permissions("quotations.update"))]
QuotationDeleter = Annotated[SecurityContext, Depends(require_permissions("quotations.delete"))]
QuotationApprover = Annotated[SecurityContext, Depends(require_permissions("quotations.approve"))]
QuotationExporter = Annotated[SecurityContext, Depends(require_permissions("quotations.export"))]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/price-lists", response_model=Page[PriceListView])
async def price_lists(
    db: DbSession,
    context: QuotationReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    project_id: str | None = None,
    status: RecordStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PriceListView]:
    return await quotation_service.list_price_lists(
        db,
        context.organization_id,
        q=q,
        project_id=project_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/discount-approval-options", response_model=ApprovalMatrixOptions)
async def discount_approval_options(
    db: DbSession, context: QuotationReader
) -> ApprovalMatrixOptions:
    return await quotation_service.approval_matrix_options(db, context.organization_id)


@router.post("/price-lists", response_model=PriceListView, status_code=201)
async def create_price_list(
    payload: PriceListCreate,
    request: Request,
    db: DbSession,
    context: QuotationCreator,
) -> PriceListView:
    return await quotation_service.create_price_list(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/price-lists/{price_list_id}", response_model=PriceListView)
async def price_list(price_list_id: str, db: DbSession, context: QuotationReader) -> PriceListView:
    return await quotation_service.get_price_list(db, context.organization_id, price_list_id)


@router.patch("/price-lists/{price_list_id}", response_model=PriceListView)
async def update_price_list(
    price_list_id: str,
    payload: PriceListUpdate,
    request: Request,
    db: DbSession,
    context: QuotationUpdater,
) -> PriceListView:
    return await quotation_service.update_price_list(
        db, context.organization_id, price_list_id, payload, _context(request, context)
    )


@router.post("/price-lists/{price_list_id}/status", response_model=PriceListView)
async def price_list_status(
    price_list_id: str,
    payload: PriceListStatusPayload,
    request: Request,
    db: DbSession,
    context: QuotationApprover,
) -> PriceListView:
    return await quotation_service.change_price_list_status(
        db, context.organization_id, price_list_id, payload, _context(request, context)
    )


@router.delete("/price-lists/{price_list_id}", status_code=204)
async def delete_price_list(
    price_list_id: str,
    request: Request,
    db: DbSession,
    context: QuotationDeleter,
) -> None:
    await quotation_service.delete_price_list(
        db, context.organization_id, price_list_id, _context(request, context)
    )


@router.post("/cost-sheets/preview", response_model=CostSheetView)
async def preview_cost_sheet(
    payload: CostSheetCreate,
    request: Request,
    db: DbSession,
    context: QuotationCreator,
) -> CostSheetView:
    return await quotation_service.calculate_cost_sheet(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/cost-sheets", response_model=Page[CostSheetView])
async def cost_sheets(
    db: DbSession,
    context: QuotationReader,
    customer_id: str | None = None,
    status: CostSheetStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CostSheetView]:
    return await quotation_service.list_cost_sheets(
        db,
        context.organization_id,
        customer_id=customer_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/cost-sheets", response_model=CostSheetView, status_code=201)
async def create_cost_sheet(
    payload: CostSheetCreate,
    request: Request,
    db: DbSession,
    context: QuotationCreator,
) -> CostSheetView:
    return await quotation_service.create_cost_sheet(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/cost-sheets/{cost_sheet_id}", response_model=CostSheetView)
async def cost_sheet(cost_sheet_id: str, db: DbSession, context: QuotationReader) -> CostSheetView:
    return await quotation_service.get_cost_sheet(db, context.organization_id, cost_sheet_id)


@router.post("/cost-sheets/{cost_sheet_id}/approval", response_model=CostSheetView)
async def decide_discount(
    cost_sheet_id: str,
    payload: ApprovalDecision,
    request: Request,
    db: DbSession,
    context: QuotationApprover,
) -> CostSheetView:
    return await quotation_service.decide_discount(
        db, context.organization_id, cost_sheet_id, payload, _context(request, context)
    )


@router.get("/quotations", response_model=Page[QuotationView])
async def quotations(
    db: DbSession,
    context: QuotationReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: QuotationStatus | None = None,
    customer_id: str | None = None,
    unit_id: str | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[QuotationView]:
    return await quotation_service.list_quotations(
        db,
        context.organization_id,
        q=q,
        status=status,
        customer_id=customer_id,
        unit_id=unit_id,
        page=page,
        page_size=page_size,
    )


@router.post("/quotations", response_model=QuotationView, status_code=201)
async def create_quotation(
    payload: QuotationCreate,
    request: Request,
    db: DbSession,
    context: QuotationCreator,
) -> QuotationView:
    return await quotation_service.create_quotation(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/quotations/stats", response_model=QuotationStats)
async def quotation_stats(db: DbSession, context: QuotationReader) -> QuotationStats:
    return await quotation_service.stats(db, context.organization_id)


@router.get("/quotations/{quotation_id}", response_model=QuotationView)
async def quotation(quotation_id: str, db: DbSession, context: QuotationReader) -> QuotationView:
    return await quotation_service.get_quotation(db, context.organization_id, quotation_id)


@router.post("/quotations/{quotation_id}/versions", response_model=QuotationView, status_code=201)
async def create_version(
    quotation_id: str,
    payload: QuotationVersionCreate,
    request: Request,
    db: DbSession,
    context: QuotationUpdater,
) -> QuotationView:
    return await quotation_service.create_quotation_version(
        db,
        context.organization_id,
        quotation_id,
        payload,
        _context(request, context),
    )


@router.post("/quotations/{quotation_id}/status", response_model=QuotationView)
async def quotation_status(
    quotation_id: str,
    payload: QuotationStatusPayload,
    request: Request,
    db: DbSession,
    context: QuotationUpdater,
) -> QuotationView:
    return await quotation_service.change_quotation_status(
        db,
        context.organization_id,
        quotation_id,
        payload,
        _context(request, context),
    )


@router.get("/quotations/{quotation_id}/pdf")
async def quotation_pdf(
    quotation_id: str,
    db: DbSession,
    context: QuotationExporter,
) -> StreamingResponse:
    quote = await quotation_service.get_quotation(db, context.organization_id, quotation_id)
    document = QuotationPdfDocument(
        organization_name=context.user.organization.name,
        quotation_number=quote.quotation_number,
        version=quote.version,
        customer_name=quote.customer_name or quote.lead_name or "Customer",
        project_name=quote.project_name,
        unit_number=quote.unit_number or "Not specified",
        currency=quote.currency,
        valid_until=str(quote.valid_until),
        lines=tuple(
            QuotationPdfLine(label=item.description, amount=item.total) for item in quote.items
        ),
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
        final_agreed_value=(
            quote.final_agreed_value if quote.final_agreed_value is not None else quote.total
        ),
        booking_amount=quote.booking_amount if quote.booking_amount is not None else quote.total,
    )
    content = BasicQuotationPdfRenderer().render(document)
    filename = f"{quote.quotation_number}-v{quote.version}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
