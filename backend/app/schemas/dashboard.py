from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class DashboardKind(StrEnum):
    EXECUTIVE = "EXECUTIVE"
    SALES = "SALES"
    MARKETING = "MARKETING"
    INVENTORY = "INVENTORY"
    COLLECTIONS = "COLLECTIONS"
    PARTNER = "PARTNER"
    CUSTOMER = "CUSTOMER"


class MetricFormat(StrEnum):
    NUMBER = "NUMBER"
    CURRENCY = "CURRENCY"
    PERCENT = "PERCENT"


class DashboardSummary(BaseModel):
    leads: int
    projects: int
    available_units: int
    bookings: int


class DashboardCatalogItem(BaseModel):
    kind: DashboardKind
    label: str
    description: str


class DashboardCatalog(BaseModel):
    items: list[DashboardCatalogItem]
    default_dashboard: DashboardKind | None


class DashboardMetric(BaseModel):
    key: str
    label: str
    value: Decimal
    format: MetricFormat
    detail: str


class DashboardChartPoint(BaseModel):
    label: str
    value: Decimal
    total: Decimal | None = None


class DashboardChart(BaseModel):
    key: str
    title: str
    description: str
    format: MetricFormat
    points: list[DashboardChartPoint]
    empty_message: str


class DashboardView(BaseModel):
    kind: DashboardKind
    title: str
    description: str
    currency: str | None
    as_of: datetime
    metrics: list[DashboardMetric]
    charts: list[DashboardChart]
