"""Add quotation and cost sheet management.

Revision ID: 20260821_0008
Revises: 20260821_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0008"
down_revision: str | None = "20260821_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cost_sheets",
        sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("lead_id", sa.String(36), nullable=True),
        sa.Column("unit_id", sa.String(36), nullable=False),
        sa.Column("price_list_id", sa.String(36), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PENDING_APPROVAL",
                "APPROVED",
                "REJECTED",
                "CONVERTED",
                "VOIDED",
                name="cost_sheet_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("base_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("gross_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("final_agreed_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("booking_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gross_value >= 0", name="ck_cost_sheets_gross_value_nonnegative"),
        sa.CheckConstraint(
            "discount_amount >= 0", name="ck_cost_sheets_discount_amount_nonnegative"
        ),
        sa.CheckConstraint("tax_amount >= 0", name="ck_cost_sheets_tax_amount_nonnegative"),
        sa.CheckConstraint(
            "final_agreed_value >= 0", name="ck_cost_sheets_final_value_nonnegative"
        ),
        sa.CheckConstraint(
            "booking_amount >= 0", name="ck_cost_sheets_booking_amount_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="fk_cost_sheets_customer_id_customers_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "lead_id"],
            ["leads.organization_id", "leads.id"],
            name="fk_cost_sheets_lead_id_leads_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "unit_id"],
            ["units.organization_id", "units.id"],
            name="fk_cost_sheets_unit_id_units_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "price_list_id"],
            ["price_lists.organization_id", "price_lists.id"],
            name="fk_cost_sheets_price_list_id_price_lists_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_cost_sheets_created_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_cost_sheets_organization_id_id"),
    )
    for columns, name in (
        (["organization_id"], op.f("ix_cost_sheets_organization_id")),
        (["customer_id"], op.f("ix_cost_sheets_customer_id")),
        (["lead_id"], op.f("ix_cost_sheets_lead_id")),
        (["unit_id"], op.f("ix_cost_sheets_unit_id")),
        (["price_list_id"], op.f("ix_cost_sheets_price_list_id")),
        (["organization_id", "status"], "ix_cost_sheets_tenant_status"),
        (["organization_id", "customer_id"], "ix_cost_sheets_tenant_customer"),
    ):
        op.create_index(name, "cost_sheets", columns)

    op.create_table(
        "cost_sheet_items",
        sa.Column("cost_sheet_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("taxable", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "cost_sheet_id"],
            ["cost_sheets.organization_id", "cost_sheets.id"],
            name="fk_cost_sheet_items_cost_sheet_id_cost_sheets_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_cost_sheet_items_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "cost_sheet_id",
            "sequence",
            name="uq_cost_sheet_items_tenant_sheet_sequence",
        ),
    )
    op.create_index(op.f("ix_cost_sheet_items_organization_id"), "cost_sheet_items", ["organization_id"])
    op.create_index(op.f("ix_cost_sheet_items_cost_sheet_id"), "cost_sheet_items", ["cost_sheet_id"])

    op.create_table(
        "discount_approvals",
        sa.Column("cost_sheet_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("approver_user_id", sa.String(36), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                "CANCELLED",
                name="discount_approval_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("requested_discount_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("requested_discount_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("self_approval_limit_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("approval_level_name", sa.String(120), nullable=False),
        sa.Column("required_approver_user_ids", sa.JSON(), nullable=False),
        sa.Column("required_approver_role_ids", sa.JSON(), nullable=False),
        sa.Column("previous_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("final_approved_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("request_notes", sa.Text(), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "cost_sheet_id"],
            ["cost_sheets.organization_id", "cost_sheets.id"],
            name="fk_discount_approvals_cost_sheet_id_cost_sheets_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_discount_approvals_requested_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "approver_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_discount_approvals_approver_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_discount_approvals_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "cost_sheet_id",
            name="uq_discount_approvals_tenant_cost_sheet",
        ),
    )
    op.create_index(op.f("ix_discount_approvals_organization_id"), "discount_approvals", ["organization_id"])
    op.create_index(op.f("ix_discount_approvals_cost_sheet_id"), "discount_approvals", ["cost_sheet_id"])
    op.create_index(
        "ix_discount_approvals_tenant_status",
        "discount_approvals",
        ["organization_id", "status"],
    )

    for column in (
        sa.Column("unit_id", sa.String(36), nullable=True),
        sa.Column("cost_sheet_id", sa.String(36), nullable=True),
        sa.Column("parent_quotation_id", sa.String(36), nullable=True),
        sa.Column("final_agreed_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("booking_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("quotations", column)
    for name, local, remote in (
        ("fk_quotations_unit_id_units_tenant", "unit_id", "units"),
        ("fk_quotations_cost_sheet_id_cost_sheets_tenant", "cost_sheet_id", "cost_sheets"),
        ("fk_quotations_parent_quotation_id_quotations_tenant", "parent_quotation_id", "quotations"),
    ):
        op.create_foreign_key(
            name,
            "quotations",
            remote,
            ["organization_id", local],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
    op.create_index(op.f("ix_quotations_unit_id"), "quotations", ["unit_id"])
    op.create_index(op.f("ix_quotations_cost_sheet_id"), "quotations", ["cost_sheet_id"])
    op.add_column("quotation_items", sa.Column("category", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("quotation_items", "category")
    op.drop_index(op.f("ix_quotations_cost_sheet_id"), table_name="quotations")
    op.drop_index(op.f("ix_quotations_unit_id"), table_name="quotations")
    for name in (
        "fk_quotations_parent_quotation_id_quotations_tenant",
        "fk_quotations_cost_sheet_id_cost_sheets_tenant",
        "fk_quotations_unit_id_units_tenant",
    ):
        op.drop_constraint(name, "quotations", type_="foreignkey")
    for column_name in (
        "issued_at",
        "pricing_snapshot",
        "booking_amount",
        "final_agreed_value",
        "parent_quotation_id",
        "cost_sheet_id",
        "unit_id",
    ):
        op.drop_column("quotations", column_name)
    op.drop_table("discount_approvals")
    op.drop_table("cost_sheet_items")
    op.drop_table("cost_sheets")
