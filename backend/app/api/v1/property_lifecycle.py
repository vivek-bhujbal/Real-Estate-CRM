from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, SecurityContext, require_permissions
from app.models.enums import PostBookingStage
from app.schemas.organization import Page
from app.schemas.property_lifecycle import (
    AcknowledgementCreate,
    AgreementCreate,
    AgreementTransition,
    BookingOption,
    CaseCreate,
    CaseDetail,
    CaseSummary,
    ConstructionCreate,
    FinalDemandCreate,
    HandoverDocumentCreate,
    LifecycleStats,
    OverrideCreate,
    OverrideDecision,
    PossessionAction,
    SnagCreate,
    SnagDecision,
)
from app.services import property_lifecycle as service
from app.services.organization import MutationContext

router = APIRouter(prefix="/property-lifecycle", tags=["post-booking property lifecycle"])

Reader = Annotated[SecurityContext, Depends(require_permissions("possession.view"))]
CaseWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("possession.create", "possession.update", any_of=True)),
]
AgreementWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("agreements.create", "agreements.update", any_of=True)),
]
AgreementApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("agreements.approve", "agreements.manage", any_of=True)),
]
ConstructionWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("construction.create", "construction.update", any_of=True)),
]
ConstructionApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("construction.approve", "construction.manage", any_of=True)),
]
FinanceWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("collections.create", "collections.update", any_of=True)),
]
FinanceApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("collections.approve", "collections.manage", any_of=True)),
]
PossessionApprover = Annotated[
    SecurityContext,
    Depends(require_permissions("possession.approve", "possession.manage", any_of=True)),
]
DocumentWriter = Annotated[
    SecurityContext,
    Depends(require_permissions("documents.create", "documents.update", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return MutationContext(
        actor_user_id=security.user.id,
        permissions=security.permissions,
        request_id=request.state.request_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/stats", response_model=LifecycleStats)
async def stats(db: DbSession, context: Reader) -> LifecycleStats:
    return await service.stats(db, context.organization_id)


@router.get("/options", response_model=list[BookingOption])
async def options(db: DbSession, context: CaseWriter) -> list[BookingOption]:
    return await service.options(db, context.organization_id)


@router.get("", response_model=Page[CaseSummary])
async def cases(
    db: DbSession,
    context: Reader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    stage: PostBookingStage | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CaseSummary]:
    return await service.list_cases(
        db, context.organization_id, q=q, stage=stage, page=page, page_size=page_size
    )


@router.post("/bookings/{booking_id}", response_model=CaseDetail, status_code=201)
async def create_case(
    booking_id: str,
    payload: CaseCreate,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    del payload
    return await service.create_case(
        db, context.organization_id, booking_id, _context(request, context)
    )


@router.get("/{case_id}", response_model=CaseDetail)
async def case(case_id: str, db: DbSession, context: Reader) -> CaseDetail:
    return await service.get_case(db, context.organization_id, case_id)


@router.post("/{case_id}/agreement", response_model=CaseDetail, status_code=201)
async def create_agreement(
    case_id: str,
    payload: AgreementCreate,
    request: Request,
    db: DbSession,
    context: AgreementWriter,
) -> CaseDetail:
    return await service.create_agreement(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/agreement/upload", response_model=CaseDetail)
async def upload_agreement(
    case_id: str,
    request: Request,
    db: DbSession,
    context: AgreementWriter,
    file: Annotated[UploadFile, File(...)],
) -> CaseDetail:
    return await service.upload_agreement(
        db, context.organization_id, case_id, file, _context(request, context)
    )


@router.post("/{case_id}/agreement/transition", response_model=CaseDetail)
async def transition_agreement(
    case_id: str,
    payload: AgreementTransition,
    request: Request,
    db: DbSession,
    context: AgreementApprover,
) -> CaseDetail:
    return await service.transition_agreement(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.get("/{case_id}/agreement/download")
async def download_agreement(case_id: str, db: DbSession, context: Reader) -> FileResponse:
    path, filename, content_type = await service.agreement_download(
        db, context.organization_id, case_id
    )
    return FileResponse(path, media_type=content_type, filename=filename)


@router.post("/{case_id}/construction", response_model=CaseDetail, status_code=201)
async def construction_update(
    case_id: str,
    payload: ConstructionCreate,
    request: Request,
    db: DbSession,
    context: ConstructionWriter,
) -> CaseDetail:
    return await service.create_construction_update(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/construction/{update_id}/publish", response_model=CaseDetail)
async def publish_construction(
    case_id: str,
    update_id: str,
    request: Request,
    db: DbSession,
    context: ConstructionApprover,
) -> CaseDetail:
    return await service.publish_construction_update(
        db, context.organization_id, case_id, update_id, _context(request, context)
    )


@router.post("/{case_id}/final-demand", response_model=CaseDetail, status_code=201)
async def final_demand(
    case_id: str,
    payload: FinalDemandCreate,
    request: Request,
    db: DbSession,
    context: FinanceWriter,
) -> CaseDetail:
    return await service.issue_final_demand(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/no-dues", response_model=CaseDetail, status_code=201)
async def no_dues(
    case_id: str,
    request: Request,
    db: DbSession,
    context: FinanceApprover,
) -> CaseDetail:
    return await service.issue_no_dues(
        db, context.organization_id, case_id, _context(request, context)
    )


@router.get("/{case_id}/no-dues/download")
async def download_no_dues(case_id: str, db: DbSession, context: Reader) -> FileResponse:
    path, filename = await service.no_dues_download(db, context.organization_id, case_id)
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.post("/{case_id}/snags", response_model=CaseDetail, status_code=201)
async def create_snag(
    case_id: str,
    payload: SnagCreate,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    return await service.create_snag(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/snags/{snag_id}/decision", response_model=CaseDetail)
async def decide_snag(
    case_id: str,
    snag_id: str,
    payload: SnagDecision,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    return await service.decide_snag(
        db, context.organization_id, case_id, snag_id, payload, _context(request, context)
    )


@router.post("/{case_id}/overrides", response_model=CaseDetail, status_code=201)
async def request_override(
    case_id: str,
    payload: OverrideCreate,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    return await service.request_override(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/overrides/{override_id}/decision", response_model=CaseDetail)
async def decide_override(
    case_id: str,
    override_id: str,
    payload: OverrideDecision,
    request: Request,
    db: DbSession,
    context: PossessionApprover,
) -> CaseDetail:
    return await service.decide_override(
        db, context.organization_id, case_id, override_id, payload, _context(request, context)
    )


@router.post("/{case_id}/possession/{action}", response_model=CaseDetail)
async def possession_action(
    case_id: str,
    action: str,
    payload: PossessionAction,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    return await service.possession_action(
        db, context.organization_id, case_id, action, payload, _context(request, context)
    )


@router.post("/{case_id}/handover", response_model=CaseDetail, status_code=201)
async def start_handover(
    case_id: str,
    payload: PossessionAction,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    return await service.start_handover(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/handover/documents", response_model=CaseDetail, status_code=201)
async def add_handover_document(
    case_id: str,
    payload: HandoverDocumentCreate,
    request: Request,
    db: DbSession,
    context: DocumentWriter,
) -> CaseDetail:
    return await service.add_handover_document(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/handover/documents/{document_id}/upload", response_model=CaseDetail)
async def upload_handover_document(
    case_id: str,
    document_id: str,
    request: Request,
    db: DbSession,
    context: DocumentWriter,
    file: Annotated[UploadFile, File(...)],
) -> CaseDetail:
    return await service.upload_handover_document(
        db, context.organization_id, case_id, document_id, file, _context(request, context)
    )


@router.get("/{case_id}/handover/documents/{document_id}/download")
async def download_handover_document(
    case_id: str, document_id: str, db: DbSession, context: Reader
) -> FileResponse:
    path, filename, content_type = await service.handover_document_download(
        db, context.organization_id, case_id, document_id
    )
    return FileResponse(path, media_type=content_type, filename=filename)


@router.post("/{case_id}/handover/acknowledge", response_model=CaseDetail)
async def acknowledge_handover(
    case_id: str,
    payload: AcknowledgementCreate,
    request: Request,
    db: DbSession,
    context: CaseWriter,
) -> CaseDetail:
    return await service.acknowledge_handover(
        db, context.organization_id, case_id, payload, _context(request, context)
    )


@router.post("/{case_id}/handover/complete", response_model=CaseDetail)
async def complete_handover(
    case_id: str,
    request: Request,
    db: DbSession,
    context: PossessionApprover,
) -> CaseDetail:
    return await service.complete_handover(
        db, context.organization_id, case_id, _context(request, context)
    )
