from pathlib import Path

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.db import Base

EXPECTED_TABLES = {
    "agreements",
    "audit_logs",
    "booking_approvals",
    "booking_applicants",
    "booking_documents",
    "booking_financing",
    "bookings",
    "branches",
    "cancellations",
    "channel_partners",
    "commission_payouts",
    "commission_structures",
    "commissions",
    "construction_updates",
    "cost_sheet_items",
    "cost_sheets",
    "customer_documents",
    "customer_activities",
    "customer_ledger_entries",
    "customers",
    "demand_letters",
    "departments",
    "discount_approvals",
    "floors",
    "financial_charges",
    "handovers",
    "handover_documents",
    "installments",
    "lead_activities",
    "lead_assignments",
    "lead_import_batches",
    "lead_notes",
    "lead_score_rules",
    "lead_sources",
    "leads",
    "lease_documents",
    "lease_moves",
    "lease_renewals",
    "leases",
    "maintenance_records",
    "notifications",
    "no_dues_certificates",
    "lost_lead_reasons",
    "organizations",
    "partner_leads",
    "partner_agreements",
    "partner_contacts",
    "partner_disputes",
    "partner_documents",
    "partner_projects",
    "partner_territories",
    "password_reset_tokens",
    "payment_plans",
    "payment_allocations",
    "payment_reconciliations",
    "payments",
    "permissions",
    "possessions",
    "possession_override_requests",
    "post_booking_cases",
    "price_lists",
    "projects",
    "quotation_items",
    "quotations",
    "receipts",
    "refresh_tokens",
    "refunds",
    "rent_payments",
    "rent_schedule_items",
    "rental_invoices",
    "rental_properties",
    "role_permissions",
    "roles",
    "service_requests",
    "service_request_attachments",
    "service_request_categories",
    "service_request_comments",
    "service_request_escalations",
    "service_request_feedback",
    "service_sla_policies",
    "site_visits",
    "site_visit_units",
    "snag_items",
    "tenants",
    "team_members",
    "teams",
    "territories",
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
