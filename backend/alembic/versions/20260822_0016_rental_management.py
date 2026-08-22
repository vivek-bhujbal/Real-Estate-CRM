"""Add isolated rental property, lease, billing, move, and renewal domain.

Revision ID: 20260822_0016
Revises: 20260821_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0016"
down_revision: str | None = "20260821_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned() -> tuple[sa.Column, ...]:
    return (
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _constraints(table: str) -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name=f"uq_{table}_organization_id_id"),
    )


def _fk(table: str, column: str, remote: str, *, ondelete: str = "RESTRICT") -> None:
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
        "rental_properties",
        *_owned(),
        sa.Column("manager_user_id", sa.String(36)),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("property_type", sa.String(80), nullable=False),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255)),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("bedrooms", sa.Integer()),
        sa.Column("bathrooms", sa.Integer()),
        sa.Column("area_sqft", sa.Numeric(12, 2)),
        sa.Column("amenities", sa.JSON()),
        sa.Column("default_monthly_rent", sa.Numeric(18, 2), nullable=False),
        sa.Column("default_security_deposit", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(11), nullable=False),
        sa.Column("notes", sa.Text()),
        *_constraints("rental_properties"),
        sa.ForeignKeyConstraint(
            ["organization_id", "manager_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_rental_properties_manager_user_id_users_tenant",
        ),
        sa.UniqueConstraint("organization_id", "code", name="uq_rental_properties_code"),
        sa.CheckConstraint(
            "default_monthly_rent >= 0 AND default_security_deposit >= 0",
            name="rental_default_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('AVAILABLE','RESERVED','OCCUPIED','MAINTENANCE','INACTIVE')",
            name="rental_property_status",
        ),
    )
    op.create_index(
        "ix_rental_properties_status", "rental_properties", ["organization_id", "status"]
    )

    for column in (
        sa.Column("user_id", sa.String(36)),
        sa.Column("alternate_phone", sa.String(32)),
        sa.Column("identity_type", sa.String(50)),
        sa.Column("identity_reference", sa.String(120)),
        sa.Column("address", sa.Text()),
        sa.Column("emergency_contact_name", sa.String(160)),
        sa.Column("emergency_contact_phone", sa.String(32)),
    ):
        op.add_column("tenants", column)
    _fk("tenants", "user_id", "users")
    op.create_unique_constraint("uq_tenants_user", "tenants", ["organization_id", "user_id"])

    op.alter_column("leases", "unit_id", existing_type=sa.String(36), nullable=True)
    op.drop_constraint("uq_leases_tenant_active_unit", "leases", type_="unique")
    for column in (
        sa.Column("property_id", sa.String(36)),
        sa.Column("created_by_user_id", sa.String(36)),
        sa.Column("approved_by_user_id", sa.String(36)),
        sa.Column("active_property_key", sa.String(36)),
        sa.Column("rent_due_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notice_period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("terms", sa.Text()),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("terminated_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("leases", column)
    _fk("leases", "property_id", "rental_properties")
    _fk("leases", "created_by_user_id", "users")
    _fk("leases", "approved_by_user_id", "users")
    op.create_unique_constraint(
        "uq_leases_active_rental_property", "leases", ["organization_id", "active_property_key"]
    )
    op.create_check_constraint(
        "sales_rental_reference_exclusive",
        "leases",
        "NOT (unit_id IS NOT NULL AND property_id IS NOT NULL)",
    )
    op.drop_constraint("lease_status", "leases", type_="check")
    op.alter_column(
        "leases", "status", existing_type=sa.String(10), type_=sa.String(18), nullable=False
    )
    op.create_check_constraint(
        "lease_status",
        "leases",
        "status IN ('DRAFT','PENDING_SIGNATURE','SIGNED','MOVE_IN_PENDING','ACTIVE',"
        "'NOTICE_GIVEN','MOVE_OUT_PENDING','EXPIRED','TERMINATED','RENEWED')",
    )

    op.create_table(
        "lease_documents",
        *_owned(),
        sa.Column("lease_id", sa.String(36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(36)),
        sa.Column("reviewed_by_user_id", sa.String(36)),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("file_name", sa.String(255)),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("content_type", sa.String(127)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *_constraints("lease_documents"),
        sa.ForeignKeyConstraint(
            ["organization_id", "lease_id"],
            ["leases.organization_id", "leases.id"],
            name="fk_lease_documents_lease_id_leases_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_documents_uploaded_by_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_documents_reviewed_by_user_id_users_tenant",
        ),
        sa.UniqueConstraint(
            "organization_id", "lease_id", "document_type", "version", name="uq_lease_doc_version"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','UPLOADED','UNDER_REVIEW','VERIFIED','REJECTED','EXPIRED')",
            name="lease_document_status",
        ),
    )
    op.create_index(
        "ix_lease_documents_status", "lease_documents", ["organization_id", "lease_id", "status"]
    )

    op.create_table(
        "rent_schedule_items",
        *_owned(),
        sa.Column("lease_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(14), nullable=False),
        *_constraints("rent_schedule_items"),
        sa.ForeignKeyConstraint(
            ["organization_id", "lease_id"],
            ["leases.organization_id", "leases.id"],
            name="fk_rent_schedule_items_lease_id_leases_tenant",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "lease_id", "sequence", name="uq_rent_schedule_sequence"
        ),
        sa.CheckConstraint("amount >= 0", name="rent_schedule_amount_nonnegative"),
        sa.CheckConstraint(
            "status IN ('SCHEDULED','INVOICED','PARTIALLY_PAID','PAID','OVERDUE','WAIVED')",
            name="rent_schedule_status",
        ),
    )
    op.create_index(
        "ix_rent_schedule_due_status",
        "rent_schedule_items",
        ["organization_id", "due_date", "status"],
    )

    op.create_table(
        "lease_renewals",
        *_owned(),
        sa.Column("lease_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("decided_by_user_id", sa.String(36)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("previous_end_date", sa.Date(), nullable=False),
        sa.Column("proposed_end_date", sa.Date(), nullable=False),
        sa.Column("previous_monthly_rent", sa.Numeric(18, 2), nullable=False),
        sa.Column("proposed_monthly_rent", sa.Numeric(18, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        *_constraints("lease_renewals"),
        sa.ForeignKeyConstraint(
            ["organization_id", "lease_id"],
            ["leases.organization_id", "leases.id"],
            name="fk_lease_renewals_lease_id_leases_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_renewals_requested_by_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "decided_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_renewals_decided_by_user_id_users_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','UNDER_REVIEW','APPROVED','REJECTED','COMPLETED','CANCELLED')",
            name="lease_renewal_status",
        ),
    )
    op.create_index("ix_lease_renewals_status", "lease_renewals", ["organization_id", "status"])

    op.create_table(
        "lease_moves",
        *_owned(),
        sa.Column("lease_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36)),
        sa.Column("completed_by_user_id", sa.String(36)),
        sa.Column("move_type", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checklist", sa.JSON()),
        sa.Column("meter_readings", sa.JSON()),
        sa.Column("notes", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_constraints("lease_moves"),
        sa.ForeignKeyConstraint(
            ["organization_id", "lease_id"],
            ["leases.organization_id", "leases.id"],
            name="fk_lease_moves_lease_id_leases_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_moves_requested_by_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "approved_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_moves_approved_by_user_id_users_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "completed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lease_moves_completed_by_user_id_users_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','UNDER_REVIEW','APPROVED','REJECTED','COMPLETED','CANCELLED')",
            name="lease_move_status",
        ),
    )
    op.create_index(
        "ix_lease_moves_status", "lease_moves", ["organization_id", "move_type", "status"]
    )

    for column in (
        sa.Column("rent_schedule_item_id", sa.String(36)),
        sa.Column("created_by_user_id", sa.String(36)),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("rental_invoices", column)
    _fk("rental_invoices", "rent_schedule_item_id", "rent_schedule_items")
    _fk("rental_invoices", "created_by_user_id", "users")

    op.add_column("rent_payments", sa.Column("submitted_by_user_id", sa.String(36)))
    op.add_column("rent_payments", sa.Column("rejection_reason", sa.Text()))
    _fk("rent_payments", "submitted_by_user_id", "users")

    op.alter_column("maintenance_records", "unit_id", existing_type=sa.String(36), nullable=True)
    op.add_column("maintenance_records", sa.Column("rental_property_id", sa.String(36)))
    op.add_column("maintenance_records", sa.Column("reported_by_user_id", sa.String(36)))
    _fk("maintenance_records", "rental_property_id", "rental_properties")
    _fk("maintenance_records", "reported_by_user_id", "users")
    op.create_check_constraint(
        "maintenance_property_required",
        "maintenance_records",
        "unit_id IS NOT NULL OR rental_property_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_maintenance_records_maintenance_property_required",
        "maintenance_records",
        type_="check",
    )
    for column in ("reported_by_user_id", "rental_property_id"):
        referenced_table = "users" if column == "reported_by_user_id" else "rental_properties"
        op.drop_constraint(
            f"fk_maintenance_records_{column}_{referenced_table}_tenant",
            "maintenance_records",
            type_="foreignkey",
        )
        op.drop_column("maintenance_records", column)
    op.alter_column("maintenance_records", "unit_id", existing_type=sa.String(36), nullable=False)
    op.drop_constraint(
        "fk_rent_payments_submitted_by_user_id_users_tenant", "rent_payments", type_="foreignkey"
    )
    op.drop_column("rent_payments", "rejection_reason")
    op.drop_column("rent_payments", "submitted_by_user_id")
    for column, remote in (
        ("rent_schedule_item_id", "rent_schedule_items"),
        ("created_by_user_id", "users"),
    ):
        op.drop_constraint(
            f"fk_rental_invoices_{column}_{remote}_tenant", "rental_invoices", type_="foreignkey"
        )
    for column in ("issued_at", "paid_amount", "created_by_user_id", "rent_schedule_item_id"):
        op.drop_column("rental_invoices", column)
    op.drop_index("ix_lease_moves_status", table_name="lease_moves")
    op.drop_table("lease_moves")
    op.drop_index("ix_lease_renewals_status", table_name="lease_renewals")
    op.drop_table("lease_renewals")
    op.drop_index("ix_rent_schedule_due_status", table_name="rent_schedule_items")
    op.drop_table("rent_schedule_items")
    op.drop_index("ix_lease_documents_status", table_name="lease_documents")
    op.drop_table("lease_documents")
    op.drop_constraint("lease_status", "leases", type_="check")
    op.execute(
        "UPDATE leases SET status = CASE "
        "WHEN status IN ('ACTIVE','NOTICE_GIVEN','MOVE_OUT_PENDING','SIGNED',"
        "'MOVE_IN_PENDING') THEN 'ACTIVE' "
        "WHEN status IN ('TERMINATED','EXPIRED','RENEWED') THEN status "
        "ELSE 'DRAFT' END"
    )
    op.alter_column(
        "leases", "status", existing_type=sa.String(18), type_=sa.String(10), nullable=False
    )
    op.create_check_constraint(
        "lease_status",
        "leases",
        "status IN ('DRAFT','ACTIVE','EXPIRED','TERMINATED','RENEWED')",
    )
    op.drop_constraint("uq_leases_active_rental_property", "leases", type_="unique")
    op.drop_constraint("ck_leases_sales_rental_reference_exclusive", "leases", type_="check")
    for column in ("property_id", "created_by_user_id", "approved_by_user_id"):
        referenced_table = "rental_properties" if column == "property_id" else "users"
        op.drop_constraint(
            f"fk_leases_{column}_{referenced_table}_tenant",
            "leases",
            type_="foreignkey",
        )
    for column in (
        "terminated_at",
        "activated_at",
        "signed_at",
        "issued_at",
        "terms",
        "notice_period_days",
        "rent_due_day",
        "active_property_key",
        "approved_by_user_id",
        "created_by_user_id",
        "property_id",
    ):
        op.drop_column("leases", column)
    op.create_unique_constraint(
        "uq_leases_tenant_active_unit", "leases", ["organization_id", "active_unit_key"]
    )
    op.alter_column("leases", "unit_id", existing_type=sa.String(36), nullable=False)
    op.drop_constraint("uq_tenants_user", "tenants", type_="unique")
    op.drop_constraint("fk_tenants_user_id_users_tenant", "tenants", type_="foreignkey")
    for column in (
        "emergency_contact_phone",
        "emergency_contact_name",
        "address",
        "identity_reference",
        "identity_type",
        "alternate_phone",
        "user_id",
    ):
        op.drop_column("tenants", column)
    op.drop_index("ix_rental_properties_status", table_name="rental_properties")
    op.drop_table("rental_properties")
