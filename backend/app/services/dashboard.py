from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_is_granted
from app.core.errors import AppError
from app.models.entities import (
    Booking,
    ChannelPartner,
    Commission,
    Customer,
    Installment,
    Lead,
    LeadSource,
    PartnerLead,
    Payment,
    Project,
    ServiceRequest,
    Unit,
)
from app.models.enums import (
    BookingStatus,
    CommissionStatus,
    CustomerStatus,
    InstallmentStatus,
    LeadStatus,
    PartnerStatus,
    PaymentStatus,
    TicketStatus,
    UnitStatus,
)
from app.schemas.dashboard import (
    DashboardCatalog,
    DashboardCatalogItem,
    DashboardChart,
    DashboardChartPoint,
    DashboardKind,
    DashboardMetric,
    DashboardView,
    MetricFormat,
)

ZERO = Decimal("0")
ACTIVE_LEADS = (
    LeadStatus.NEW,
    LeadStatus.ASSIGNED,
    LeadStatus.ATTEMPTED,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
)
OPEN_TICKETS = (
    TicketStatus.OPEN,
    TicketStatus.ASSIGNED,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_FOR_CUSTOMER,
)

CATALOG = {
    DashboardKind.EXECUTIVE: (
        "Executive",
        "Organization-wide sales, collections, pipeline, and inventory position.",
        (
            "leads.view",
            "bookings.view",
            "inventory.view",
            "collections.view",
            "payments.view",
        ),
    ),
    DashboardKind.SALES: (
        "Sales",
        "Lead conversion, confirmed bookings, and sales pipeline movement.",
        ("leads.view", "bookings.view"),
    ),
    DashboardKind.MARKETING: (
        "Marketing",
        "Lead acquisition and source conversion based on registered lead records.",
        ("leads.view",),
    ),
    DashboardKind.INVENTORY: (
        "Inventory",
        "Live unit availability and project-level inventory composition.",
        ("inventory.view",),
    ),
    DashboardKind.COLLECTIONS: (
        "Collections",
        "Installment receivables, overdue balances, and verified payment collections.",
        ("collections.view", "payments.view"),
    ),
    DashboardKind.PARTNER: (
        "Partner",
        "Channel partner activation, attributed bookings, leads, and commissions.",
        ("partners.view", "commissions.view"),
    ),
    DashboardKind.CUSTOMER: (
        "Customer",
        "Customer growth, confirmed booking value, and open service workload.",
        ("customers.view", "bookings.view", "service_requests.view"),
    ),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _allowed(permissions: Iterable[str], kind: DashboardKind) -> bool:
    permission_set = set(permissions)
    return all(permission_is_granted(permission_set, required) for required in CATALOG[kind][2])


def available_catalog(permissions: frozenset[str]) -> DashboardCatalog:
    available = [kind for kind in DashboardKind if _allowed(permissions, kind)]
    default = _default_dashboard(permissions, available)
    return DashboardCatalog(
        items=[
            DashboardCatalogItem(
                kind=kind,
                label=CATALOG[kind][0],
                description=CATALOG[kind][1],
            )
            for kind in available
        ],
        default_dashboard=default,
    )


def _default_dashboard(
    permissions: frozenset[str], available: list[DashboardKind]
) -> DashboardKind | None:
    if not available:
        return None
    if DashboardKind.EXECUTIVE in available:
        return DashboardKind.EXECUTIVE
    preferred: list[DashboardKind] = []
    if permission_is_granted(permissions, "partners.create"):
        preferred.append(DashboardKind.PARTNER)
    if permission_is_granted(permissions, "collections.create") and not permission_is_granted(
        permissions, "leads.create"
    ):
        preferred.append(DashboardKind.COLLECTIONS)
    if permission_is_granted(permissions, "service_requests.assign"):
        preferred.append(DashboardKind.CUSTOMER)
    preferred.extend(
        (
            DashboardKind.SALES,
            DashboardKind.MARKETING,
            DashboardKind.INVENTORY,
            DashboardKind.COLLECTIONS,
            DashboardKind.PARTNER,
            DashboardKind.CUSTOMER,
        )
    )
    return next((kind for kind in preferred if kind in available), available[0])


async def _count(db: AsyncSession, organization_id: str, model: type[Any], *conditions: Any) -> int:
    statement = (
        select(func.count())
        .select_from(model)
        .where(model.organization_id == organization_id, *conditions)
    )
    return int(await db.scalar(statement) or 0)


async def _sum(
    db: AsyncSession,
    organization_id: str,
    model: type[Any],
    column: Any,
    *conditions: Any,
) -> Decimal:
    value = await db.scalar(
        select(func.coalesce(func.sum(column), 0))
        .select_from(model)
        .where(model.organization_id == organization_id, *conditions)
    )
    return Decimal(str(value or 0))


def _percentage(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return ZERO
    return (Decimal(numerator) * Decimal("100") / Decimal(denominator)).quantize(Decimal("0.01"))


def _metric(
    key: str,
    label: str,
    value: int | Decimal,
    format_: MetricFormat,
    detail: str,
) -> DashboardMetric:
    return DashboardMetric(
        key=key,
        label=label,
        value=Decimal(value),
        format=format_,
        detail=detail,
    )


async def _group_points(
    db: AsyncSession,
    organization_id: str,
    model: type[Any],
    column: Any,
) -> list[DashboardChartPoint]:
    rows = (
        await db.execute(
            select(column, func.count())
            .select_from(model)
            .where(model.organization_id == organization_id)
            .group_by(column)
            .order_by(column)
        )
    ).all()
    return [
        DashboardChartPoint(
            label=getattr(group, "value", str(group)).replace("_", " ").title(),
            value=Decimal(count),
        )
        for group, count in rows
    ]


def _month_starts(month_count: int = 6) -> list[date]:
    current = date.today().replace(day=1)
    starts: list[date] = []
    for offset in range(month_count - 1, -1, -1):
        absolute_month = current.year * 12 + current.month - 1 - offset
        starts.append(date(absolute_month // 12, absolute_month % 12 + 1, 1))
    return starts


async def _monthly_points(
    db: AsyncSession,
    organization_id: str,
    model: type[Any],
    date_column: Any,
    value_column: Any | None = None,
    *conditions: Any,
) -> list[DashboardChartPoint]:
    starts = _month_starts()
    first = datetime.combine(starts[0], datetime.min.time())
    columns = [date_column]
    if value_column is not None:
        columns.append(value_column)
    rows = (
        await db.execute(
            select(*columns)
            .select_from(model)
            .where(
                model.organization_id == organization_id,
                date_column.is_not(None),
                date_column >= first,
                *conditions,
            )
        )
    ).all()
    values = {(start.year, start.month): ZERO for start in starts}
    for row in rows:
        occurred = row[0]
        if not isinstance(occurred, (date, datetime)):
            continue
        amount = Decimal("1") if value_column is None else Decimal(str(row[1] or 0))
        key = (occurred.year, occurred.month)
        if key in values:
            values[key] += amount
    return [
        DashboardChartPoint(label=start.strftime("%b %Y"), value=values[(start.year, start.month)])
        for start in starts
    ]


def _chart(
    key: str,
    title: str,
    description: str,
    format_: MetricFormat,
    points: list[DashboardChartPoint],
    empty_message: str,
) -> DashboardChart:
    return DashboardChart(
        key=key,
        title=title,
        description=description,
        format=format_,
        points=points,
        empty_message=empty_message,
    )


async def _receivables(db: AsyncSession, organization_id: str) -> tuple[Decimal, Decimal]:
    outstanding_expression = Installment.amount - Installment.paid_amount
    valid = Installment.status != InstallmentStatus.WAIVED
    outstanding = await _sum(
        db,
        organization_id,
        Installment,
        outstanding_expression,
        valid,
        outstanding_expression > 0,
    )
    overdue = await _sum(
        db,
        organization_id,
        Installment,
        outstanding_expression,
        valid,
        outstanding_expression > 0,
        Installment.due_date < date.today(),
    )
    return outstanding, overdue


async def executive(db: AsyncSession, organization_id: str, currency: str | None) -> DashboardView:
    confirmed = await _count(
        db, organization_id, Booking, Booking.status == BookingStatus.CONFIRMED
    )
    sales_value = await _sum(
        db,
        organization_id,
        Booking,
        Booking.agreed_price,
        Booking.status == BookingStatus.CONFIRMED,
    )
    collected = await _sum(
        db,
        organization_id,
        Payment,
        Payment.amount,
        Payment.status == PaymentStatus.COMPLETED,
    )
    outstanding, _ = await _receivables(db, organization_id)
    active_leads = await _count(db, organization_id, Lead, Lead.status.in_(ACTIVE_LEADS))
    sales_trend = await _monthly_points(
        db,
        organization_id,
        Booking,
        Booking.booked_at,
        Booking.agreed_price,
        Booking.status == BookingStatus.CONFIRMED,
    )
    booking_status = await _group_points(db, organization_id, Booking, Booking.status)
    return DashboardView(
        kind=DashboardKind.EXECUTIVE,
        title="Executive overview",
        description=CATALOG[DashboardKind.EXECUTIVE][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "active_leads",
                "Active leads",
                active_leads,
                MetricFormat.NUMBER,
                "Leads in non-terminal pipeline statuses.",
            ),
            _metric(
                "confirmed_bookings",
                "Confirmed bookings",
                confirmed,
                MetricFormat.NUMBER,
                "Bookings whose current status is CONFIRMED.",
            ),
            _metric(
                "confirmed_sales_value",
                "Confirmed sales value",
                sales_value,
                MetricFormat.CURRENCY,
                "Agreed price summed only for confirmed bookings.",
            ),
            _metric(
                "collections_received",
                "Collections received",
                collected,
                MetricFormat.CURRENCY,
                "Payments whose current status is COMPLETED.",
            ),
            _metric(
                "outstanding",
                "Outstanding",
                outstanding,
                MetricFormat.CURRENCY,
                "Installment amount less paid amount, excluding waived installments.",
            ),
        ],
        charts=[
            _chart(
                "sales_trend",
                "Confirmed sales trend",
                "Agreed value of bookings confirmed in each of the last six months.",
                MetricFormat.CURRENCY,
                sales_trend,
                "No confirmed booking value exists for this period.",
            ),
            _chart(
                "booking_status",
                "Booking status mix",
                "Current booking records grouped by their explicit workflow status.",
                MetricFormat.NUMBER,
                booking_status,
                "No booking records exist yet.",
            ),
        ],
    )


async def sales(db: AsyncSession, organization_id: str, currency: str | None) -> DashboardView:
    total = await _count(db, organization_id, Lead)
    active = await _count(db, organization_id, Lead, Lead.status.in_(ACTIVE_LEADS))
    qualified = await _count(db, organization_id, Lead, Lead.status == LeadStatus.QUALIFIED)
    converted = await _count(db, organization_id, Lead, Lead.status == LeadStatus.CONVERTED)
    confirmed = await _count(
        db, organization_id, Booking, Booking.status == BookingStatus.CONFIRMED
    )
    booked_value = await _sum(
        db,
        organization_id,
        Booking,
        Booking.agreed_price,
        Booking.status == BookingStatus.CONFIRMED,
    )
    pipeline = await _group_points(db, organization_id, Lead, Lead.status)
    bookings = await _monthly_points(
        db,
        organization_id,
        Booking,
        Booking.booked_at,
        None,
        Booking.status == BookingStatus.CONFIRMED,
    )
    return DashboardView(
        kind=DashboardKind.SALES,
        title="Sales performance",
        description=CATALOG[DashboardKind.SALES][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "total_leads",
                "Total leads",
                total,
                MetricFormat.NUMBER,
                "All lead records currently stored.",
            ),
            _metric(
                "active_leads",
                "Active pipeline",
                active,
                MetricFormat.NUMBER,
                "Leads in NEW through QUALIFIED statuses.",
            ),
            _metric(
                "qualified_leads",
                "Qualified leads",
                qualified,
                MetricFormat.NUMBER,
                "Leads currently marked QUALIFIED.",
            ),
            _metric(
                "conversion_rate",
                "Lead conversion",
                _percentage(converted, total),
                MetricFormat.PERCENT,
                "Converted leads divided by all lead records.",
            ),
            _metric(
                "confirmed_bookings",
                "Confirmed bookings",
                confirmed,
                MetricFormat.NUMBER,
                "Bookings currently marked CONFIRMED.",
            ),
            _metric(
                "booked_value",
                "Confirmed value",
                booked_value,
                MetricFormat.CURRENCY,
                "Agreed price of confirmed bookings only.",
            ),
        ],
        charts=[
            _chart(
                "lead_pipeline",
                "Lead pipeline",
                "Current leads grouped by status.",
                MetricFormat.NUMBER,
                pipeline,
                "No lead records exist yet.",
            ),
            _chart(
                "monthly_bookings",
                "Confirmed bookings",
                "Count of bookings confirmed in each of the last six months.",
                MetricFormat.NUMBER,
                bookings,
                "No bookings were confirmed in this period.",
            ),
        ],
    )


async def marketing(db: AsyncSession, organization_id: str, currency: str | None) -> DashboardView:
    total = await _count(db, organization_id, Lead)
    converted = await _count(db, organization_id, Lead, Lead.status == LeadStatus.CONVERTED)
    unassigned = await _count(db, organization_id, Lead, Lead.owner_user_id.is_(None))
    month_start = datetime.combine(date.today().replace(day=1), datetime.min.time())
    new_this_month = await _count(db, organization_id, Lead, Lead.created_at >= month_start)
    acquisition = await _monthly_points(db, organization_id, Lead, Lead.created_at)
    source_rows = (
        await db.execute(
            select(LeadSource.name, Lead.status)
            .select_from(Lead)
            .outerjoin(
                LeadSource,
                and_(
                    LeadSource.organization_id == Lead.organization_id,
                    LeadSource.id == Lead.source_id,
                ),
            )
            .where(Lead.organization_id == organization_id)
        )
    ).all()
    source_totals: dict[str, list[int]] = {}
    for source_name, status in source_rows:
        label = str(source_name) if source_name else "Unspecified"
        bucket = source_totals.setdefault(label, [0, 0])
        bucket[0] += 1
        if status == LeadStatus.CONVERTED:
            bucket[1] += 1
    source_points = [
        DashboardChartPoint(
            label=label,
            value=_percentage(values[1], values[0]),
            total=Decimal(values[0]),
        )
        for label, values in sorted(source_totals.items(), key=lambda item: (-item[1][0], item[0]))
    ]
    return DashboardView(
        kind=DashboardKind.MARKETING,
        title="Marketing acquisition",
        description=CATALOG[DashboardKind.MARKETING][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "total_leads",
                "Acquired leads",
                total,
                MetricFormat.NUMBER,
                "All lead records across every configured source.",
            ),
            _metric(
                "new_this_month",
                "Added this month",
                new_this_month,
                MetricFormat.NUMBER,
                "Leads created since the first day of the current month.",
            ),
            _metric(
                "converted",
                "Converted leads",
                converted,
                MetricFormat.NUMBER,
                "Lead records currently marked CONVERTED.",
            ),
            _metric(
                "conversion_rate",
                "Conversion rate",
                _percentage(converted, total),
                MetricFormat.PERCENT,
                "Converted leads divided by all acquired leads.",
            ),
            _metric(
                "unassigned",
                "Unassigned leads",
                unassigned,
                MetricFormat.NUMBER,
                "Lead records without an owner user.",
            ),
        ],
        charts=[
            _chart(
                "lead_acquisition",
                "Lead acquisition",
                "Lead records created in each of the last six months.",
                MetricFormat.NUMBER,
                acquisition,
                "No leads were created in this period.",
            ),
            _chart(
                "source_conversion",
                "Source conversion",
                "Conversion percentage by actual lead source; the small count is total "
                "leads from that source.",
                MetricFormat.PERCENT,
                source_points,
                "No source-linked lead data exists yet.",
            ),
        ],
    )


async def inventory(db: AsyncSession, organization_id: str, currency: str | None) -> DashboardView:
    total = await _count(db, organization_id, Unit)
    available = await _count(db, organization_id, Unit, Unit.status == UnitStatus.AVAILABLE)
    soft_hold = await _count(db, organization_id, Unit, Unit.status == UnitStatus.SOFT_HOLD)
    hard_hold = await _count(db, organization_id, Unit, Unit.status == UnitStatus.HARD_HOLD)
    committed = await _count(
        db,
        organization_id,
        Unit,
        Unit.status.in_((UnitStatus.BOOKED, UnitStatus.SOLD)),
    )
    available_value = await _sum(
        db,
        organization_id,
        Unit,
        Unit.base_price,
        Unit.status == UnitStatus.AVAILABLE,
    )
    status_points = await _group_points(db, organization_id, Unit, Unit.status)
    project_rows = (
        await db.execute(
            select(Project.name, Unit.status)
            .select_from(Project)
            .outerjoin(
                Unit,
                and_(
                    Unit.organization_id == Project.organization_id,
                    Unit.project_id == Project.id,
                ),
            )
            .where(Project.organization_id == organization_id)
            .order_by(Project.name)
        )
    ).all()
    project_counts: dict[str, list[int]] = {}
    for project_name, status in project_rows:
        values = project_counts.setdefault(str(project_name), [0, 0])
        if status is not None:
            values[1] += 1
            if status == UnitStatus.AVAILABLE:
                values[0] += 1
    project_points = [
        DashboardChartPoint(label=name, value=Decimal(values[0]), total=Decimal(values[1]))
        for name, values in project_counts.items()
    ]
    return DashboardView(
        kind=DashboardKind.INVENTORY,
        title="Inventory position",
        description=CATALOG[DashboardKind.INVENTORY][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "total_units",
                "Total units",
                total,
                MetricFormat.NUMBER,
                "Every unit record in the organization.",
            ),
            _metric(
                "available_units",
                "Available",
                available,
                MetricFormat.NUMBER,
                "Units whose live status is AVAILABLE.",
            ),
            _metric(
                "soft_hold",
                "Soft hold",
                soft_hold,
                MetricFormat.NUMBER,
                "Units whose live status is SOFT_HOLD.",
            ),
            _metric(
                "hard_hold",
                "Hard hold",
                hard_hold,
                MetricFormat.NUMBER,
                "Units whose live status is HARD_HOLD.",
            ),
            _metric(
                "booked_or_sold",
                "Booked or sold",
                committed,
                MetricFormat.NUMBER,
                "Units currently marked BOOKED or SOLD.",
            ),
            _metric(
                "available_base_value",
                "Available base value",
                available_value,
                MetricFormat.CURRENCY,
                "Configured base price summed for available units; null prices contribute zero.",
            ),
        ],
        charts=[
            _chart(
                "unit_status",
                "Unit status mix",
                "Current units grouped by explicit inventory status.",
                MetricFormat.NUMBER,
                status_points,
                "No unit records exist yet.",
            ),
            _chart(
                "project_availability",
                "Availability by project",
                "Available units by project; the small count is total units in that project.",
                MetricFormat.NUMBER,
                project_points,
                "No project inventory exists yet.",
            ),
        ],
    )


