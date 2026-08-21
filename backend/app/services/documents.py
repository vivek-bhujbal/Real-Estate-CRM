import asyncio
import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import ceil
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError as BaseAppError
from app.models.entities import (
    AuditLog,
    Booking,
    Customer,
    CustomerDocument,
    Permission,
    RolePermission,
    User,
    UserRole,
)
from app.models.enums import DocumentStatus
from app.schemas.documents import (
    DocumentBookingOption,
    DocumentCustomerOption,
    DocumentOptions,
    DocumentRequestCreate,
    DocumentReviewDecision,
    DocumentReviewerOption,
    DocumentStartReview,
    DocumentStats,
    DocumentView,
)
from app.schemas.organization import Page
from app.services.organization import MutationContext
from app.storage.local import LocalStorage

ALLOWED_FILE_TYPES = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}


class AppError(BaseAppError):
    """Document-domain convenience error with a compact positional signature."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, code=code, message=message)


EXPIRABLE_STATUSES = (
    DocumentStatus.PENDING,
    DocumentStatus.UPLOADED,
    DocumentStatus.UNDER_REVIEW,
    DocumentStatus.VERIFIED,
)


@dataclass(frozen=True, slots=True)
class PreparedFile:
    path: Path
    file_name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _not_found() -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", "The requested document was not found")


def _audit(
    organization_id: str,
    context: MutationContext,
    action: str,
    document_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type="document",
        entity_id=document_id,
        previous_value=before,
        new_value=after,
        request_id=context.request_id,
        ip_address=context.ip_address,
        created_at=_now(),
    )


def _system_audit(document: CustomerDocument, before: dict[str, Any]) -> AuditLog:
    return AuditLog(
        organization_id=document.organization_id,
        actor_user_id=None,
        action="document.expired",
        entity_type="document",
        entity_id=document.id,
        previous_value=before,
        new_value={"status": DocumentStatus.EXPIRED.value},
        request_id=None,
        ip_address=None,
        created_at=_now(),
    )


def _snapshot(document: CustomerDocument) -> dict[str, Any]:
    return {
        "document_set_id": document.document_set_id,
        "customer_id": document.customer_id,
        "booking_id": document.booking_id,
        "document_type": document.document_type,
        "version": document.version,
        "status": document.status.value,
        "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
        "reviewed_by_user_id": document.reviewed_by_user_id,
        "rejection_reason": document.rejection_reason,
    }


def _normalize_type(value: str) -> str:
    normalized = "_".join(value.strip().upper().replace("-", " ").split())
    if len(normalized) < 2 or not all(char.isalnum() or char == "_" for char in normalized):
        raise AppError(
            422,
            "INVALID_DOCUMENT_TYPE",
            "Document type may contain only letters, numbers, spaces, hyphens, and underscores",
        )
    return normalized


def _validate_expiry(expiry_date: date | None) -> None:
    if expiry_date is not None and expiry_date < datetime.now(UTC).date():
        raise AppError(422, "INVALID_EXPIRY_DATE", "Expiry date cannot be in the past")


async def _entity(
    db: AsyncSession, organization_id: str, document_id: str, *, lock: bool = False
) -> CustomerDocument:
    statement = select(CustomerDocument).where(
        CustomerDocument.organization_id == organization_id,
        CustomerDocument.id == document_id,
    )
    if lock:
        statement = statement.with_for_update()
    document = (await db.scalars(statement)).first()
    if document is None:
        raise _not_found()
    return document


async def _customer(db: AsyncSession, organization_id: str, customer_id: str) -> Customer:
    customer = (
        await db.scalars(
            select(Customer).where(
                Customer.organization_id == organization_id, Customer.id == customer_id
            )
        )
    ).first()
    if customer is None:
        raise AppError(404, "CUSTOMER_NOT_FOUND", "The selected customer was not found")
    return customer


async def _booking(
    db: AsyncSession, organization_id: str, booking_id: str | None, customer_id: str
) -> Booking | None:
    if booking_id is None:
        return None
    booking = (
        await db.scalars(
            select(Booking).where(
                Booking.organization_id == organization_id, Booking.id == booking_id
            )
        )
    ).first()
    if booking is None:
        raise AppError(404, "BOOKING_NOT_FOUND", "The selected booking was not found")
    if booking.customer_id != customer_id:
        raise AppError(
            422,
            "BOOKING_CUSTOMER_MISMATCH",
            "The booking does not belong to the selected customer",
        )
    return booking


async def _view(db: AsyncSession, organization_id: str, document: CustomerDocument) -> DocumentView:
    customer_name = await db.scalar(
        select(Customer.full_name).where(
            Customer.organization_id == organization_id, Customer.id == document.customer_id
        )
    )
    booking_number = None
    if document.booking_id:
        booking_number = await db.scalar(
            select(Booking.booking_number).where(
                Booking.organization_id == organization_id, Booking.id == document.booking_id
            )
        )
    uploader_name = None
    if document.uploaded_by_user_id:
        uploader_name = await db.scalar(
            select(User.full_name).where(
                User.organization_id == organization_id,
                User.id == document.uploaded_by_user_id,
            )
        )
    reviewer_name = None
    if document.reviewed_by_user_id:
        reviewer_name = await db.scalar(
            select(User.full_name).where(
                User.organization_id == organization_id,
                User.id == document.reviewed_by_user_id,
            )
        )
    return DocumentView(
        id=document.id,
        document_set_id=document.document_set_id,
        supersedes_document_id=document.supersedes_document_id,
        customer_id=document.customer_id,
        customer_name=customer_name or "Unknown customer",
        booking_id=document.booking_id,
        booking_number=booking_number,
        document_type=document.document_type,
        version=document.version,
        is_current=document.is_current,
        file_name=document.file_name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status,
        expiry_date=document.expiry_date,
        uploaded_by_user_id=document.uploaded_by_user_id,
        uploaded_by_name=uploader_name,
        reviewed_by_user_id=document.reviewed_by_user_id,
        reviewer_name=reviewer_name,
        rejection_reason=document.rejection_reason,
        review_notes=document.review_notes,
        uploaded_at=document.uploaded_at,
        review_started_at=document.review_started_at,
        reviewed_at=document.reviewed_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def expire_due_documents(db: AsyncSession, organization_id: str) -> int:
    documents = list(
        await db.scalars(
            select(CustomerDocument).where(
                CustomerDocument.organization_id == organization_id,
                CustomerDocument.is_current.is_(True),
                CustomerDocument.expiry_date.is_not(None),
                CustomerDocument.expiry_date < datetime.now(UTC).date(),
                CustomerDocument.status.in_(EXPIRABLE_STATUSES),
            )
        )
    )
    for document in documents:
        before = _snapshot(document)
        document.status = DocumentStatus.EXPIRED
        document.reviewed_at = _now()
        db.add(_system_audit(document, before))
    if documents:
        await db.commit()
    return len(documents)


async def list_documents(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: DocumentStatus | None,
    document_type: str | None,
    customer_id: str | None,
    booking_id: str | None,
    current_only: bool,
    page: int,
    page_size: int,
) -> Page[DocumentView]:
    await expire_due_documents(db, organization_id)
    conditions: list[Any] = [CustomerDocument.organization_id == organization_id]
    if current_only:
        conditions.append(CustomerDocument.is_current.is_(True))
    if status:
        conditions.append(CustomerDocument.status == status)
    if document_type:
        conditions.append(CustomerDocument.document_type == _normalize_type(document_type))
    if customer_id:
        conditions.append(CustomerDocument.customer_id == customer_id)
    if booking_id:
        conditions.append(CustomerDocument.booking_id == booking_id)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                CustomerDocument.file_name.ilike(pattern),
                CustomerDocument.document_type.ilike(pattern),
                CustomerDocument.customer_id.in_(
                    select(Customer.id).where(
                        Customer.organization_id == organization_id,
                        Customer.full_name.ilike(pattern),
                    )
                ),
                CustomerDocument.booking_id.in_(
                    select(Booking.id).where(
                        Booking.organization_id == organization_id,
                        Booking.booking_number.ilike(pattern),
                    )
                ),
            )
        )
    total = int(await db.scalar(select(func.count(CustomerDocument.id)).where(*conditions)) or 0)
    documents = list(
        await db.scalars(
            select(CustomerDocument)
            .where(*conditions)
            .order_by(CustomerDocument.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _view(db, organization_id, item) for item in documents],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def document_stats(db: AsyncSession, organization_id: str) -> DocumentStats:
    await expire_due_documents(db, organization_id)
    rows = (
        await db.execute(
            select(CustomerDocument.status, func.count(CustomerDocument.id))
            .where(
                CustomerDocument.organization_id == organization_id,
                CustomerDocument.is_current.is_(True),
            )
            .group_by(CustomerDocument.status)
        )
    ).all()
    counts = {item.value: count for item, count in rows}
    return DocumentStats(
        total_current=sum(counts.values()),
        pending=counts.get(DocumentStatus.PENDING.value, 0),
        uploaded=counts.get(DocumentStatus.UPLOADED.value, 0),
        under_review=counts.get(DocumentStatus.UNDER_REVIEW.value, 0),
        verified=counts.get(DocumentStatus.VERIFIED.value, 0),
        rejected=counts.get(DocumentStatus.REJECTED.value, 0),
        expired=counts.get(DocumentStatus.EXPIRED.value, 0),
    )


async def document_options(db: AsyncSession, organization_id: str) -> DocumentOptions:
    customers = list(
        await db.scalars(
            select(Customer)
            .where(Customer.organization_id == organization_id)
            .order_by(Customer.full_name)
            .limit(500)
        )
    )
    bookings = list(
        await db.scalars(
            select(Booking)
            .where(Booking.organization_id == organization_id)
            .order_by(Booking.created_at.desc())
            .limit(500)
        )
    )
    reviewers = list(
        await db.scalars(
            select(User)
            .join(
                UserRole,
                (UserRole.organization_id == User.organization_id) & (UserRole.user_id == User.id),
            )
            .join(
                RolePermission,
                (RolePermission.organization_id == UserRole.organization_id)
                & (RolePermission.role_id == UserRole.role_id),
            )
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Permission.code.in_(("documents.approve", "documents.manage")),
            )
            .distinct()
            .order_by(User.full_name)
            .limit(500)
        )
    )
    return DocumentOptions(
        customers=[
            DocumentCustomerOption(
                id=item.id, full_name=item.full_name, email=item.email, phone=item.phone
            )
            for item in customers
        ],
        bookings=[
            DocumentBookingOption(
                id=item.id,
                customer_id=item.customer_id,
                booking_number=item.booking_number,
                status=item.status.value,
            )
            for item in bookings
        ],
        reviewers=[
            DocumentReviewerOption(id=item.id, full_name=item.full_name, email=item.email)
            for item in reviewers
        ],
    )


async def create_request(
    db: AsyncSession,
    organization_id: str,
    payload: DocumentRequestCreate,
    context: MutationContext,
) -> DocumentView:
    _validate_expiry(payload.expiry_date)
    await _customer(db, organization_id, payload.customer_id)
    await _booking(db, organization_id, payload.booking_id, payload.customer_id)
    document_id = str(uuid.uuid4())
    document = CustomerDocument(
        id=document_id,
        organization_id=organization_id,
        customer_id=payload.customer_id,
        booking_id=payload.booking_id,
        document_set_id=document_id,
        current_version_key=document_id,
        version=1,
        is_current=True,
        document_type=_normalize_type(payload.document_type),
        status=DocumentStatus.PENDING,
        expiry_date=payload.expiry_date,
    )
    db.add(document)
    db.add(
        _audit(
            organization_id,
            context,
            "document.requested",
            document.id,
            None,
            _snapshot(document),
        )
    )
    await db.commit()
    await db.refresh(document)
    return await _view(db, organization_id, document)


def _detected_type(header: bytes) -> str | None:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


async def _prepare_file(upload: UploadFile) -> PreparedFile:
    raw_name = (upload.filename or "").replace("\\", "/")
    file_name = Path(raw_name).name.strip()
    if not file_name or len(file_name) > 255 or any(ord(char) < 32 for char in file_name):
        raise AppError(422, "INVALID_FILE_NAME", "A valid file name is required")
    maximum = get_settings().max_upload_bytes
    handle = tempfile.NamedTemporaryFile(prefix="crm-document-", suffix=".upload", delete=False)
    path = Path(handle.name)
    size = 0
    checksum = hashlib.sha256()
    header = b""
    try:
        while chunk := await upload.read(64 * 1024):
            size += len(chunk)
            if size > maximum:
                raise AppError(
                    413,
                    "FILE_TOO_LARGE",
                    f"The file exceeds the {maximum // (1024 * 1024)} MB upload limit",
                )
            if len(header) < 16:
                header = (header + chunk)[:16]
            checksum.update(chunk)
            await asyncio.to_thread(handle.write, chunk)
        await asyncio.to_thread(handle.flush)
    except Exception:
        await asyncio.to_thread(handle.close)
        if await asyncio.to_thread(path.exists):
            await asyncio.to_thread(path.unlink)
        raise
    finally:
        await upload.close()
    await asyncio.to_thread(handle.close)
    if size == 0:
        await asyncio.to_thread(path.unlink)
        raise AppError(422, "EMPTY_FILE", "The uploaded file is empty")
    content_type = _detected_type(header)
    suffix = Path(file_name).suffix.lower()
    if content_type is None or suffix not in ALLOWED_FILE_TYPES[content_type]:
        await asyncio.to_thread(path.unlink)
        raise AppError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "Only genuine PDF, JPEG, and PNG documents are accepted",
        )
    return PreparedFile(path, file_name, content_type, size, checksum.hexdigest())


def _storage_key(document: CustomerDocument) -> str:
    return (
        f"documents/{document.organization_id}/{document.document_set_id}/"
        f"v{document.version}/{uuid.uuid4().hex}.private"
    )


async def _persist_upload(
    db: AsyncSession,
    document: CustomerDocument,
    prepared: PreparedFile,
    context: MutationContext,
    *,
    action: str,
) -> DocumentView:
    storage = LocalStorage(get_settings().storage_local_path)
    key = _storage_key(document)
    try:
        await storage.save(key=key, source=prepared.path)
        document.storage_key = key
        document.file_name = prepared.file_name
        document.content_type = prepared.content_type
        document.size_bytes = prepared.size_bytes
        document.checksum_sha256 = prepared.checksum_sha256
        document.uploaded_by_user_id = context.actor_user_id
        document.uploaded_at = _now()
        document.status = DocumentStatus.UPLOADED
        document.reviewed_by_user_id = None
        document.review_started_at = None
        document.reviewed_at = None
        document.rejection_reason = None
        document.review_notes = None
        db.add(
            _audit(
                document.organization_id,
                context,
                action,
                document.id,
                None,
                {
                    **_snapshot(document),
                    "file_name": document.file_name,
                    "content_type": document.content_type,
                    "size_bytes": document.size_bytes,
                },
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
    await db.refresh(document)
    return await _view(db, document.organization_id, document)


async def upload_initial(
    db: AsyncSession,
    organization_id: str,
    document_id: str,
    upload: UploadFile,
    context: MutationContext,
) -> DocumentView:
    document = await _entity(db, organization_id, document_id, lock=True)
    if not document.is_current or document.status != DocumentStatus.PENDING or document.storage_key:
        raise AppError(409, "DOCUMENT_ALREADY_UPLOADED", "This document request already has a file")
    _validate_expiry(document.expiry_date)
    prepared = await _prepare_file(upload)
    return await _persist_upload(db, document, prepared, context, action="document.uploaded")


async def upload_version(
    db: AsyncSession,
    organization_id: str,
    document_id: str,
    upload: UploadFile,
    expiry_date: date | None,
    context: MutationContext,
) -> DocumentView:
    current = await _entity(db, organization_id, document_id, lock=True)
    if not current.is_current:
        raise AppError(
            409,
            "NOT_CURRENT_VERSION",
            "A new version must be based on the current document",
        )
    if current.storage_key is None:
        raise AppError(
            409,
            "UPLOAD_INITIAL_VERSION",
            "Upload the pending document before versioning it",
        )
    next_expiry = expiry_date if expiry_date is not None else current.expiry_date
    _validate_expiry(next_expiry)
    prepared = await _prepare_file(upload)
    next_document = CustomerDocument(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        customer_id=current.customer_id,
        booking_id=current.booking_id,
        document_set_id=current.document_set_id,
        supersedes_document_id=current.id,
        current_version_key=current.document_set_id,
        version=current.version + 1,
        is_current=True,
        document_type=current.document_type,
        status=DocumentStatus.PENDING,
        expiry_date=next_expiry,
    )
    current.is_current = False
    current.current_version_key = None
    db.add(next_document)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if await asyncio.to_thread(prepared.path.exists):
            await asyncio.to_thread(prepared.path.unlink)
        raise AppError(
            409, "VERSION_CONFLICT", "Another document version was created first"
        ) from exc
    return await _persist_upload(
        db, next_document, prepared, context, action="document.version_uploaded"
    )


async def start_review(
    db: AsyncSession,
    organization_id: str,
    document_id: str,
    payload: DocumentStartReview,
    context: MutationContext,
) -> DocumentView:
    document = await _entity(db, organization_id, document_id, lock=True)
    if not document.is_current or document.status != DocumentStatus.UPLOADED:
        raise AppError(
            409,
            "INVALID_DOCUMENT_STATE",
            "Only an uploaded current version can enter review",
        )
    reviewer_id = payload.reviewer_user_id or context.actor_user_id
    reviewer = (
        await db.scalars(
            select(User)
            .join(
                UserRole,
                (UserRole.organization_id == User.organization_id) & (UserRole.user_id == User.id),
            )
            .join(
                RolePermission,
                (RolePermission.organization_id == UserRole.organization_id)
                & (RolePermission.role_id == UserRole.role_id),
            )
            .join(
                Permission,
                (Permission.organization_id == RolePermission.organization_id)
                & (Permission.id == RolePermission.permission_id),
            )
            .where(
                User.organization_id == organization_id,
                User.id == reviewer_id,
                User.is_active.is_(True),
                Permission.code.in_(("documents.approve", "documents.manage")),
            )
        )
    ).first()
    if reviewer is None:
        raise AppError(
            404,
            "REVIEWER_NOT_FOUND",
            "The selected reviewer is inactive or lacks document approval permission",
        )
    can_assign = (
        "documents.assign" in context.permissions or "documents.manage" in context.permissions
    )
    if reviewer_id != context.actor_user_id and not can_assign:
        raise AppError(403, "REVIEWER_ASSIGNMENT_NOT_ALLOWED", "You cannot assign another reviewer")
    before = _snapshot(document)
    document.status = DocumentStatus.UNDER_REVIEW
    document.reviewed_by_user_id = reviewer_id
    document.review_started_at = _now()
    document.review_notes = (payload.notes or "").strip() or None
    db.add(
        _audit(
            organization_id,
            context,
            "document.review_started",
            document.id,
            before,
            _snapshot(document),
        )
    )
    await db.commit()
    await db.refresh(document)
    return await _view(db, organization_id, document)


async def decide_review(
    db: AsyncSession,
    organization_id: str,
    document_id: str,
    payload: DocumentReviewDecision,
    context: MutationContext,
) -> DocumentView:
    document = await _entity(db, organization_id, document_id, lock=True)
    if not document.is_current or document.status != DocumentStatus.UNDER_REVIEW:
        raise AppError(409, "INVALID_DOCUMENT_STATE", "Only a document under review can be decided")
    if (
        document.reviewed_by_user_id != context.actor_user_id
        and "documents.manage" not in context.permissions
    ):
        raise AppError(
            403,
            "REVIEWER_MISMATCH",
            "Only the assigned reviewer can decide this document",
        )
    before = _snapshot(document)
    document.status = DocumentStatus(payload.status)
    document.reviewed_at = _now()
    document.rejection_reason = (
        (payload.rejection_reason or "").strip()
        if payload.status == DocumentStatus.REJECTED.value
        else None
    )
    if payload.notes is not None:
        document.review_notes = payload.notes.strip() or None
    db.add(
        _audit(
            organization_id,
            context,
            (
                "document.verified"
                if document.status == DocumentStatus.VERIFIED
                else "document.rejected"
            ),
            document.id,
            before,
            _snapshot(document),
        )
    )
    await db.commit()
    await db.refresh(document)
    return await _view(db, organization_id, document)


async def version_history(
    db: AsyncSession, organization_id: str, document_id: str
) -> list[DocumentView]:
    document = await _entity(db, organization_id, document_id)
    versions = list(
        await db.scalars(
            select(CustomerDocument)
            .where(
                CustomerDocument.organization_id == organization_id,
                CustomerDocument.document_set_id == document.document_set_id,
            )
            .order_by(CustomerDocument.version.desc())
        )
    )
    return [await _view(db, organization_id, item) for item in versions]


async def get_document(db: AsyncSession, organization_id: str, document_id: str) -> DocumentView:
    await expire_due_documents(db, organization_id)
    return await _view(db, organization_id, await _entity(db, organization_id, document_id))


async def prepare_download(
    db: AsyncSession,
    organization_id: str,
    document_id: str,
    context: MutationContext,
) -> tuple[Path, str, str]:
    document = await _entity(db, organization_id, document_id)
    if not document.storage_key or not document.file_name or not document.content_type:
        raise AppError(409, "DOCUMENT_NOT_UPLOADED", "This document does not have an uploaded file")
    storage = LocalStorage(get_settings().storage_local_path)
    try:
        path = await storage.path_for_read(key=document.storage_key)
    except FileNotFoundError as exc:
        raise AppError(404, "DOCUMENT_FILE_NOT_FOUND", "The document file is unavailable") from exc
    db.add(
        _audit(
            organization_id,
            context,
            "document.downloaded",
            document.id,
            None,
            {"version": document.version, "file_name": document.file_name},
        )
    )
    await db.commit()
    return path, document.file_name, document.content_type
