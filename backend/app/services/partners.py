import asyncio
import re
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Any

from fastapi import UploadFile
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.entities import (
    AuditLog,
    Booking,
    ChannelPartner,
    Commission,
    CommissionPayout,
    CommissionStructure,
    Lead,
    PartnerAgreement,
    PartnerContact,
    PartnerDispute,
    PartnerDocument,
    PartnerLead,
    PartnerProject,
    PartnerTerritory,
    Project,
    Territory,
    Unit,
    User,
)
from app.models.enums import (
    AgreementStatus,
    BookingStatus,
    CommissionStatus,
    DocumentStatus,
    LeadStatus,
    PartnerStatus,
    PaymentStatus,
    WorkflowStatus,
)
from app.schemas.organization import Page
from app.schemas.partners import (
    CommissionDecision,
    CommissionStructureCreate,
    CommissionStructureView,
    CommissionView,
    DisputeAssign,
    DisputeCreate,
    DisputeDecision,
    DisputeView,
    LifecycleAction,
    PartnerAgreementCreate,
    PartnerAgreementView,
    PartnerApplicationCreate,
    PartnerAssignmentsUpdate,
    PartnerComplianceUpdate,
    PartnerContactCreate,
    PartnerContactView,
    PartnerDetail,
    PartnerDocumentDecision,
    PartnerDocumentRequest,
    PartnerDocumentView,
    PartnerLeadCreate,
    PartnerLeadView,
    PartnerOption,
    PartnerOptions,
    PartnerProfileUpdate,
    PartnerStats,
    PartnerSummary,
    PayoutCreate,
    PayoutProcess,
    PayoutView,
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
        raise _error("RESOURCE_NOT_FOUND", "Channel partner record not found", 404)
    return item


async def _name(db: AsyncSession, org: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = await db.scalar(
        select(User.full_name).where(User.organization_id == org, User.id == user_id)
    )
    return str(value) if value else None


def _normalize_email(value: str | None) -> str | None:
    return value.strip().lower() if value else None


def _normalize_phone(value: str | None) -> str | None:
    return re.sub(r"\D", "", value) if value else None


async def _summary(db: AsyncSession, org: str, partner: ChannelPartner) -> PartnerSummary:
    lead_count = int(
        await db.scalar(
            select(func.count(PartnerLead.id)).where(
                PartnerLead.organization_id == org,
                PartnerLead.channel_partner_id == partner.id,
                PartnerLead.status == WorkflowStatus.APPROVED,
                PartnerLead.protected_until >= date.today(),
            )
        )
        or 0
    )
    booking_count = int(
        await db.scalar(
            select(func.count(Booking.id)).where(
                Booking.organization_id == org,
                Booking.channel_partner_id == partner.id,
                Booking.status == BookingStatus.CONFIRMED,
            )
        )
        or 0
    )
    commission_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Commission.amount), 0), func.min(Commission.currency)
            ).where(
                Commission.organization_id == org,
                Commission.channel_partner_id == partner.id,
                Commission.status.in_((CommissionStatus.ELIGIBLE, CommissionStatus.APPROVED)),
                Commission.commission_payout_id.is_(None),
            )
        )
    ).one()
    return PartnerSummary(
        id=partner.id,
        code=partner.code,
        name=partner.name,
        legal_name=partner.legal_name,
        partner_type=partner.partner_type,
        contact_name=partner.contact_name,
        email=partner.email,
        phone=partner.phone,
        city=partner.city,
        status=partner.status,
        manager_name=await _name(db, org, partner.manager_user_id),
        active_leads=lead_count,
        confirmed_bookings=booking_count,
        payable_commission=_money(commission_row[0] or ZERO),
        currency=commission_row[1],
        created_at=partner.created_at,
        updated_at=partner.updated_at,
    )