async def collections(
    db: AsyncSession, organization_id: str, currency: str | None
) -> DashboardView:
    receivable = await _sum(
        db,
        organization_id,
        Installment,
        Installment.amount,
        Installment.status != InstallmentStatus.WAIVED,
    )
    outstanding, overdue = await _receivables(db, organization_id)
    collected = await _sum(
        db,
        organization_id,
        Payment,
        Payment.amount,
        Payment.status == PaymentStatus.COMPLETED,
    )
    completed_payments = await _count(
        db, organization_id, Payment, Payment.status == PaymentStatus.COMPLETED
    )
    overdue_count = await _count(
        db,
        organization_id,
        Installment,
        Installment.status != InstallmentStatus.WAIVED,
        Installment.status != InstallmentStatus.PAID,
        Installment.paid_amount < Installment.amount,
        Installment.due_date < date.today(),
    )
    status_points = await _group_points(db, organization_id, Installment, Installment.status)
    payment_trend = await _monthly_points(
        db,
        organization_id,
        Payment,
        Payment.paid_at,
        Payment.amount,
        Payment.status == PaymentStatus.COMPLETED,
    )
    return DashboardView(
        kind=DashboardKind.COLLECTIONS,
        title="Collections control",
        description=CATALOG[DashboardKind.COLLECTIONS][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "scheduled_receivable",
                "Scheduled receivable",
                receivable,
                MetricFormat.CURRENCY,
                "Installment amount excluding waived installments.",
            ),
            _metric(
                "collected",
                "Completed payments",
                collected,
                MetricFormat.CURRENCY,
                "Amount from payment records currently marked COMPLETED.",
            ),
            _metric(
                "outstanding",
                "Outstanding",
                outstanding,
                MetricFormat.CURRENCY,
                "Installment amount less allocated paid amount, excluding waivers.",
            ),
            _metric(
                "overdue",
                "Overdue amount",
                overdue,
                MetricFormat.CURRENCY,
                "Outstanding installment balance with a due date before today.",
            ),
            _metric(
                "overdue_installments",
                "Overdue installments",
                overdue_count,
                MetricFormat.NUMBER,
                "Unpaid or partially paid installments past their due date.",
            ),
            _metric(
                "completed_payment_count",
                "Verified payment records",
                completed_payments,
                MetricFormat.NUMBER,
                "Count of payments currently marked COMPLETED.",
            ),
        ],
        charts=[
            _chart(
                "installment_status",
                "Installment status",
                "Installment records grouped by their explicit payment status.",
                MetricFormat.NUMBER,
                status_points,
                "No installment schedule exists yet.",
            ),
            _chart(
                "collection_trend",
                "Completed collections",
                "Completed payment amount by paid date over the last six months.",
                MetricFormat.CURRENCY,
                payment_trend,
                "No completed payments exist for this period.",
            ),
        ],
    )


