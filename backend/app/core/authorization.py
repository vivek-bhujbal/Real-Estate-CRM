from dataclasses import dataclass

PERMISSION_ACTIONS = (
    "view",
    "create",
    "update",
    "delete",
    "approve",
    "assign",
    "export",
    "manage",
)

PERMISSION_MODULES = {
    "dashboard": "dashboards",
    "organization": "organization settings",
    "branches": "branches",
    "departments": "departments",
    "teams": "teams",
    "territories": "territories",
    "users": "users",
    "roles": "roles and permissions",
    "audit": "audit logs",
    "leads": "leads",
    "customers": "customers",
    "activities": "sales activities",
    "projects": "projects",
    "inventory": "inventory",
    "visits": "site visits",
    "quotations": "quotations and cost sheets",
    "bookings": "bookings",
    "documents": "business documents",
    "agreements": "agreements",
    "collections": "collections and demands",
    "payments": "payments and receipts",
    "partners": "channel partners",
    "commissions": "commissions and payouts",
    "financing": "loan and financing workflows",
    "construction": "construction updates",
    "possession": "possession and handover",
    "service_requests": "service requests",
    "properties": "rental properties",
    "tenants": "tenants",
    "leases": "leases",
    "maintenance": "maintenance records",
    "notifications": "notifications",
    "workflows": "workflows and approvals",
    "reports": "reports",
}

ACTION_DESCRIPTIONS = {
    "view": "View",
    "create": "Create",
    "update": "Update",
    "delete": "Delete",
    "approve": "Approve",
    "assign": "Assign",
    "export": "Export",
    "manage": "Manage",
}

PERMISSION_CATALOG = {
    f"{module}.{action}": f"{ACTION_DESCRIPTIONS[action]} {label}"
    for module, label in PERMISSION_MODULES.items()
    for action in PERMISSION_ACTIONS
}


@dataclass(frozen=True, slots=True)
class RoleTemplate:
    name: str
    description: str
    permissions: frozenset[str]


def _grant(
    *modules: str,
    actions: tuple[str, ...] = PERMISSION_ACTIONS,
) -> set[str]:
    return {f"{module}.{action}" for module in modules for action in actions}


def _view_export(*modules: str) -> set[str]:
    return _grant(*modules, actions=("view", "export"))


ALL_PERMISSIONS = frozenset(PERMISSION_CATALOG)

BUSINESS_OWNER_PERMISSIONS = frozenset(
    ALL_PERMISSIONS
    - _grant("roles", actions=("create", "update", "delete", "approve", "manage"))
    - _grant("audit", actions=("create", "update", "delete", "approve", "assign", "manage"))
)

SALES_HEAD_PERMISSIONS = frozenset(
    _grant(
        "leads",
        "customers",
        "activities",
        "visits",
        "quotations",
        "bookings",
        "documents",
        "notifications",
        "workflows",
    )
    | _view_export("dashboard", "projects", "inventory", "reports")
    | _grant("users", "roles", actions=("view", "assign"))
    | _grant("branches", "departments", "teams", "territories", "organization", actions=("view",))
)

BRANCH_MANAGER_PERMISSIONS = frozenset(
    _grant(
        "leads",
        "customers",
        "activities",
        "visits",
        "quotations",
        "bookings",
        "documents",
        actions=("view", "create", "update", "approve", "assign", "export"),
    )
    | _view_export("dashboard", "reports")
    | _grant(
        "projects",
        "inventory",
        actions=("view", "create", "update", "delete", "approve", "assign", "export"),
    )
    | _grant("users", "roles", actions=("view", "assign"))
    | _grant("branches", "departments", actions=("view", "update"))
    | _grant("teams", "territories", actions=("view", "create", "update", "assign"))
)

INSIDE_SALES_PERMISSIONS = frozenset(
    _grant("leads", actions=("view", "create", "update", "assign", "export"))
    | _grant("customers", "activities", actions=("view", "create", "update"))
    | _grant("visits", actions=("view", "create", "update", "assign"))
    | _grant("notifications", actions=("view", "create", "update"))
    | _grant("dashboard", "projects", "inventory", "reports", actions=("view",))
)

FIELD_SALES_PERMISSIONS = frozenset(
    _grant("leads", "customers", actions=("view", "update"))
    | _grant("activities", "visits", "quotations", actions=("view", "create", "update"))
    | _grant("bookings", actions=("view", "create", "update"))
    | _grant("documents", actions=("view", "create"))
    | _grant("dashboard", "projects", actions=("view",))
    | _grant("inventory", actions=("view", "assign"))
)

CRM_EXECUTIVE_PERMISSIONS = frozenset(
    _grant(
        "customers",
        "bookings",
        "documents",
        "agreements",
        "possession",
        "service_requests",
        "notifications",
        actions=("view", "create", "update", "assign", "export"),
    )
    | _grant("leads", "projects", "inventory", "payments", "collections", actions=("view",))
    | _grant("dashboard", "reports", actions=("view", "export"))
)

