from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, status_enum, tenant_fk, tenant_unique
from app.models.enums import (
    EscalationStatus,
    NotificationChannel,
    NotificationStatus,
    ServicePriority,
    ServiceStatus,
    TicketStatus,
)


class ServiceRequestCategory(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_request_categories"
    __table_args__ = (
        tenant_unique(__tablename__),
        Index("uq_service_categories_code", "organization_id", "code", unique=True),
        Index("ix_service_categories_active", "organization_id", "is_active"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceSLAPolicy(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_sla_policies"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "category_id", "service_request_categories", ondelete="CASCADE"),
        Index(
            "uq_service_sla_category_priority",
            "organization_id",
            "category_id",
            "priority",
            unique=True,
        ),
        CheckConstraint("first_response_minutes > 0", name="sla_response_positive"),
        CheckConstraint("resolution_minutes > 0", name="sla_resolution_positive"),
        CheckConstraint("escalation_minutes > 0", name="sla_escalation_positive"),
        CheckConstraint(
            "first_response_minutes <= escalation_minutes "
            "AND escalation_minutes <= resolution_minutes",
            name="sla_deadline_order",
        ),
    )

    category_id: Mapped[str] = mapped_column(String(36), nullable=False)
    priority: Mapped[ServicePriority] = mapped_column(
        status_enum(ServicePriority, "service_sla_priority"), nullable=False
    )
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    escalation_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceRequest(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "customer_id", "customers"),
        tenant_fk(__tablename__, "tenant_id", "tenants"),
        tenant_fk(__tablename__, "project_id", "projects"),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "category_id", "service_request_categories"),
        tenant_fk(__tablename__, "sla_policy_id", "service_sla_policies"),
        tenant_fk(__tablename__, "opened_by_user_id", "users"),
        tenant_fk(__tablename__, "assigned_user_id", "users"),
        tenant_fk(__tablename__, "assigned_by_user_id", "users"),
        tenant_fk(__tablename__, "resolved_by_user_id", "users"),
        tenant_fk(__tablename__, "closed_by_user_id", "users"),
        CheckConstraint(
            "customer_id IS NOT NULL OR tenant_id IS NOT NULL OR opened_by_user_id IS NOT NULL",
            name="requester_required",
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
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sla_policy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    opened_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    closed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_number: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    priority: Mapped[ServicePriority] = mapped_column(
        status_enum(ServicePriority, "service_request_priority"),
        default=ServicePriority.MEDIUM,
        nullable=False,
    )
    status: Mapped[TicketStatus] = mapped_column(
        status_enum(TicketStatus, "service_request_status"),
        default=TicketStatus.OPEN,
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalation_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_customer_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_agent_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceRequestComment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_request_comments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "service_request_id", "service_requests", ondelete="CASCADE"),
        tenant_fk(__tablename__, "author_user_id", "users"),
        Index(
            "ix_service_comments_ticket_created",
            "organization_id",
            "service_request_id",
            "created_at",
        ),
    )

    service_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ServiceRequestAttachment(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_request_attachments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "service_request_id", "service_requests", ondelete="CASCADE"),
        tenant_fk(__tablename__, "comment_id", "service_request_comments", ondelete="CASCADE"),
        tenant_fk(__tablename__, "uploaded_by_user_id", "users"),
        Index(
            "ix_service_attachments_ticket",
            "organization_id",
            "service_request_id",
            "created_at",
        ),
    )

    service_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    comment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ServiceRequestEscalation(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_request_escalations"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "service_request_id", "service_requests", ondelete="CASCADE"),
        tenant_fk(__tablename__, "escalated_by_user_id", "users"),
        tenant_fk(__tablename__, "from_user_id", "users"),
        tenant_fk(__tablename__, "to_user_id", "users"),
        tenant_fk(__tablename__, "acknowledged_by_user_id", "users"),
        Index(
            "ix_service_escalations_ticket_status",
            "organization_id",
            "service_request_id",
            "status",
        ),
    )

    service_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    escalated_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    to_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    acknowledged_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[EscalationStatus] = mapped_column(
        status_enum(EscalationStatus, "service_escalation_status"),
        default=EscalationStatus.OPEN,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    escalated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceRequestFeedback(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_request_feedback"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "service_request_id", "service_requests", ondelete="CASCADE"),
        tenant_fk(__tablename__, "submitted_by_user_id", "users"),
        Index(
            "uq_service_feedback_ticket",
            "organization_id",
            "service_request_id",
            unique=True,
        ),
        CheckConstraint("rating >= 1 AND rating <= 5", name="feedback_rating_range"),
    )

    service_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    submitted_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Maintenance(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "unit_id", "units"),
        tenant_fk(__tablename__, "rental_property_id", "rental_properties"),
        tenant_fk(__tablename__, "reported_by_user_id", "users"),
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
            "unit_id IS NOT NULL OR rental_property_id IS NOT NULL",
            name="maintenance_property_required",
        ),
        CheckConstraint(
            "(cost IS NULL AND currency IS NULL) OR (cost IS NOT NULL AND currency IS NOT NULL)",
            name="cost_currency_pair",
        ),
        Index("ix_maintenance_tenant_unit_status", "organization_id", "unit_id", "status"),
    )

    unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rental_property_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reported_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
        Index(
            "ix_notifications_tenant_user_unread",
            "organization_id",
            "recipient_user_id",
            "read_at",
            "created_at",
        ),
        Index(
            "uq_notifications_tenant_delivery_dedupe",
            "organization_id",
            "recipient_user_id",
            "channel",
            "deduplication_key",
            unique=True,
        ),
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
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    deduplication_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        Index("ix_audit_tenant_action_created", "organization_id", "action", "created_at"),
        Index("ix_audit_tenant_actor_created", "organization_id", "actor_user_id", "created_at"),
    )

    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    device_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(AuditLog, "before_update")
def _prevent_audit_update(*_: object) -> None:
    raise ValueError("Audit records are append-only and cannot be updated")


@event.listens_for(AuditLog, "before_delete")
def _prevent_audit_delete(*_: object) -> None:
    raise ValueError("Audit records are append-only and cannot be deleted")
