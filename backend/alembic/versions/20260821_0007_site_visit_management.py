"""Add complete site visit management.

Revision ID: 20260821_0007
Revises: 20260821_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0007"
down_revision: str | None = "20260821_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attendees", sa.JSON(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(120), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("site_visits", column)
    op.create_foreign_key(
        "fk_site_visits_created_by_user_id_users_tenant",
        "site_visits",
        "users",
        ["organization_id", "created_by_user_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_site_visits_site_visit_status", "site_visits", type_="check")
    op.create_check_constraint(
        "ck_site_visits_site_visit_status",
        "site_visits",
        "status IN ('SCHEDULED','CONFIRMED','CHECKED_IN','COMPLETED','CANCELLED','NO_SHOW')",
    )
    op.create_table(
        "site_visit_units",
        sa.Column("site_visit_id", sa.String(36), nullable=False),
        sa.Column("unit_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "site_visit_id"],
            ["site_visits.organization_id", "site_visits.id"],
            name="fk_site_visit_units_site_visit_id_site_visits_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "unit_id"],
            ["units.organization_id", "units.id"],
            name="fk_site_visit_units_unit_id_units_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_site_visit_units_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "site_visit_id",
            "unit_id",
            name="uq_site_visit_units_tenant_visit_unit",
        ),
    )
    op.create_index(
        op.f("ix_site_visit_units_organization_id"),
        "site_visit_units",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_site_visit_units_site_visit_id"),
        "site_visit_units",
        ["site_visit_id"],
    )
    op.create_index(
        op.f("ix_site_visit_units_unit_id"), "site_visit_units", ["unit_id"]
    )
def downgrade() -> None:
    op.execute(
        "UPDATE site_visits SET status = 'CONFIRMED' WHERE status = 'CHECKED_IN'"
    )
    op.drop_table("site_visit_units")
    op.drop_constraint("ck_site_visits_site_visit_status", "site_visits", type_="check")
    op.create_check_constraint(
        "ck_site_visits_site_visit_status",
        "site_visits",
        "status IN ('SCHEDULED','CONFIRMED','COMPLETED','CANCELLED','NO_SHOW')",
    )
    op.drop_constraint(
        "fk_site_visits_created_by_user_id_users_tenant",
        "site_visits",
        type_="foreignkey",
    )
    for column_name in (
        "next_follow_up_at",
        "outcome",
        "feedback",
        "attendees",
        "check_out_at",
        "check_in_at",
        "created_by_user_id",
    ):
        op.drop_column("site_visits", column_name)
