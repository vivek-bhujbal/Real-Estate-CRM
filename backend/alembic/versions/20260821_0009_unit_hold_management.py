"""Add approval-aware unit hold management.

Revision ID: 20260821_0009
Revises: 20260821_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0009"
down_revision: str | None = "20260821_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

old_status = sa.Enum(
    "ACTIVE",
    "RELEASED",
    "EXPIRED",
    "CONVERTED",
    name="unit_hold_status",
    native_enum=False,
    create_constraint=True,
)
new_status = sa.Enum(
    "PENDING_APPROVAL",
    "ACTIVE",
    "REJECTED",
    "RELEASED",
    "EXPIRED",
    "CONVERTED",
    name="unit_hold_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.drop_constraint("unit_hold_status", "unit_holds", type_="check")
    op.alter_column(
        "unit_holds",
        "status",
        existing_type=old_status,
        type_=new_status,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "unit_hold_status",
        "unit_holds",
        "status IN ('PENDING_APPROVAL','ACTIVE','REJECTED','RELEASED','EXPIRED','CONVERTED')",
    )
    op.add_column(
        "unit_holds",
        sa.Column(
            "hold_type",
            sa.Enum(
                "SOFT_HOLD",
                "HARD_HOLD",
                name="unit_hold_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    op.add_column("unit_holds", sa.Column("hold_reason", sa.Text(), nullable=True))
    op.add_column("unit_holds", sa.Column("approved_by_user_id", sa.String(36), nullable=True))
    op.add_column("unit_holds", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("unit_holds", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("unit_holds", sa.Column("approval_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_unit_holds_approved_by_user_id_users_tenant",
        "unit_holds",
        "users",
        ["organization_id", "approved_by_user_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_unit_holds_approved_by_user_id_users_tenant", "unit_holds", type_="foreignkey"
    )
    op.drop_column("unit_holds", "approval_notes")
    op.drop_column("unit_holds", "rejected_at")
    op.drop_column("unit_holds", "approved_at")
    op.drop_column("unit_holds", "approved_by_user_id")
    op.drop_column("unit_holds", "hold_reason")
    op.drop_column("unit_holds", "hold_type")
    op.drop_constraint("unit_hold_status", "unit_holds", type_="check")
    op.alter_column(
        "unit_holds",
        "status",
        existing_type=new_status,
        type_=old_status,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "unit_hold_status",
        "unit_holds",
        "status IN ('ACTIVE','RELEASED','EXPIRED','CONVERTED')",
    )
