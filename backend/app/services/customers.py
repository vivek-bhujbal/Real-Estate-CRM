from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.models.entities import (
    Agreement,
    AuditLog,
    Booking,
    Branch,
    Customer,
    CustomerActivity,
    CustomerDocument,
    CustomerLedger,
    Lead,
    LeadActivity,
    LeadSource,
    Payment,
    Possession,
    Project,
    Quotation,
    ServiceRequest,
    SiteVisit,
    Unit,
    User,
)
from app.models.enums import CustomerStatus, LedgerEntryType, PaymentStatus
from app.schemas.customers import (
    AgreementRecord,
    Customer360View,
    CustomerActivityPayload,
    CustomerActivityView,
    CustomerCreate,
    CustomerStats,
    CustomerUpdate,
    CustomerView,
    DocumentRecord,
    FinancialSummary,
    JourneyRecord,
    PaymentRecord,
    PossessionRecord,
    SalesRecord,
    ServiceRequestRecord,
    TimelineRecord,
)
from app.schemas.leads import AssigneeView
from app.schemas.organization import Page
from app.services.documents import expire_due_documents
from app.services.organization import MutationContext


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _not_found() -> AppError:
    return AppError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="The requested resource was not found",
    )


def _normalize_email(value: str | None) -> str | None:
    return value.strip().lower() if value else None


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _granted(permissions: frozenset[str], permission: str) -> bool:
    return permission_is_granted(permissions, permission)


def _snapshot(customer: Customer) -> dict[str, Any]:
    return {
        "full_name": customer.full_name,
        "email": customer.email,
        "phone": customer.phone,
        "status": customer.status.value,
        "owner_user_id": customer.owner_user_id,
        "branch_id": customer.branch_id,
        "preferred_location": customer.preferred_location,
        "budget_min": str(customer.budget_min) if customer.budget_min is not None else None,
        "budget_max": str(customer.budget_max) if customer.budget_max is not None else None,
    }


def _audit(
    organization_id: str,
    context: MutationContext,
    action: str,
    entity_type: str,
    entity_id: str,
    previous_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organization_id=organization_id,
        actor_user_id=context.actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=previous_value,
        new_value=new_value,
        request_id=context.request_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        device_metadata=context.device_metadata,
        created_at=_now(),
    )


async def _customer(
    db: AsyncSession, organization_id: str, customer_id: str, *, lock: bool = False
) -> Customer:
    statement = select(Customer).where(
        Customer.organization_id == organization_id, Customer.id == customer_id
    )
    if lock:
        statement = statement.with_for_update()
    customer = (await db.scalars(statement)).first()
    if customer is None:
        raise _not_found()
    return customer


