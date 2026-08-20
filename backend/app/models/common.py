from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationOwnedMixin:
    """Adds the mandatory tenant discriminator used by every tenant-owned row."""

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )


def tenant_unique(table_name: str) -> UniqueConstraint:
    """Makes (organization_id, id) a valid composite FK target."""

    return UniqueConstraint("organization_id", "id", name=f"uq_{table_name}_organization_id_id")


def tenant_fk(
    table_name: str,
    local_column: str,
    remote_table: str,
    *,
    ondelete: str = "RESTRICT",
    name: str | None = None,
) -> ForeignKeyConstraint:
    """Prevents a child row from referencing a row in another organization."""

    return ForeignKeyConstraint(
        ["organization_id", local_column],
        [f"{remote_table}.organization_id", f"{remote_table}.id"],
        name=name or f"fk_{table_name}_{local_column}_{remote_table}_tenant",
        ondelete=ondelete,
    )


def status_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=max(len(item.value) for item in enum_type),
    )
