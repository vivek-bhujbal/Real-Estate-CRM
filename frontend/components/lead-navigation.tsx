"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { permissionGranted } from "@/lib/api";

const items = [
  { label: "All leads", href: "/leads", permission: "leads.view" },
  { label: "Kanban", href: "/leads/kanban", permission: "leads.view" },
  { label: "Allocation", href: "/leads/allocation", permission: "leads.assign" },
  { label: "Unattended", href: "/leads/unattended", permission: "leads.view" },
  { label: "Ageing", href: "/leads/ageing", permission: "leads.view" },
  { label: "Duplicates", href: "/leads/duplicates", permission: "leads.view" },
  { label: "Import", href: "/leads/import", permission: "leads.manage" }
];

export function LeadNavigation() {
  const pathname = usePathname();
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const exactMatch = items.some((item) => item.href === pathname);

  return (
    <nav className="settings-tabs lead-tabs" aria-label="Lead management">
      {items.filter((item) => permissionGranted(permissions, item.permission)).map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={pathname === item.href || (item.href === "/leads" && !exactMatch && pathname.startsWith("/leads/")) ? "active" : ""}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
