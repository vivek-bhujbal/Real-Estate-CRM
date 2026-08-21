"""Add complete lead-management structures.

Revision ID: 20260821_0004
Revises: 20260821_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0004"
down_revision: str | None = "20260821_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned_columns() -> list[sa.Column]:
    return [
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "lost_lead_reasons",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_owned_columns(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_lost_lead_reasons_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lost_lead_reasons")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_lost_lead_reasons_organization_id_code"
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_lost_lead_reasons_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_lost_lead_reasons_organization_id"),
        "lost_lead_reasons",
        ["organization_id"],
    )

    op.create_table(
        "lead_import_batches",
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), nullable=False),
        sa.Column("error_rows", sa.Integer(), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=True),
        sa.Column("errors_json", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_owned_columns(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_lead_import_batches_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lead_import_batches_created_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_import_batches")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_lead_import_batches_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_lead_import_batches_organization_id"),
        "lead_import_batches",
        ["organization_id"],
    )
    op.create_index(
        "ix_lead_import_batches_tenant_created",
        "lead_import_batches",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "lead_score_rules",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("operator", sa.String(20), nullable=False),
        sa.Column("comparison_value", sa.String(255), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_owned_columns(),
        sa.CheckConstraint("points >= -100 AND points <= 100", name="ck_lead_score_rules_points_range"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_lead_score_rules_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_score_rules")),
        sa.UniqueConstraint("organization_id", "name", name="uq_lead_score_rules_tenant_name"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_lead_score_rules_organization_id_id"
        ),
    )
    op.create_index(
        op.f("ix_lead_score_rules_organization_id"),
        "lead_score_rules",
        ["organization_id"],
    )

    for column in (
        sa.Column("branch_id", sa.String(36), nullable=True),
        sa.Column("lost_reason_id", sa.String(36), nullable=True),
        sa.Column("import_batch_id", sa.String(36), nullable=True),
        sa.Column("duplicate_of_lead_id", sa.String(36), nullable=True),
        sa.Column("alternate_phone", sa.String(32), nullable=True),
        sa.Column("normalized_email", sa.String(254), nullable=True),
        sa.Column("normalized_phone", sa.String(32), nullable=True),
        sa.Column("company_name", sa.String(160), nullable=True),
        sa.Column("preferred_location", sa.String(200), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("budget_min", sa.Numeric(18, 2), nullable=True),
        sa.Column("budget_max", sa.Numeric(18, 2), nullable=True),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("qualification_notes", sa.Text(), nullable=True),
        sa.Column("lost_notes", sa.Text(), nullable=True),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("leads", column)

    op.create_check_constraint("ck_leads_score_range", "leads", "score >= 0 AND score <= 100")
    op.create_check_constraint(
        "ck_leads_budget_range",
        "leads",
        "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
    )
    lead_foreign_keys = (
        ("branch_id", "branches", "fk_leads_branch_id_branches_tenant"),
        ("lost_reason_id", "lost_lead_reasons", "fk_leads_lost_reason_id_lost_lead_reasons_tenant"),
        ("import_batch_id", "lead_import_batches", "fk_leads_import_batch_id_lead_import_batches_tenant"),
        ("duplicate_of_lead_id", "leads", "fk_leads_duplicate_of_lead_id_leads_tenant"),
    )
    for column_name, remote_table, constraint_name in lead_foreign_keys:
        op.create_foreign_key(
            constraint_name,
            "leads",
            remote_table,
            ["organization_id", column_name],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_index(op.f(f"ix_leads_{column_name}"), "leads", [column_name])
    for index_name, columns in (
        ("ix_leads_tenant_normalized_phone", ["organization_id", "normalized_phone"]),
        ("ix_leads_tenant_normalized_email", ["organization_id", "normalized_email"]),
        ("ix_leads_tenant_owner_status", ["organization_id", "owner_user_id", "status"]),
        ("ix_leads_tenant_follow_up", ["organization_id", "next_follow_up_at"]),
    ):
        op.create_index(index_name, "leads", columns)

    op.add_column("lead_activities", sa.Column("due_at", sa.DateTime(timezone=True)))
    op.add_column("lead_activities", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("lead_activities", sa.Column("outcome", sa.String(255)))
    op.add_column(
        "lead_activities",
        sa.Column("is_completed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "lead_notes",
        sa.Column("lead_id", sa.String(36), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        *_owned_columns(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_lead_notes_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "lead_id"],
            ["leads.organization_id", "leads.id"],
            name="fk_lead_notes_lead_id_leads_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_lead_notes_created_by_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_notes")),
        sa.UniqueConstraint("organization_id", "id", name="uq_lead_notes_organization_id_id"),
    )
    op.create_index(op.f("ix_lead_notes_organization_id"), "lead_notes", ["organization_id"])
    op.create_index(
        "ix_lead_notes_tenant_lead_created",
        "lead_notes",
        ["organization_id", "lead_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("lead_notes")
    op.drop_column("lead_activities", "is_completed")
    op.drop_column("lead_activities", "outcome")
    op.drop_column("lead_activities", "completed_at")
    op.drop_column("lead_activities", "due_at")

    for index_name in (
        "ix_leads_tenant_follow_up",
        "ix_leads_tenant_owner_status",
        "ix_leads_tenant_normalized_email",
        "ix_leads_tenant_normalized_phone",
    ):
        op.drop_index(index_name, table_name="leads")
    lead_foreign_keys = (
        ("duplicate_of_lead_id", "fk_leads_duplicate_of_lead_id_leads_tenant"),
        ("import_batch_id", "fk_leads_import_batch_id_lead_import_batches_tenant"),
        ("lost_reason_id", "fk_leads_lost_reason_id_lost_lead_reasons_tenant"),
        ("branch_id", "fk_leads_branch_id_branches_tenant"),
    )
    for column_name, constraint_name in lead_foreign_keys:
        op.drop_index(op.f(f"ix_leads_{column_name}"), table_name="leads")
        op.drop_constraint(constraint_name, "leads", type_="foreignkey")
    op.drop_constraint("ck_leads_budget_range", "leads", type_="check")
    op.drop_constraint("ck_leads_score_range", "leads", type_="check")
    for column_name in (
        "next_follow_up_at",
        "last_activity_at",
        "converted_at",
        "qualified_at",
        "lost_notes",
        "qualification_notes",
        "score_breakdown",
        "score",
        "budget_max",
        "budget_min",
        "requirements",
        "preferred_location",
        "company_name",
        "normalized_phone",
        "normalized_email",
        "alternate_phone",
        "duplicate_of_lead_id",
        "import_batch_id",
        "lost_reason_id",
        "branch_id",
    ):
        op.drop_column("leads", column_name)
    op.drop_table("lead_score_rules")
    op.drop_table("lead_import_batches")
    op.drop_table("lost_lead_reasons")
