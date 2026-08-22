from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, SecurityContext, mutation_context, require_permissions
from app.core.responses import private_file_response
from app.models.enums import LeaseStatus, RentalPropertyStatus
from app.schemas.organization import Page
from app.schemas.rentals import (
    InvoiceCreate,
    LeaseCreate,
    LeaseDetail,
    LeaseDocumentCreate,
    LeaseDocumentDecision,
    LeaseSummary,
    LeaseTransition,
    MaintenanceCreate,
    MaintenanceUpdate,
    MoveComplete,
    MoveCreate,
    PaymentCreate,
    PaymentDecision,
    RenewalCreate,
    RentalOptions,
    RentalPropertyCreate,
    RentalPropertyUpdate,
    RentalPropertyView,
    RentalStats,
    TenantCreate,
    TenantUpdate,
    TenantView,
    WorkflowDecision,
)
from app.services import rentals as service
from app.services.organization import MutationContext

router = APIRouter(prefix="/rentals", tags=["rental management"])

RentalReader = Annotated[
    SecurityContext,
    Depends(require_permissions("properties.view", "leases.view", any_of=True)),
]
PropertyWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("properties.create", "properties.update", any_of=True)),
]
TenantWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("tenants.create", "tenants.update", any_of=True)),
]
LeaseWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("leases.create", "leases.update", any_of=True)),
]
LeaseApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("leases.approve", "leases.manage", any_of=True)),
]
DocumentWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("documents.create", "documents.update", any_of=True)),
]
PaymentWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("payments.create", "payments.update", any_of=True)),
]
PaymentReviewer = Annotated[
    SecurityContext,
    Depends(
        require_permissions("payments.approve", "payments.manage", "leases.approve", any_of=True)
    ),
]
MaintenanceWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("maintenance.create", "maintenance.update", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return mutation_context(request, security)


@router.get("/stats", response_model=RentalStats)
async def rental_stats(db: DbSession, context: RentalReader) -> RentalStats:
    mutation = MutationContext(
        actor_user_id=context.user.id,
        permissions=context.permissions,
        request_id=None,
        ip_address=None,
    )
    return await service.stats(db, context.organization_id, mutation)


@router.get("/options", response_model=RentalOptions)
async def rental_options(db: DbSession, context: LeaseWriter) -> RentalOptions:
    return await service.options(db, context.organization_id)


@router.get("/properties", response_model=Page[RentalPropertyView])
async def properties(
    request: Request,
    db: DbSession,
    context: RentalReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: RentalPropertyStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[RentalPropertyView]:
    return await service.list_properties(
        db,
        context.organization_id,
        _context(request, context),
        q=q,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/properties", response_model=RentalPropertyView, status_code=201)
async def create_property(
    payload: RentalPropertyCreate,
    request: Request,
    db: DbSession,
    context: PropertyWriter,
) -> RentalPropertyView:
    return await service.create_property(
        db, context.organization_id, payload, _context(request, context)
    )


@router.patch("/properties/{property_id}", response_model=RentalPropertyView)
async def update_property(
    property_id: str,
    payload: RentalPropertyUpdate,
    request: Request,
    db: DbSession,
    context: PropertyWriter,
) -> RentalPropertyView:
    return await service.update_property(
        db, context.organization_id, property_id, payload, _context(request, context)
    )


@router.get("/tenants", response_model=Page[TenantView])
async def tenants(
    db: DbSession,
    context: TenantWriter,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[TenantView]:
    return await service.list_tenants(
        db, context.organization_id, q=q, page=page, page_size=page_size
    )


@router.post("/tenants", response_model=TenantView, status_code=201)
async def create_tenant(
    payload: TenantCreate,
    request: Request,
    db: DbSession,
    context: TenantWriter,
) -> TenantView:
    return await service.create_tenant(
        db, context.organization_id, payload, _context(request, context)
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantView)
async def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    request: Request,
    db: DbSession,
    context: TenantWriter,
) -> TenantView:
    return await service.update_tenant(
        db, context.organization_id, tenant_id, payload, _context(request, context)
    )


@router.get("/leases", response_model=Page[LeaseSummary])
async def leases(
    request: Request,
    db: DbSession,
    context: RentalReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: LeaseStatus | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[LeaseSummary]:
    return await service.list_leases(
        db,
        context.organization_id,
        _context(request, context),
        q=q,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/leases", response_model=LeaseDetail, status_code=201)
async def create_lease(
    payload: LeaseCreate,
    request: Request,
    db: DbSession,
    context: LeaseWriter,
) -> LeaseDetail:
    return await service.create_lease(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/leases/{lease_id}", response_model=LeaseDetail)
async def lease_detail(
    lease_id: str,
    request: Request,
    db: DbSession,
    context: RentalReader,
) -> LeaseDetail:
    return await service.lease_detail(
        db, context.organization_id, lease_id, _context(request, context)
    )


@router.post("/leases/{lease_id}/transition", response_model=LeaseDetail)
async def transition_lease(
    lease_id: str,
    payload: LeaseTransition,
    request: Request,
    db: DbSession,
    context: LeaseApprover,
) -> LeaseDetail:
    return await service.transition_lease(
        db, context.organization_id, lease_id, payload, _context(request, context)
    )


@router.post("/leases/{lease_id}/documents", response_model=LeaseDetail, status_code=201)
async def add_document(
    lease_id: str,
    payload: LeaseDocumentCreate,
    request: Request,
    db: DbSession,
    context: LeaseWriter,
) -> LeaseDetail:
    return await service.add_document(
        db, context.organization_id, lease_id, payload, _context(request, context)
    )


@router.post("/leases/{lease_id}/documents/{document_id}/upload", response_model=LeaseDetail)
async def upload_document(
    lease_id: str,
    document_id: str,
    request: Request,
    db: DbSession,
    context: DocumentWriter,
    file: Annotated[UploadFile, File(...)],
) -> LeaseDetail:
    return await service.upload_document(
        db, context.organization_id, lease_id, document_id, file, _context(request, context)
    )


@router.post("/leases/{lease_id}/documents/{document_id}/decision", response_model=LeaseDetail)
async def decide_document(
    lease_id: str,
    document_id: str,
    payload: LeaseDocumentDecision,
    request: Request,
    db: DbSession,
    context: LeaseApprover,
) -> LeaseDetail:
    return await service.decide_document(
        db,
        context.organization_id,
        lease_id,
        document_id,
        payload,
        _context(request, context),
    )


@router.get("/leases/{lease_id}/documents/{document_id}/download")
async def download_document(
    lease_id: str,
    document_id: str,
    request: Request,
    db: DbSession,
    context: RentalReader,
) -> FileResponse:
    path, filename, content_type = await service.document_download(
        db,
        context.organization_id,
        lease_id,
        document_id,
        _context(request, context),
    )
    return private_file_response(path, filename=filename, media_type=content_type)


@router.post("/leases/{lease_id}/invoices", response_model=LeaseDetail, status_code=201)
async def issue_invoice(
    lease_id: str,
    payload: InvoiceCreate,
    request: Request,
    db: DbSession,
    context: LeaseWriter,
) -> LeaseDetail:
    return await service.issue_invoice(
        db, context.organization_id, lease_id, payload, _context(request, context)
    )


@router.post("/leases/{lease_id}/invoices/{invoice_id}/payments", response_model=LeaseDetail)
async def submit_payment(
    lease_id: str,
    invoice_id: str,
    payload: PaymentCreate,
    request: Request,
    db: DbSession,
    context: PaymentWriter,
) -> LeaseDetail:
    return await service.submit_payment(
        db,
        context.organization_id,
        lease_id,
        invoice_id,
        payload,
        _context(request, context),
    )


@router.post("/leases/{lease_id}/payments/{payment_id}/decision", response_model=LeaseDetail)
async def decide_payment(
    lease_id: str,
    payment_id: str,
    payload: PaymentDecision,
    request: Request,
    db: DbSession,
    context: PaymentReviewer,
) -> LeaseDetail:
    return await service.decide_payment(
        db,
        context.organization_id,
        lease_id,
        payment_id,
        payload,
        _context(request, context),
    )


@router.post("/leases/{lease_id}/renewals", response_model=LeaseDetail, status_code=201)
async def request_renewal(
    lease_id: str,
    payload: RenewalCreate,
    request: Request,
    db: DbSession,
    context: RentalReader,
) -> LeaseDetail:
    return await service.request_renewal(
        db, context.organization_id, lease_id, payload, _context(request, context)
    )


@router.post("/leases/{lease_id}/renewals/{renewal_id}/decision", response_model=LeaseDetail)
async def decide_renewal(
    lease_id: str,
    renewal_id: str,
    payload: WorkflowDecision,
    request: Request,
    db: DbSession,
    context: LeaseApprover,
) -> LeaseDetail:
    return await service.decide_renewal(
        db,
        context.organization_id,
        lease_id,
        renewal_id,
        payload,
        _context(request, context),
    )


@router.post("/leases/{lease_id}/moves", response_model=LeaseDetail, status_code=201)
async def request_move(
    lease_id: str,
    payload: MoveCreate,
    request: Request,
    db: DbSession,
    context: RentalReader,
) -> LeaseDetail:
    return await service.request_move(
        db, context.organization_id, lease_id, payload, _context(request, context)
    )


@router.post("/leases/{lease_id}/moves/{move_id}/decision", response_model=LeaseDetail)
async def decide_move(
    lease_id: str,
    move_id: str,
    payload: WorkflowDecision,
    request: Request,
    db: DbSession,
    context: LeaseApprover,
) -> LeaseDetail:
    return await service.decide_move(
        db,
        context.organization_id,
        lease_id,
        move_id,
        payload,
        _context(request, context),
    )


@router.post("/leases/{lease_id}/moves/{move_id}/complete", response_model=LeaseDetail)
async def complete_move(
    lease_id: str,
    move_id: str,
    payload: MoveComplete,
    request: Request,
    db: DbSession,
    context: LeaseApprover,
) -> LeaseDetail:
    return await service.complete_move(
        db,
        context.organization_id,
        lease_id,
        move_id,
        payload,
        _context(request, context),
    )


@router.post("/maintenance", response_model=LeaseDetail, status_code=201)
async def create_maintenance(
    payload: MaintenanceCreate,
    request: Request,
    db: DbSession,
    context: MaintenanceWriter,
) -> LeaseDetail:
    return await service.create_maintenance(
        db, context.organization_id, payload, _context(request, context)
    )


@router.post("/leases/{lease_id}/maintenance/{maintenance_id}", response_model=LeaseDetail)
async def update_maintenance(
    lease_id: str,
    maintenance_id: str,
    payload: MaintenanceUpdate,
    request: Request,
    db: DbSession,
    context: MaintenanceWriter,
) -> LeaseDetail:
    return await service.update_maintenance(
        db,
        context.organization_id,
        lease_id,
        maintenance_id,
        payload,
        _context(request, context),
    )
