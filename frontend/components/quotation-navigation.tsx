"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { permissionGranted } from "@/lib/api";

export function QuotationNavigation() {
  const pathname = usePathname();
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  return <nav className="section-tabs" aria-label="Quotation management">
    <Link className={pathname === "/quotations" ? "active" : ""} href="/quotations">Quotations</Link>
    {permissionGranted(permissions, "quotations.approve") && <Link className={pathname === "/discount-approvals" ? "active" : ""} href="/discount-approvals">Approvals</Link>}
    {permissionGranted(permissions, "quotations.create") && <Link className={pathname === "/quotations/create" ? "active" : ""} href="/quotations/create">New cost sheet</Link>}
    <Link className={pathname === "/price-lists" ? "active" : ""} href="/price-lists">Price lists</Link>
  </nav>;
}
