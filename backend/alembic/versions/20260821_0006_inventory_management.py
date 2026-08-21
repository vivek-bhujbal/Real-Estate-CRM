"""Add project and property inventory management fields.

Revision ID: 20260821_0006
Revises: 20260821_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0006"
down_revision: str | None = "20260821_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("project_type", sa.String(80), nullable=True),
        sa.Column("address_line1", sa.String(200), nullable=True),
        sa.Column("address_line2", sa.String(200), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("rera_number", sa.String(80), nullable=True),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("expected_possession_date", sa.Date(), nullable=True),
        sa.Column("default_currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("amenities", sa.JSON(), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=True),
    ):
        op.add_column("projects", column)
    op.alter_column("projects", "default_currency", server_default=None)

    for column in (
        sa.Column("carpet_area_sqft", sa.Numeric(12, 2), nullable=True),
        sa.Column("built_up_area_sqft", sa.Numeric(12, 2), nullable=True),
        sa.Column("facing", sa.String(40), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("balconies", sa.Integer(), nullable=True),
        sa.Column("amenities", sa.JSON(), nullable=True),
        sa.Column("price_components", sa.JSON(), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=True),
    ):
        op.add_column("units", column)
    for name, condition in (
        ("ck_units_carpet_area_sqft_positive", "carpet_area_sqft IS NULL OR carpet_area_sqft > 0"),
        ("ck_units_built_up_area_sqft_positive", "built_up_area_sqft IS NULL OR built_up_area_sqft > 0"),
        ("ck_units_bedrooms_nonnegative", "bedrooms IS NULL OR bedrooms >= 0"),
        ("ck_units_bathrooms_nonnegative", "bathrooms IS NULL OR bathrooms >= 0"),
        ("ck_units_balconies_nonnegative", "balconies IS NULL OR balconies >= 0"),
    ):
        op.create_check_constraint(name, "units", condition)
    op.drop_constraint("ck_units_unit_status", "units", type_="check")
    op.execute("UPDATE units SET status = 'SOLD' WHERE status = 'LEASED'")
    op.execute("UPDATE units SET status = 'HARD_HOLD' WHERE status = 'BLOCKED'")
    op.create_check_constraint(
        "ck_units_unit_status",
        "units",
        "status IN ('AVAILABLE','SOFT_HOLD','HARD_HOLD','BOOKING_INITIATED','BOOKED','SOLD','CANCELLED_RELEASED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_units_unit_status", "units", type_="check")
    op.execute("UPDATE units SET status = 'HARD_HOLD' WHERE status = 'BOOKING_INITIATED'")
    op.execute("UPDATE units SET status = 'AVAILABLE' WHERE status = 'CANCELLED_RELEASED'")
    op.create_check_constraint(
        "ck_units_unit_status",
        "units",
        "status IN ('AVAILABLE','SOFT_HOLD','HARD_HOLD','BOOKING_INITIATED','BOOKED','SOLD','LEASED','BLOCKED')",
    )
    for name in (
        "ck_units_balconies_nonnegative",
        "ck_units_bathrooms_nonnegative",
        "ck_units_bedrooms_nonnegative",
        "ck_units_built_up_area_sqft_positive",
        "ck_units_carpet_area_sqft_positive",
    ):
        op.drop_constraint(name, "units", type_="check")
    for column_name in (
        "configuration", "price_components", "amenities", "balconies", "bathrooms",
        "bedrooms", "facing", "built_up_area_sqft", "carpet_area_sqft",
    ):
        op.drop_column("units", column_name)
    for column_name in (
        "configuration", "amenities", "default_currency", "expected_possession_date",
        "launch_date", "rera_number", "country", "postal_code", "state", "city",
        "address_line2", "address_line1", "project_type",
    ):
        op.drop_column("projects", column_name)