async def _validate_references(
    db: AsyncSession,
    organization_id: str,
    owner_user_id: str | None,
    branch_id: str | None,
) -> None:
    if owner_user_id is not None:
        owner = await db.scalar(
            select(User.id).where(
                User.organization_id == organization_id,
                User.id == owner_user_id,
                User.is_active.is_(True),
            )
        )
        if owner is None:
            raise AppError(
                status_code=400,
                code="INVALID_OWNER",
                message="Select an active user in this organization",
            )
    if branch_id is not None:
        branch = await db.scalar(
            select(Branch.id).where(
                Branch.organization_id == organization_id,
                Branch.id == branch_id,
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise AppError(
                status_code=400,
                code="INVALID_BRANCH",
                message="Select an active branch in this organization",
            )


async def _duplicate_ids(
    db: AsyncSession,
    organization_id: str,
    email: str | None,
    phone: str | None,
    exclude_id: str | None = None,
) -> list[str]:
    criteria = []
    normalized_email = _normalize_email(email)
    normalized_phone = _normalize_phone(phone)
    if normalized_email:
        criteria.append(Customer.normalized_email == normalized_email)
    if normalized_phone:
        criteria.append(Customer.normalized_phone == normalized_phone)
    if not criteria:
        return []
    statement = select(Customer.id).where(
        Customer.organization_id == organization_id, or_(*criteria)
    )
    if exclude_id:
        statement = statement.where(Customer.id != exclude_id)
    return list((await db.scalars(statement)).all())


async def _views(
    db: AsyncSession,
    organization_id: str,
    customers: list[Customer],
    permissions: frozenset[str] | None = None,
) -> list[CustomerView]:
    if not customers:
        return []
    ids = [customer.id for customer in customers]
    owner_ids = {customer.owner_user_id for customer in customers if customer.owner_user_id}
    branch_ids = {customer.branch_id for customer in customers if customer.branch_id}
    owners = (
        {
            item.id: item.full_name
            for item in (
                await db.scalars(
                    select(User).where(
                        User.organization_id == organization_id, User.id.in_(owner_ids)
                    )
                )
            ).all()
        }
        if owner_ids
        else {}
    )
    branches = (
        {
            item.id: item.name
            for item in (
                await db.scalars(
                    select(Branch).where(
                        Branch.organization_id == organization_id, Branch.id.in_(branch_ids)
                    )
                )
            ).all()
        }
        if branch_ids
        else {}
    )
    activity_counts: dict[str, int] = (
        {
            customer_id: count
            for customer_id, count in (
                await db.execute(
                    select(CustomerActivity.customer_id, func.count(CustomerActivity.id))
                    .where(
                        CustomerActivity.organization_id == organization_id,
                        CustomerActivity.customer_id.in_(ids),
                    )
                    .group_by(CustomerActivity.customer_id)
                )
            ).all()
        }
        if permissions is not None and _granted(permissions, "activities.view")
        else {}
    )
    booking_counts: dict[str, int] = (
        {
            customer_id: count
            for customer_id, count in (
                await db.execute(
                    select(Booking.customer_id, func.count(Booking.id))
                    .where(Booking.organization_id == organization_id, Booking.customer_id.in_(ids))
                    .group_by(Booking.customer_id)
                )
            ).all()
        }
        if permissions is not None and _granted(permissions, "bookings.view")
        else {}
    )
    return [
        CustomerView(
            id=item.id,
            converted_from_lead_id=item.converted_from_lead_id,
            full_name=item.full_name,
            email=item.email,
            phone=item.phone,
            alternate_phone=item.alternate_phone,
            date_of_birth=item.date_of_birth,
            gender=item.gender,
            occupation=item.occupation,
            company_name=item.company_name,
            address_line1=item.address_line1,
            address_line2=item.address_line2,
            city=item.city,
            state=item.state,
            postal_code=item.postal_code,
            country=item.country,
            preferred_location=item.preferred_location,
            requirements=item.requirements,
            budget_min=item.budget_min,
            budget_max=item.budget_max,
            owner_user_id=item.owner_user_id,
            owner_name=owners.get(item.owner_user_id) if item.owner_user_id else None,
            branch_id=item.branch_id,
            branch_name=branches.get(item.branch_id) if item.branch_id else None,
            communication_preferences=item.communication_preferences,
            status=item.status,
            activity_count=activity_counts.get(item.id, 0),
            booking_count=booking_counts.get(item.id, 0),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in customers
    ]


async def list_customers(
    db: AsyncSession,
    organization_id: str,
    *,
    q: str | None,
    status: CustomerStatus | None,
    owner_user_id: str | None,
    branch_id: str | None,
    page: int,
    page_size: int,
    permissions: frozenset[str],
) -> Page[CustomerView]:
    filters = [Customer.organization_id == organization_id]
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                Customer.full_name.ilike(term),
                Customer.email.ilike(term),
                Customer.phone.ilike(term),
                Customer.company_name.ilike(term),
            )
        )
    if status is not None:
        filters.append(Customer.status == status)
    if owner_user_id:
        filters.append(Customer.owner_user_id == owner_user_id)
    if branch_id:
        filters.append(Customer.branch_id == branch_id)
    total = int(await db.scalar(select(func.count(Customer.id)).where(*filters)) or 0)
    items = list(
        (
            await db.scalars(
                select(Customer)
                .where(*filters)
                .order_by(Customer.updated_at.desc(), Customer.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=await _views(db, organization_id, items, permissions),
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def customer_stats(db: AsyncSession, organization_id: str) -> CustomerStats:
    rows = (
        await db.execute(
            select(Customer.status, func.count(Customer.id))
            .where(Customer.organization_id == organization_id)
            .group_by(Customer.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    return CustomerStats(
        total=sum(counts.values()),
        prospects=counts.get(CustomerStatus.PROSPECT, 0),
        active=counts.get(CustomerStatus.ACTIVE, 0),
        inactive=counts.get(CustomerStatus.INACTIVE, 0),
        blocked=counts.get(CustomerStatus.BLOCKED, 0),
    )


async def list_assignees(db: AsyncSession, organization_id: str) -> list[AssigneeView]:
    users = list(
        (
            await db.scalars(
                select(User)
                .where(User.organization_id == organization_id, User.is_active.is_(True))
                .order_by(User.full_name, User.email)
            )
        ).all()
    )
    return [
        AssigneeView(
            id=user.id, full_name=user.full_name, email=user.email, branch_id=user.branch_id
        )
        for user in users
    ]


async def create_customer(
    db: AsyncSession,
    organization_id: str,
    payload: CustomerCreate,
    context: MutationContext,
) -> CustomerView:
    if (payload.owner_user_id or payload.branch_id) and not _granted(
        context.permissions, "customers.assign"
    ):
        raise AppError(
            status_code=403,
            code="PERMISSION_DENIED",
            message="Customer assignment permission is required",
        )
    await _validate_references(db, organization_id, payload.owner_user_id, payload.branch_id)
    duplicates = await _duplicate_ids(
        db, organization_id, str(payload.email) if payload.email else None, payload.phone
    )
    if duplicates:
        raise AppError(
            status_code=409,
            code="DUPLICATE_CUSTOMER",
            message="A customer with this email or phone already exists",
        )
    values = payload.model_dump()
    values["email"] = str(payload.email) if payload.email else None
    values["normalized_email"] = _normalize_email(values["email"])
    values["normalized_phone"] = _normalize_phone(payload.phone)
    customer = Customer(organization_id=organization_id, status=CustomerStatus.PROSPECT, **values)
    db.add(customer)
    await db.flush()
    db.add(
        _audit(
            organization_id,
            context,
            "customer.created",
            "customer",
            customer.id,
            None,
            _snapshot(customer),
        )
    )
    await db.commit()
    await db.refresh(customer)
    return (await _views(db, organization_id, [customer], context.permissions))[0]


async def get_customer(
    db: AsyncSession,
    organization_id: str,
    customer_id: str,
    permissions: frozenset[str],
) -> CustomerView:
    customer = await _customer(db, organization_id, customer_id)
    return (await _views(db, organization_id, [customer], permissions))[0]


async def update_customer(
    db: AsyncSession,
    organization_id: str,
    customer_id: str,
    payload: CustomerUpdate,
    context: MutationContext,
) -> CustomerView:
    customer = await _customer(db, organization_id, customer_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if any(key in changes for key in ("owner_user_id", "branch_id")) and not _granted(
        context.permissions, "customers.assign"
    ):
        raise AppError(
            status_code=403,
            code="PERMISSION_DENIED",
            message="Customer assignment permission is required",
        )
    resulting_email = (
        str(changes.get("email"))
        if changes.get("email")
        else (None if "email" in changes else customer.email)
    )
    resulting_phone = changes.get("phone", customer.phone)
    if not resulting_email and not resulting_phone:
        raise AppError(
            status_code=400, code="CONTACT_REQUIRED", message="Email or phone is required"
        )
    resulting_min = changes.get("budget_min", customer.budget_min)
    resulting_max = changes.get("budget_max", customer.budget_max)
    if resulting_min is not None and resulting_max is not None and resulting_min > resulting_max:
        raise AppError(
            status_code=400,
            code="INVALID_BUDGET_RANGE",
            message="Minimum budget cannot exceed maximum budget",
        )
    await _validate_references(
        db,
        organization_id,
        changes.get("owner_user_id", customer.owner_user_id),
        changes.get("branch_id", customer.branch_id),
    )
    duplicates = await _duplicate_ids(
        db, organization_id, resulting_email, resulting_phone, customer.id
    )
    if duplicates:
        raise AppError(
            status_code=409,
            code="DUPLICATE_CUSTOMER",
            message="A customer with this email or phone already exists",
        )
    before = _snapshot(customer)
    if "email" in changes:
        changes["email"] = resulting_email
        changes["normalized_email"] = _normalize_email(resulting_email)
    if "phone" in changes:
        changes["normalized_phone"] = _normalize_phone(resulting_phone)
    for field, value in changes.items():
        setattr(customer, field, value)
    customer.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "customer.updated",
            "customer",
            customer.id,
            before,
            _snapshot(customer),
        )
    )
    await db.commit()
    await db.refresh(customer)
    return (await _views(db, organization_id, [customer], context.permissions))[0]


async def delete_customer(
    db: AsyncSession, organization_id: str, customer_id: str, context: MutationContext
) -> None:
    customer = await _customer(db, organization_id, customer_id, lock=True)
    db.add(
        _audit(
            organization_id,
            context,
            "customer.deleted",
            "customer",
            customer.id,
            _snapshot(customer),
            None,
        )
    )
    await db.delete(customer)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            status_code=409,
            code="CUSTOMER_IN_USE",
            message="Customer cannot be deleted while linked records exist",
        ) from exc


async def _activity_views(
    db: AsyncSession, organization_id: str, records: list[CustomerActivity]
) -> list[CustomerActivityView]:
    user_ids = {record.performed_by_user_id for record in records if record.performed_by_user_id}
    users = (
        {
            user.id: user.full_name
            for user in (
                await db.scalars(
                    select(User).where(
                        User.organization_id == organization_id, User.id.in_(user_ids)
                    )
                )
            ).all()
        }
        if user_ids
        else {}
    )
    return [
        CustomerActivityView(
            id=record.id,
            activity_type=record.activity_type,
            subject=record.subject,
            notes=record.notes,
            channel=record.channel,
            direction=record.direction,
            performed_by_user_id=record.performed_by_user_id,
            performed_by_name=(
                users.get(record.performed_by_user_id) if record.performed_by_user_id else None
            ),
            occurred_at=record.occurred_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        for record in records
    ]


async def list_activities(
    db: AsyncSession, organization_id: str, customer_id: str
) -> list[CustomerActivityView]:
    await _customer(db, organization_id, customer_id)
    records = list(
        (
            await db.scalars(
                select(CustomerActivity)
                .where(
                    CustomerActivity.organization_id == organization_id,
                    CustomerActivity.customer_id == customer_id,
                )
                .order_by(CustomerActivity.occurred_at.desc())
            )
        ).all()
    )
    return await _activity_views(db, organization_id, records)


async def create_activity(
    db: AsyncSession,
    organization_id: str,
    customer_id: str,
    payload: CustomerActivityPayload,
    context: MutationContext,
) -> CustomerActivityView:
    await _customer(db, organization_id, customer_id)
    record = CustomerActivity(
        organization_id=organization_id,
        customer_id=customer_id,
        performed_by_user_id=context.actor_user_id,
        occurred_at=payload.occurred_at or _now(),
        **payload.model_dump(exclude={"occurred_at"}),
    )
    db.add(record)
    await db.flush()
    db.add(
        _audit(
            organization_id,
            context,
            "customer.activity.created",
            "customer_activity",
            record.id,
            None,
            {
                "customer_id": customer_id,
                "subject": record.subject,
                "activity_type": record.activity_type.value,
            },
        )
    )
    await db.commit()
    await db.refresh(record)
    return (await _activity_views(db, organization_id, [record]))[0]


async def update_activity(
    db: AsyncSession,
    organization_id: str,
    customer_id: str,
    activity_id: str,
    payload: CustomerActivityPayload,
    context: MutationContext,
) -> CustomerActivityView:
    await _customer(db, organization_id, customer_id)
    record = (
        await db.scalars(
            select(CustomerActivity)
            .where(
                CustomerActivity.organization_id == organization_id,
                CustomerActivity.customer_id == customer_id,
                CustomerActivity.id == activity_id,
            )
            .with_for_update()
        )
    ).first()
    if record is None:
        raise _not_found()
    before = {"subject": record.subject, "activity_type": record.activity_type.value}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "occurred_at" and value is None:
            continue
        setattr(record, field, value)
    record.updated_at = _now()
    db.add(
        _audit(
            organization_id,
            context,
            "customer.activity.updated",
            "customer_activity",
            record.id,
            before,
            {"subject": record.subject, "activity_type": record.activity_type.value},
        )
    )
    await db.commit()
    await db.refresh(record)
    return (await _activity_views(db, organization_id, [record]))[0]


async def delete_activity(
    db: AsyncSession,
    organization_id: str,
    customer_id: str,
    activity_id: str,
    context: MutationContext,
) -> None:
    await _customer(db, organization_id, customer_id)
    record = (
        await db.scalars(
            select(CustomerActivity).where(
                CustomerActivity.organization_id == organization_id,
                CustomerActivity.customer_id == customer_id,
                CustomerActivity.id == activity_id,
            )
        )
    ).first()
    if record is None:
        raise _not_found()
    db.add(
        _audit(
            organization_id,
            context,
            "customer.activity.deleted",
            "customer_activity",
            record.id,
            {"customer_id": customer_id, "subject": record.subject},
            None,
        )
    )
    await db.delete(record)
    await db.commit()


async def customer_360(
    db: AsyncSession,
    organization_id: str,
    customer_id: str,
    permissions: frozenset[str],
) -> Customer360View:
    customer = await _customer(db, organization_id, customer_id)
    view = (await _views(db, organization_id, [customer], permissions))[0]
    result = Customer360View(customer=view, available_sections=[])
    timeline: list[TimelineRecord] = [
        TimelineRecord(
            id=customer.id,
            kind="customer",
            title="Customer profile created",
            status=customer.status.value,
            occurred_at=customer.created_at,
        )
    ]

    if customer.converted_from_lead_id and _granted(permissions, "leads.view"):
        row = (
            await db.execute(
                select(Lead, LeadSource.name)
                .outerjoin(
                    LeadSource,
                    (LeadSource.organization_id == Lead.organization_id)
                    & (LeadSource.id == Lead.source_id),
                )
                .where(
                    Lead.organization_id == organization_id,
                    Lead.id == customer.converted_from_lead_id,
                )
            )
        ).first()
        if row:
            lead, source_name = row
            result.lead_history = [
                JourneyRecord(
                    id=lead.id,
                    status=lead.status.value,
                    source_name=source_name,
                    score=lead.score,
                    created_at=lead.created_at,
                    converted_at=lead.converted_at,
                )
            ]
            result.available_sections.append("lead_history")
            if _granted(permissions, "activities.view"):
                lead_activities = list(
                    (
                        await db.scalars(
                            select(LeadActivity).where(
                                LeadActivity.organization_id == organization_id,
                                LeadActivity.lead_id == lead.id,
                            )
                        )
                    ).all()
                )
                timeline.extend(
                    TimelineRecord(
                        id=item.id,
                        kind="lead_activity",
                        title=item.subject,
                        detail=item.notes,
                        status=item.activity_type.value,
                        occurred_at=item.occurred_at,
                    )
                    for item in lead_activities
                )

    if _granted(permissions, "activities.view"):
        result.activities = await list_activities(db, organization_id, customer_id)
        result.available_sections.append("activities")
        timeline.extend(
            TimelineRecord(
                id=item.id,
                kind="activity",
                title=item.subject,
                detail=item.notes,
                status=item.activity_type.value,
                occurred_at=item.occurred_at,
            )
            for item in result.activities
        )

    project_names = {
        item.id: item.name
        for item in (
            await db.scalars(select(Project).where(Project.organization_id == organization_id))
        ).all()
    }
    unit_numbers = {
        item.id: item.unit_number
        for item in (
            await db.scalars(select(Unit).where(Unit.organization_id == organization_id))
        ).all()
    }
    if _granted(permissions, "visits.view"):
        visits = list(
            (
                await db.scalars(
                    select(SiteVisit)
                    .where(
                        SiteVisit.organization_id == organization_id,
                        SiteVisit.customer_id == customer_id,
                    )
                    .order_by(SiteVisit.scheduled_at.desc())
                )
            ).all()
        )
        result.sales.extend(
            SalesRecord(
                id=item.id,
                kind="site_visit",
                reference="Site visit",
                status=item.status.value,
                project_name=project_names.get(item.project_id),
                unit_number=unit_numbers.get(item.unit_id) if item.unit_id else None,
                occurred_at=item.scheduled_at,
                secondary_date=item.completed_at,
            )
            for item in visits
        )
        result.available_sections.append("visits")
    if _granted(permissions, "quotations.view"):
        quotations = list(
            (
                await db.scalars(
                    select(Quotation)
                    .where(
                        Quotation.organization_id == organization_id,
                        Quotation.customer_id == customer_id,
                    )
                    .order_by(Quotation.created_at.desc())
                )
            ).all()
        )
        result.sales.extend(
            SalesRecord(
                id=item.id,
                kind="quotation",
                reference=item.quotation_number,
                status=item.status.value,
                project_name=project_names.get(item.project_id),
                amount=item.total,
                currency=item.currency,
                occurred_at=item.created_at,
                secondary_date=item.valid_until,
            )
            for item in quotations
        )
        result.available_sections.append("quotations")
    bookings = list(
        (
            await db.scalars(
                select(Booking)
                .where(
                    Booking.organization_id == organization_id, Booking.customer_id == customer_id
                )
                .order_by(Booking.created_at.desc())
            )
        ).all()
    )
    booking_numbers = {item.id: item.booking_number for item in bookings}
    if _granted(permissions, "bookings.view"):
        result.sales.extend(
            SalesRecord(
                id=item.id,
                kind="booking",
                reference=item.booking_number,
                status=item.status.value,
                unit_number=unit_numbers.get(item.unit_id),
                amount=item.booking_amount,
                currency=item.currency,
                occurred_at=item.booked_at or item.created_at,
            )
            for item in bookings
        )
        result.available_sections.append("bookings")
    for item in result.sales:
        timeline.append(
            TimelineRecord(
                id=item.id,
                kind=item.kind,
                title=item.reference,
                detail=item.project_name or item.unit_number,
                status=item.status,
                occurred_at=item.occurred_at,
            )
        )

    if _granted(permissions, "documents.view"):
        await expire_due_documents(db, organization_id)
        document_rows = (
            await db.execute(
                select(CustomerDocument, User.full_name)
                .outerjoin(
                    User,
                    (User.organization_id == CustomerDocument.organization_id)
                    & (User.id == CustomerDocument.uploaded_by_user_id),
                )
                .where(
                    CustomerDocument.organization_id == organization_id,
                    CustomerDocument.customer_id == customer_id,
                    CustomerDocument.is_current.is_(True),
                )
                .order_by(CustomerDocument.created_at.desc())
            )
        ).all()
        result.documents = [
            DocumentRecord(
                id=item.id,
                document_type=item.document_type,
                file_name=item.file_name,
                content_type=item.content_type,
                size_bytes=item.size_bytes,
                status=item.status.value,
                version=item.version,
                expiry_date=item.expiry_date,
                booking_id=item.booking_id,
                rejection_reason=item.rejection_reason,
                uploaded_by_name=user_name,
                created_at=item.created_at,
            )
            for item, user_name in document_rows
        ]
        result.available_sections.append("documents")

    if _granted(permissions, "payments.view") or _granted(permissions, "collections.view"):
        payments = list(
            (
                await db.scalars(
                    select(Payment)
                    .where(
                        Payment.organization_id == organization_id,
                        Payment.customer_id == customer_id,
                    )
                    .order_by(Payment.created_at.desc())
                )
            ).all()
        )
        result.payments = [
            PaymentRecord(
                id=item.id,
                booking_number=booking_numbers.get(item.booking_id),
                amount=item.amount,
                currency=item.currency,
                method=item.method,
                status=item.status.value,
                reference_number=item.reference_number,
                paid_at=item.paid_at,
                created_at=item.created_at,
            )
            for item in payments
        ]
        paid = sum(
            (item.amount for item in payments if item.status == PaymentStatus.COMPLETED),
            Decimal("0"),
        )
        entries = list(
            (
                await db.scalars(
                    select(CustomerLedger).where(
                        CustomerLedger.organization_id == organization_id,
                        CustomerLedger.customer_id == customer_id,
                    )
                )
            ).all()
        )
        outstanding = sum(
            (
                item.amount if item.entry_type != LedgerEntryType.CREDIT else -item.amount
                for item in entries
            ),
            Decimal("0"),
        )
        currencies = {item.currency for item in entries} or {item.currency for item in payments}
        result.financial_summary = FinancialSummary(
            currency=next(iter(currencies)) if len(currencies) == 1 else None,
            paid_amount=paid,
            outstanding_amount=max(outstanding, Decimal("0")),
        )
        result.available_sections.append("payments")
        timeline.extend(
            TimelineRecord(
                id=item.id,
                kind="payment",
                title=f"Payment {item.status.lower()}",
                detail=item.reference_number,
                status=item.status,
                occurred_at=item.paid_at or item.created_at,
            )
            for item in result.payments
        )

    if _granted(permissions, "agreements.view"):
        agreement_rows = (
            await db.execute(
                select(Agreement, Booking.booking_number)
                .join(
                    Booking,
                    (Booking.organization_id == Agreement.organization_id)
                    & (Booking.id == Agreement.booking_id),
                )
                .where(
                    Agreement.organization_id == organization_id, Booking.customer_id == customer_id
                )
                .order_by(Agreement.created_at.desc())
            )
        ).all()
        result.agreements = [
            AgreementRecord(
                id=item.id,
                booking_number=number,
                agreement_number=item.agreement_number,
                status=item.status.value,
                issued_at=item.issued_at,
                signed_at=item.signed_at,
                registered_at=item.registered_at,
            )
            for item, number in agreement_rows
        ]
        result.available_sections.append("agreements")

    if _granted(permissions, "possession.view"):
        possession_rows = (
            await db.execute(
                select(Possession, Booking.booking_number, Unit.unit_number)
                .join(
                    Booking,
                    (Booking.organization_id == Possession.organization_id)
                    & (Booking.id == Possession.booking_id),
                )
                .join(
                    Unit,
                    (Unit.organization_id == Possession.organization_id)
                    & (Unit.id == Possession.unit_id),
                )
                .where(
                    Possession.organization_id == organization_id,
                    Possession.customer_id == customer_id,
                )
                .order_by(Possession.created_at.desc())
            )
        ).all()
        result.possessions = [
            PossessionRecord(
                id=item.id,
                booking_number=booking_number,
                unit_number=unit_number,
                status=item.status.value,
                offered_at=item.offered_at,
                scheduled_at=item.scheduled_at,
                completed_at=item.completed_at,
            )
            for item, booking_number, unit_number in possession_rows
        ]
        result.available_sections.append("possession")

    if _granted(permissions, "service_requests.view"):
        requests = list(
            (
                await db.scalars(
                    select(ServiceRequest)
                    .where(
                        ServiceRequest.organization_id == organization_id,
                        ServiceRequest.customer_id == customer_id,
                    )
                    .order_by(ServiceRequest.opened_at.desc())
                )
            ).all()
        )
        result.service_requests = [
            ServiceRequestRecord(
                id=item.id,
                request_number=item.request_number,
                category=item.category,
                priority=item.priority.value,
                status=item.status.value,
                subject=item.subject,
                opened_at=item.opened_at,
                resolved_at=item.resolved_at,
            )
            for item in requests
        ]
        result.available_sections.append("service_requests")
        timeline.extend(
            TimelineRecord(
                id=item.id,
                kind="service_request",
                title=item.subject,
                detail=item.request_number,
                status=item.status,
                occurred_at=item.opened_at,
            )
            for item in result.service_requests
        )

    result.timeline = sorted(timeline, key=lambda item: item.occurred_at, reverse=True)[:200]
    return result
