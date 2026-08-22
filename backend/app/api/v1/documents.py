from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, SecurityContext, mutation_context, require_permissions
from app.core.responses import private_file_response
from app.models.enums import DocumentStatus
from app.schemas.documents import (
    DocumentOptions,
    DocumentRequestCreate,
    DocumentReviewDecision,
    DocumentStartReview,
    DocumentStats,
    DocumentView,
)
from app.schemas.organization import Page
from app.services import documents as document_service
from app.services.organization import MutationContext

router = APIRouter(prefix="/documents", tags=["documents"])

DocumentReader = Annotated[SecurityContext, Depends(require_permissions("documents.view"))]
DocumentCreator = Annotated[SecurityContext, Depends(require_permissions("documents.create"))]
DocumentApprover = Annotated[SecurityContext, Depends(require_permissions("documents.approve"))]
DocumentOptionReader = Annotated[
    SecurityContext,
    Depends(require_permissions("documents.create", "documents.approve", any_of=True)),
]


def _context(request: Request, security: SecurityContext) -> MutationContext:
    return mutation_context(request, security)


@router.get("", response_model=Page[DocumentView])
async def documents(
    db: DbSession,
    context: DocumentReader,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: DocumentStatus | None = None,
    document_type: Annotated[str | None, Query(max_length=80)] = None,
    customer_id: str | None = None,
    booking_id: str | None = None,
    current_only: bool = True,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[DocumentView]:
    return await document_service.list_documents(
        db,
        context.organization_id,
        q=q,
        status=status,
        document_type=document_type,
        customer_id=customer_id,
        booking_id=booking_id,
        current_only=current_only,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DocumentStats)
async def stats(db: DbSession, context: DocumentReader) -> DocumentStats:
    return await document_service.document_stats(db, context.organization_id)


@router.get("/options", response_model=DocumentOptions)
async def options(db: DbSession, context: DocumentOptionReader) -> DocumentOptions:
    return await document_service.document_options(db, context.organization_id)


@router.post("/requests", response_model=DocumentView, status_code=201)
async def create_request(
    payload: DocumentRequestCreate,
    request: Request,
    db: DbSession,
    context: DocumentCreator,
) -> DocumentView:
    return await document_service.create_request(
        db, context.organization_id, payload, _context(request, context)
    )


@router.get("/{document_id}", response_model=DocumentView)
async def document(document_id: str, db: DbSession, context: DocumentReader) -> DocumentView:
    return await document_service.get_document(db, context.organization_id, document_id)


@router.post("/{document_id}/upload", response_model=DocumentView)
async def upload_initial(
    document_id: str,
    request: Request,
    db: DbSession,
    context: DocumentCreator,
    file: Annotated[UploadFile, File()],
) -> DocumentView:
    return await document_service.upload_initial(
        db, context.organization_id, document_id, file, _context(request, context)
    )


@router.post("/{document_id}/versions", response_model=DocumentView, status_code=201)
async def upload_version(
    document_id: str,
    request: Request,
    db: DbSession,
    context: DocumentCreator,
    file: Annotated[UploadFile, File()],
    expiry_date: Annotated[date | None, Form()] = None,
) -> DocumentView:
    return await document_service.upload_version(
        db,
        context.organization_id,
        document_id,
        file,
        expiry_date,
        _context(request, context),
    )


@router.post("/{document_id}/review/start", response_model=DocumentView)
async def start_review(
    document_id: str,
    payload: DocumentStartReview,
    request: Request,
    db: DbSession,
    context: DocumentApprover,
) -> DocumentView:
    return await document_service.start_review(
        db, context.organization_id, document_id, payload, _context(request, context)
    )


@router.post("/{document_id}/review", response_model=DocumentView)
async def decide_review(
    document_id: str,
    payload: DocumentReviewDecision,
    request: Request,
    db: DbSession,
    context: DocumentApprover,
) -> DocumentView:
    return await document_service.decide_review(
        db, context.organization_id, document_id, payload, _context(request, context)
    )


@router.get("/{document_id}/versions", response_model=list[DocumentView])
async def versions(document_id: str, db: DbSession, context: DocumentReader) -> list[DocumentView]:
    return await document_service.version_history(db, context.organization_id, document_id)


@router.get("/{document_id}/download", response_class=FileResponse)
async def download(
    document_id: str,
    request: Request,
    db: DbSession,
    context: DocumentReader,
) -> FileResponse:
    path, file_name, content_type = await document_service.prepare_download(
        db, context.organization_id, document_id, _context(request, context)
    )
    return private_file_response(path, filename=file_name, media_type=content_type)
