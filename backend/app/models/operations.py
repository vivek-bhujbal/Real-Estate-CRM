from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, status_enum, tenant_fk, tenant_unique
from app.models.enums import NotificationChannel, NotificationStatus, ServicePriority, ServiceStatus


class ServiceRequest(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "project_id", "projects"),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "assigned_user_id", "users"),
        CheckConstraint(
            "customer_id IS NOT NULL OR tenant_id IS NOT NULL", name="requester_required"
        ),
        Index(
            "ix_service_requests_tenant_number", "organization_id", "request_number", unique=True
        ),
        Index(
            "ix_service_requests_tenant_status_priority", "organization_id", "status", "priority"
        ),
        Index(
            "ix_service_requests_tenant_assignee", "organization_id", "assigned_user_id", "status"
        ),
    )

    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_number: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    priority: Mapped[ServicePriority] = mapped_column(
        status_enum(ServicePriority, "service_request_priority"),
        default=ServicePriority.MEDIUM,
        nullable=False,
    )
    status: Mapped[ServiceStatus] = mapped_column(
        status_enum(ServiceStatus, "service_request_status"),
        default=ServiceStatus.OPEN,
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Maintenance(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "lease_id", "leases"),
        tenant_fk(
            __tablename__,
            "service_request_id",
            "service_requests",
            name="fk_maintenance_service_request_tenant",
        ),
        tenant_fk(__tablename__, "assigned_user_id", "users"),
        CheckConstraint("cost IS NULL OR cost >= 0", name="cost_nonnegative"),
        CheckConstraint(
            "(cost IS NULL AND currency IS NULL) OR (cost IS NOT NULL AND currency IS NOT NULL)",
            name="cost_currency_pair",
        ),
        Index("ix_maintenance_tenant_unit_status", "organization_id", "unit_id", "status"),
    )

    unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    service_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ServiceStatus] = mapped_column(
        status_enum(ServiceStatus, "maintenance_status"),
        default=ServiceStatus.OPEN,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)


class Notification(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "recipient_user_id", "users", ondelete="CASCADE"),
        tenant_fk(__tablename__, "customer_id", "customers", ondelete="CASCADE"),
        tenant_fk(__tablename__, "tenant_id", "tenants", ondelete="CASCADE"),
        CheckConstraint(
            "recipient_user_id IS NOT NULL OR customer_id IS NOT NULL OR tenant_id IS NOT NULL",
            name="recipient_required",
        ),
        Index(
            "ix_notifications_tenant_user_status", "organization_id", "recipient_user_id", "status"
        ),
        Index("ix_notifications_tenant_created", "organization_id", "created_at"),
    )

    recipient_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        status_enum(NotificationChannel, "notification_channel"), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        status_enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.QUEUED,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AuditLog(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "actor_user_id", "users"),
        Index("ix_audit_tenant_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_audit_tenant_created", "organization_id", "created_at"),
    )

    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
