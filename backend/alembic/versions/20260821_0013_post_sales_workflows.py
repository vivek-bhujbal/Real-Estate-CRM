"""Add audited cancellation, refund, and unit transfer workflow state.

Revision ID: 20260821_0013
Revises: 20260821_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0013"
down_revision: str | None = "20260821_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_cancellations_tenant_booking", "cancellations", type_="unique")
    op.add_column("cancellations", sa.Column("reviewed_by_user_id", sa.String(36)))
    op.add_column("cancellations", sa.Column("review_notes", sa.Text()))
    op.add_column("cancellations", sa.Column("decision_notes", sa.Text()))
    op.add_column("cancellations", sa.Column("active_booking_key", sa.String(36)))
    op.add_column(
        "cancellations",
        sa.Column("paid_amount_snapshot", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "cancellations",
        sa.Column("deduction_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "cancellations",
        sa.Column("refund_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column("cancellations", sa.Column("calculation_snapshot", sa.JSON()))
    op.add_column("cancellations", sa.Column("document_number", sa.String(80)))
    op.add_column("cancellations", sa.Column("document_storage_key", sa.String(512)))
    op.add_column("cancellations", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("cancellations", sa.Column("unit_released_at", sa.DateTime(timezone=True)))
    op.add_column("cancellations", sa.Column("document_generated_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_cancellations_reviewed_by_user_id_users_tenant",
        "cancellations",
        "users",
        ["organization_id", "reviewed_by_user_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_cancellations_tenant_active_booking",
        "cancellations",
        ["organization_id", "active_booking_key"],
    )
    op.create_check_constraint(
        "ck_cancellations_amounts_nonnegative",
        "cancellations",
        "paid_amount_snapshot >= 0 AND deduction_amount >= 0 AND refund_amount >= 0",
    )

    op.add_column("unit_transfers", sa.Column("quotation_id", sa.String(36)))
    op.add_column("unit_transfers", sa.Column("reviewed_by_user_id", sa.String(36)))
    op.add_column("unit_transfers", sa.Column("review_notes", sa.Text()))
    op.add_column("unit_transfers", sa.Column("decision_notes", sa.Text()))
    op.add_column("unit_transfers", sa.Column("active_booking_key", sa.String(36)))
    op.add_column(
        "unit_transfers",
        sa.Column("old_agreed_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "unit_transfers",
        sa.Column("new_agreed_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "unit_transfers",
        sa.Column("price_difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "unit_transfers",
        sa.Column("paid_amount_snapshot", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column("unit_transfers", sa.Column("pricing_snapshot", sa.JSON()))
    op.add_column(
        "unit_transfers",
        sa.Column("payment_plan_snapshot", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("unit_transfers", sa.Column("commission_snapshot", sa.JSON()))
    op.add_column("unit_transfers", sa.Column("document_number", sa.String(80)))
    op.add_column("unit_transfers", sa.Column("document_storage_key", sa.String(512)))
    op.add_column("unit_transfers", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("unit_transfers", sa.Column("document_generated_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_unit_transfers_quotation_id_quotations_tenant",
        "unit_transfers",
        "quotations",
        ["organization_id", "quotation_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_unit_transfers_reviewed_by_user_id_users_tenant",
        "unit_transfers",
        "users",
        ["organization_id", "reviewed_by_user_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_unit_transfers_tenant_active_booking",
        "unit_transfers",
        ["organization_id", "active_booking_key"],
    )
    op.create_check_constraint(
        "ck_unit_transfers_prices_nonnegative",
        "unit_transfers",
        "old_agreed_price >= 0 AND new_agreed_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_unit_transfers_prices_nonnegative", "unit_transfers", type_="check")
    op.drop_constraint("uq_unit_transfers_tenant_active_booking", "unit_transfers", type_="unique")
    op.drop_constraint(
        "fk_unit_transfers_reviewed_by_user_id_users_tenant",
        "unit_transfers",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_transfers_quotation_id_quotations_tenant",
        "unit_transfers",
        type_="foreignkey",
    )
    for column in (
        "document_generated_at",
        "reviewed_at",
        "document_storage_key",
        "document_number",
        "commission_snapshot",
        "payment_plan_snapshot",
        "pricing_snapshot",
        "paid_amount_snapshot",
        "price_difference",
        "new_agreed_price",
        "old_agreed_price",
        "active_booking_key",
        "decision_notes",
        "review_notes",
        "reviewed_by_user_id",
        "quotation_id",
    ):
        op.drop_column("unit_transfers", column)

    op.drop_constraint("ck_cancellations_amounts_nonnegative", "cancellations", type_="check")
    op.drop_constraint("uq_cancellations_tenant_active_booking", "cancellations", type_="unique")
    op.drop_constraint(
        "fk_cancellations_reviewed_by_user_id_users_tenant",
        "cancellations",
        type_="foreignkey",
    )
    for column in (
        "document_generated_at",
        "unit_released_at",
        "reviewed_at",
        "document_storage_key",
        "document_number",
        "calculation_snapshot",
        "refund_amount",
        "deduction_amount",
        "paid_amount_snapshot",
        "active_booking_key",
        "decision_notes",
        "review_notes",
        "reviewed_by_user_id",
    ):
        op.drop_column("cancellations", column)
    op.create_unique_constraint(
        "uq_cancellations_tenant_booking", "cancellations", ["organization_id", "booking_id"]
    )
