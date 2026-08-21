"""Add complete transactional booking management.

Revision ID: 20260821_0011
Revises: 20260821_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0011"
down_revision: str | None = "20260821_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

old_status = sa.Enum(
    "DRAFT",
    "DOCUMENTATION_PENDING",
    "PAYMENT_PENDING",
    "SUBMITTED",
    "VERIFICATION",
    "APPROVAL",
    "CONFIRMED",
    "CANCELLED",
    name="booking_status",
    native_enum=False,
    create_constraint=True,
)
new_status = sa.Enum(
    "DRAFT",
    "DOCUMENTATION_PENDING",
    "PAYMENT_PENDING",
    "SUBMITTED",
    "VERIFICATION",
    "APPROVAL",
    "CONFIRMED",
    "REJECTED",
    "CANCELLED",
    name="booking_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.drop_constraint("booking_status", "bookings", type_="check")
    op.alter_column(
        "bookings",
        "status",
        existing_type=old_status,
        type_=new_status,
        existing_nullable=False,
    )
    for name in (
        "unit_hold_id",
        "salesperson_user_id",
        "channel_partner_id",
        "verified_by_user_id",
        "confirmed_by_user_id",
    ):
        op.add_column("bookings", sa.Column(name, sa.String(36), nullable=True))
    op.add_column("bookings", sa.Column("agreed_price", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column("bookings", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("verification_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings", sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bookings", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "agreed_price_nonnegative", "bookings", "agreed_price IS NULL OR agreed_price >= 0"
    )
    op.create_check_constraint(
        "discount_amount_nonnegative", "bookings", "discount_amount >= 0"
    )
    foreign_keys = (
        ("unit_hold_id", "unit_holds"),
        ("salesperson_user_id", "users"),
        ("channel_partner_id", "channel_partners"),
        ("verified_by_user_id", "users"),
        ("confirmed_by_user_id", "users"),
    )
    for column, remote in foreign_keys:
        op.create_foreign_key(
            f"fk_bookings_{column}_{remote}_tenant",
            "bookings",
            remote,
            ["organization_id", column],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "booking_applicants",
        sa.Column("booking_id", sa.String(36), nullable=False),
        sa.Column("customer_id", sa.String(36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("primary_booking_key", sa.String(36), nullable=True),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("tax_identifier", sa.String(80), nullable=True),
        sa.Column("relationship_to_primary", sa.String(80), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence > 0", name="sequence_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id", "booking_id"],
            ["bookings.organization_id", "bookings.id"],
            name="fk_booking_applicants_booking_id_bookings_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="fk_booking_applicants_customer_id_customers_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_booking_applicants_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id", "booking_id", "sequence", name="uq_booking_applicants_sequence"
        ),
        sa.UniqueConstraint(
            "organization_id", "primary_booking_key", name="uq_booking_applicants_primary"
        ),
    )
    op.create_index("ix_booking_applicants_organization_id", "booking_applicants", ["organization_id"])
    op.create_index("ix_booking_applicants_booking_id", "booking_applicants", ["booking_id"])

    op.create_table(
        "booking_financing",
        sa.Column("booking_id", sa.String(36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NOT_REQUIRED",
                "APPLIED",
                "UNDER_REVIEW",
                "SANCTIONED",
                "REJECTED",
                "DISBURSED",
                name="booking_financing_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("lender_name", sa.String(180), nullable=True),
        sa.Column("loan_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("application_number", sa.String(100), nullable=True),
        sa.Column("sanction_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "loan_amount IS NULL OR loan_amount >= 0",
            name="loan_amount_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "booking_id"],
            ["bookings.organization_id", "bookings.id"],
            name="fk_booking_financing_booking_id_bookings_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_booking_financing_organization_id_id"),
        sa.UniqueConstraint("organization_id", "booking_id", name="uq_booking_financing_booking"),
    )
    op.create_index("ix_booking_financing_organization_id", "booking_financing", ["organization_id"])
    op.create_index("ix_booking_financing_booking_id", "booking_financing", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_financing_booking_id", table_name="booking_financing")
    op.drop_index("ix_booking_financing_organization_id", table_name="booking_financing")
    op.drop_table("booking_financing")
    op.drop_index("ix_booking_applicants_booking_id", table_name="booking_applicants")
    op.drop_index("ix_booking_applicants_organization_id", table_name="booking_applicants")
    op.drop_table("booking_applicants")
    for column, remote in reversed(
        (
            ("unit_hold_id", "unit_holds"),
            ("salesperson_user_id", "users"),
            ("channel_partner_id", "channel_partners"),
            ("verified_by_user_id", "users"),
            ("confirmed_by_user_id", "users"),
        )
    ):
        op.drop_constraint(f"fk_bookings_{column}_{remote}_tenant", "bookings", type_="foreignkey")
    op.drop_constraint("discount_amount_nonnegative", "bookings", type_="check")
    op.drop_constraint("agreed_price_nonnegative", "bookings", type_="check")
    for column in (
        "rejection_reason",
        "cancelled_at",
        "rejected_at",
        "approval_requested_at",
        "verification_completed_at",
        "submitted_at",
        "discount_amount",
        "agreed_price",
        "confirmed_by_user_id",
        "verified_by_user_id",
        "channel_partner_id",
        "salesperson_user_id",
        "unit_hold_id",
    ):
        op.drop_column("bookings", column)
    op.execute("UPDATE bookings SET status = 'CANCELLED' WHERE status = 'REJECTED'")
    op.drop_constraint("booking_status", "bookings", type_="check")
    op.alter_column(
        "bookings",
        "status",
        existing_type=new_status,
        type_=old_status,
        existing_nullable=False,
    )
