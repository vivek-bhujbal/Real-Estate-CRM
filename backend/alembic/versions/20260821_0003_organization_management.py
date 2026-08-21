"""Add organization management structures.

Revision ID: 20260821_0003
Revises: 20260821_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0003"
down_revision: str | None = "20260821_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("legal_name", sa.String(200), nullable=True))
    op.add_column("organizations", sa.Column("contact_email", sa.String(254), nullable=True))
    op.add_column("organizations", sa.Column("contact_phone", sa.String(30), nullable=True))
    op.add_column("organizations", sa.Column("timezone", sa.String(64), nullable=True))
    op.add_column("organizations", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("organizations", sa.Column("date_format", sa.String(24), nullable=True))

    op.create_table(
        "teams",
        sa.Column("branch_id", sa.String(36), nullable=True),
        sa.Column("manager_user_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_teams_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "branch_id"],
            ["branches.organization_id", "branches.id"],
            name="fk_teams_branch_id_branches_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "manager_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_teams_manager_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("organization_id", "code", name="uq_teams_organization_id_code"),
        sa.UniqueConstraint("organization_id", "id", name="uq_teams_organization_id_id"),
    )
    op.create_index(op.f("ix_teams_branch_id"), "teams", ["branch_id"], unique=False)
    op.create_index(
        op.f("ix_teams_manager_user_id"), "teams", ["manager_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_teams_organization_id"), "teams", ["organization_id"], unique=False
    )

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_team_members_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["teams.organization_id", "teams.id"],
            name="fk_team_members_team_id_teams_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_team_members_user_id_users_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_members")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_team_members_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "team_id", "user_id", name="uq_team_members_tenant_team_user"
        ),
    )
    op.create_index(
        op.f("ix_team_members_organization_id"),
        "team_members",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_members_tenant_user",
        "team_members",
        ["organization_id", "user_id"],
        unique=False,
    )

    op.create_table(
        "territories",
        sa.Column("branch_id", sa.String(36), nullable=True),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("manager_user_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_territories_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "branch_id"],
            ["branches.organization_id", "branches.id"],
            name="fk_territories_branch_id_branches_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "manager_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_territories_manager_user_id_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["territories.organization_id", "territories.id"],
            name="fk_territories_parent_id_territories_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_territories")),
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_territories_organization_id_code"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_territories_organization_id_id"),
    )
    op.create_index(
        op.f("ix_territories_branch_id"), "territories", ["branch_id"], unique=False
    )
    op.create_index(
        op.f("ix_territories_manager_user_id"),
        "territories",
        ["manager_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_territories_organization_id"),
        "territories",
        ["organization_id"],
        unique=False,
    )
    op.create_index(op.f("ix_territories_parent_id"), "territories", ["parent_id"], unique=False)


def downgrade() -> None:
    op.drop_table("territories")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_column("organizations", "date_format")
    op.drop_column("organizations", "currency")
    op.drop_column("organizations", "timezone")
    op.drop_column("organizations", "contact_phone")
    op.drop_column("organizations", "contact_email")
    op.drop_column("organizations", "legal_name")
