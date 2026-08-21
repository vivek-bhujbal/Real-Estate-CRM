"""Add secure versioned customer and booking document management.

Revision ID: 20260821_0010
Revises: 20260821_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0010"
down_revision: str | None = "20260821_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

old_status = sa.Enum(
    "PENDING",
    "VERIFIED",
    "REJECTED",
    "EXPIRED",
    name="customer_document_status",
    native_enum=False,
    create_constraint=True,
)
new_status = sa.Enum(
    "PENDING",
    "UPLOADED",
    "UNDER_REVIEW",
    "VERIFIED",
    "REJECTED",
    "EXPIRED",
    name="customer_document_status",
    native_enum=False,
    create_constraint=True,
)
old_booking_status = sa.Enum(
    "PENDING",
    "VERIFIED",
    "REJECTED",
    "EXPIRED",
    name="booking_document_status",
    native_enum=False,
    create_constraint=True,
)
new_booking_status = sa.Enum(
    "PENDING",
    "UPLOADED",
    "UNDER_REVIEW",
    "VERIFIED",
    "REJECTED",
    "EXPIRED",
    name="booking_document_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.drop_constraint("booking_document_status", "booking_documents", type_="check")
    op.alter_column(
        "booking_documents",
        "status",
        existing_type=old_booking_status,
        type_=new_booking_status,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "booking_document_status",
        "booking_documents",
        "status IN ('PENDING','UPLOADED','UNDER_REVIEW','VERIFIED','REJECTED','EXPIRED')",
    )
    op.drop_constraint("customer_document_status", "customer_documents", type_="check")
    op.alter_column(
        "customer_documents",
        "status",
        existing_type=old_status,
        type_=new_status,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "customer_document_status",
        "customer_documents",
        "status IN ('PENDING','UPLOADED','UNDER_REVIEW','VERIFIED','REJECTED','EXPIRED')",
    )
    op.alter_column("customer_documents", "file_name", existing_type=sa.String(255), nullable=True)
    op.alter_column("customer_documents", "storage_key", existing_type=sa.String(512), nullable=True)
    op.alter_column("customer_documents", "content_type", existing_type=sa.String(127), nullable=True)
    op.alter_column("customer_documents", "size_bytes", existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        "customer_documents", "checksum_sha256", existing_type=sa.String(64), nullable=True
    )

    op.add_column("customer_documents", sa.Column("booking_id", sa.String(36), nullable=True))
    op.add_column(
        "customer_documents", sa.Column("reviewed_by_user_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "customer_documents", sa.Column("document_set_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "customer_documents", sa.Column("supersedes_document_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "customer_documents", sa.Column("current_version_key", sa.String(36), nullable=True)
    )
    op.add_column(
        "customer_documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "customer_documents",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("customer_documents", sa.Column("expiry_date", sa.Date(), nullable=True))
    op.add_column(
        "customer_documents", sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "customer_documents",
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "customer_documents", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("customer_documents", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("customer_documents", sa.Column("review_notes", sa.Text(), nullable=True))

    # Existing rows already contain a file, so normalize them as uploaded version one records.
    op.execute(
        "UPDATE customer_documents SET document_set_id = id, current_version_key = id, "
        "uploaded_at = created_at, status = CASE WHEN status = 'PENDING' THEN 'UPLOADED' "
        "ELSE status END"
    )
    op.alter_column(
        "customer_documents", "document_set_id", existing_type=sa.String(36), nullable=False
    )
    op.alter_column("customer_documents", "version", server_default=None)
    op.alter_column("customer_documents", "is_current", server_default=None)

    op.create_foreign_key(
        "fk_customer_documents_booking_id_bookings_tenant",
        "customer_documents",
        "bookings",
        ["organization_id", "booking_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_customer_documents_reviewed_by_user_id_users_tenant",
        "customer_documents",
        "users",
        ["organization_id", "reviewed_by_user_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_customer_documents_supersedes_document_id_customer_documents_tenant",
        "customer_documents",
        "customer_documents",
        ["organization_id", "supersedes_document_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_customer_documents_tenant_set_version",
        "customer_documents",
        ["organization_id", "document_set_id", "version"],
    )
    op.create_unique_constraint(
        "uq_customer_documents_tenant_current_version",
        "customer_documents",
        ["organization_id", "current_version_key"],
    )
    op.create_check_constraint(
        "ck_customer_documents_version_positive", "customer_documents", "version > 0"
    )
    op.create_check_constraint(
        "ck_customer_documents_size_nonnegative",
        "customer_documents",
        "size_bytes IS NULL OR size_bytes >= 0",
    )
    op.create_index(
        "ix_customer_documents_tenant_booking",
        "customer_documents",
        ["organization_id", "booking_id"],
    )
    op.create_index(
        "ix_customer_documents_tenant_status",
        "customer_documents",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.execute(
        "UPDATE customer_documents SET status = 'PENDING' "
        "WHERE status IN ('UPLOADED','UNDER_REVIEW')"
    )
    op.execute(
        "UPDATE booking_documents SET status = 'PENDING' "
        "WHERE status IN ('UPLOADED','UNDER_REVIEW')"
    )
    op.drop_index("ix_customer_documents_tenant_status", table_name="customer_documents")
    op.drop_index("ix_customer_documents_tenant_booking", table_name="customer_documents")
    op.drop_constraint("ck_customer_documents_size_nonnegative", "customer_documents", type_="check")
    op.drop_constraint("ck_customer_documents_version_positive", "customer_documents", type_="check")
    op.drop_constraint(
        "uq_customer_documents_tenant_current_version", "customer_documents", type_="unique"
    )
    op.drop_constraint(
        "uq_customer_documents_tenant_set_version", "customer_documents", type_="unique"
    )
    op.drop_constraint(
        "fk_customer_documents_supersedes_document_id_customer_documents_tenant",
        "customer_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_customer_documents_reviewed_by_user_id_users_tenant",
        "customer_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_customer_documents_booking_id_bookings_tenant",
        "customer_documents",
        type_="foreignkey",
    )
    for column in (
        "review_notes",
        "rejection_reason",
        "reviewed_at",
        "review_started_at",
        "uploaded_at",
        "expiry_date",
        "is_current",
        "version",
        "current_version_key",
        "supersedes_document_id",
        "document_set_id",
        "reviewed_by_user_id",
        "booking_id",
    ):
        op.drop_column("customer_documents", column)
    op.alter_column("customer_documents", "checksum_sha256", existing_type=sa.String(64), nullable=False)
    op.alter_column("customer_documents", "size_bytes", existing_type=sa.Integer(), nullable=False)
    op.alter_column("customer_documents", "content_type", existing_type=sa.String(127), nullable=False)
    op.alter_column("customer_documents", "storage_key", existing_type=sa.String(512), nullable=False)
    op.alter_column("customer_documents", "file_name", existing_type=sa.String(255), nullable=False)
    op.drop_constraint("customer_document_status", "customer_documents", type_="check")
    op.alter_column(
        "customer_documents",
        "status",
        existing_type=new_status,
        type_=old_status,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "customer_document_status",
        "customer_documents",
        "status IN ('PENDING','VERIFIED','REJECTED','EXPIRED')",
    )
    op.drop_constraint("booking_document_status", "booking_documents", type_="check")
    op.alter_column(
        "booking_documents",
        "status",
        existing_type=new_booking_status,
        type_=old_booking_status,
        existing_nullable=False,
    )
    op.create_check_constraint(
        "booking_document_status",
        "booking_documents",
        "status IN ('PENDING','VERIFIED','REJECTED','EXPIRED')",
    )