COLLECTIONS_EXECUTIVE_PERMISSIONS = frozenset(
    _grant(
        "collections",
        "payments",
        "notifications",
        actions=("view", "create", "update", "assign", "export"),
    )
    | _grant("customers", "bookings", "agreements", actions=("view",))
    | _view_export("dashboard", "reports")
)

FINANCE_PERMISSIONS = frozenset(
    _grant("collections", "payments", "commissions", "financing")
    | _grant("bookings", "agreements", "customers", actions=("view", "export"))
    | _view_export("dashboard", "reports", "audit")
)

CHANNEL_MANAGER_PERMISSIONS = frozenset(
    _grant("partners", "commissions", "leads")
    | _grant("customers", "activities", "visits", "bookings", actions=("view", "create", "update"))
    | _view_export("dashboard", "projects", "inventory", "reports")
)

BROKER_PERMISSIONS = frozenset(
    _grant("leads", actions=("view", "create", "update"))
    | _grant("customers", "activities", "visits", actions=("view", "create"))
    | _grant("partners", "commissions", "bookings", actions=("view", "export"))
    | _grant("projects", "inventory", "documents", actions=("view",))
)

PROPERTY_MANAGER_PERMISSIONS = frozenset(
    _grant("properties", "tenants", "leases", "maintenance", "service_requests")
    | _grant(
        "payments",
        "documents",
        "notifications",
        actions=("view", "create", "update", "export"),
    )
    | _view_export("dashboard", "reports")
)

CUSTOMER_PERMISSIONS = frozenset(
    _grant(
        "bookings",
        "documents",
        "agreements",
        "payments",
        "construction",
        "possession",
        "service_requests",
        "notifications",
        actions=("view",),
    )
    | _grant("service_requests", actions=("create", "update"))
    | _grant("payments", "documents", actions=("create",))
)

TENANT_PERMISSIONS = frozenset(
    _grant("properties", "leases", "payments", "notifications", actions=("view",))
    | _grant("service_requests", actions=("view", "create", "update"))
    | _grant("documents", "payments", actions=("view", "create"))
)

AUDITOR_PERMISSIONS = frozenset(
    _view_export(*PERMISSION_MODULES) | _grant("audit", actions=("view", "export", "manage"))
)

ROLE_TEMPLATES = (
    RoleTemplate(
        "Organization Administrator",
        "Full organization administration and platform access",
        ALL_PERMISSIONS,
    ),
    RoleTemplate(
        "Business Owner / Director",
        "Executive oversight, approvals, exports, and business management",
        BUSINESS_OWNER_PERMISSIONS,
    ),
    RoleTemplate(
        "Sales Head",
        "Sales leadership, assignment, approvals, and pipeline management",
        SALES_HEAD_PERMISSIONS,
    ),
    RoleTemplate(
        "Branch / Project Manager",
        "Branch and project-level sales team operations",
        BRANCH_MANAGER_PERMISSIONS,
    ),
    RoleTemplate(
        "Inside Sales / Telecalling Executive",
        "Lead qualification, calling activities, and visit scheduling",
        INSIDE_SALES_PERMISSIONS,
    ),
    RoleTemplate(
        "Field Sales Executive",
        "Visits, quotations, customer follow-up, and booking initiation",
        FIELD_SALES_PERMISSIONS,
    ),
    RoleTemplate(
        "CRM Executive",
        "Customer, booking, documentation, possession, and service coordination",
        CRM_EXECUTIVE_PERMISSIONS,
    ),
    RoleTemplate(
        "Collections Executive",
        "Demand, collection, receipt, and customer follow-up operations",
        COLLECTIONS_EXECUTIVE_PERMISSIONS,
    ),
    RoleTemplate(
        "Finance & Accounts User",
        "Financial verification, approvals, reconciliation, and reporting",
        FINANCE_PERMISSIONS,
    ),
    RoleTemplate(
        "Channel Partner Manager",
        "Partner onboarding, protected leads, commissions, and payouts",
        CHANNEL_MANAGER_PERMISSIONS,
    ),
    RoleTemplate(
        "Broker / Channel Partner",
        "Partner lead registration and authorized deal visibility",
        BROKER_PERMISSIONS,
    ),
    RoleTemplate(
        "Property Manager",
        "Rental property, tenant, lease, and maintenance operations",
        PROPERTY_MANAGER_PERMISSIONS,
    ),
    RoleTemplate(
        "Customer / Buyer",
        "Buyer self-service access to authorized records and requests",
        CUSTOMER_PERMISSIONS,
    ),
    RoleTemplate(
        "Tenant",
        "Tenant self-service access to lease, payment, and service records",
        TENANT_PERMISSIONS,
    ),
    RoleTemplate(
        "Auditor / Compliance User",
        "Read-only and export access with audit oversight",
        AUDITOR_PERMISSIONS,
    ),
)

ROLE_TEMPLATE_BY_NAME = {template.name: template for template in ROLE_TEMPLATES}


def permission_is_granted(granted: set[str] | frozenset[str], required: str) -> bool:
    if required in granted:
        return True
    module, separator, _action = required.partition(".")
    return bool(separator and f"{module}.manage" in granted)
