"""Add production authentication lifecycle state.

Revision ID: 20260821_0002
Revises: 20260821_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0002"
down_revision: str | None = "20260821_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.alter_column("users", "auth_version", server_default=None)

    op.add_column(
        "refresh_tokens",
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing sessions retain their original expiry as the absolute boundary.
    # This is a technical state backfill and creates no users or business data.
    op.execute("UPDATE refresh_tokens SET absolute_expires_at = expires_at")
    op.alter_column(
        "refresh_tokens",
        "absolute_expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_password_reset_tokens_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_password_reset_tokens_user_id_users_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_password_reset_tokens_organization_id_id",
        ),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_expiry",
        "password_reset_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_organization_id"),
        "password_reset_tokens",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_password_reset_tokens_tenant_user_active",
        "password_reset_tokens",
        ["organization_id", "user_id", "consumed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_column("refresh_tokens", "absolute_expires_at")
    op.drop_column("users", "auth_version")
