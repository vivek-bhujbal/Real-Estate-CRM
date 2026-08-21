"""Add channel partner lifecycle, compliance, attribution, commissions and disputes.

Revision ID: 20260821_0014
Revises: 20260821_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0014"
down_revision: str | None = "20260821_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _owned_constraints(
    table: str,
) -> tuple[sa.ForeignKeyConstraint, sa.PrimaryKeyConstraint, sa.UniqueConstraint]:
    return (
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name=f"uq_{table}_organization_id_id"),
    )


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
    partner_columns = (
        sa.Column("applied_by_user_id", sa.String(36)),
        sa.Column("legal_name", sa.String(200)),
        sa.Column("partner_type", sa.String(80)),
        sa.Column("registration_number", sa.String(100)),
        sa.Column("registration_date", sa.Date()),
        sa.Column("website", sa.String(255)),
        sa.Column("address_line1", sa.String(255)),
        sa.Column("address_line2", sa.String(255)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(100)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("country", sa.String(100)),
        sa.Column("gst_number", sa.String(40)),
        sa.Column("tax_registration_name", sa.String(200)),
        sa.Column("bank_account_holder", sa.String(200)),
        sa.Column("bank_name", sa.String(160)),
        sa.Column("bank_branch", sa.String(160)),
        sa.Column("bank_ifsc", sa.String(30)),
        sa.Column("bank_account_last4", sa.String(4)),
        sa.Column("bank_account_reference", sa.String(255)),
        sa.Column("manager_user_id", sa.String(36)),
        sa.Column("approved_by_user_id", sa.String(36)),
        sa.Column("activated_by_user_id", sa.String(36)),
        sa.Column("default_commission_percent", sa.Numeric(7, 4)),
        sa.Column("lead_protection_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("application_notes", sa.Text()),
        sa.Column("review_notes", sa.Text()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("documents_verified_at", sa.DateTime(timezone=True)),
        sa.Column("agreement_completed_at", sa.DateTime(timezone=True)),
        sa.Column("approval_requested_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
    )
    for column in partner_columns:
        op.add_column("channel_partners", column)
    op.create_unique_constraint(
        "uq_channel_partners_registration",
        "channel_partners",
        ["organization_id", "registration_number"],
    )
    for column in (
        "applied_by_user_id",
        "manager_user_id",
        "approved_by_user_id",
        "activated_by_user_id",
    ):
        _tenant_fk("channel_partners", column, "users")
    # SQLAlchemy's non-native enum creates this named check in the foundation migration.
    op.drop_constraint("channel_partner_status", "channel_partners", type_="check")
    op.create_check_constraint(
        "channel_partner_status",
        "channel_partners",
        "status IN ('PENDING','APPLICATION','DOCUMENT_VERIFICATION','AGREEMENT_PENDING',"
        "'APPROVAL_PENDING','APPROVED','ACTIVE','REJECTED','SUSPENDED','INACTIVE')",
    )

    op.create_table(
        "partner_contacts",
        sa.Column("channel_partner_id", sa.String(36), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("designation", sa.String(100)),
        sa.Column("email", sa.String(254)),
        sa.Column("phone", sa.String(32)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_owned_columns(),
        *_owned_constraints("partner_contacts"),
        sa.ForeignKeyConstraint(
            ["organization_id", "channel_partner_id"],
            ["channel_partners.organization_id", "channel_partners.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "channel_partner_id", "email", name="uq_partner_contacts_email"
        ),
    )
    op.create_index(
        "ix_partner_contacts_partner", "partner_contacts", ["organization_id", "channel_partner_id"]
    )

    for table, remote_column, remote_table, unique_name in (
        ("partner_territories", "territory_id", "territories", "uq_partner_territory"),
        ("partner_projects", "project_id", "projects", "uq_partner_project"),
    ):
        op.create_table(
            table,
            sa.Column("channel_partner_id", sa.String(36), nullable=False),
            sa.Column(remote_column, sa.String(36), nullable=False),
            *_owned_columns(),
            *_owned_constraints(table),
            sa.ForeignKeyConstraint(
                ["organization_id", "channel_partner_id"],
                ["channel_partners.organization_id", "channel_partners.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["organization_id", remote_column],
                [f"{remote_table}.organization_id", f"{remote_table}.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "organization_id", "channel_partner_id", remote_column, name=unique_name
            ),
        )

    op.create_table(
        "partner_documents",
        sa.Column("channel_partner_id", sa.String(36), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("file_name", sa.String(255)),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("content_type", sa.String(127)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("uploaded_by_user_id", sa.String(36)),
        sa.Column("reviewed_by_user_id", sa.String(36)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("review_notes", sa.Text()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *_owned_columns(),
        *_owned_constraints("partner_documents"),
        sa.ForeignKeyConstraint(
            ["organization_id", "channel_partner_id"],
            ["channel_partners.organization_id", "channel_partners.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.UniqueConstraint("organization_id", "storage_key", name="uq_partner_document_storage"),
        sa.CheckConstraint(
            "status IN ('PENDING','UPLOADED','UNDER_REVIEW','VERIFIED','REJECTED','EXPIRED')",
            name="partner_document_status",
        ),
    )
    op.create_index(
        "ix_partner_documents_partner_status",
        "partner_documents",
        ["organization_id", "channel_partner_id", "status"],
    )

    op.create_table(
        "partner_agreements",
        sa.Column("channel_partner_id", sa.String(36), nullable=False),
        sa.Column("agreement_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date()),
        sa.Column("commission_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("terms_summary", sa.Text()),
        sa.Column("file_name", sa.String(255)),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("verified_by_user_id", sa.String(36)),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        *_owned_columns(),
        *_owned_constraints("partner_agreements"),
        sa.ForeignKeyConstraint(
            ["organization_id", "channel_partner_id"],
            ["channel_partners.organization_id", "channel_partners.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "verified_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.UniqueConstraint(
            "organization_id", "agreement_number", name="uq_partner_agreement_number"
        ),
        sa.CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 100", name="commission_percent_valid"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','ISSUED','SIGNED','REGISTERED','TERMINATED')",
            name="partner_agreement_status",
        ),
    )
    op.create_index(
        "ix_partner_agreements_partner_status",
        "partner_agreements",
        ["organization_id", "channel_partner_id", "status"],
    )

    op.create_table(
        "commission_structures",
        sa.Column("channel_partner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36)),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("rate_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("calculation_basis", sa.String(40), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active_scope_key", sa.String(100)),
        *_owned_columns(),
        *_owned_constraints("commission_structures"),
        sa.ForeignKeyConstraint(
            ["organization_id", "channel_partner_id"],
            ["channel_partners.organization_id", "channel_partners.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "active_scope_key", name="uq_commission_structure_active_scope"
        ),
        sa.CheckConstraint("rate_percent >= 0 AND rate_percent <= 100", name="rate_percent_valid"),
    )
    op.create_index(
        "ix_commission_structures_partner",
        "commission_structures",
        ["organization_id", "channel_partner_id", "is_active"],
    )

    for column in (
        sa.Column("registered_by_user_id", sa.String(36)),
        sa.Column("approved_by_user_id", sa.String(36)),
        sa.Column("active_email_key", sa.String(254)),
        sa.Column("active_phone_key", sa.String(32)),
        sa.Column("registration_notes", sa.Text()),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("partner_leads", column)
    _tenant_fk("partner_leads", "registered_by_user_id", "users")
    _tenant_fk("partner_leads", "approved_by_user_id", "users")
    op.create_unique_constraint(
        "uq_partner_lead_active_email", "partner_leads", ["organization_id", "active_email_key"]
    )
    op.create_unique_constraint(
        "uq_partner_lead_active_phone", "partner_leads", ["organization_id", "active_phone_key"]
    )

    for column in (
        sa.Column("requested_by_user_id", sa.String(36)),
        sa.Column("notes", sa.Text()),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("commission_payouts", column)
    _tenant_fk("commission_payouts", "requested_by_user_id", "users")
    op.add_column("commissions", sa.Column("commission_structure_id", sa.String(36)))
    _tenant_fk("commissions", "commission_structure_id", "commission_structures")

    op.create_table(
        "partner_disputes",
        sa.Column("channel_partner_id", sa.String(36), nullable=False),
        sa.Column("partner_lead_id", sa.String(36)),
        sa.Column("booking_id", sa.String(36)),
        sa.Column("commission_id", sa.String(36)),
        sa.Column("commission_payout_id", sa.String(36)),
        sa.Column("raised_by_user_id", sa.String(36), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(36)),
        sa.Column("resolved_by_user_id", sa.String(36)),
        sa.Column("dispute_number", sa.String(80), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text()),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_owned_columns(),
        *_owned_constraints("partner_disputes"),
        sa.ForeignKeyConstraint(
            ["organization_id", "channel_partner_id"],
            ["channel_partners.organization_id", "channel_partners.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "partner_lead_id"],
            ["partner_leads.organization_id", "partner_leads.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "booking_id"], ["bookings.organization_id", "bookings.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "commission_id"], ["commissions.organization_id", "commissions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "commission_payout_id"],
            ["commission_payouts.organization_id", "commission_payouts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "raised_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "assigned_to_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "resolved_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.UniqueConstraint("organization_id", "dispute_number", name="uq_partner_dispute_number"),
        sa.CheckConstraint(
            "status IN ('REQUESTED','UNDER_REVIEW','APPROVED','REJECTED','COMPLETED','CANCELLED')",
            name="partner_dispute_status",
        ),
    )
    op.create_index(
        "ix_partner_disputes_partner_status",
        "partner_disputes",
        ["organization_id", "channel_partner_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("partner_disputes")
    op.drop_constraint(
        "fk_commissions_commission_structure_id_commission_structures_tenant",
        "commissions",
        type_="foreignkey",
    )
    op.drop_column("commissions", "commission_structure_id")
    op.drop_constraint(
        "fk_commission_payouts_requested_by_user_id_users_tenant",
        "commission_payouts",
        type_="foreignkey",
    )
    for column in (
        "rejected_at",
        "approved_at",
        "requested_at",
        "decision_notes",
        "notes",
        "requested_by_user_id",
    ):
        op.drop_column("commission_payouts", column)
    op.drop_constraint("uq_partner_lead_active_phone", "partner_leads", type_="unique")
    op.drop_constraint("uq_partner_lead_active_email", "partner_leads", type_="unique")
    op.drop_constraint(
        "fk_partner_leads_approved_by_user_id_users_tenant", "partner_leads", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_partner_leads_registered_by_user_id_users_tenant", "partner_leads", type_="foreignkey"
    )
    for column in (
        "decided_at",
        "decision_notes",
        "registration_notes",
        "active_phone_key",
        "active_email_key",
        "approved_by_user_id",
        "registered_by_user_id",
    ):
        op.drop_column("partner_leads", column)
    for table in (
        "commission_structures",
        "partner_agreements",
        "partner_documents",
        "partner_projects",
        "partner_territories",
        "partner_contacts",
    ):
        op.drop_table(table)
    op.drop_constraint("channel_partner_status", "channel_partners", type_="check")
    op.create_check_constraint(
        "channel_partner_status",
        "channel_partners",
        "status IN ('PENDING','ACTIVE','SUSPENDED','INACTIVE')",
    )
    for column in (
        "activated_at",
        "approved_at",
        "approval_requested_at",
        "agreement_completed_at",
        "documents_verified_at",
        "applied_at",
        "rejection_reason",
        "review_notes",
        "application_notes",
        "lead_protection_days",
        "default_commission_percent",
        "activated_by_user_id",
        "approved_by_user_id",
        "manager_user_id",
        "bank_account_reference",
        "bank_account_last4",
        "bank_ifsc",
        "bank_branch",
        "bank_name",
        "bank_account_holder",
        "tax_registration_name",
        "gst_number",
        "country",
        "postal_code",
        "state",
        "city",
        "address_line2",
        "address_line1",
        "website",
        "registration_date",
        "registration_number",
        "partner_type",
        "legal_name",
        "applied_by_user_id",
    ):
        op.drop_column("channel_partners", column)