async def list_partners(
    db: AsyncSession,
    org: str,
    *,
    q: str | None,
    status: PartnerStatus | None,
    manager_user_id: str | None,
    territory_id: str | None,
    project_id: str | None,
    page: int,
    page_size: int,
) -> Page[PartnerSummary]:
    statement = select(ChannelPartner)
    filters: list[Any] = [ChannelPartner.organization_id == org]
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                ChannelPartner.name.ilike(like),
                ChannelPartner.code.ilike(like),
                ChannelPartner.registration_number.ilike(like),
                ChannelPartner.email.ilike(like),
            )
        )
    if status:
        filters.append(ChannelPartner.status == status)
    if manager_user_id:
        filters.append(ChannelPartner.manager_user_id == manager_user_id)
    if territory_id:
        statement = statement.join(
            PartnerTerritory,
            (PartnerTerritory.organization_id == ChannelPartner.organization_id)
            & (PartnerTerritory.channel_partner_id == ChannelPartner.id),
        )
        filters.append(PartnerTerritory.territory_id == territory_id)
    if project_id:
        statement = statement.join(
            PartnerProject,
            (PartnerProject.organization_id == ChannelPartner.organization_id)
            & (PartnerProject.channel_partner_id == ChannelPartner.id),
        )
        filters.append(PartnerProject.project_id == project_id)
    statement = statement.where(*filters)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = list(
        await db.scalars(
            statement.order_by(ChannelPartner.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[await _summary(db, org, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


async def _document_view(item: PartnerDocument) -> PartnerDocumentView:
    return PartnerDocumentView(
        id=item.id,
        document_type=item.document_type,
        status=item.status,
        file_name=item.file_name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        expiry_date=item.expiry_date,
        rejection_reason=item.rejection_reason,
        review_notes=item.review_notes,
        uploaded_at=item.uploaded_at,
        reviewed_at=item.reviewed_at,
    )


async def _agreement_view(item: PartnerAgreement) -> PartnerAgreementView:
    return PartnerAgreementView(
        id=item.id,
        agreement_number=item.agreement_number,
        status=item.status,
        effective_from=item.effective_from,
        effective_until=item.effective_until,
        commission_percent=item.commission_percent,
        terms_summary=item.terms_summary,
        file_name=item.file_name,
        issued_at=item.issued_at,
        signed_at=item.signed_at,
    )


async def _commission_view(db: AsyncSession, org: str, item: Commission) -> CommissionView:
    booking = await _entity(db, Booking, org, item.booking_id)
    return CommissionView(
        id=item.id,
        booking_id=booking.id,
        booking_number=booking.booking_number,
        status=item.status,
        rate_percent=item.rate_percent,
        amount=item.amount,
        currency=item.currency,
        commission_payout_id=item.commission_payout_id,
    )


async def _payout_view(db: AsyncSession, org: str, item: CommissionPayout) -> PayoutView:
    ids = list(
        await db.scalars(
            select(Commission.id).where(
                Commission.organization_id == org, Commission.commission_payout_id == item.id
            )
        )
    )
    return PayoutView(
        id=item.id,
        payout_number=item.payout_number,
        status=item.status,
        amount=item.amount,
        currency=item.currency,
        reference_number=item.reference_number,
        notes=item.notes,
        decision_notes=item.decision_notes,
        requested_at=item.requested_at,
        approved_at=item.approved_at,
        paid_at=item.paid_at,
        commission_ids=ids,
    )


async def _dispute_view(db: AsyncSession, org: str, item: PartnerDispute) -> DisputeView:
    relations = (
        ("lead", item.partner_lead_id),
        ("booking", item.booking_id),
        ("commission", item.commission_id),
        ("payout", item.commission_payout_id),
    )
    related_type, related_id = next((kind, value) for kind, value in relations if value)
    return DisputeView(
        id=item.id,
        dispute_number=item.dispute_number,
        category=item.category,
        status=item.status,
        description=item.description,
        resolution=item.resolution,
        related_type=related_type,
        related_id=str(related_id),
        assigned_to_name=await _name(db, org, item.assigned_to_user_id),
        raised_at=item.raised_at,
        resolved_at=item.resolved_at,
    )


async def detail(db: AsyncSession, org: str, partner_id: str) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    contacts = list(
        await db.scalars(
            select(PartnerContact)
            .where(
                PartnerContact.organization_id == org,
                PartnerContact.channel_partner_id == partner.id,
            )
            .order_by(PartnerContact.is_primary.desc(), PartnerContact.full_name)
        )
    )
    documents = list(
        await db.scalars(
            select(PartnerDocument)
            .where(
                PartnerDocument.organization_id == org,
                PartnerDocument.channel_partner_id == partner.id,
            )
            .order_by(PartnerDocument.created_at.desc())
        )
    )
    agreements = list(
        await db.scalars(
            select(PartnerAgreement)
            .where(
                PartnerAgreement.organization_id == org,
                PartnerAgreement.channel_partner_id == partner.id,
            )
            .order_by(PartnerAgreement.created_at.desc())
        )
    )
    structures = list(
        await db.scalars(
            select(CommissionStructure)
            .where(
                CommissionStructure.organization_id == org,
                CommissionStructure.channel_partner_id == partner.id,
            )
            .order_by(CommissionStructure.effective_from.desc())
        )
    )
    partner_leads = list(
        await db.scalars(
            select(PartnerLead)
            .where(PartnerLead.organization_id == org, PartnerLead.channel_partner_id == partner.id)
            .order_by(PartnerLead.registered_at.desc())
            .limit(100)
        )
    )
    commissions = list(
        await db.scalars(
            select(Commission)
            .where(Commission.organization_id == org, Commission.channel_partner_id == partner.id)
            .order_by(Commission.created_at.desc())
            .limit(100)
        )
    )
    payouts = list(
        await db.scalars(
            select(CommissionPayout)
            .where(
                CommissionPayout.organization_id == org,
                CommissionPayout.channel_partner_id == partner.id,
            )
            .order_by(CommissionPayout.created_at.desc())
            .limit(100)
        )
    )
    disputes = list(
        await db.scalars(
            select(PartnerDispute)
            .where(
                PartnerDispute.organization_id == org,
                PartnerDispute.channel_partner_id == partner.id,
            )
            .order_by(PartnerDispute.created_at.desc())
            .limit(100)
        )
    )
    territory_ids = list(
        await db.scalars(
            select(PartnerTerritory.territory_id).where(
                PartnerTerritory.organization_id == org,
                PartnerTerritory.channel_partner_id == partner.id,
            )
        )
    )
    project_ids = list(
        await db.scalars(
            select(PartnerProject.project_id).where(
                PartnerProject.organization_id == org,
                PartnerProject.channel_partner_id == partner.id,
            )
        )
    )
    project_names = {
        project.id: project.name
        for project in list(
            await db.scalars(
                select(Project).where(
                    Project.organization_id == org,
                    Project.id.in_([item.project_id for item in structures if item.project_id]),
                )
            )
        )
    }
    lead_rows: list[PartnerLeadView] = []
    for item in partner_leads:
        lead = await _entity(db, Lead, org, item.lead_id)
        lead_rows.append(
            PartnerLeadView(
                id=item.id,
                lead_id=lead.id,
                lead_name=lead.full_name,
                email=lead.email,
                phone=lead.phone,
                status=item.status,
                registered_at=item.registered_at,
                protected_until=item.protected_until,
                registration_notes=item.registration_notes,
            )
        )
    return PartnerDetail(
        partner=await _summary(db, org, partner),
        registration_number=partner.registration_number,
        registration_date=partner.registration_date,
        website=partner.website,
        address={
            "line1": partner.address_line1,
            "line2": partner.address_line2,
            "city": partner.city,
            "state": partner.state,
            "postal_code": partner.postal_code,
            "country": partner.country,
        },
        tax={
            "tax_identifier": partner.tax_identifier,
            "gst_number": partner.gst_number,
            "registration_name": partner.tax_registration_name,
        },
        bank={
            "account_holder": partner.bank_account_holder,
            "bank_name": partner.bank_name,
            "branch": partner.bank_branch,
            "ifsc": partner.bank_ifsc,
            "account_last4": partner.bank_account_last4,
            "account_reference": partner.bank_account_reference,
        },
        lead_protection_days=partner.lead_protection_days,
        application_notes=partner.application_notes,
        review_notes=partner.review_notes,
        rejection_reason=partner.rejection_reason,
        territory_ids=territory_ids,
        project_ids=project_ids,
        contacts=[
            PartnerContactView(
                id=item.id,
                full_name=item.full_name,
                designation=item.designation,
                email=item.email,
                phone=item.phone,
                is_primary=item.is_primary,
                is_active=item.is_active,
            )
            for item in contacts
        ],
        documents=[await _document_view(item) for item in documents],
        agreements=[await _agreement_view(item) for item in agreements],
        commission_structures=[
            CommissionStructureView(
                id=item.id,
                project_id=item.project_id,
                project_name=project_names.get(item.project_id) if item.project_id else None,
                name=item.name,
                rate_percent=item.rate_percent,
                calculation_basis=item.calculation_basis,
                effective_from=item.effective_from,
                effective_until=item.effective_until,
                is_active=item.is_active,
            )
            for item in structures
        ],
        leads=lead_rows,
        commissions=[await _commission_view(db, org, item) for item in commissions],
        payouts=[await _payout_view(db, org, item) for item in payouts],
        disputes=[await _dispute_view(db, org, item) for item in disputes],
        lifecycle={
            "applied_at": partner.applied_at,
            "documents_verified_at": partner.documents_verified_at,
            "agreement_completed_at": partner.agreement_completed_at,
            "approval_requested_at": partner.approval_requested_at,
            "approved_at": partner.approved_at,
            "activated_at": partner.activated_at,
        },
    )


async def stats(db: AsyncSession, org: str) -> PartnerStats:
    rows = (
        await db.execute(
            select(ChannelPartner.status, func.count(ChannelPartner.id))
            .where(ChannelPartner.organization_id == org)
            .group_by(ChannelPartner.status)
        )
    ).all()
    counts = {status: int(value) for status, value in rows}
    payable = (
        await db.scalar(
            select(func.coalesce(func.sum(Commission.amount), 0)).where(
                Commission.organization_id == org,
                Commission.status.in_((CommissionStatus.ELIGIBLE, CommissionStatus.APPROVED)),
                Commission.commission_payout_id.is_(None),
            )
        )
        or ZERO
    )
    return PartnerStats(
        total=sum(counts.values()),
        applications=counts.get(PartnerStatus.APPLICATION, 0)
        + counts.get(PartnerStatus.PENDING, 0),
        verification=counts.get(PartnerStatus.DOCUMENT_VERIFICATION, 0)
        + counts.get(PartnerStatus.AGREEMENT_PENDING, 0),
        approval_queue=counts.get(PartnerStatus.APPROVAL_PENDING, 0)
        + counts.get(PartnerStatus.APPROVED, 0),
        active=counts.get(PartnerStatus.ACTIVE, 0),
        suspended=counts.get(PartnerStatus.SUSPENDED, 0),
        payable_commission=_money(payable),
    )


async def options(db: AsyncSession, org: str) -> PartnerOptions:
    managers = list(
        await db.scalars(
            select(User)
            .where(User.organization_id == org, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )
    territories = list(
        await db.scalars(
            select(Territory)
            .where(Territory.organization_id == org, Territory.is_active.is_(True))
            .order_by(Territory.name)
        )
    )
    projects = list(
        await db.scalars(
            select(Project).where(Project.organization_id == org).order_by(Project.name)
        )
    )
    return PartnerOptions(
        managers=[PartnerOption(id=item.id, label=item.full_name) for item in managers],
        territories=[PartnerOption(id=item.id, label=item.name) for item in territories],
        projects=[PartnerOption(id=item.id, label=item.name) for item in projects],
    )


async def create_application(
    db: AsyncSession, org: str, payload: PartnerApplicationCreate, context: MutationContext
) -> PartnerDetail:
    now = _now()
    item = ChannelPartner(
        organization_id=org,
        applied_by_user_id=context.actor_user_id,
        code=payload.code,
        name=payload.name.strip(),
        legal_name=payload.legal_name.strip(),
        partner_type=payload.partner_type.strip(),
        registration_number=payload.registration_number.strip(),
        registration_date=payload.registration_date,
        website=payload.website,
        address_line1=payload.address_line1.strip(),
        address_line2=payload.address_line2,
        city=payload.city.strip(),
        state=payload.state.strip(),
        postal_code=payload.postal_code.strip(),
        country=payload.country.strip(),
        contact_name=payload.contact_name.strip(),
        email=str(payload.email),
        phone=payload.phone.strip(),
        manager_user_id=payload.manager_user_id,
        application_notes=payload.application_notes,
        status=PartnerStatus.APPLICATION,
        applied_at=now,
        lead_protection_days=30,
    )
    if item.manager_user_id:
        await _entity(db, User, org, item.manager_user_id)
    db.add(item)
    try:
        await db.flush()
        db.add(
            PartnerContact(
                organization_id=org,
                channel_partner_id=item.id,
                full_name=item.contact_name or item.name,
                email=item.email,
                phone=item.phone,
                is_primary=True,
                is_active=True,
            )
        )
        db.add(
            _audit(
                org,
                context,
                "partner.application.created",
                "channel_partner",
                item.id,
                None,
                {"code": item.code, "name": item.name, "status": item.status.value},
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(
            "PARTNER_ALREADY_EXISTS", "Partner code or registration number already exists"
        ) from exc
    return await detail(db, org, item.id)


async def update_profile(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerProfileUpdate,
    context: MutationContext,
) -> PartnerDetail:
    item = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    if item.status in (PartnerStatus.ACTIVE, PartnerStatus.SUSPENDED, PartnerStatus.INACTIVE):
        raise _error(
            "PROFILE_CHANGE_REQUIRES_REVIEW", "Approved partner identity cannot be edited directly"
        )
    before = {key: getattr(item, key) for key in payload.model_fields_set}
    values = payload.model_dump(exclude_unset=True)
    if "email" in values and values["email"] is not None:
        values["email"] = str(values["email"])
    if values.get("manager_user_id"):
        await _entity(db, User, org, str(values["manager_user_id"]))
    for key, value in values.items():
        setattr(item, key, value.strip() if isinstance(value, str) else value)
    db.add(
        _audit(org, context, "partner.profile.updated", "channel_partner", item.id, before, values)
    )
    await db.commit()
    return await detail(db, org, item.id)


async def update_compliance(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerComplianceUpdate,
    context: MutationContext,
) -> PartnerDetail:
    item = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    before = {
        "tax_identifier": item.tax_identifier,
        "bank_account_last4": item.bank_account_last4,
        "lead_protection_days": item.lead_protection_days,
    }
    for key, value in payload.model_dump().items():
        setattr(item, key, value.strip() if isinstance(value, str) else value)
    db.add(
        _audit(
            org,
            context,
            "partner.compliance.updated",
            "channel_partner",
            item.id,
            before,
            {
                "tax_identifier": item.tax_identifier,
                "bank_account_last4": item.bank_account_last4,
                "lead_protection_days": item.lead_protection_days,
                "bank_reference_configured": True,
            },
        )
    )
    await db.commit()
    return await detail(db, org, item.id)


async def update_assignments(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerAssignmentsUpdate,
    context: MutationContext,
) -> PartnerDetail:
    item = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    for territory_id in set(payload.territory_ids):
        await _entity(db, Territory, org, territory_id)
    for project_id in set(payload.project_ids):
        await _entity(db, Project, org, project_id)
    before_territories = list(
        await db.scalars(
            select(PartnerTerritory.territory_id).where(
                PartnerTerritory.organization_id == org,
                PartnerTerritory.channel_partner_id == item.id,
            )
        )
    )
    before_projects = list(
        await db.scalars(
            select(PartnerProject.project_id).where(
                PartnerProject.organization_id == org, PartnerProject.channel_partner_id == item.id
            )
        )
    )
    await db.execute(
        delete(PartnerTerritory).where(
            PartnerTerritory.organization_id == org, PartnerTerritory.channel_partner_id == item.id
        )
    )
    await db.execute(
        delete(PartnerProject).where(
            PartnerProject.organization_id == org, PartnerProject.channel_partner_id == item.id
        )
    )
    db.add_all(
        [
            PartnerTerritory(organization_id=org, channel_partner_id=item.id, territory_id=value)
            for value in set(payload.territory_ids)
        ]
        + [
            PartnerProject(organization_id=org, channel_partner_id=item.id, project_id=value)
            for value in set(payload.project_ids)
        ]
    )
    db.add(
        _audit(
            org,
            context,
            "partner.assignments.updated",
            "channel_partner",
            item.id,
            {"territory_ids": before_territories, "project_ids": before_projects},
            payload.model_dump(),
        )
    )
    await db.commit()
    return await detail(db, org, item.id)


async def add_contact(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerContactCreate,
    context: MutationContext,
) -> PartnerDetail:
    await _entity(db, ChannelPartner, org, partner_id)
    if payload.is_primary:
        existing = list(
            await db.scalars(
                select(PartnerContact)
                .where(
                    PartnerContact.organization_id == org,
                    PartnerContact.channel_partner_id == partner_id,
                    PartnerContact.is_primary.is_(True),
                )
                .with_for_update()
            )
        )
        for contact in existing:
            contact.is_primary = False
    item = PartnerContact(
        organization_id=org,
        channel_partner_id=partner_id,
        full_name=payload.full_name.strip(),
        designation=payload.designation,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        is_primary=payload.is_primary,
        is_active=True,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "partner.contact.created",
            "partner_contact",
            item.id,
            None,
            {"partner_id": partner_id, "name": item.full_name, "is_primary": item.is_primary},
        )
    )
    await db.commit()
    return await detail(db, org, partner_id)


async def start_document_verification(
    db: AsyncSession, org: str, partner_id: str, payload: LifecycleAction, context: MutationContext
) -> PartnerDetail:
    item = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    if item.status not in (PartnerStatus.APPLICATION, PartnerStatus.PENDING):
        raise _error(
            "INVALID_PARTNER_TRANSITION", "Only an application can enter document verification"
        )
    item.status = PartnerStatus.DOCUMENT_VERIFICATION
    item.review_notes = payload.notes.strip()
    db.add(
        _audit(
            org,
            context,
            "partner.document_verification.started",
            "channel_partner",
            item.id,
            {"status": PartnerStatus.APPLICATION.value},
            {"status": item.status.value, "notes": item.review_notes},
        )
    )
    await db.commit()
    return await detail(db, org, item.id)


async def request_document(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerDocumentRequest,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    if partner.status not in (PartnerStatus.APPLICATION, PartnerStatus.DOCUMENT_VERIFICATION):
        raise _error(
            "DOCUMENT_STAGE_CLOSED",
            "Compliance documents can only be requested during verification",
        )
    item = PartnerDocument(
        organization_id=org,
        channel_partner_id=partner.id,
        document_type=payload.document_type.strip().upper().replace(" ", "_"),
        status=DocumentStatus.PENDING,
        expiry_date=payload.expiry_date,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "partner.document.requested",
            "partner_document",
            item.id,
            None,
            {"partner_id": partner.id, "document_type": item.document_type},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def upload_document(
    db: AsyncSession,
    org: str,
    partner_id: str,
    document_id: str,
    upload: UploadFile,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    item = await _entity(db, PartnerDocument, org, document_id, lock=True)
    if item.channel_partner_id != partner.id or item.status not in (
        DocumentStatus.PENDING,
        DocumentStatus.REJECTED,
    ):
        raise _error("DOCUMENT_NOT_UPLOADABLE", "Document is not awaiting an upload")
    prepared = await _prepare_file(upload)
    key = f"pd/{org}/{item.id}/{uuid.uuid4().hex[:16]}.private"
    storage = get_storage()
    try:
        await storage.save(key=key, source=prepared.path)
        old_key = item.storage_key
        item.storage_key = key
        item.file_name = prepared.file_name
        item.content_type = prepared.content_type
        item.size_bytes = prepared.size_bytes
        item.checksum_sha256 = prepared.checksum_sha256
        item.uploaded_by_user_id = context.actor_user_id
        item.uploaded_at = _now()
        item.status = DocumentStatus.UPLOADED
        item.rejection_reason = None
        item.review_notes = None
        db.add(
            _audit(
                org,
                context,
                "partner.document.uploaded",
                "partner_document",
                item.id,
                None,
                {
                    "file_name": item.file_name,
                    "content_type": item.content_type,
                    "size_bytes": item.size_bytes,
                },
            )
        )
        await db.commit()
        if old_key:
            await storage.delete(key=old_key)
    except Exception:
        await db.rollback()
        await storage.delete(key=key)
        raise
    finally:
        if await asyncio.to_thread(prepared.path.exists):
            await asyncio.to_thread(prepared.path.unlink)
    return await detail(db, org, partner.id)


async def decide_document(
    db: AsyncSession,
    org: str,
    partner_id: str,
    document_id: str,
    payload: PartnerDocumentDecision,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    item = await _entity(db, PartnerDocument, org, document_id, lock=True)
    if item.channel_partner_id != partner.id or item.status not in (
        DocumentStatus.UPLOADED,
        DocumentStatus.UNDER_REVIEW,
    ):
        raise _error("DOCUMENT_NOT_REVIEWABLE", "Uploaded document is required")
    if item.uploaded_by_user_id == context.actor_user_id:
        raise _error(
            "SELF_APPROVAL_NOT_ALLOWED", "Document uploader cannot verify the same document", 403
        )
    previous = item.status
    item.status = DocumentStatus(payload.status)
    item.reviewed_by_user_id = context.actor_user_id
    item.review_notes = payload.notes
    item.rejection_reason = payload.rejection_reason if payload.status == "REJECTED" else None
    item.reviewed_at = _now()
    db.add(
        _audit(
            org,
            context,
            "partner.document.reviewed",
            "partner_document",
            item.id,
            {"status": previous.value},
            {"status": item.status.value, "rejection_reason": item.rejection_reason},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def complete_document_verification(
    db: AsyncSession, org: str, partner_id: str, payload: LifecycleAction, context: MutationContext
) -> PartnerDetail:
    item = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    documents = list(
        await db.scalars(
            select(PartnerDocument)
            .where(
                PartnerDocument.organization_id == org,
                PartnerDocument.channel_partner_id == item.id,
            )
            .with_for_update()
        )
    )
    if (
        item.status != PartnerStatus.DOCUMENT_VERIFICATION
        or not documents
        or any(document.status != DocumentStatus.VERIFIED for document in documents)
    ):
        raise _error(
            "COMPLIANCE_NOT_VERIFIED", "Every requested compliance document must be verified"
        )
    item.status = PartnerStatus.AGREEMENT_PENDING
    item.documents_verified_at = _now()
    item.review_notes = payload.notes.strip()
    db.add(
        _audit(
            org,
            context,
            "partner.document_verification.completed",
            "channel_partner",
            item.id,
            {"status": PartnerStatus.DOCUMENT_VERIFICATION.value},
            {"status": item.status.value, "verified_documents": len(documents)},
        )
    )
    await db.commit()
    return await detail(db, org, item.id)


async def create_agreement(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerAgreementCreate,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    if partner.status != PartnerStatus.AGREEMENT_PENDING:
        raise _error("AGREEMENT_STAGE_CLOSED", "Partner must complete document verification first")
    item = PartnerAgreement(
        organization_id=org,
        channel_partner_id=partner.id,
        agreement_number=payload.agreement_number.strip().upper(),
        status=AgreementStatus.DRAFT,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        commission_percent=payload.commission_percent,
        terms_summary=payload.terms_summary,
    )
    db.add(item)
    try:
        await db.flush()
        db.add(
            _audit(
                org,
                context,
                "partner.agreement.created",
                "partner_agreement",
                item.id,
                None,
                {
                    "partner_id": partner.id,
                    "agreement_number": item.agreement_number,
                    "commission_percent": str(item.commission_percent),
                },
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("AGREEMENT_NUMBER_EXISTS", "Agreement number already exists") from exc
    return await detail(db, org, partner.id)


async def upload_signed_agreement(
    db: AsyncSession,
    org: str,
    partner_id: str,
    agreement_id: str,
    upload: UploadFile,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    item = await _entity(db, PartnerAgreement, org, agreement_id, lock=True)
    if (
        item.channel_partner_id != partner.id
        or partner.status != PartnerStatus.AGREEMENT_PENDING
        or item.status not in (AgreementStatus.DRAFT, AgreementStatus.ISSUED)
    ):
        raise _error("AGREEMENT_NOT_SIGNABLE", "Agreement is not awaiting a signed copy")
    prepared = await _prepare_file(upload)
    if prepared.content_type != "application/pdf":
        if await asyncio.to_thread(prepared.path.exists):
            await asyncio.to_thread(prepared.path.unlink)
        raise _error("AGREEMENT_PDF_REQUIRED", "Signed agreement must be a PDF", 415)
    key = f"pa/{org}/{item.id}/{uuid.uuid4().hex[:16]}.private"
    storage = get_storage()
    try:
        await storage.save(key=key, source=prepared.path)
        item.storage_key = key
        item.file_name = prepared.file_name
        item.status = AgreementStatus.SIGNED
        item.issued_at = item.issued_at or _now()
        item.signed_at = _now()
        item.verified_by_user_id = context.actor_user_id
        partner.agreement_completed_at = item.signed_at
        db.add(
            _audit(
                org,
                context,
                "partner.agreement.signed",
                "partner_agreement",
                item.id,
                {"status": AgreementStatus.DRAFT.value},
                {"status": item.status.value, "file_name": item.file_name},
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
    return await detail(db, org, partner.id)


async def create_commission_structure(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: CommissionStructureCreate,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    if payload.project_id:
        await _entity(db, Project, org, payload.project_id)
    scope = payload.project_id or "DEFAULT"
    active_key = f"{partner.id}:{scope}"
    existing = (
        await db.scalars(
            select(CommissionStructure)
            .where(
                CommissionStructure.organization_id == org,
                CommissionStructure.active_scope_key == active_key,
            )
            .with_for_update()
        )
    ).first()
    if existing:
        existing.is_active = False
        existing.active_scope_key = None
    item = CommissionStructure(
        organization_id=org,
        channel_partner_id=partner.id,
        project_id=payload.project_id,
        name=payload.name.strip(),
        rate_percent=payload.rate_percent,
        calculation_basis=payload.calculation_basis,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        is_active=True,
        active_scope_key=active_key,
    )
    db.add(item)
    await db.flush()
    if payload.project_id is None:
        partner.default_commission_percent = payload.rate_percent
    db.add(
        _audit(
            org,
            context,
            "partner.commission_structure.created",
            "commission_structure",
            item.id,
            {"replaced_structure_id": existing.id if existing else None},
            {
                "partner_id": partner.id,
                "project_id": item.project_id,
                "rate_percent": str(item.rate_percent),
                "effective_from": str(item.effective_from),
            },
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def submit_approval(
    db: AsyncSession, org: str, partner_id: str, payload: LifecycleAction, context: MutationContext
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    signed = await db.scalar(
        select(PartnerAgreement.id).where(
            PartnerAgreement.organization_id == org,
            PartnerAgreement.channel_partner_id == partner.id,
            PartnerAgreement.status == AgreementStatus.SIGNED,
            PartnerAgreement.effective_from <= date.today(),
            or_(
                PartnerAgreement.effective_until.is_(None),
                PartnerAgreement.effective_until >= date.today(),
            ),
        )
    )
    if partner.status != PartnerStatus.AGREEMENT_PENDING or not signed:
        raise _error("SIGNED_AGREEMENT_REQUIRED", "A current signed agreement is required")
    partner.status = PartnerStatus.APPROVAL_PENDING
    partner.approval_requested_at = _now()
    partner.review_notes = payload.notes.strip()
    db.add(
        _audit(
            org,
            context,
            "partner.approval.requested",
            "channel_partner",
            partner.id,
            {"status": PartnerStatus.AGREEMENT_PENDING.value},
            {"status": partner.status.value, "notes": partner.review_notes},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def decide_approval(
    db: AsyncSession,
    org: str,
    partner_id: str,
    status: str,
    payload: LifecycleAction,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    if partner.status != PartnerStatus.APPROVAL_PENDING:
        raise _error("INVALID_PARTNER_TRANSITION", "Partner is not awaiting approval")
    if partner.applied_by_user_id == context.actor_user_id:
        raise _error(
            "SELF_APPROVAL_NOT_ALLOWED", "Application creator cannot approve the partner", 403
        )
    partner.approved_by_user_id = context.actor_user_id
    partner.review_notes = payload.notes.strip()
    if status == "APPROVED":
        partner.status = PartnerStatus.APPROVED
        partner.approved_at = _now()
    else:
        partner.status = PartnerStatus.REJECTED
        partner.rejection_reason = payload.notes.strip()
    db.add(
        _audit(
            org,
            context,
            "partner.approval.decided",
            "channel_partner",
            partner.id,
            {"status": PartnerStatus.APPROVAL_PENDING.value},
            {"status": partner.status.value, "notes": partner.review_notes},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def activate(
    db: AsyncSession, org: str, partner_id: str, payload: LifecycleAction, context: MutationContext
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    structure = await db.scalar(
        select(CommissionStructure.id).where(
            CommissionStructure.organization_id == org,
            CommissionStructure.channel_partner_id == partner.id,
            CommissionStructure.is_active.is_(True),
            CommissionStructure.effective_from <= date.today(),
            or_(
                CommissionStructure.effective_until.is_(None),
                CommissionStructure.effective_until >= date.today(),
            ),
        )
    )
    if partner.status != PartnerStatus.APPROVED:
        raise _error("PARTNER_NOT_APPROVED", "Partner approval is required before activation")
    if not all(
        (
            partner.tax_identifier,
            partner.tax_registration_name,
            partner.bank_account_holder,
            partner.bank_name,
            partner.bank_ifsc,
            partner.bank_account_last4,
            partner.bank_account_reference,
        )
    ):
        raise _error(
            "COMPLIANCE_DETAILS_INCOMPLETE", "Tax and bank verification details are required"
        )
    if not structure:
        raise _error("COMMISSION_STRUCTURE_REQUIRED", "An active commission structure is required")
    partner.status = PartnerStatus.ACTIVE
    partner.activated_by_user_id = context.actor_user_id
    partner.activated_at = _now()
    partner.review_notes = payload.notes.strip()
    db.add(
        _audit(
            org,
            context,
            "partner.activated",
            "channel_partner",
            partner.id,
            {"status": PartnerStatus.APPROVED.value},
            {"status": partner.status.value, "notes": partner.review_notes},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def set_operational_status(
    db: AsyncSession,
    org: str,
    partner_id: str,
    status: PartnerStatus,
    payload: LifecycleAction,
    context: MutationContext,
) -> PartnerDetail:
    if status not in (PartnerStatus.ACTIVE, PartnerStatus.SUSPENDED, PartnerStatus.INACTIVE):
        raise _error("INVALID_OPERATIONAL_STATUS", "Unsupported partner status", 422)
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    if partner.status not in (
        PartnerStatus.ACTIVE,
        PartnerStatus.SUSPENDED,
        PartnerStatus.INACTIVE,
    ):
        raise _error(
            "PARTNER_NOT_ACTIVATED", "Only an activated partner can change operational status"
        )
    before = partner.status
    partner.status = status
    if status == PartnerStatus.ACTIVE:
        partner.activated_by_user_id = context.actor_user_id
        partner.activated_at = _now()
    db.add(
        _audit(
            org,
            context,
            "partner.operational_status.changed",
            "channel_partner",
            partner.id,
            {"status": before.value},
            {"status": status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def register_lead(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payload: PartnerLeadCreate,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    if partner.status != PartnerStatus.ACTIVE:
        raise _error("PARTNER_INACTIVE", "Only an active channel partner can register leads")
    email = _normalize_email(str(payload.email) if payload.email else None)
    phone = _normalize_phone(payload.phone)
    protection_matches: list[Any] = []
    if email:
        protection_matches.append(PartnerLead.active_email_key == email)
    if phone:
        protection_matches.append(PartnerLead.active_phone_key == phone)
    conflict = await db.scalar(
        select(PartnerLead.id)
        .where(
            PartnerLead.organization_id == org,
            PartnerLead.status == WorkflowStatus.APPROVED,
            PartnerLead.protected_until >= date.today(),
            or_(*protection_matches),
        )
        .with_for_update()
    )
    if conflict:
        raise _error("LEAD_PROTECTED", "This contact is protected for another partner")
    lead = Lead(
        organization_id=org,
        full_name=payload.full_name.strip(),
        email=email,
        phone=payload.phone,
        normalized_email=email,
        normalized_phone=phone,
        preferred_location=payload.preferred_location,
        requirements=payload.requirements,
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
        status=LeadStatus.NEW,
        score=0,
        metadata_json={"channel_partner_id": partner.id},
    )
    db.add(lead)
    await db.flush()
    protected_until = date.today().fromordinal(
        date.today().toordinal() + partner.lead_protection_days
    )
    item = PartnerLead(
        organization_id=org,
        channel_partner_id=partner.id,
        lead_id=lead.id,
        registered_by_user_id=context.actor_user_id,
        approved_by_user_id=context.actor_user_id,
        status=WorkflowStatus.APPROVED,
        registered_at=_now(),
        protected_until=protected_until,
        active_email_key=email,
        active_phone_key=phone,
        registration_notes=payload.registration_notes,
        decided_at=_now(),
    )
    db.add(item)
    try:
        await db.flush()
        db.add(
            _audit(
                org,
                context,
                "partner.lead.registered",
                "partner_lead",
                item.id,
                None,
                {
                    "partner_id": partner.id,
                    "lead_id": lead.id,
                    "protected_until": str(protected_until),
                },
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("LEAD_PROTECTED", "This contact was protected concurrently") from exc
    return await detail(db, org, partner.id)


async def decide_commission(
    db: AsyncSession,
    org: str,
    partner_id: str,
    commission_id: str,
    payload: CommissionDecision,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    item = await _entity(db, Commission, org, commission_id, lock=True)
    if (
        item.channel_partner_id != partner.id
        or item.status != CommissionStatus.ELIGIBLE
        or item.commission_payout_id
    ):
        raise _error("COMMISSION_NOT_APPROVABLE", "Commission is not eligible for approval")
    before = item.status
    item.status = (
        CommissionStatus.APPROVED if payload.status == "APPROVED" else CommissionStatus.REVERSED
    )
    item.approved_by_user_id = (
        context.actor_user_id if item.status == CommissionStatus.APPROVED else None
    )
    db.add(
        _audit(
            org,
            context,
            "partner.commission.decided",
            "commission",
            item.id,
            {"status": before.value},
            {"status": item.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def request_payout(
    db: AsyncSession, org: str, partner_id: str, payload: PayoutCreate, context: MutationContext
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id, lock=True)
    if partner.status != PartnerStatus.ACTIVE:
        raise _error("PARTNER_INACTIVE", "Payouts require an active partner")
    commissions = list(
        await db.scalars(
            select(Commission)
            .where(
                Commission.organization_id == org,
                Commission.channel_partner_id == partner.id,
                Commission.id.in_(set(payload.commission_ids)),
            )
            .with_for_update()
        )
    )
    if len(commissions) != len(set(payload.commission_ids)) or any(
        item.status != CommissionStatus.APPROVED or item.commission_payout_id
        for item in commissions
    ):
        raise _error("COMMISSION_NOT_PAYABLE", "Every commission must be approved and unallocated")
    currencies = {item.currency for item in commissions}
    if len(currencies) != 1:
        raise _error("PAYOUT_CURRENCY_MISMATCH", "A payout can contain only one currency")
    item = CommissionPayout(
        organization_id=org,
        channel_partner_id=partner.id,
        requested_by_user_id=context.actor_user_id,
        payout_number=payload.payout_number.strip().upper(),
        status=PaymentStatus.PENDING,
        amount=_money(sum((entry.amount for entry in commissions), ZERO)),
        currency=currencies.pop(),
        notes=payload.notes,
        requested_at=_now(),
    )
    db.add(item)
    try:
        await db.flush()
        for commission in commissions:
            commission.commission_payout_id = item.id
        db.add(
            _audit(
                org,
                context,
                "partner.payout.requested",
                "commission_payout",
                item.id,
                None,
                {
                    "partner_id": partner.id,
                    "amount": str(item.amount),
                    "commission_ids": payload.commission_ids,
                },
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(
            "PAYOUT_CONFLICT", "Payout number or commission allocation already exists"
        ) from exc
    return await detail(db, org, partner.id)


async def decide_payout(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payout_id: str,
    payload: CommissionDecision,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    item = await _entity(db, CommissionPayout, org, payout_id, lock=True)
    if item.channel_partner_id != partner.id or item.status != PaymentStatus.PENDING:
        raise _error("PAYOUT_FINALIZED", "Payout decision is already recorded")
    if item.requested_by_user_id == context.actor_user_id:
        raise _error("SELF_APPROVAL_NOT_ALLOWED", "Payout requester cannot approve it", 403)
    item.approved_by_user_id = context.actor_user_id
    item.decision_notes = payload.notes
    if payload.status == "APPROVED":
        item.status = PaymentStatus.PROCESSING
        item.approved_at = _now()
    else:
        item.status = PaymentStatus.FAILED
        item.rejected_at = _now()
        commissions = list(
            await db.scalars(
                select(Commission)
                .where(
                    Commission.organization_id == org, Commission.commission_payout_id == item.id
                )
                .with_for_update()
            )
        )
        for commission in commissions:
            commission.commission_payout_id = None
    db.add(
        _audit(
            org,
            context,
            "partner.payout.decided",
            "commission_payout",
            item.id,
            {"status": PaymentStatus.PENDING.value},
            {"status": item.status.value, "notes": payload.notes},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def process_payout(
    db: AsyncSession,
    org: str,
    partner_id: str,
    payout_id: str,
    payload: PayoutProcess,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    item = await _entity(db, CommissionPayout, org, payout_id, lock=True)
    if item.channel_partner_id != partner.id or item.status != PaymentStatus.PROCESSING:
        raise _error("PAYOUT_NOT_APPROVED", "Payout must be approved before processing")
    commissions = list(
        await db.scalars(
            select(Commission)
            .where(Commission.organization_id == org, Commission.commission_payout_id == item.id)
            .with_for_update()
        )
    )
    if _money(sum((entry.amount for entry in commissions), ZERO)) != item.amount:
        raise _error("PAYOUT_AMOUNT_CHANGED", "Commission total changed after approval")
    item.status = PaymentStatus.COMPLETED
    item.reference_number = payload.reference_number.strip()
    item.paid_at = _now()
    for commission in commissions:
        commission.status = CommissionStatus.PAID
    db.add(
        _audit(
            org,
            context,
            "partner.payout.processed",
            "commission_payout",
            item.id,
            {"status": PaymentStatus.PROCESSING.value},
            {
                "status": item.status.value,
                "reference_number": item.reference_number,
                "amount": str(item.amount),
            },
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def create_dispute(
    db: AsyncSession, org: str, partner_id: str, payload: DisputeCreate, context: MutationContext
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    relations: tuple[tuple[type[Any], str | None], ...] = (
        (PartnerLead, payload.partner_lead_id),
        (Booking, payload.booking_id),
        (Commission, payload.commission_id),
        (CommissionPayout, payload.commission_payout_id),
    )
    for model, entity_id in relations:
        if entity_id:
            related = await _entity(db, model, org, entity_id)
            if getattr(related, "channel_partner_id", partner.id) != partner.id:
                raise _error(
                    "DISPUTE_SCOPE_MISMATCH", "Related record belongs to another partner", 422
                )
    now = _now()
    item = PartnerDispute(
        organization_id=org,
        channel_partner_id=partner.id,
        partner_lead_id=payload.partner_lead_id,
        booking_id=payload.booking_id,
        commission_id=payload.commission_id,
        commission_payout_id=payload.commission_payout_id,
        raised_by_user_id=context.actor_user_id,
        dispute_number=f"DSP-{now:%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        category=payload.category.strip().upper().replace(" ", "_"),
        status=WorkflowStatus.REQUESTED,
        description=payload.description.strip(),
        raised_at=now,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "partner.dispute.created",
            "partner_dispute",
            item.id,
            None,
            {
                "partner_id": partner.id,
                "dispute_number": item.dispute_number,
                "category": item.category,
            },
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def assign_dispute(
    db: AsyncSession,
    org: str,
    partner_id: str,
    dispute_id: str,
    payload: DisputeAssign,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    user = await _entity(db, User, org, payload.assigned_to_user_id)
    if not user.is_active:
        raise _error("ASSIGNEE_INACTIVE", "Dispute assignee must be active", 422)
    item = await _entity(db, PartnerDispute, org, dispute_id, lock=True)
    if item.channel_partner_id != partner.id or item.status != WorkflowStatus.REQUESTED:
        raise _error("DISPUTE_NOT_ASSIGNABLE", "Dispute is not awaiting assignment")
    item.assigned_to_user_id = user.id
    item.assigned_at = _now()
    item.status = WorkflowStatus.UNDER_REVIEW
    db.add(
        _audit(
            org,
            context,
            "partner.dispute.assigned",
            "partner_dispute",
            item.id,
            {"status": WorkflowStatus.REQUESTED.value},
            {"status": item.status.value, "assigned_to_user_id": user.id},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def decide_dispute(
    db: AsyncSession,
    org: str,
    partner_id: str,
    dispute_id: str,
    payload: DisputeDecision,
    context: MutationContext,
) -> PartnerDetail:
    partner = await _entity(db, ChannelPartner, org, partner_id)
    item = await _entity(db, PartnerDispute, org, dispute_id, lock=True)
    if item.channel_partner_id != partner.id or item.status != WorkflowStatus.UNDER_REVIEW:
        raise _error("DISPUTE_NOT_REVIEWED", "Dispute must be under review")
    if item.assigned_to_user_id and item.assigned_to_user_id != context.actor_user_id:
        raise _error(
            "ASSIGNEE_MISMATCH", "Only the assigned reviewer can resolve this dispute", 403
        )
    item.status = WorkflowStatus(payload.status)
    item.resolution = payload.resolution.strip()
    item.resolved_by_user_id = context.actor_user_id
    item.resolved_at = _now()
    db.add(
        _audit(
            org,
            context,
            "partner.dispute.resolved",
            "partner_dispute",
            item.id,
            {"status": WorkflowStatus.UNDER_REVIEW.value},
            {"status": item.status.value, "resolution": item.resolution},
        )
    )
    await db.commit()
    return await detail(db, org, partner.id)


async def prepare_document_download(
    db: AsyncSession, org: str, document_id: str
) -> tuple[StoredFile, str, str]:
    item = await _entity(db, PartnerDocument, org, document_id)
    if not item.storage_key or not item.file_name or not item.content_type:
        raise _error("DOCUMENT_NOT_UPLOADED", "Partner document is unavailable", 404)
    path = await get_storage().path_for_read(key=item.storage_key)
    return path, item.file_name, item.content_type


async def prepare_agreement_download(
    db: AsyncSession, org: str, agreement_id: str
) -> tuple[StoredFile, str]:
    item = await _entity(db, PartnerAgreement, org, agreement_id)
    if not item.storage_key or not item.file_name:
        raise _error("AGREEMENT_NOT_UPLOADED", "Signed agreement is unavailable", 404)
    path = await get_storage().path_for_read(key=item.storage_key)
    return path, item.file_name


async def accrue_booking_commission(
    db: AsyncSession, org: str, booking: Booking, context: MutationContext
) -> Commission | None:
    if not booking.channel_partner_id or booking.agreed_price is None:
        return None
    unit = await _entity(db, Unit, org, booking.unit_id)
    today = date.today()
    structures = list(
        await db.scalars(
            select(CommissionStructure)
            .where(
                CommissionStructure.organization_id == org,
                CommissionStructure.channel_partner_id == booking.channel_partner_id,
                CommissionStructure.is_active.is_(True),
                CommissionStructure.effective_from <= today,
                or_(
                    CommissionStructure.effective_until.is_(None),
                    CommissionStructure.effective_until >= today,
                ),
                or_(
                    CommissionStructure.project_id == unit.project_id,
                    CommissionStructure.project_id.is_(None),
                ),
            )
            .order_by(
                CommissionStructure.project_id.is_(None), CommissionStructure.effective_from.desc()
            )
        )
    )
    if not structures:
        raise _error(
            "COMMISSION_STRUCTURE_MISSING",
            "Active partner booking has no applicable commission structure",
        )
    structure = structures[0]
    item = Commission(
        organization_id=org,
        channel_partner_id=booking.channel_partner_id,
        booking_id=booking.id,
        commission_structure_id=structure.id,
        status=CommissionStatus.ELIGIBLE,
        rate_percent=structure.rate_percent,
        amount=_money(booking.agreed_price * structure.rate_percent / Decimal("100")),
        currency=booking.currency,
    )
    db.add(item)
    await db.flush()
    db.add(
        _audit(
            org,
            context,
            "partner.commission.accrued",
            "commission",
            item.id,
            None,
            {
                "booking_id": booking.id,
                "structure_id": structure.id,
                "rate_percent": str(item.rate_percent),
                "amount": str(item.amount),
            },
        )
    )
    return item
