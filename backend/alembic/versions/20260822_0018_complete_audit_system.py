"""Add request device metadata and query indexes to append-only audit records.

Revision ID: 20260822_0018
Revises: 20260822_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0018"
down_revision: str | None = "20260822_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(512), nullable=True))
    op.add_column("audit_logs", sa.Column("device_metadata", sa.JSON(), nullable=True))
    op.create_index(
        "ix_audit_tenant_action_created",
        "audit_logs",
        ["organization_id", "action", "created_at"],
    )
    op.create_index(
        "ix_audit_tenant_actor_created",
        "audit_logs",
        ["organization_id", "actor_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_tenant_actor_created", table_name="audit_logs")
    op.drop_index("ix_audit_tenant_action_created", table_name="audit_logs")
    op.drop_column("audit_logs", "device_metadata")
    op.drop_column("audit_logs", "user_agent")
