import asyncio
import calendar
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Lease,
    LeaseDocument,
    LeaseMove,
    LeaseRenewal,
    Maintenance,
    RentalInvoice,
    RentalProperty,
    RentPayment,
    RentScheduleItem,
    Tenant,
    User,
)
from app.models.enums import (
    DocumentStatus,
    InvoiceStatus,
    LeaseStatus,
    PaymentStatus,
    RentalPropertyStatus,
    RentScheduleStatus,
    ServiceStatus,
    TenantStatus,
    WorkflowStatus,
)
from app.schemas.organization import Page
from app.schemas.rentals import (
    InvoiceCreate,
    InvoiceView,
    LeaseCreate,
    LeaseDetail,
    LeaseDocumentCreate,
    LeaseDocumentDecision,
    LeaseDocumentView,
    LeaseSummary,
    LeaseTransition,
    MaintenanceCreate,
    MaintenanceUpdate,
    MaintenanceView,
    MoveComplete,
    MoveCreate,
    MoveView,
    PaymentCreate,
    PaymentDecision,
    PaymentView,
    RenewalCreate,
    RenewalView,
    RentalOptions,
    RentalPropertyCreate,
    RentalPropertyUpdate,
    RentalPropertyView,
    RentalStats,
    ScheduleView,
    TenantCreate,
    TenantUpdate,
    TenantView,
    WorkflowDecision,
)
from app.services.documents import _prepare_file
from app.services.organization import MutationContext
from app.storage import StoredFile, get_storage

ZERO = Decimal("0.00")
MONEY = Decimal("0.01")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _error(code: str, message: str, status: int = 409) -> AppError:
    return AppError(status_code=status, code=code, message=message)


def _audit(
    org: str,
    context: MutationContext,
    action: str,
    kind: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=org,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type=kind,
        entity_id=entity_id,
        previous_value=before,
        new_value=after,
        request_id=context.request_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
        created_at=_now(),
    )


async def _entity[T](
    db: AsyncSession, model: type[T], org: str, entity_id: str, *, lock: bool = False
) -> T:
    statement = select(model).where(model.organization_id == org, model.id == entity_id)  # type: ignore[attr-defined]
    if lock:
        statement = statement.with_for_update()
    item = (await db.scalars(statement)).first()
    if item is None:
        raise _error("RESOURCE_NOT_FOUND", "Rental record not found", 404)
    return item


def _can_manage(context: MutationContext, module: str) -> bool:
    return any(
        permission in context.permissions
        for permission in (f"{module}.manage", f"{module}.update", f"{module}.approve")
    )


async def _actor_tenant(db: AsyncSession, org: str, user_id: str) -> Tenant | None:
    return (
        await db.scalars(
            select(Tenant).where(Tenant.organization_id == org, Tenant.user_id == user_id)
        )
    ).first()


async def _scoped_lease(
    db: AsyncSession,
    org: str,
    lease_id: str,
    context: MutationContext,
    *,
    lock: bool = False,
) -> Lease:
    lease = await _entity(db, Lease, org, lease_id, lock=lock)
    if not lease.property_id:
        raise _error("RESOURCE_NOT_FOUND", "Rental record not found", 404)
    if _can_manage(context, "leases"):
        return lease
    tenant = await _actor_tenant(db, org, context.actor_user_id)
    if not tenant or lease.tenant_id != tenant.id:
        raise _error("RESOURCE_NOT_FOUND", "Rental record not found", 404)
    return lease


