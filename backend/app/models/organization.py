from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import OrganizationOwnedMixin, tenant_fk, tenant_unique


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class Branch(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "code", name="uq_branches_organization_id_code"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Department(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "branch_id", "branches"),
        UniqueConstraint(
            "organization_id", "branch_id", "name", name="uq_departments_tenant_branch_name"
        ),
    )

    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "branch_id", "branches"),
        tenant_fk(__tablename__, "department_id", "departments"),
        UniqueConstraint("organization_id", "email", name="uq_users_organization_id_email"),
    )

    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="users")


class Role(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "name", name="uq_roles_organization_id_name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Permission(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (
        tenant_unique(__tablename__),
        UniqueConstraint("organization_id", "code", name="uq_permissions_organization_id_code"),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class UserRole(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "user_id", "users", ondelete="CASCADE"),
        tenant_fk(__tablename__, "role_id", "roles", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id", "user_id", "role_id", name="uq_user_roles_tenant_user_role"
        ),
        Index("ix_user_roles_tenant_user", "organization_id", "user_id"),
    )

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role_id: Mapped[str] = mapped_column(String(36), nullable=False)


class RolePermission(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "role_id", "roles", ondelete="CASCADE"),
        tenant_fk(__tablename__, "permission_id", "permissions", ondelete="CASCADE"),
        UniqueConstraint(
            "organization_id",
            "role_id",
            "permission_id",
            name="uq_role_permissions_tenant_role_permission",
        ),
        Index("ix_role_permissions_tenant_role", "organization_id", "role_id"),
    )

    role_id: Mapped[str] = mapped_column(String(36), nullable=False)
    permission_id: Mapped[str] = mapped_column(String(36), nullable=False)


class RefreshToken(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "user_id", "users", ondelete="CASCADE"),
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_tenant_user", "organization_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


class PasswordResetToken(OrganizationOwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        tenant_unique(__tablename__),
        tenant_fk(__tablename__, "user_id", "users", ondelete="CASCADE"),
        UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
        Index(
            "ix_password_reset_tokens_tenant_user_active",
            "organization_id",
            "user_id",
            "consumed_at",
        ),
        Index("ix_password_reset_tokens_expiry", "expires_at"),
    )

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
