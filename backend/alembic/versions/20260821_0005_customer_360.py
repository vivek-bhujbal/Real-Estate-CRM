"""Add Customer 360 profile and communication structures.

Revision ID: 20260821_0005
Revises: 20260821_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0005"
down_revision: str | None = "20260821_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("branch_id", sa.String(36), nullable=True),
        sa.Column("alternate_phone", sa.String(32), nullable=True),
        sa.Column("normalized_email", sa.String(254), nullable=True),
        sa.Column("normalized_phone", sa.String(32), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(30), nullable=True),
        sa.Column("occupation", sa.String(120), nullable=True),
        sa.Column("company_name", sa.String(160), nullable=True),
        sa.Column("address_line1", sa.String(200), nullable=True),
        sa.Column("address_line2", sa.String(200), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("preferred_location", sa.String(200), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("budget_min", sa.Numeric(18, 2), nullable=True),
        sa.Column("budget_max", sa.Numeric(18, 2), nullable=True),
        sa.Column("communication_preferences", sa.JSON(), nullable=True),
    )
    for column in columns:
        op.add_column("customers", column)

    op.create_check_constraint(
        "ck_customers_budget_range",
        "customers",
        "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
    )
    for column_name, remote_table in (("owner_user_id", "users"), ("branch_id", "branches")):
        op.create_foreign_key(
            f"fk_customers_{column_name}_{remote_table}_tenant",
            "customers",
            remote_table,
            ["organization_id", column_name],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_index(op.f(f"ix_customers_{column_name}"), "customers", [column_name])
    for name, columns_ in (
        ("ix_customers_tenant_normalized_phone", ["organization_id", "normalized_phone"]),
        ("ix_customers_tenant_normalized_email", ["organization_id", "normalized_email"]),
        ("ix_customers_tenant_owner_status", ["organization_id", "owner_user_id", "status"]),
    ):
        op.create_index(name, "customers", columns_)

    activity_type = sa.Enum(
        "CALL", "EMAIL", "MEETING", "NOTE", "STATUS_CHANGE", "FOLLOW_UP",
        name="customer_activity_type",
    )
    op.create_table(
        "customer_activities",
        sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("performed_by_user_id", sa.String(36), nullable=True),
        sa.Column("activity_type", activity_type, nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(40), nullable=True),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name=op.f("fk_customer_activities_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="fk_customer_activities_customer_id_customers_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "performed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_customer_activities_performed_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_activities")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_customer_activities_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_customer_activities_organization_id"),
        "customer_activities",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_activities_tenant_customer_occurred",
        "customer_activities",
        ["organization_id", "customer_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("customer_activities")
    for name in (
        "ix_customers_tenant_owner_status",
        "ix_customers_tenant_normalized_email",
        "ix_customers_tenant_normalized_phone",
    ):
        op.drop_index(name, table_name="customers")
    for column_name, remote_table in (("branch_id", "branches"), ("owner_user_id", "users")):
        op.drop_index(op.f(f"ix_customers_{column_name}"), table_name="customers")
        op.drop_constraint(
            f"fk_customers_{column_name}_{remote_table}_tenant",
            "customers",
            type_="foreignkey",
        )
    op.drop_constraint("ck_customers_budget_range", "customers", type_="check")
    for column_name in (
        "communication_preferences", "budget_max", "budget_min", "requirements",
        "preferred_location", "country", "postal_code", "state", "city",
        "address_line2", "address_line1", "company_name", "occupation", "gender",
        "date_of_birth", "normalized_phone", "normalized_email", "alternate_phone",
        "branch_id", "owner_user_id",
    ):
        op.drop_column("customers", column_name)
