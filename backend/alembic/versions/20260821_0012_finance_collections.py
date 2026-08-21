"""Add finance allocation, reconciliation, charges, and controlled refunds.

Revision ID: 20260821_0012
Revises: 20260821_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0012"
down_revision: str | None = "20260821_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_fk(table: str, column: str, remote: str, *, ondelete: str = "RESTRICT") -> None:
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
        "payment_allocations",
        sa.Column("payment_id", sa.String(36), nullable=False),
        sa.Column("installment_id", sa.String(36), nullable=True),
        sa.Column("demand_letter_id", sa.String(36), nullable=True),
        sa.Column("allocated_by_user_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "payment_id"],
            ["payments.organization_id", "payments.id"],
            name="fk_payment_allocations_payment_id_payments_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "installment_id"],
            ["installments.organization_id", "installments.id"],
            name="fk_payment_allocations_installment_id_installments_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "demand_letter_id"],
            ["demand_letters.organization_id", "demand_letters.id"],
            name="fk_payment_allocations_demand_letter_id_demand_letters_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "allocated_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_payment_allocations_allocated_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_payment_allocations_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_payment_allocations_idempotency"
        ),
    )
    op.create_index(
        "ix_payment_allocations_organization_id", "payment_allocations", ["organization_id"]
    )
    op.create_index(
        "ix_payment_allocations_payment", "payment_allocations", ["organization_id", "payment_id"]
    )

    op.create_table(
        "payment_reconciliations",
        sa.Column("payment_id", sa.String(36), nullable=False),
        sa.Column("reconciled_by_user_id", sa.String(36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "MATCHED",
                "MISMATCHED",
                "RESOLVED",
                name="payment_reconciliation_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("expected_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("received_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("difference_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("external_reference", sa.String(120), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expected_amount > 0 AND received_amount >= 0", name="amounts_valid"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "payment_id"],
            ["payments.organization_id", "payments.id"],
            name="fk_payment_reconciliations_payment_id_payments_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reconciled_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_payment_reconciliations_reconciled_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_payment_reconciliations_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_payment_reconciliations_idempotency"
        ),
    )
    op.create_index(
        "ix_payment_reconciliations_organization_id", "payment_reconciliations", ["organization_id"]
    )
    op.create_index(
        "ix_payment_reconciliations_status",
        "payment_reconciliations",
        ["organization_id", "status"],
    )

    op.create_table(
        "financial_charges",
        sa.Column("booking_id", sa.String(36), nullable=False),
        sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("installment_id", sa.String(36), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("waived_by_user_id", sa.String(36), nullable=True),
        sa.Column(
            "charge_type",
            sa.Enum(
                "PENALTY",
                "INTEREST",
                name="financial_charge_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "APPLIED",
                "PARTIALLY_PAID",
                "PAID",
                "WAIVED",
                name="financial_charge_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("principal_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("rate_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("days_calculated", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("calculation_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("waived_reason", sa.String(500), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "principal_amount >= 0 AND rate_percent >= 0 AND days_calculated >= 0 AND amount > 0 AND paid_amount >= 0",
            name="amounts_valid",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_financial_charges_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_financial_charges_idempotency"
        ),
    )
    op.create_index(
        "ix_financial_charges_organization_id", "financial_charges", ["organization_id"]
    )
    op.create_index(
        "ix_financial_charges_booking_status",
        "financial_charges",
        ["organization_id", "booking_id", "status"],
    )
    for column, remote in (
        ("booking_id", "bookings"),
        ("customer_id", "customers"),
        ("installment_id", "installments"),
        ("created_by_user_id", "users"),
        ("waived_by_user_id", "users"),
    ):
        _tenant_fk("financial_charges", column, remote)

    op.alter_column("refunds", "cancellation_id", existing_type=sa.String(36), nullable=True)
    for name in ("booking_id", "requested_by_user_id", "approved_by_user_id"):
        op.add_column("refunds", sa.Column(name, sa.String(36), nullable=True))
    op.add_column("refunds", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("refunds", sa.Column("decision_notes", sa.Text(), nullable=True))
    op.add_column("refunds", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("refunds", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refunds", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    for column, remote in (
        ("booking_id", "bookings"),
        ("requested_by_user_id", "users"),
        ("approved_by_user_id", "users"),
    ):
        _tenant_fk("refunds", column, remote)
    op.create_unique_constraint(
        "uq_refunds_idempotency", "refunds", ["organization_id", "idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_refunds_idempotency", "refunds", type_="unique")
    for column, remote in reversed(
        (
            ("booking_id", "bookings"),
            ("requested_by_user_id", "users"),
            ("approved_by_user_id", "users"),
        )
    ):
        op.drop_constraint(f"fk_refunds_{column}_{remote}_tenant", "refunds", type_="foreignkey")
    for name in (
        "rejected_at",
        "approved_at",
        "idempotency_key",
        "decision_notes",
        "reason",
        "approved_by_user_id",
        "requested_by_user_id",
        "booking_id",
    ):
        op.drop_column("refunds", name)
    op.alter_column("refunds", "cancellation_id", existing_type=sa.String(36), nullable=False)
    op.drop_index("ix_financial_charges_booking_status", table_name="financial_charges")
    op.drop_index("ix_financial_charges_organization_id", table_name="financial_charges")
    op.drop_table("financial_charges")
    op.drop_index("ix_payment_reconciliations_status", table_name="payment_reconciliations")
    op.drop_index(
        "ix_payment_reconciliations_organization_id", table_name="payment_reconciliations"
    )
    op.drop_table("payment_reconciliations")
    op.drop_index("ix_payment_allocations_payment", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_organization_id", table_name="payment_allocations")
    op.drop_table("payment_allocations")