async def partner(db: AsyncSession, organization_id: str, currency: str | None) -> DashboardView:
    active = await _count(
        db, organization_id, ChannelPartner, ChannelPartner.status == PartnerStatus.ACTIVE
    )
    registered_leads = await _count(db, organization_id, PartnerLead)
    attributed_bookings = await _count(
        db,
        organization_id,
        Booking,
        Booking.channel_partner_id.is_not(None),
        Booking.status == BookingStatus.CONFIRMED,
    )
    attributed_value = await _sum(
        db,
        organization_id,
        Booking,
        Booking.agreed_price,
        Booking.channel_partner_id.is_not(None),
        Booking.status == BookingStatus.CONFIRMED,
    )
    earned_commission = await _sum(
        db,
        organization_id,
        Commission,
        Commission.amount,
        Commission.status.in_(
            (CommissionStatus.ELIGIBLE, CommissionStatus.APPROVED, CommissionStatus.PAID)
        ),
    )
    pending_commission = await _sum(
        db,
        organization_id,
        Commission,
        Commission.amount,
        Commission.status.in_((CommissionStatus.ELIGIBLE, CommissionStatus.APPROVED)),
    )
    status_points = await _group_points(db, organization_id, ChannelPartner, ChannelPartner.status)
    booked_value = func.coalesce(
        func.sum(case((Booking.status == BookingStatus.CONFIRMED, Booking.agreed_price), else_=0)),
        0,
    )
    performance_rows = (
        await db.execute(
            select(ChannelPartner.name, booked_value)
            .select_from(ChannelPartner)
            .outerjoin(
                Booking,
                and_(
                    Booking.organization_id == ChannelPartner.organization_id,
                    Booking.channel_partner_id == ChannelPartner.id,
                ),
            )
            .where(ChannelPartner.organization_id == organization_id)
            .group_by(ChannelPartner.id, ChannelPartner.name)
            .order_by(booked_value.desc(), ChannelPartner.name)
            .limit(10)
        )
    ).all()
    performance = [
        DashboardChartPoint(label=str(name), value=Decimal(str(value or 0)))
        for name, value in performance_rows
    ]
    return DashboardView(
        kind=DashboardKind.PARTNER,
        title="Partner performance",
        description=CATALOG[DashboardKind.PARTNER][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "active_partners",
                "Active partners",
                active,
                MetricFormat.NUMBER,
                "Channel partners currently marked ACTIVE.",
            ),
            _metric(
                "registered_leads",
                "Registered leads",
                registered_leads,
                MetricFormat.NUMBER,
                "Lead registrations recorded through channel partners.",
            ),
            _metric(
                "confirmed_bookings",
                "Partner bookings",
                attributed_bookings,
                MetricFormat.NUMBER,
                "Confirmed bookings with a channel partner attribution.",
            ),
            _metric(
                "attributed_value",
                "Attributed value",
                attributed_value,
                MetricFormat.CURRENCY,
                "Agreed price of confirmed partner-attributed bookings.",
            ),
            _metric(
                "earned_commission",
                "Earned commission",
                earned_commission,
                MetricFormat.CURRENCY,
                "Eligible, approved, or paid commission records.",
            ),
            _metric(
                "pending_commission",
                "Pending payout",
                pending_commission,
                MetricFormat.CURRENCY,
                "Eligible or approved commissions not yet marked PAID.",
            ),
        ],
        charts=[
            _chart(
                "partner_status",
                "Partner lifecycle",
                "Channel partners grouped by current lifecycle status.",
                MetricFormat.NUMBER,
                status_points,
                "No channel partner records exist yet.",
            ),
            _chart(
                "partner_value",
                "Confirmed value by partner",
                "Agreed value from confirmed bookings attributed to each partner.",
                MetricFormat.CURRENCY,
                performance,
                "No partner-attributed confirmed bookings exist yet.",
            ),
        ],
    )


