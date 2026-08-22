"""Add typed, deduplicated notification event architecture.

Revision ID: 20260822_0019
Revises: 20260822_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0019"
down_revision: str | None = "20260822_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("event_type", sa.String(80), nullable=True))
    op.add_column("notifications", sa.Column("action_url", sa.String(500), nullable=True))
    op.add_column("notifications", sa.Column("data", sa.JSON(), nullable=True))
    op.add_column("notifications", sa.Column("deduplication_key", sa.String(180), nullable=True))
    op.add_column(
        "notifications", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_notifications_tenant_user_unread",
        "notifications",
        ["organization_id", "recipient_user_id", "read_at", "created_at"],
    )
    op.create_index(
        "uq_notifications_tenant_delivery_dedupe",
        "notifications",
        ["organization_id", "recipient_user_id", "channel", "deduplication_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_notifications_tenant_delivery_dedupe", table_name="notifications")
    op.drop_index("ix_notifications_tenant_user_unread", table_name="notifications")
    op.drop_column("notifications", "scheduled_for")
    op.drop_column("notifications", "deduplication_key")
    op.drop_column("notifications", "data")
    op.drop_column("notifications", "action_url")
    op.drop_column("notifications", "event_type")
