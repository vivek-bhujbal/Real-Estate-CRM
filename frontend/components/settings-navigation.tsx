"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { permissionGranted } from "@/lib/api";

const items = [
  { label: "Organization", href: "/settings/organization", permission: "organization.view" },
  { label: "Branches", href: "/settings/branches", permission: "branches.view" },
  { label: "Departments", href: "/settings/departments", permission: "departments.view" },
  { label: "Users", href: "/settings/users", permission: "users.view" },
  { label: "Teams", href: "/settings/teams", permission: "teams.view" },
  { label: "Territories", href: "/settings/territories", permission: "territories.view" },
  { label: "Roles", href: "/settings/roles", permission: "roles.view" },
  { label: "Audit trail", href: "/settings/audit", permission: "audit.view" }
];

export function SettingsNavigation() {
  const pathname = usePathname();
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];

  return (
    <nav className="settings-tabs" aria-label="Organization settings">
      {items.filter((item) => permissionGranted(permissions, item.permission)).map((item) => (
        <Link key={item.href} href={item.href} className={pathname === item.href ? "active" : ""}>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
