"""Add governed post-booking property lifecycle records.

Revision ID: 20260821_0015
Revises: 20260821_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0015"
down_revision: str | None = "20260821_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _owned_constraints(table: str) -> tuple[sa.Constraint, ...]:
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
        "post_booking_cases",
        *_owned_columns(),
        sa.Column("booking_id", sa.String(36), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("final_demand_letter_id", sa.String(36)),
        sa.Column("status", sa.String(22), nullable=False),
        sa.Column("readiness_snapshot", sa.JSON()),
        sa.Column("agreement_completed_at", sa.DateTime(timezone=True)),
        sa.Column("construction_ready_at", sa.DateTime(timezone=True)),
        sa.Column("final_demand_issued_at", sa.DateTime(timezone=True)),
        sa.Column("final_payment_verified_at", sa.DateTime(timezone=True)),
        sa.Column("no_dues_issued_at", sa.DateTime(timezone=True)),
        sa.Column("snagging_completed_at", sa.DateTime(timezone=True)),
        sa.Column("possession_completed_at", sa.DateTime(timezone=True)),
        sa.Column("handover_completed_at", sa.DateTime(timezone=True)),
        *_owned_constraints("post_booking_cases"),
        sa.ForeignKeyConstraint(
            ["organization_id", "booking_id"], ["bookings.organization_id", "bookings.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "final_demand_letter_id"],
            ["demand_letters.organization_id", "demand_letters.id"],
        ),
        sa.UniqueConstraint("organization_id", "booking_id", name="uq_post_booking_cases_booking"),
        sa.CheckConstraint(
            "status IN ('AGREEMENT_PENDING','CONSTRUCTION','POSSESSION_READINESS','FINAL_DEMAND',"
            "'FINAL_PAYMENT','NO_DUES','SNAGGING','POSSESSION','HANDOVER','COMPLETED')",
            name="post_booking_stage",
        ),
    )
    op.create_index(
        "ix_post_booking_cases_status", "post_booking_cases", ["organization_id", "status"]
    )

    op.create_table(
        "possession_override_requests",
        *_owned_columns(),
        sa.Column("post_booking_case_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("decided_by_user_id", sa.String(36)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("missing_conditions", sa.JSON(), nullable=False),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *_owned_constraints("possession_override_requests"),
        sa.ForeignKeyConstraint(
            ["organization_id", "post_booking_case_id"],
            ["post_booking_cases.organization_id", "post_booking_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "decided_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','UNDER_REVIEW','APPROVED','REJECTED','COMPLETED','CANCELLED')",
            name="possession_override_status",
        ),
    )
    op.create_index(
        "ix_possession_overrides_status",
        "possession_override_requests",
        ["organization_id", "status"],
    )

    for column in (
        sa.Column("post_booking_case_id", sa.String(36)),
        sa.Column("readiness_override_id", sa.String(36)),
        sa.Column("offered_by_user_id", sa.String(36)),
        sa.Column("scheduled_by_user_id", sa.String(36)),
        sa.Column("completed_by_user_id", sa.String(36)),
        sa.Column("notes", sa.Text()),
    ):
        op.add_column("possessions", column)
    _fk("possessions", "post_booking_case_id", "post_booking_cases")
    _fk("possessions", "readiness_override_id", "possession_override_requests")
    for column in ("offered_by_user_id", "scheduled_by_user_id", "completed_by_user_id"):
        _fk("possessions", column, "users")

    op.create_table(
        "no_dues_certificates",
        *_owned_columns(),
        sa.Column("post_booking_case_id", sa.String(36), nullable=False),
        sa.Column("booking_id", sa.String(36), nullable=False),
        sa.Column("issued_by_user_id", sa.String(36), nullable=False),
        sa.Column("certificate_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("financial_snapshot", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        *_owned_constraints("no_dues_certificates"),
        sa.ForeignKeyConstraint(
            ["organization_id", "post_booking_case_id"],
            ["post_booking_cases.organization_id", "post_booking_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "booking_id"], ["bookings.organization_id", "bookings.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "issued_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.UniqueConstraint("organization_id", "booking_id", name="uq_no_dues_booking"),
        sa.UniqueConstraint("organization_id", "certificate_number", name="uq_no_dues_number"),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','INACTIVE','ARCHIVED')", name="no_dues_status"),
    )

    op.create_table(
        "snag_items",
        *_owned_columns(),
        sa.Column("post_booking_case_id", sa.String(36), nullable=False),
        sa.Column("reported_by_user_id", sa.String(36), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(36)),
        sa.Column("area", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("status", sa.String(11), nullable=False),
        sa.Column("resolution_notes", sa.Text()),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        *_owned_constraints("snag_items"),
        sa.ForeignKeyConstraint(
            ["organization_id", "post_booking_case_id"],
            ["post_booking_cases.organization_id", "post_booking_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reported_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "resolved_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','RESOLVED','ACCEPTED','WAIVED')", name="snag_status"
        ),
    )
    op.create_index(
        "ix_snag_items_case_status", "snag_items", ["organization_id", "post_booking_case_id", "status"]
    )

    for column in (
        sa.Column("acknowledged_by_user_id", sa.String(36)),
        sa.Column("customer_acknowledgement_name", sa.String(160)),
        sa.Column("customer_acknowledgement_notes", sa.Text()),
        sa.Column("customer_acknowledged_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("handovers", column)
    _fk("handovers", "acknowledged_by_user_id", "users")

    op.create_table(
        "handover_documents",
        *_owned_columns(),
        sa.Column("handover_id", sa.String(36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(36)),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("file_name", sa.String(255)),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("content_type", sa.String(127)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        *_owned_constraints("handover_documents"),
        sa.ForeignKeyConstraint(
            ["organization_id", "handover_id"],
            ["handovers.organization_id", "handovers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"], ["users.organization_id", "users.id"]
        ),
        sa.UniqueConstraint(
            "organization_id", "handover_id", "document_type", name="uq_handover_document_type"
        ),
    )

    for column in (
        sa.Column("issued_by_user_id", sa.String(36)),
        sa.Column("signed_by_user_id", sa.String(36)),
        sa.Column("registered_by_user_id", sa.String(36)),
        sa.Column("file_name", sa.String(255)),
        sa.Column("content_type", sa.String(127)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("registration_number", sa.String(100)),
        sa.Column("notes", sa.Text()),
    ):
        op.add_column("agreements", column)
    for column in ("issued_by_user_id", "signed_by_user_id", "registered_by_user_id"):
        _fk("agreements", column, "users")
    op.add_column(
        "demand_letters", sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("demand_letters", "is_final")
    for column in ("issued_by_user_id", "signed_by_user_id", "registered_by_user_id"):
        op.drop_constraint(f"fk_agreements_{column}_users_tenant", "agreements", type_="foreignkey")
    for column in (
        "notes", "registration_number", "checksum_sha256", "size_bytes", "content_type",
        "file_name", "registered_by_user_id", "signed_by_user_id", "issued_by_user_id",
    ):
        op.drop_column("agreements", column)
    op.drop_table("handover_documents")
    op.drop_constraint(
        "fk_handovers_acknowledged_by_user_id_users_tenant", "handovers", type_="foreignkey"
    )
    for column in (
        "customer_acknowledged_at", "customer_acknowledgement_notes",
        "customer_acknowledgement_name", "acknowledged_by_user_id",
    ):
        op.drop_column("handovers", column)
    op.drop_index("ix_snag_items_case_status", table_name="snag_items")
    op.drop_table("snag_items")
    op.drop_table("no_dues_certificates")
    for column in ("offered_by_user_id", "scheduled_by_user_id", "completed_by_user_id"):
        op.drop_constraint(f"fk_possessions_{column}_users_tenant", "possessions", type_="foreignkey")
    op.drop_constraint(
        "fk_possessions_readiness_override_id_possession_override_requests_tenant",
        "possessions", type_="foreignkey",
    )
    op.drop_constraint(
        "fk_possessions_post_booking_case_id_post_booking_cases_tenant",
        "possessions", type_="foreignkey",
    )
    for column in (
        "notes", "completed_by_user_id", "scheduled_by_user_id", "offered_by_user_id",
        "readiness_override_id", "post_booking_case_id",
    ):
        op.drop_column("possessions", column)
    op.drop_index("ix_possession_overrides_status", table_name="possession_override_requests")
    op.drop_table("possession_override_requests")
    op.drop_index("ix_post_booking_cases_status", table_name="post_booking_cases")
    op.drop_table("post_booking_cases")
