from app.core.authorization import (
    ALL_PERMISSIONS,
    PERMISSION_ACTIONS,
    PERMISSION_CATALOG,
    PERMISSION_MODULES,
    ROLE_TEMPLATES,
    permission_is_granted,
)

EXPECTED_ROLES = [
    "Organization Administrator",
    "Business Owner / Director",
    "Sales Head",
    "Branch / Project Manager",
    "Inside Sales / Telecalling Executive",
    "Field Sales Executive",
    "CRM Executive",
    "Collections Executive",
    "Finance & Accounts User",
    "Channel Partner Manager",
    "Broker / Channel Partner",
    "Property Manager",
    "Customer / Buyer",
    "Tenant",
    "Auditor / Compliance User",
]


def test_permission_catalog_has_every_action_for_every_module() -> None:
    expected = {
        f"{module}.{action}" for module in PERMISSION_MODULES for action in PERMISSION_ACTIONS
    }
    assert set(PERMISSION_CATALOG) == expected
    assert len(PERMISSION_CATALOG) == len(PERMISSION_MODULES) * len(PERMISSION_ACTIONS)


def test_all_fifteen_role_templates_use_only_catalog_permissions() -> None:
    assert [template.name for template in ROLE_TEMPLATES] == EXPECTED_ROLES
    assert len({template.name for template in ROLE_TEMPLATES}) == 15
    for template in ROLE_TEMPLATES:
        assert template.permissions
        assert template.permissions <= ALL_PERMISSIONS


def test_administrator_has_every_permission_and_manage_implies_module_actions() -> None:
    administrator = ROLE_TEMPLATES[0]
    assert administrator.permissions == ALL_PERMISSIONS
    assert permission_is_granted({"leads.manage"}, "leads.delete")
    assert not permission_is_granted({"leads.manage"}, "payments.view")


def test_auditor_template_has_only_read_and_export_permissions() -> None:
    auditor = next(role for role in ROLE_TEMPLATES if role.name == "Auditor / Compliance User")
    assert auditor.permissions
    assert all(code.endswith((".view", ".export")) for code in auditor.permissions)
    assert "audit.view" in auditor.permissions
    assert "audit.export" in auditor.permissions
    assert "audit.manage" not in auditor.permissions


def test_operational_roles_can_read_and_acknowledge_in_app_notifications() -> None:
    for role in ROLE_TEMPLATES[:-1]:
        assert "notifications.view" in role.permissions
        assert "notifications.update" in role.permissions
