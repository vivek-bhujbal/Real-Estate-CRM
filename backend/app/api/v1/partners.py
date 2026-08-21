from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.entities import PartnerAgreement, PartnerDocument
from app.models.enums import PartnerStatus
from app.schemas.organization import Page
from app.schemas.partners import (
    CommissionDecision,
    CommissionStructureCreate,
    DisputeAssign,
    DisputeCreate,
    DisputeDecision,
    LifecycleAction,
    PartnerAgreementCreate,
    PartnerApplicationCreate,
    PartnerAssignmentsUpdate,
    PartnerComplianceUpdate,
    PartnerContactCreate,
    PartnerDetail,
    PartnerDocumentDecision,
    PartnerDocumentRequest,
    PartnerLeadCreate,
    PartnerOptions,
    PartnerProfileUpdate,
    PartnerStats,
    PartnerSummary,
    PayoutCreate,
    PayoutProcess,
)
from app.services import partners as service
from app.services.organization import MutationContext

router = APIRouter(prefix="/partners", tags=["channel partners"])

Reader = Annotated[SecurityContext, Depends(require_permissions("partners.view"))]
Creator = Annotated[SecurityContext, Depends(require_permissions("partners.create"))]
Updater = Annotated[SecurityContext, Depends(require_permissions("partners.update"))]
Approver = Annotated[SecurityContext, Depends(require_permissions("partners.approve"))]
Assigner = Annotated[
    SecurityContext,
    Depends(require_permissions("partners.assign", "partners.update", any_of=True)),
]
CommissionReader = Annotated[
    SecurityContext,
    Depends(require_permissions("commissions.view", "partners.view", any_of=True)),
]
CommissionCreator = Annotated[
    SecurityContext,
    Depends(require_permissions("commissions.create", "commissions.manage", any_of=True)),
]
CommissionApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("commissions.approve", "commissions.manage", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("", response_model=Page[PartnerSummary])
async def partners(
    db: DbSession,
    context: Reader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: PartnerStatus | None = None,
    manager_user_id: str | None = None,
    territory_id: str | None = None,
    project_id: str | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PartnerSummary]:
    return await service.list_partners(
        db,
        context.organization_id,
        q=q,
        status=status,
        manager_user_id=manager_user_id,
        territory_id=territory_id,
        project_id=project_id,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=PartnerStats)
async def stats(db: DbSession, context: Reader) -> PartnerStats:
    return await service.stats(db, context.organization_id)


@router.get("/options", response_model=PartnerOptions)
async def options(db: DbSession, context: Reader) -> PartnerOptions:
    return await service.options(db, context.organization_id)


@router.post("", response_model=PartnerDetail, status_code=201)
async def create_partner(
    payload: PartnerApplicationCreate,
    request: Request,
    db: DbSession,
    context: Creator,
) -> PartnerDetail:
    return await service.create_application(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/{partner_id}", response_model=PartnerDetail)
async def partner(partner_id: str, db: DbSession, context: Reader) -> PartnerDetail:
    return await service.detail(db, context.organization_id, partner_id)


@router.patch("/{partner_id}/profile", response_model=PartnerDetail)
async def update_profile(
    partner_id: str,
    payload: PartnerProfileUpdate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.update_profile(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.put("/{partner_id}/compliance", response_model=PartnerDetail)
async def update_compliance(
    partner_id: str,
    payload: PartnerComplianceUpdate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.update_compliance(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.put("/{partner_id}/assignments", response_model=PartnerDetail)
async def update_assignments(
    partner_id: str,
    payload: PartnerAssignmentsUpdate,
    request: Request,
    db: DbSession,
    context: Assigner,
) -> PartnerDetail:
    return await service.update_assignments(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/contacts", response_model=PartnerDetail, status_code=201)
async def add_contact(
    partner_id: str,
    payload: PartnerContactCreate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.add_contact(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/lifecycle/document-verification", response_model=PartnerDetail)
async def start_document_verification(
    partner_id: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.start_document_verification(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/documents", response_model=PartnerDetail, status_code=201)
async def request_document(
    partner_id: str,
    payload: PartnerDocumentRequest,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.request_document(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/documents/{document_id}/upload", response_model=PartnerDetail)
async def upload_document(
    partner_id: str,
    document_id: str,
    request: Request,
    db: DbSession,
    context: Updater,
    file: Annotated[UploadFile, File()],
) -> PartnerDetail:
    return await service.upload_document(
        db,
        context.organization_id,
        partner_id,
        document_id,
        file,
        _context(request, context),
    )


@router.post("/{partner_id}/documents/{document_id}/decision", response_model=PartnerDetail)
async def decide_document(
    partner_id: str,
    document_id: str,
    payload: PartnerDocumentDecision,
    request: Request,
    db: DbSession,
    context: Approver,
) -> PartnerDetail:
    return await service.decide_document(
        db,
        context.organization_id,
        partner_id,
        document_id,
        payload,
        _context(request, context),
    )


@router.get("/{partner_id}/documents/{document_id}/download")
async def download_document(
    partner_id: str, document_id: str, db: DbSession, context: Reader
) -> FileResponse:
    item = await service._entity(db, PartnerDocument, context.organization_id, document_id)
    if item.channel_partner_id != partner_id:
        raise service._error("RESOURCE_NOT_FOUND", "Partner document not found", 404)
    path, filename, content_type = await service.prepare_document_download(
        db, context.organization_id, document_id
    )
    return FileResponse(path, filename=filename, media_type=content_type)


@router.post("/{partner_id}/lifecycle/documents-complete", response_model=PartnerDetail)
async def documents_complete(
    partner_id: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    context: Approver,
) -> PartnerDetail:
    return await service.complete_document_verification(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/agreements", response_model=PartnerDetail, status_code=201)
async def create_agreement(
    partner_id: str,
    payload: PartnerAgreementCreate,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.create_agreement(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/agreements/{agreement_id}/signed-copy", response_model=PartnerDetail)
async def signed_agreement(
    partner_id: str,
    agreement_id: str,
    request: Request,
    db: DbSession,
    context: Approver,
    file: Annotated[UploadFile, File()],
) -> PartnerDetail:
    return await service.upload_signed_agreement(
        db,
        context.organization_id,
        partner_id,
        agreement_id,
        file,
        _context(request, context),
    )


@router.get("/{partner_id}/agreements/{agreement_id}/download")
async def download_agreement(
    partner_id: str, agreement_id: str, db: DbSession, context: Reader
) -> FileResponse:
    item = await service._entity(db, PartnerAgreement, context.organization_id, agreement_id)
    if item.channel_partner_id != partner_id:
        raise service._error("RESOURCE_NOT_FOUND", "Partner agreement not found", 404)
    path, filename = await service.prepare_agreement_download(
        db, context.organization_id, agreement_id
    )
    return FileResponse(path, filename=filename, media_type="application/pdf")


@router.post("/{partner_id}/commission-structures", response_model=PartnerDetail, status_code=201)
async def create_commission_structure(
    partner_id: str,
    payload: CommissionStructureCreate,
    request: Request,
    db: DbSession,
    context: CommissionCreator,
) -> PartnerDetail:
    return await service.create_commission_structure(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/lifecycle/submit-approval", response_model=PartnerDetail)
async def submit_approval(
    partner_id: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    context: Updater,
) -> PartnerDetail:
    return await service.submit_approval(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/lifecycle/{decision}", response_model=PartnerDetail)
async def approval_decision(
    partner_id: str,
    decision: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    context: Approver,
) -> PartnerDetail:
    if decision not in {"approve", "reject"}:
        raise service._error("INVALID_DECISION", "Decision must be approve or reject", 422)
    return await service.decide_approval(
        db,
        context.organization_id,
        partner_id,
        "APPROVED" if decision == "approve" else "REJECTED",
        payload,
        _context(request, context),
    )


@router.post("/{partner_id}/lifecycle/activate/final", response_model=PartnerDetail)
async def activate(
    partner_id: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    context: Approver,
) -> PartnerDetail:
    return await service.activate(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/status/{status}", response_model=PartnerDetail)
async def operational_status(
    partner_id: str,
    status: PartnerStatus,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    context: Approver,
) -> PartnerDetail:
    return await service.set_operational_status(
        db, context.organization_id, partner_id, status, payload, _context(request, context)
    )


@router.post("/{partner_id}/leads", response_model=PartnerDetail, status_code=201)
async def register_lead(
    partner_id: str,
    payload: PartnerLeadCreate,
    request: Request,
    db: DbSession,
    context: Creator,
) -> PartnerDetail:
    return await service.register_lead(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/commissions/{commission_id}/decision", response_model=PartnerDetail)
async def commission_decision(
    partner_id: str,
    commission_id: str,
    payload: CommissionDecision,
    request: Request,
    db: DbSession,
    context: CommissionApprover,
) -> PartnerDetail:
    return await service.decide_commission(
        db,
        context.organization_id,
        partner_id,
        commission_id,
        payload,
        _context(request, context),
    )


@router.post("/{partner_id}/payouts", response_model=PartnerDetail, status_code=201)
async def request_payout(
    partner_id: str,
    payload: PayoutCreate,
    request: Request,
    db: DbSession,
    context: CommissionCreator,
) -> PartnerDetail:
    return await service.request_payout(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/payouts/{payout_id}/decision", response_model=PartnerDetail)
async def payout_decision(
    partner_id: str,
    payout_id: str,
    payload: CommissionDecision,
    request: Request,
    db: DbSession,
    context: CommissionApprover,
) -> PartnerDetail:
    return await service.decide_payout(
        db,
        context.organization_id,
        partner_id,
        payout_id,
        payload,
        _context(request, context),
    )


@router.post("/{partner_id}/payouts/{payout_id}/process", response_model=PartnerDetail)
async def process_payout(
    partner_id: str,
    payout_id: str,
    payload: PayoutProcess,
    request: Request,
    db: DbSession,
    context: CommissionApprover,
) -> PartnerDetail:
    return await service.process_payout(
        db,
        context.organization_id,
        partner_id,
        payout_id,
        payload,
        _context(request, context),
    )


@router.post("/{partner_id}/disputes", response_model=PartnerDetail, status_code=201)
async def create_dispute(
    partner_id: str,
    payload: DisputeCreate,
    request: Request,
    db: DbSession,
    context: Creator,
) -> PartnerDetail:
    return await service.create_dispute(
        db, context.organization_id, partner_id, payload, _context(request, context)
    )


@router.post("/{partner_id}/disputes/{dispute_id}/assign", response_model=PartnerDetail)
async def assign_dispute(
    partner_id: str,
    dispute_id: str,
    payload: DisputeAssign,
    request: Request,
    db: DbSession,
    context: Assigner,
) -> PartnerDetail:
    return await service.assign_dispute(
        db,
        context.organization_id,
        partner_id,
        dispute_id,
        payload,
        _context(request, context),
    )


@router.post("/{partner_id}/disputes/{dispute_id}/decision", response_model=PartnerDetail)
async def decide_dispute(
    partner_id: str,
    dispute_id: str,
    payload: DisputeDecision,
    request: Request,
    db: DbSession,
    context: Approver,
) -> PartnerDetail:
    return await service.decide_dispute(
        db,
        context.organization_id,
        partner_id,
        dispute_id,
        payload,
        _context(request, context),
    )