async def _user_name(db: AsyncSession, org: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = await db.scalar(
        select(User.full_name).where(User.organization_id == org, User.id == user_id)
    )
    return str(value) if value is not None else None


async def _property_view(db: AsyncSession, org: str, item: RentalProperty) -> RentalPropertyView:
    active = await db.scalar(
        select(Lease.id).where(
            Lease.organization_id == org,
            Lease.property_id == item.id,
            Lease.active_property_key == item.id,
        )
    )
    return RentalPropertyView(
        id=item.id,
        code=item.code,
        name=item.name,
        property_type=item.property_type,
        address=", ".join(
            filter(
                None,
                (
                    item.address_line1,
                    item.address_line2,
                    item.city,
                    item.state,
                    item.postal_code,
                    item.country,
                ),
            )
        ),
        city=item.city,
        bedrooms=item.bedrooms,
        bathrooms=item.bathrooms,
        area_sqft=item.area_sqft,
        amenities=item.amenities or [],
        default_monthly_rent=item.default_monthly_rent,
        default_security_deposit=item.default_security_deposit,
        currency=item.currency,
        status=item.status,
        manager_user_id=item.manager_user_id,
        manager_name=await _user_name(db, org, item.manager_user_id),
        active_lease_id=active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _tenant_view(db: AsyncSession, org: str, item: Tenant) -> TenantView:
    active = int(
        await db.scalar(
            select(func.count(Lease.id)).where(
                Lease.organization_id == org,
                Lease.tenant_id == item.id,
                Lease.status.in_(
                    (
                        LeaseStatus.SIGNED,
                        LeaseStatus.MOVE_IN_PENDING,
                        LeaseStatus.ACTIVE,
                        LeaseStatus.NOTICE_GIVEN,
                        LeaseStatus.MOVE_OUT_PENDING,
                    )
                ),
            )
        )
        or 0
    )
    outstanding = (
        await db.scalar(
            select(
                func.coalesce(func.sum(RentalInvoice.total - RentalInvoice.paid_amount), 0)
            ).where(
                RentalInvoice.organization_id == org,
                RentalInvoice.tenant_id == item.id,
                RentalInvoice.status.not_in((InvoiceStatus.PAID, InvoiceStatus.VOIDED)),
            )
        )
        or ZERO
    )
    return TenantView(
        id=item.id,
        user_id=item.user_id,
        full_name=item.full_name,
        email=item.email,
        phone=item.phone,
        alternate_phone=item.alternate_phone,
        identity_type=item.identity_type,
        identity_reference=item.identity_reference,
        address=item.address,
        emergency_contact_name=item.emergency_contact_name,
        emergency_contact_phone=item.emergency_contact_phone,
        status=item.status,
        active_leases=active,
        outstanding_rent=Decimal(outstanding),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def expire_overdue(db: AsyncSession, org: str) -> None:
    invoices = list(
        await db.scalars(
            select(RentalInvoice).where(
                RentalInvoice.organization_id == org,
                RentalInvoice.due_date < date.today(),
                RentalInvoice.status.in_((InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID)),
            )
        )
    )
    changed = False
    for invoice in invoices:
        if invoice.paid_amount < invoice.total:
            invoice.status = InvoiceStatus.OVERDUE
            if invoice.rent_schedule_item_id:
                schedule = await _entity(db, RentScheduleItem, org, invoice.rent_schedule_item_id)
                schedule.status = RentScheduleStatus.OVERDUE
            changed = True
    if changed:
        await db.commit()


async def list_properties(
    db: AsyncSession,
    org: str,
    context: MutationContext,
    *,
    q: str | None,
    status: RentalPropertyStatus | None,
    page: int,
    page_size: int,
) -> Page[RentalPropertyView]:
    statement = select(RentalProperty).where(RentalProperty.organization_id == org)
    if not _can_manage(context, "leases"):
        tenant = await _actor_tenant(db, org, context.actor_user_id)
        owned_property_ids = select(Lease.property_id).where(
            Lease.organization_id == org,
            Lease.tenant_id == (tenant.id if tenant else ""),
        )
        statement = statement.where(RentalProperty.id.in_(owned_property_ids))
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                RentalProperty.name.ilike(pattern),
                RentalProperty.code.ilike(pattern),
                RentalProperty.city.ilike(pattern),
            )
        )
    if status:
        statement = statement.where(RentalProperty.status == status)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = list(
        await db.scalars(
            statement.order_by(RentalProperty.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _property_view(db, org, item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def create_property(
    db: AsyncSession,
    org: str,
    payload: RentalPropertyCreate,
    context: MutationContext,
) -> RentalPropertyView:
    if payload.manager_user_id:
        manager = await _entity(db, User, org, payload.manager_user_id)
        if not manager.is_active:
            raise _error("MANAGER_INACTIVE", "Property manager must be active", 422)
    item = RentalProperty(
        organization_id=org,
        manager_user_id=payload.manager_user_id,
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        property_type=payload.property_type.strip().upper(),
        address_line1=payload.address_line1.strip(),
        address_line2=payload.address_line2,
        city=payload.city.strip(),
        state=payload.state.strip(),
        postal_code=payload.postal_code.strip(),
        country=payload.country.strip(),
        bedrooms=payload.bedrooms,
        bathrooms=payload.bathrooms,
        area_sqft=payload.area_sqft,
        amenities=payload.amenities,
        default_monthly_rent=payload.default_monthly_rent,
        default_security_deposit=payload.default_security_deposit,
        currency=payload.currency.upper(),
        status=RentalPropertyStatus.AVAILABLE,
        notes=payload.notes,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("RENTAL_PROPERTY_CODE_EXISTS", "Rental property code already exists") from exc
    db.add(
        _audit(
            org,
            context,
            "rental.property.created",
            "rental_property",
            item.id,
            None,
            {"code": item.code, "status": item.status.value},
        )
    )
    await db.commit()
    await db.refresh(item)
    return await _property_view(db, org, item)


async def update_property(
    db: AsyncSession,
    org: str,
    property_id: str,
    payload: RentalPropertyUpdate,
    context: MutationContext,
) -> RentalPropertyView:
    item = await _entity(db, RentalProperty, org, property_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("manager_user_id"):
        manager = await _entity(db, User, org, changes["manager_user_id"])
        if not manager.is_active:
            raise _error("MANAGER_INACTIVE", "Property manager must be active", 422)
    if "status" in changes and item.status == RentalPropertyStatus.OCCUPIED:
        if changes["status"] != RentalPropertyStatus.OCCUPIED:
            raise _error(
                "ACTIVE_LEASE_EXISTS", "Occupied property status is controlled by lease move-out"
            )
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    db.add(
        _audit(
            org,
            context,
            "rental.property.updated",
            "rental_property",
            item.id,
            {key: str(value) for key, value in before.items()},
            {key: str(value) for key, value in changes.items()},
        )
    )
    await db.commit()
    return await _property_view(db, org, item)


async def list_tenants(
    db: AsyncSession, org: str, *, q: str | None, page: int, page_size: int
) -> Page[TenantView]:
    statement = select(Tenant).where(Tenant.organization_id == org)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Tenant.full_name.ilike(pattern),
                Tenant.email.ilike(pattern),
                Tenant.phone.ilike(pattern),
            )
        )
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = list(
        await db.scalars(
            statement.order_by(Tenant.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _tenant_view(db, org, item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def create_tenant(
    db: AsyncSession, org: str, payload: TenantCreate, context: MutationContext
) -> TenantView:
    if payload.user_id:
        user = await _entity(db, User, org, payload.user_id)
        if not user.is_active:
            raise _error("TENANT_USER_INACTIVE", "Linked tenant user must be active", 422)
    item = Tenant(
        organization_id=org,
        user_id=payload.user_id,
        full_name=payload.full_name.strip(),
        email=str(payload.email).lower() if payload.email else None,
        phone=payload.phone.strip(),
        alternate_phone=payload.alternate_phone,
        identity_type=payload.identity_type,
        identity_reference=payload.identity_reference,
        address=payload.address,
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_phone=payload.emergency_contact_phone,
        status=TenantStatus.ACTIVE,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("TENANT_USER_ALREADY_LINKED", "User is already linked to a tenant") from exc
    db.add(
        _audit(
            org,
            context,
            "rental.tenant.created",
            "tenant",
            item.id,
            None,
            {"full_name": item.full_name, "user_id": item.user_id},
        )
    )
    await db.commit()
    await db.refresh(item)
    return await _tenant_view(db, org, item)


async def update_tenant(
    db: AsyncSession,
    org: str,
    tenant_id: str,
    payload: TenantUpdate,
    context: MutationContext,
) -> TenantView:
    item = await _entity(db, Tenant, org, tenant_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, str(value).lower() if key == "email" and value else value)
    db.add(
        _audit(
            org,
            context,
            "rental.tenant.updated",
            "tenant",
            item.id,
            {key: str(value) for key, value in before.items()},
            {key: str(value) for key, value in changes.items()},
        )
    )
    await db.commit()
    return await _tenant_view(db, org, item)


def _add_months(value: date, months: int) -> date:
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


async def _append_schedule(
    db: AsyncSession, lease: Lease, start: date, end: date, start_sequence: int = 1
) -> None:
    cursor = start
    sequence = start_sequence
    period_index = 1
    while cursor <= end:
        period_start = cursor
        period_end = min(_add_months(start, period_index) - timedelta(days=1), end)
        due_date = date(cursor.year, cursor.month, min(lease.rent_due_day, 28))
        if due_date < period_start:
            due_month = _add_months(cursor.replace(day=1), 1)
            due_date = date(due_month.year, due_month.month, min(lease.rent_due_day, 28))
        due_date = min(due_date, period_end)
        db.add(
            RentScheduleItem(
                organization_id=lease.organization_id,
                lease_id=lease.id,
                sequence=sequence,
                period_start=period_start,
                period_end=period_end,
                due_date=due_date,
                amount=lease.monthly_rent,
                currency=lease.currency,
                status=RentScheduleStatus.SCHEDULED,
            )
        )
        cursor = period_end + timedelta(days=1)
        sequence += 1
        period_index += 1


async def create_lease(
    db: AsyncSession, org: str, payload: LeaseCreate, context: MutationContext
) -> LeaseDetail:
    tenant = await _entity(db, Tenant, org, payload.tenant_id)
    property_record = await _entity(db, RentalProperty, org, payload.property_id, lock=True)
    if tenant.status != TenantStatus.ACTIVE:
        raise _error("TENANT_INACTIVE", "Only active tenants can enter a lease")
    if property_record.status != RentalPropertyStatus.AVAILABLE:
        raise _error("RENTAL_PROPERTY_UNAVAILABLE", "Rental property is not available")
    item = Lease(
        organization_id=org,
        tenant_id=tenant.id,
        unit_id=None,
        property_id=property_record.id,
        created_by_user_id=context.actor_user_id,
        lease_number=payload.lease_number.strip().upper(),
        status=LeaseStatus.DRAFT,
        start_date=payload.start_date,
        end_date=payload.end_date,
        monthly_rent=payload.monthly_rent,
        security_deposit=payload.security_deposit,
        currency=payload.currency.upper(),
        active_unit_key=None,
        active_property_key=None,
        rent_due_day=payload.rent_due_day,
        notice_period_days=payload.notice_period_days,
        terms=payload.terms,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("LEASE_NUMBER_EXISTS", "Lease number already exists") from exc
    db.add(
        LeaseDocument(
            organization_id=org,
            lease_id=item.id,
            document_type="LEASE_AGREEMENT",
            version=1,
            is_required=True,
            status=DocumentStatus.PENDING,
        )
    )
    db.add(
        _audit(
            org,
            context,
            "rental.lease.created",
            "lease",
            item.id,
            None,
            {"property_id": item.property_id, "tenant_id": item.tenant_id},
        )
    )
    await db.commit()
    return await lease_detail(db, org, item.id, context)


async def _lease_summary(db: AsyncSession, org: str, lease: Lease) -> LeaseSummary:
    tenant = await _entity(db, Tenant, org, lease.tenant_id)
    property_record = await _entity(db, RentalProperty, org, lease.property_id)
    outstanding = (
        await db.scalar(
            select(
                func.coalesce(func.sum(RentalInvoice.total - RentalInvoice.paid_amount), 0)
            ).where(
                RentalInvoice.organization_id == org,
                RentalInvoice.lease_id == lease.id,
                RentalInvoice.status.not_in((InvoiceStatus.PAID, InvoiceStatus.VOIDED)),
            )
        )
        or ZERO
    )
    overdue = int(
        await db.scalar(
            select(func.count(RentalInvoice.id)).where(
                RentalInvoice.organization_id == org,
                RentalInvoice.lease_id == lease.id,
                RentalInvoice.status == InvoiceStatus.OVERDUE,
            )
        )
        or 0
    )
    return LeaseSummary(
        id=lease.id,
        lease_number=lease.lease_number,
        status=lease.status,
        tenant_id=tenant.id,
        tenant_name=tenant.full_name,
        property_id=property_record.id,
        property_name=property_record.name,
        property_code=property_record.code,
        start_date=lease.start_date,
        end_date=lease.end_date,
        monthly_rent=lease.monthly_rent,
        currency=lease.currency,
        outstanding=Decimal(outstanding),
        overdue_invoices=overdue,
        updated_at=lease.updated_at,
    )


async def list_leases(
    db: AsyncSession,
    org: str,
    context: MutationContext,
    *,
    q: str | None,
    status: LeaseStatus | None,
    page: int,
    page_size: int,
) -> Page[LeaseSummary]:
    await expire_overdue(db, org)
    statement = select(Lease).where(Lease.organization_id == org, Lease.property_id.is_not(None))
    if not _can_manage(context, "leases"):
        tenant = await _actor_tenant(db, org, context.actor_user_id)
        if not tenant:
            return Page(items=[], page=page, page_size=page_size, total=0, pages=0)
        statement = statement.where(Lease.tenant_id == tenant.id)
    if status:
        statement = statement.where(Lease.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        statement = (
            statement.join(
                Tenant,
                (Tenant.organization_id == Lease.organization_id) & (Tenant.id == Lease.tenant_id),
            )
            .join(
                RentalProperty,
                (RentalProperty.organization_id == Lease.organization_id)
                & (RentalProperty.id == Lease.property_id),
            )
            .where(
                or_(
                    Lease.lease_number.ilike(pattern),
                    Tenant.full_name.ilike(pattern),
                    RentalProperty.name.ilike(pattern),
                    RentalProperty.code.ilike(pattern),
                )
            )
        )
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = list(
        await db.scalars(
            statement.order_by(Lease.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _lease_summary(db, org, item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def lease_detail(
    db: AsyncSession, org: str, lease_id: str, context: MutationContext
) -> LeaseDetail:
    await expire_overdue(db, org)
    lease = await _scoped_lease(db, org, lease_id, context)
    documents = list(
        await db.scalars(
            select(LeaseDocument)
            .where(LeaseDocument.organization_id == org, LeaseDocument.lease_id == lease.id)
            .order_by(LeaseDocument.document_type, LeaseDocument.version.desc())
        )
    )
    schedule = list(
        await db.scalars(
            select(RentScheduleItem)
            .where(RentScheduleItem.organization_id == org, RentScheduleItem.lease_id == lease.id)
            .order_by(RentScheduleItem.sequence)
        )
    )
    invoices = list(
        await db.scalars(
            select(RentalInvoice)
            .where(RentalInvoice.organization_id == org, RentalInvoice.lease_id == lease.id)
            .order_by(RentalInvoice.due_date.desc())
        )
    )
    payments = list(
        await db.scalars(
            select(RentPayment)
            .where(RentPayment.organization_id == org, RentPayment.lease_id == lease.id)
            .order_by(RentPayment.created_at.desc())
        )
    )
    renewals = list(
        await db.scalars(
            select(LeaseRenewal)
            .where(LeaseRenewal.organization_id == org, LeaseRenewal.lease_id == lease.id)
            .order_by(LeaseRenewal.requested_at.desc())
        )
    )
    moves = list(
        await db.scalars(
            select(LeaseMove)
            .where(LeaseMove.organization_id == org, LeaseMove.lease_id == lease.id)
            .order_by(LeaseMove.requested_at.desc())
        )
    )
    maintenance = list(
        await db.scalars(
            select(Maintenance)
            .where(Maintenance.organization_id == org, Maintenance.lease_id == lease.id)
            .order_by(Maintenance.created_at.desc())
        )
    )
    return LeaseDetail(
        lease=await _lease_summary(db, org, lease),
        security_deposit=lease.security_deposit,
        rent_due_day=lease.rent_due_day,
        notice_period_days=lease.notice_period_days,
        terms=lease.terms,
        documents=[
            LeaseDocumentView.model_validate(item, from_attributes=True) for item in documents
        ],
        schedule=[ScheduleView.model_validate(item, from_attributes=True) for item in schedule],
        invoices=[
            InvoiceView(
                id=item.id,
                rent_schedule_item_id=item.rent_schedule_item_id,
                invoice_number=item.invoice_number,
                status=item.status,
                period_start=item.period_start,
                period_end=item.period_end,
                issue_date=item.issue_date,
                due_date=item.due_date,
                amount=item.amount,
                tax_amount=item.tax_amount,
                total=item.total,
                paid_amount=item.paid_amount,
                outstanding=max(item.total - item.paid_amount, ZERO),
                currency=item.currency,
            )
            for item in invoices
        ],
        payments=[PaymentView.model_validate(item, from_attributes=True) for item in payments],
        renewals=[RenewalView.model_validate(item, from_attributes=True) for item in renewals],
        moves=[MoveView.model_validate(item, from_attributes=True) for item in moves],
        maintenance=[
            MaintenanceView.model_validate(item, from_attributes=True) for item in maintenance
        ],
    )


async def transition_lease(
    db: AsyncSession,
    org: str,
    lease_id: str,
    payload: LeaseTransition,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can transition a lease", 403)
    target = LeaseStatus(payload.status)
    allowed = {
        LeaseStatus.DRAFT: LeaseStatus.PENDING_SIGNATURE,
        LeaseStatus.PENDING_SIGNATURE: LeaseStatus.SIGNED,
    }
    if allowed.get(lease.status) != target:
        raise _error("INVALID_LEASE_TRANSITION", f"Cannot move lease to {target.value}")
    if target == LeaseStatus.SIGNED:
        missing = int(
            await db.scalar(
                select(func.count(LeaseDocument.id)).where(
                    LeaseDocument.organization_id == org,
                    LeaseDocument.lease_id == lease.id,
                    LeaseDocument.is_required.is_(True),
                    LeaseDocument.status != DocumentStatus.VERIFIED,
                )
            )
            or 0
        )
        if missing:
            raise _error(
                "LEASE_DOCUMENTS_INCOMPLETE", "All required lease documents must be verified"
            )
        property_record = await _entity(db, RentalProperty, org, lease.property_id, lock=True)
        if property_record.status != RentalPropertyStatus.AVAILABLE:
            raise _error("RENTAL_PROPERTY_UNAVAILABLE", "Rental property is no longer available")
        lease.status = LeaseStatus.MOVE_IN_PENDING
        lease.signed_at = _now()
        lease.approved_by_user_id = context.actor_user_id
        lease.active_property_key = property_record.id
        property_record.status = RentalPropertyStatus.RESERVED
        await _append_schedule(db, lease, lease.start_date, lease.end_date)
    else:
        lease.status = target
        lease.issued_at = _now()
    db.add(
        _audit(
            org,
            context,
            "rental.lease.status_changed",
            "lease",
            lease.id,
            None,
            {"status": lease.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def add_document(
    db: AsyncSession,
    org: str,
    lease_id: str,
    payload: LeaseDocumentCreate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context)
    document_type = payload.document_type.strip().upper().replace(" ", "_")
    version = (
        int(
            await db.scalar(
                select(func.coalesce(func.max(LeaseDocument.version), 0)).where(
                    LeaseDocument.organization_id == org,
                    LeaseDocument.lease_id == lease.id,
                    LeaseDocument.document_type == document_type,
                )
            )
            or 0
        )
        + 1
    )
    item = LeaseDocument(
        organization_id=org,
        lease_id=lease.id,
        document_type=document_type,
        version=version,
        is_required=payload.is_required,
        status=DocumentStatus.PENDING,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "rental.lease_document.requested",
            "lease_document",
            item.id,
            None,
            {"document_type": document_type, "version": version},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def upload_document(
    db: AsyncSession,
    org: str,
    lease_id: str,
    document_id: str,
    upload: UploadFile,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context)
    item = await _entity(db, LeaseDocument, org, document_id, lock=True)
    if item.lease_id != lease.id:
        raise _error("RESOURCE_NOT_FOUND", "Lease document not found", 404)
    prepared = await _prepare_file(upload)
    storage = get_storage()
    key = f"rentals/d/{org}/{item.id}/{uuid.uuid4().hex[:16]}.private"
    old_key = item.storage_key
    try:
        await storage.save(key=key, source=prepared.path)
        item.uploaded_by_user_id = context.actor_user_id
        item.file_name = prepared.file_name
        item.storage_key = key
        item.content_type = prepared.content_type
        item.size_bytes = prepared.size_bytes
        item.checksum_sha256 = prepared.checksum_sha256
        item.status = DocumentStatus.UPLOADED
        item.uploaded_at = _now()
        item.rejection_reason = None
        db.add(
            _audit(
                org,
                context,
                "rental.lease_document.uploaded",
                "lease_document",
                item.id,
                None,
                {"file_name": item.file_name, "checksum": item.checksum_sha256},
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
    if old_key:
        await storage.delete(key=old_key)
    return await lease_detail(db, org, lease.id, context)


async def decide_document(
    db: AsyncSession,
    org: str,
    lease_id: str,
    document_id: str,
    payload: LeaseDocumentDecision,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can verify documents", 403)
    item = await _entity(db, LeaseDocument, org, document_id, lock=True)
    if item.lease_id != lease.id or item.status != DocumentStatus.UPLOADED:
        raise _error("DOCUMENT_NOT_REVIEWABLE", "Document is not awaiting review")
    if item.uploaded_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Document uploader cannot verify it", 403)
    item.status = DocumentStatus(payload.status)
    item.reviewed_by_user_id = context.actor_user_id
    item.reviewed_at = _now()
    item.rejection_reason = payload.notes if item.status == DocumentStatus.REJECTED else None
    db.add(
        _audit(
            org,
            context,
            "rental.lease_document.reviewed",
            "lease_document",
            item.id,
            {"status": "UPLOADED"},
            {"status": item.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def issue_invoice(
    db: AsyncSession,
    org: str,
    lease_id: str,
    payload: InvoiceCreate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can issue rent invoices", 403)
    schedule = await _entity(db, RentScheduleItem, org, payload.schedule_item_id, lock=True)
    if schedule.lease_id != lease.id or schedule.status not in (
        RentScheduleStatus.SCHEDULED,
        RentScheduleStatus.OVERDUE,
    ):
        raise _error("RENT_SCHEDULE_NOT_INVOICEABLE", "Schedule item is not invoiceable")
    total = _money(schedule.amount + payload.tax_amount)
    item = RentalInvoice(
        organization_id=org,
        lease_id=lease.id,
        tenant_id=lease.tenant_id,
        rent_schedule_item_id=schedule.id,
        created_by_user_id=context.actor_user_id,
        invoice_number=payload.invoice_number.strip().upper(),
        status=InvoiceStatus.ISSUED,
        period_start=schedule.period_start,
        period_end=schedule.period_end,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        amount=schedule.amount,
        tax_amount=payload.tax_amount,
        total=total,
        paid_amount=ZERO,
        currency=lease.currency,
        issued_at=_now(),
    )
    db.add(item)
    schedule.status = RentScheduleStatus.INVOICED
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("RENT_INVOICE_EXISTS", "Invoice number or rent period already exists") from exc
    db.add(
        _audit(
            org,
            context,
            "rental.invoice.issued",
            "rental_invoice",
            item.id,
            None,
            {"amount": str(total), "schedule_item_id": schedule.id},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def submit_payment(
    db: AsyncSession,
    org: str,
    lease_id: str,
    invoice_id: str,
    payload: PaymentCreate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    invoice = await _entity(db, RentalInvoice, org, invoice_id, lock=True)
    if invoice.lease_id != lease.id or invoice.status in (InvoiceStatus.PAID, InvoiceStatus.VOIDED):
        raise _error("INVOICE_NOT_PAYABLE", "Rent invoice is not payable")
    existing = (
        await db.scalars(
            select(RentPayment).where(
                RentPayment.organization_id == org,
                RentPayment.idempotency_key == payload.idempotency_key,
            )
        )
    ).first()
    if existing:
        return await lease_detail(db, org, lease.id, context)
    committed = (
        await db.scalar(
            select(func.coalesce(func.sum(RentPayment.amount), 0)).where(
                RentPayment.organization_id == org,
                RentPayment.rental_invoice_id == invoice.id,
                RentPayment.status.in_((PaymentStatus.PENDING, PaymentStatus.COMPLETED)),
            )
        )
        or ZERO
    )
    if Decimal(committed) + payload.amount > invoice.total:
        raise _error("PAYMENT_EXCEEDS_INVOICE", "Payment cannot exceed invoice outstanding", 422)
    item = RentPayment(
        organization_id=org,
        rental_invoice_id=invoice.id,
        lease_id=lease.id,
        tenant_id=lease.tenant_id,
        verified_by_user_id=None,
        submitted_by_user_id=context.actor_user_id,
        status=PaymentStatus.PENDING,
        amount=payload.amount,
        currency=lease.currency,
        method=payload.method.strip().upper(),
        reference_number=payload.reference_number,
        idempotency_key=payload.idempotency_key,
        paid_at=(
            payload.paid_at.astimezone(UTC).replace(tzinfo=None)
            if payload.paid_at and payload.paid_at.tzinfo
            else (payload.paid_at or datetime.now(UTC)).replace(tzinfo=None)
        ),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "rental.payment.submitted",
            "rent_payment",
            item.id,
            None,
            {"invoice_id": invoice.id, "amount": str(item.amount)},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def decide_payment(
    db: AsyncSession,
    org: str,
    lease_id: str,
    payment_id: str,
    payload: PaymentDecision,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can verify rent payments", 403)
    payment = await _entity(db, RentPayment, org, payment_id, lock=True)
    invoice = await _entity(db, RentalInvoice, org, payment.rental_invoice_id, lock=True)
    if payment.lease_id != lease.id or payment.status != PaymentStatus.PENDING:
        raise _error("PAYMENT_FINALIZED", "Payment decision is already recorded")
    if payment.submitted_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Payment submitter cannot verify it", 403)
    payment.verified_by_user_id = context.actor_user_id
    payment.verified_at = _now()
    if payload.status == "FAILED":
        payment.status = PaymentStatus.FAILED
        payment.rejection_reason = payload.notes
    else:
        if invoice.paid_amount + payment.amount > invoice.total:
            raise _error("PAYMENT_EXCEEDS_INVOICE", "Verified payments exceed invoice total")
        payment.status = PaymentStatus.COMPLETED
        invoice.paid_amount += payment.amount
        schedule = (
            await _entity(db, RentScheduleItem, org, invoice.rent_schedule_item_id, lock=True)
            if invoice.rent_schedule_item_id
            else None
        )
        if invoice.paid_amount >= invoice.total:
            invoice.status = InvoiceStatus.PAID
            if schedule:
                schedule.status = RentScheduleStatus.PAID
        else:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
            if schedule:
                schedule.status = RentScheduleStatus.PARTIALLY_PAID
    db.add(
        _audit(
            org,
            context,
            "rental.payment.reviewed",
            "rent_payment",
            payment.id,
            {"status": "PENDING"},
            {"status": payment.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def request_renewal(
    db: AsyncSession,
    org: str,
    lease_id: str,
    payload: RenewalCreate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if lease.status != LeaseStatus.ACTIVE or payload.proposed_end_date <= lease.end_date:
        raise _error("LEASE_NOT_RENEWABLE", "Active lease renewal must extend the end date")
    if await db.scalar(
        select(LeaseRenewal.id).where(
            LeaseRenewal.organization_id == org,
            LeaseRenewal.lease_id == lease.id,
            LeaseRenewal.status == WorkflowStatus.REQUESTED,
        )
    ):
        raise _error("RENEWAL_PENDING", "A renewal request is already pending")
    item = LeaseRenewal(
        organization_id=org,
        lease_id=lease.id,
        requested_by_user_id=context.actor_user_id,
        status=WorkflowStatus.REQUESTED,
        previous_end_date=lease.end_date,
        proposed_end_date=payload.proposed_end_date,
        previous_monthly_rent=lease.monthly_rent,
        proposed_monthly_rent=payload.proposed_monthly_rent,
        reason=payload.reason.strip(),
        requested_at=_now(),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "rental.renewal.requested",
            "lease_renewal",
            item.id,
            None,
            {
                "new_end_date": str(item.proposed_end_date),
                "new_rent": str(item.proposed_monthly_rent),
            },
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def decide_renewal(
    db: AsyncSession,
    org: str,
    lease_id: str,
    renewal_id: str,
    payload: WorkflowDecision,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can approve renewals", 403)
    item = await _entity(db, LeaseRenewal, org, renewal_id, lock=True)
    if item.lease_id != lease.id or item.status != WorkflowStatus.REQUESTED:
        raise _error("RENEWAL_FINALIZED", "Renewal is not awaiting decision")
    if item.requested_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Renewal requester cannot approve it", 403)
    item.decided_by_user_id = context.actor_user_id
    item.decision_notes = payload.notes
    item.decided_at = _now()
    if payload.status == "REJECTED":
        item.status = WorkflowStatus.REJECTED
    else:
        old_end = lease.end_date
        last_sequence = int(
            await db.scalar(
                select(func.coalesce(func.max(RentScheduleItem.sequence), 0)).where(
                    RentScheduleItem.organization_id == org,
                    RentScheduleItem.lease_id == lease.id,
                )
            )
            or 0
        )
        lease.end_date = item.proposed_end_date
        lease.monthly_rent = item.proposed_monthly_rent
        await _append_schedule(
            db, lease, old_end + timedelta(days=1), lease.end_date, last_sequence + 1
        )
        item.status = WorkflowStatus.COMPLETED
        item.applied_at = _now()
    db.add(
        _audit(
            org,
            context,
            "rental.renewal.decided",
            "lease_renewal",
            item.id,
            {"status": "REQUESTED"},
            {"status": item.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def request_move(
    db: AsyncSession,
    org: str,
    lease_id: str,
    payload: MoveCreate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    expected = LeaseStatus.MOVE_IN_PENDING if payload.move_type == "MOVE_IN" else LeaseStatus.ACTIVE
    if lease.status != expected:
        raise _error("INVALID_MOVE_STATE", f"Lease is not ready for {payload.move_type.lower()}")
    if await db.scalar(
        select(LeaseMove.id).where(
            LeaseMove.organization_id == org,
            LeaseMove.lease_id == lease.id,
            LeaseMove.move_type == payload.move_type,
            LeaseMove.status.in_((WorkflowStatus.REQUESTED, WorkflowStatus.APPROVED)),
        )
    ):
        raise _error("MOVE_PENDING", "A move workflow is already pending")
    scheduled = payload.scheduled_at
    if scheduled.tzinfo:
        scheduled = scheduled.astimezone(UTC).replace(tzinfo=None)
    item = LeaseMove(
        organization_id=org,
        lease_id=lease.id,
        requested_by_user_id=context.actor_user_id,
        move_type=payload.move_type,
        status=WorkflowStatus.REQUESTED,
        scheduled_at=scheduled,
        notes=payload.notes,
        requested_at=_now(),
    )
    db.add(item)
    if payload.move_type == "MOVE_OUT":
        lease.status = LeaseStatus.NOTICE_GIVEN
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "rental.move.requested",
            "lease_move",
            item.id,
            None,
            {"move_type": item.move_type, "scheduled_at": item.scheduled_at.isoformat()},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def decide_move(
    db: AsyncSession,
    org: str,
    lease_id: str,
    move_id: str,
    payload: WorkflowDecision,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can approve moves", 403)
    item = await _entity(db, LeaseMove, org, move_id, lock=True)
    if item.lease_id != lease.id or item.status != WorkflowStatus.REQUESTED:
        raise _error("MOVE_FINALIZED", "Move is not awaiting decision")
    if item.requested_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Move requester cannot approve it", 403)
    item.approved_by_user_id = context.actor_user_id
    item.approved_at = _now()
    item.notes = payload.notes
    item.status = WorkflowStatus(payload.status)
    if payload.status == "APPROVED" and item.move_type == "MOVE_OUT":
        lease.status = LeaseStatus.MOVE_OUT_PENDING
    elif payload.status == "REJECTED" and item.move_type == "MOVE_OUT":
        lease.status = LeaseStatus.ACTIVE
    db.add(
        _audit(
            org,
            context,
            "rental.move.decided",
            "lease_move",
            item.id,
            {"status": "REQUESTED"},
            {"status": item.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def complete_move(
    db: AsyncSession,
    org: str,
    lease_id: str,
    move_id: str,
    payload: MoveComplete,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context, lock=True)
    if not _can_manage(context, "leases"):
        raise _error("PERMISSION_DENIED", "Only a property manager can complete moves", 403)
    item = await _entity(db, LeaseMove, org, move_id, lock=True)
    property_record = await _entity(db, RentalProperty, org, lease.property_id, lock=True)
    if item.lease_id != lease.id or item.status != WorkflowStatus.APPROVED:
        raise _error("MOVE_NOT_APPROVED", "Move must be approved before completion")
    if item.move_type == "MOVE_OUT":
        outstanding = (
            await db.scalar(
                select(
                    func.coalesce(func.sum(RentalInvoice.total - RentalInvoice.paid_amount), 0)
                ).where(
                    RentalInvoice.organization_id == org,
                    RentalInvoice.lease_id == lease.id,
                    RentalInvoice.status.not_in((InvoiceStatus.PAID, InvoiceStatus.VOIDED)),
                )
            )
            or ZERO
        )
        if Decimal(outstanding) > ZERO:
            raise _error("RENT_OUTSTANDING", "Move-out is blocked until rent invoices are settled")
        lease.status = LeaseStatus.TERMINATED
        lease.terminated_at = _now()
        lease.active_property_key = None
        property_record.status = RentalPropertyStatus.AVAILABLE
    else:
        lease.status = LeaseStatus.ACTIVE
        lease.activated_at = _now()
        property_record.status = RentalPropertyStatus.OCCUPIED
    item.status = WorkflowStatus.COMPLETED
    item.completed_by_user_id = context.actor_user_id
    item.completed_at = _now()
    item.checklist = payload.checklist
    item.meter_readings = payload.meter_readings
    item.notes = payload.notes or item.notes
    db.add(
        _audit(
            org,
            context,
            "rental.move.completed",
            "lease_move",
            item.id,
            {"status": "APPROVED"},
            {
                "status": "COMPLETED",
                "lease_status": lease.status.value,
                "property_status": property_record.status.value,
                "checklist": item.checklist,
            },
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def create_maintenance(
    db: AsyncSession,
    org: str,
    payload: MaintenanceCreate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, payload.lease_id, context)
    item = Maintenance(
        organization_id=org,
        unit_id=None,
        rental_property_id=lease.property_id,
        reported_by_user_id=context.actor_user_id,
        lease_id=lease.id,
        service_request_id=None,
        assigned_user_id=None,
        status=ServiceStatus.OPEN,
        title=payload.title.strip(),
        description=payload.description.strip(),
        scheduled_at=(
            payload.scheduled_at.astimezone(UTC).replace(tzinfo=None)
            if payload.scheduled_at and payload.scheduled_at.tzinfo
            else payload.scheduled_at
        ),
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "rental.maintenance.created",
            "maintenance",
            item.id,
            None,
            {"lease_id": lease.id, "property_id": lease.property_id},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def update_maintenance(
    db: AsyncSession,
    org: str,
    lease_id: str,
    maintenance_id: str,
    payload: MaintenanceUpdate,
    context: MutationContext,
) -> LeaseDetail:
    lease = await _scoped_lease(db, org, lease_id, context)
    item = await _entity(db, Maintenance, org, maintenance_id, lock=True)
    if item.lease_id != lease.id:
        raise _error("RESOURCE_NOT_FOUND", "Maintenance record not found", 404)
    if not _can_manage(context, "maintenance") and payload.status not in ("CLOSED", "CANCELLED"):
        raise _error("PERMISSION_DENIED", "Tenant can only close or cancel own maintenance", 403)
    before = item.status.value
    item.status = ServiceStatus(payload.status)
    item.assigned_user_id = payload.assigned_user_id or item.assigned_user_id
    if payload.scheduled_at:
        item.scheduled_at = (
            payload.scheduled_at.astimezone(UTC).replace(tzinfo=None)
            if payload.scheduled_at.tzinfo
            else payload.scheduled_at
        )
    if payload.cost is not None:
        item.cost, item.currency = payload.cost, payload.currency
    if item.status in (ServiceStatus.RESOLVED, ServiceStatus.CLOSED):
        item.completed_at = _now()
    db.add(
        _audit(
            org,
            context,
            "rental.maintenance.updated",
            "maintenance",
            item.id,
            {"status": before},
            {"status": item.status.value, "cost": str(item.cost) if item.cost else None},
        )
    )
    await db.commit()
    return await lease_detail(db, org, lease.id, context)


async def stats(db: AsyncSession, org: str, context: MutationContext) -> RentalStats:
    await expire_overdue(db, org)
    lease_scope = select(Lease.id).where(
        Lease.organization_id == org, Lease.property_id.is_not(None)
    )
    if not _can_manage(context, "leases"):
        tenant = await _actor_tenant(db, org, context.actor_user_id)
        lease_scope = lease_scope.where(Lease.tenant_id == (tenant.id if tenant else ""))
    lease_ids = list(await db.scalars(lease_scope))
    property_ids = list(
        await db.scalars(
            select(Lease.property_id).where(
                Lease.organization_id == org, Lease.id.in_(lease_ids or [""])
            )
        )
    )
    manager = _can_manage(context, "leases")
    property_filter = RentalProperty.organization_id == org
    if not manager:
        property_filter = RentalProperty.id.in_(property_ids or [""])
    total_properties = int(
        await db.scalar(select(func.count(RentalProperty.id)).where(property_filter)) or 0
    )
    available = int(
        await db.scalar(
            select(func.count(RentalProperty.id)).where(
                property_filter, RentalProperty.status == RentalPropertyStatus.AVAILABLE
            )
        )
        or 0
    )
    occupied = int(
        await db.scalar(
            select(func.count(RentalProperty.id)).where(
                property_filter, RentalProperty.status == RentalPropertyStatus.OCCUPIED
            )
        )
        or 0
    )
    active = int(
        await db.scalar(
            select(func.count(Lease.id)).where(
                Lease.organization_id == org,
                Lease.id.in_(lease_ids or [""]),
                Lease.status == LeaseStatus.ACTIVE,
            )
        )
        or 0
    )
    overdue = int(
        await db.scalar(
            select(func.count(RentalInvoice.id)).where(
                RentalInvoice.organization_id == org,
                RentalInvoice.lease_id.in_(lease_ids or [""]),
                RentalInvoice.status == InvoiceStatus.OVERDUE,
            )
        )
        or 0
    )
    outstanding = (
        await db.scalar(
            select(
                func.coalesce(func.sum(RentalInvoice.total - RentalInvoice.paid_amount), 0)
            ).where(
                RentalInvoice.organization_id == org,
                RentalInvoice.lease_id.in_(lease_ids or [""]),
                RentalInvoice.status.not_in((InvoiceStatus.PAID, InvoiceStatus.VOIDED)),
            )
        )
        or ZERO
    )
    open_maintenance = int(
        await db.scalar(
            select(func.count(Maintenance.id)).where(
                Maintenance.organization_id == org,
                Maintenance.lease_id.in_(lease_ids or [""]),
                Maintenance.status.not_in((ServiceStatus.CLOSED, ServiceStatus.CANCELLED)),
            )
        )
        or 0
    )
    return RentalStats(
        total_properties=total_properties,
        available_properties=available,
        occupied_properties=occupied,
        active_leases=active,
        overdue_invoices=overdue,
        outstanding_rent=Decimal(outstanding),
        open_maintenance=open_maintenance,
    )


async def options(db: AsyncSession, org: str) -> RentalOptions:
    properties = list(
        await db.scalars(
            select(RentalProperty)
            .where(
                RentalProperty.organization_id == org,
                RentalProperty.status == RentalPropertyStatus.AVAILABLE,
            )
            .order_by(RentalProperty.name)
        )
    )
    tenants = list(
        await db.scalars(
            select(Tenant)
            .where(Tenant.organization_id == org, Tenant.status == TenantStatus.ACTIVE)
            .order_by(Tenant.full_name)
        )
    )
    users = list(
        await db.scalars(
            select(User)
            .where(User.organization_id == org, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )
    return RentalOptions(
        properties=[await _property_view(db, org, item) for item in properties],
        tenants=[await _tenant_view(db, org, item) for item in tenants],
        managers=[{"id": item.id, "label": item.full_name} for item in users],
    )


async def document_download(
    db: AsyncSession,
    org: str,
    lease_id: str,
    document_id: str,
    context: MutationContext,
) -> tuple[StoredFile, str, str]:
    lease = await _scoped_lease(db, org, lease_id, context)
    item = await _entity(db, LeaseDocument, org, document_id)
    if (
        item.lease_id != lease.id
        or not item.storage_key
        or not item.file_name
        or not item.content_type
    ):
        raise _error("LEASE_DOCUMENT_MISSING", "Lease document is unavailable", 404)
    path = await get_storage().path_for_read(key=item.storage_key)
    return path, item.file_name, item.content_type
