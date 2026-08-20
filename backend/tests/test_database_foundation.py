from pathlib import Path

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.db import Base

EXPECTED_TABLES = {
    "agreements",
    "audit_logs",
    "booking_approvals",
    "booking_documents",
    "bookings",
    "branches",
    "cancellations",
    "channel_partners",
    "commission_payouts",
    "commissions",
    "construction_updates",
    "customer_documents",
    "customer_ledger_entries",
    "customers",
    "demand_letters",
    "departments",
    "floors",
    "handovers",
    "installments",
    "lead_activities",
    "lead_assignments",
    "lead_sources",
    "leads",
    "leases",
    "maintenance_records",
    "notifications",
    "organizations",
    "partner_leads",
    "password_reset_tokens",
    "payment_plans",
    "payments",
    "permissions",
    "possessions",
    "price_lists",
    "projects",
    "quotation_items",
    "quotations",
    "receipts",
    "refresh_tokens",
    "refunds",
    "rent_payments",
    "rental_invoices",
    "role_permissions",
    "roles",
    "service_requests",
    "site_visits",
    "tenants",
    "towers",
    "unit_holds",
    "unit_transfers",
    "units",
    "user_roles",
    "users",
}


def test_complete_foundation_table_inventory() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_tenant_table_has_isolation_and_timestamps() -> None:
    for table_name, table in Base.metadata.tables.items():
        if table_name == "organizations":
            continue

        assert "organization_id" in table.c, table_name
        assert "created_at" in table.c, table_name
        assert any(
            isinstance(constraint, UniqueConstraint)
            and tuple(column.name for column in constraint.columns) == ("organization_id", "id")
            for constraint in table.constraints
        ), table_name


def test_domain_foreign_keys_are_tenant_scoped() -> None:
    for table_name, table in Base.metadata.tables.items():
        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            remote_tables = {element.column.table.name for element in constraint.elements}
            if remote_tables == {"organizations"}:
                continue

            local_columns = {column.name for column in constraint.columns}
            assert "organization_id" in local_columns, (table_name, constraint.name)
            assert len(remote_tables) == 1, (table_name, constraint.name)
            assert {element.column.name for element in constraint.elements} == {
                "organization_id",
                "id",
            }, (table_name, constraint.name)


def test_migrations_are_explicit_and_data_free() -> None:
    migration_dir = Path(__file__).parents[1] / "alembic" / "versions"
    migrations = list(migration_dir.glob("*.py"))

    assert migrations
    for migration in migrations:
        source = migration.read_text(encoding="utf-8").lower()
        assert "create_all" not in source
        assert "drop_all" not in source
        assert "bulk_insert" not in source
        assert "insert into" not in source
