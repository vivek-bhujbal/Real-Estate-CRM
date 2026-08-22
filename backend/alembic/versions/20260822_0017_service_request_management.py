"""Add complete service request, SLA, conversation, and feedback workflows.

Revision ID: 20260822_0017
Revises: 20260822_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0017"
down_revision: str | None = "20260822_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned() -> tuple[sa.Column, ...]:
    return (
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _constraints(table: str) -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=f"fk_{table}_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.UniqueConstraint("organization_id", "id", name=f"uq_{table}_organization_id_id"),
    )


def _fk(table: str, column: str, remote: str, *, ondelete: str = "RESTRICT") -> None:
    op.create_foreign_key(
        f"fk_{table}_{column}_{remote}_tenant",
        table,
        remote,
        ["organization_id", column],
        ["organization_id", "id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        "service_request_categories",
        *_owned(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_constraints("service_request_categories"),
    )
    op.create_index(
        "uq_service_categories_code",
        "service_request_categories",
        ["organization_id", "code"],
        unique=True,
    )
    op.create_index(
        "ix_service_categories_active",
        "service_request_categories",
        ["organization_id", "is_active"],
    )

    op.create_table(
        "service_sla_policies",
        *_owned(),
        sa.Column("category_id", sa.String(36), nullable=False),
        sa.Column("priority", sa.String(6), nullable=False),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.Column("escalation_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_constraints("service_sla_policies"),
        sa.ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_request_categories.organization_id", "service_request_categories.id"],
            name="fk_service_sla_policies_category_id_service_request_categories_tenant",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW','MEDIUM','HIGH','URGENT')",
            name="service_sla_priority",
        ),
        sa.CheckConstraint("first_response_minutes > 0", name="sla_response_positive"),
        sa.CheckConstraint("resolution_minutes > 0", name="sla_resolution_positive"),
        sa.CheckConstraint("escalation_minutes > 0", name="sla_escalation_positive"),
        sa.CheckConstraint(
            "first_response_minutes <= escalation_minutes "
            "AND escalation_minutes <= resolution_minutes",
            name="sla_deadline_order",
        ),
    )
    op.create_index(
        "uq_service_sla_category_priority",
        "service_sla_policies",
        ["organization_id", "category_id", "priority"],
        unique=True,
    )

    for column in (
        sa.Column("category_id", sa.String(36)),
        sa.Column("sla_policy_id", sa.String(36)),
        sa.Column("opened_by_user_id", sa.String(36)),
        sa.Column("assigned_by_user_id", sa.String(36)),
        sa.Column("resolved_by_user_id", sa.String(36)),
        sa.Column("closed_by_user_id", sa.String(36)),
        sa.Column("response_due_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_due_at", sa.DateTime(timezone=True)),
        sa.Column("escalation_due_at", sa.DateTime(timezone=True)),
        sa.Column("first_responded_at", sa.DateTime(timezone=True)),
        sa.Column("last_customer_reply_at", sa.DateTime(timezone=True)),
        sa.Column("last_agent_reply_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_summary", sa.Text()),
        sa.Column("closure_notes", sa.Text()),
        sa.Column("is_escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        op.add_column("service_requests", column)
    for column, remote in (
        ("category_id", "service_request_categories"),
        ("sla_policy_id", "service_sla_policies"),
        ("opened_by_user_id", "users"),
        ("assigned_by_user_id", "users"),
        ("resolved_by_user_id", "users"),
        ("closed_by_user_id", "users"),
    ):
        _fk("service_requests", column, remote)
    op.alter_column("service_requests", "is_escalated", server_default=None)
    op.drop_constraint(
        op.f("ck_service_requests_requester_required"),
        "service_requests",
        type_="check",
    )
    op.create_check_constraint(
        "requester_required",
        "service_requests",
        "customer_id IS NOT NULL OR tenant_id IS NOT NULL OR opened_by_user_id IS NOT NULL",
    )
    op.drop_constraint(
        op.f("ck_service_requests_service_request_status"),
        "service_requests",
        type_="check",
    )
    op.execute("UPDATE service_requests SET status = 'CLOSED' WHERE status = 'CANCELLED'")
    op.alter_column(
        "service_requests",
        "status",
        existing_type=sa.String(11),
        type_=sa.String(20),
        nullable=False,
    )
    op.alter_column(
        "service_requests",
        "category",
        existing_type=sa.String(80),
        type_=sa.String(120),
        nullable=False,
    )
    op.create_check_constraint(
        "service_request_status",
        "service_requests",
        "status IN ('OPEN','ASSIGNED','IN_PROGRESS','WAITING_FOR_CUSTOMER','RESOLVED','CLOSED')",
    )
    op.create_index(
        "ix_service_requests_sla_due",
        "service_requests",
        ["organization_id", "status", "resolution_due_at"],
    )

    op.create_table(
        "service_request_comments",
        *_owned(),
        sa.Column("service_request_id", sa.String(36), nullable=False),
        sa.Column("author_user_id", sa.String(36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        *_constraints("service_request_comments"),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_service_request_comments_service_request_id_service_requests_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "author_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_comments_author_user_id_users_tenant",
        ),
    )
    op.create_index(
        "ix_service_comments_ticket_created",
        "service_request_comments",
        ["organization_id", "service_request_id", "created_at"],
    )

    op.create_table(
        "service_request_attachments",
        *_owned(),
        sa.Column("service_request_id", sa.String(36), nullable=False),
        sa.Column("comment_id", sa.String(36)),
        sa.Column("uploaded_by_user_id", sa.String(36), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        *_constraints("service_request_attachments"),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_service_request_attachments_service_request_id_service_requests_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "comment_id"],
            ["service_request_comments.organization_id", "service_request_comments.id"],
            name="fk_service_request_attachments_comment_id_service_request_comments_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_attachments_uploaded_by_user_id_users_tenant",
        ),
    )
    op.create_index(
        "ix_service_attachments_ticket",
        "service_request_attachments",
        ["organization_id", "service_request_id", "created_at"],
    )

    op.create_table(
        "service_request_escalations",
        *_owned(),
        sa.Column("service_request_id", sa.String(36), nullable=False),
        sa.Column("escalated_by_user_id", sa.String(36)),
        sa.Column("from_user_id", sa.String(36)),
        sa.Column("to_user_id", sa.String(36), nullable=False),
        sa.Column("acknowledged_by_user_id", sa.String(36)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_constraints("service_request_escalations"),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_service_request_escalations_service_request_id_service_requests_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "escalated_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_escalations_escalated_by_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "from_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_escalations_from_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "to_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_escalations_to_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "acknowledged_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_escalations_acknowledged_by_user_id_users_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','RESOLVED')",
            name="service_escalation_status",
        ),
    )
    op.create_index(
        "ix_service_escalations_ticket_status",
        "service_request_escalations",
        ["organization_id", "service_request_id", "status"],
    )

    op.create_table(
        "service_request_feedback",
        *_owned(),
        sa.Column("service_request_id", sa.String(36), nullable=False),
        sa.Column("submitted_by_user_id", sa.String(36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        *_constraints("service_request_feedback"),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_service_request_feedback_service_request_id_service_requests_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "submitted_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_service_request_feedback_submitted_by_user_id_users_tenant",
        ),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="feedback_rating_range"),
    )
    op.create_index(
        "uq_service_feedback_ticket",
        "service_request_feedback",
        ["organization_id", "service_request_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_service_feedback_ticket", table_name="service_request_feedback")
    op.drop_table("service_request_feedback")
    op.drop_index("ix_service_escalations_ticket_status", table_name="service_request_escalations")
    op.drop_table("service_request_escalations")
    op.drop_index("ix_service_attachments_ticket", table_name="service_request_attachments")
    op.drop_table("service_request_attachments")
    op.drop_index("ix_service_comments_ticket_created", table_name="service_request_comments")
    op.drop_table("service_request_comments")
    op.drop_index("ix_service_requests_sla_due", table_name="service_requests")
    op.drop_constraint(
        op.f("ck_service_requests_service_request_status"),
        "service_requests",
        type_="check",
    )
    op.execute(
        "UPDATE service_requests SET status = 'IN_PROGRESS' WHERE status = 'WAITING_FOR_CUSTOMER'"
    )
    op.alter_column(
        "service_requests",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(11),
        nullable=False,
    )
    op.create_check_constraint(
        "service_request_status",
        "service_requests",
        "status IN ('OPEN','ASSIGNED','IN_PROGRESS','RESOLVED','CLOSED','CANCELLED')",
    )
    op.drop_constraint(
        op.f("ck_service_requests_requester_required"),
        "service_requests",
        type_="check",
    )
    # The older schema cannot represent self-service requests linked only to a user.
    op.execute(
        "DELETE FROM service_requests WHERE customer_id IS NULL AND tenant_id IS NULL"
    )
    op.create_check_constraint(
        "requester_required",
        "service_requests",
        "customer_id IS NOT NULL OR tenant_id IS NOT NULL",
    )
    op.execute("UPDATE service_requests SET category = LEFT(category, 80)")
    op.alter_column(
        "service_requests",
        "category",
        existing_type=sa.String(120),
        type_=sa.String(80),
        nullable=False,
    )
    for column, remote in (
        ("category_id", "service_request_categories"),
        ("sla_policy_id", "service_sla_policies"),
        ("opened_by_user_id", "users"),
        ("assigned_by_user_id", "users"),
        ("resolved_by_user_id", "users"),
        ("closed_by_user_id", "users"),
    ):
        op.drop_constraint(
            f"fk_service_requests_{column}_{remote}_tenant",
            "service_requests",
            type_="foreignkey",
        )
    for column in (
        "is_escalated",
        "closure_notes",
        "resolution_summary",
        "last_agent_reply_at",
        "last_customer_reply_at",
        "first_responded_at",
        "escalation_due_at",
        "resolution_due_at",
        "response_due_at",
        "closed_by_user_id",
        "resolved_by_user_id",
        "assigned_by_user_id",
        "opened_by_user_id",
        "sla_policy_id",
        "category_id",
    ):
        op.drop_column("service_requests", column)
    op.drop_index("uq_service_sla_category_priority", table_name="service_sla_policies")
    op.drop_table("service_sla_policies")
    op.drop_index("ix_service_categories_active", table_name="service_request_categories")
    op.drop_index("uq_service_categories_code", table_name="service_request_categories")
    op.drop_table("service_request_categories")