async def customer(db: AsyncSession, organization_id: str, currency: str | None) -> DashboardView:
    total = await _count(db, organization_id, Customer)
    active = await _count(db, organization_id, Customer, Customer.status == CustomerStatus.ACTIVE)
    prospects = await _count(
        db, organization_id, Customer, Customer.status == CustomerStatus.PROSPECT
    )
    confirmed_bookings = await _count(
        db, organization_id, Booking, Booking.status == BookingStatus.CONFIRMED
    )
    booked_value = await _sum(
        db,
        organization_id,
        Booking,
        Booking.agreed_price,
        Booking.status == BookingStatus.CONFIRMED,
    )
    open_tickets = await _count(
        db, organization_id, ServiceRequest, ServiceRequest.status.in_(OPEN_TICKETS)
    )
    status_points = await _group_points(db, organization_id, Customer, Customer.status)
    growth = await _monthly_points(db, organization_id, Customer, Customer.created_at)
    return DashboardView(
        kind=DashboardKind.CUSTOMER,
        title="Customer portfolio",
        description=CATALOG[DashboardKind.CUSTOMER][1],
        currency=currency,
        as_of=_now(),
        metrics=[
            _metric(
                "total_customers",
                "Total customers",
                total,
                MetricFormat.NUMBER,
                "All customer profile records in the organization.",
            ),
            _metric(
                "active_customers",
                "Active customers",
                active,
                MetricFormat.NUMBER,
                "Customer profiles currently marked ACTIVE.",
            ),
            _metric(
                "prospects",
                "Prospects",
                prospects,
                MetricFormat.NUMBER,
                "Customer profiles currently marked PROSPECT.",
            ),
            _metric(
                "confirmed_bookings",
                "Confirmed bookings",
                confirmed_bookings,
                MetricFormat.NUMBER,
                "Bookings currently marked CONFIRMED.",
            ),
            _metric(
                "confirmed_value",
                "Confirmed customer value",
                booked_value,
                MetricFormat.CURRENCY,
                "Agreed price summed only for confirmed bookings.",
            ),
            _metric(
                "open_service_requests",
                "Open service requests",
                open_tickets,
                MetricFormat.NUMBER,
                "Tickets in OPEN, ASSIGNED, IN PROGRESS, or WAITING FOR CUSTOMER.",
            ),
        ],
        charts=[
            _chart(
                "customer_status",
                "Customer status",
                "Customer profiles grouped by current status.",
                MetricFormat.NUMBER,
                status_points,
                "No customer profiles exist yet.",
            ),
            _chart(
                "customer_growth",
                "Customer growth",
                "Customer profiles created in each of the last six months.",
                MetricFormat.NUMBER,
                growth,
                "No customer profiles were created in this period.",
            ),
        ],
    )


BUILDERS = {
    DashboardKind.EXECUTIVE: executive,
    DashboardKind.SALES: sales,
    DashboardKind.MARKETING: marketing,
    DashboardKind.INVENTORY: inventory,
    DashboardKind.COLLECTIONS: collections,
    DashboardKind.PARTNER: partner,
    DashboardKind.CUSTOMER: customer,
}


async def dashboard_view(
    db: AsyncSession,
    organization_id: str,
    permissions: frozenset[str],
    kind: DashboardKind,
    currency: str | None,
) -> DashboardView:
    if not _allowed(permissions, kind):
        raise AppError(
            status_code=403,
            code="DASHBOARD_ACCESS_DENIED",
            message="Your role does not have access to the data required by this dashboard",
        )
    return await BUILDERS[kind](db, organization_id, currency)
