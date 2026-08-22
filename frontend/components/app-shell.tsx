"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ModalAccessibility } from "@/components/modal-accessibility";
import { NotificationCenter } from "@/components/notification-center";
import { permissionGranted } from "@/lib/api";

type NavigationItem = { label: string; icon: string; href: string; permission: string };
type NavigationGroup = { label: string; items: NavigationItem[] };

const navigation: NavigationGroup[] = [
  { label: "Workspace", items: [
    { label: "Overview", icon: "grid", href: "/dashboard", permission: "dashboard.view" },
    { label: "Leads", icon: "users", href: "/leads", permission: "leads.view" },
    { label: "Customers", icon: "contact", href: "/customers", permission: "customers.view" },
    { label: "Site visits", icon: "calendar", href: "/site-visits", permission: "visits.view" },
  ] },
  { label: "Sales inventory", items: [
    { label: "Projects", icon: "building", href: "/projects", permission: "projects.view" },
    { label: "Inventory", icon: "home", href: "/inventory", permission: "inventory.view" },
    { label: "Unit holds", icon: "shield", href: "/inventory/holds", permission: "inventory.view" },
    { label: "Quotations", icon: "file", href: "/quotations", permission: "quotations.view" },
    { label: "Bookings", icon: "briefcase", href: "/bookings", permission: "bookings.view" },
  ] },
  { label: "Revenue", items: [
    { label: "Collections", icon: "wallet", href: "/collections", permission: "collections.view" },
    { label: "Channel partners", icon: "users", href: "/partners", permission: "partners.view" },
  ] },
  { label: "Operations", items: [
    { label: "Documents", icon: "file", href: "/documents", permission: "documents.view" },
    { label: "Post-sales", icon: "shield", href: "/post-sales", permission: "bookings.view" },
    { label: "Property lifecycle", icon: "building", href: "/property-lifecycle", permission: "possession.view" },
    { label: "Rentals", icon: "home", href: "/rentals", permission: "properties.view" },
    { label: "Service desk", icon: "contact", href: "/service-requests", permission: "service_requests.view" },
  ] },
];

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    contact: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M15 8h3M15 12h3M6 16h12"/></>,
    building: <><path d="M3 21h18M6 21V3h12v18M9 7h2M13 7h2M9 11h2M13 11h2M10 21v-5h4v5"/></>,
    home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v11h14V10M9 21v-6h6v6"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/></>,
    wallet: <><path d="M20 7V5a2 2 0 0 0-2-2H5a3 3 0 0 0 0 6h15v12H5a3 3 0 0 1-3-3V6"/><path d="M16 13h4"/></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></>,
    briefcase: <><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1v.1h-4V21a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4h-.1v-4H3a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1v-.1h4V3a1.7 1.7 0 0 0 1.1 1.6 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.15.37.36.7.6 1 .28.27.63.4 1 .4h.1v4H21a1.7 1.7 0 0 0-1.6.6z"/></>,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function routeLabel(pathname: string) {
  const segment = pathname.split("/").filter(Boolean).at(-1) ?? "dashboard";
  if (/^[0-9a-f]{8}-/i.test(segment)) return "Details";
  return segment.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { session, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const visibleGroups = useMemo(() => navigation.map((group) => ({
    ...group,
    items: group.items.filter((item) => permissionGranted(permissions, item.permission)),
  })).filter((group) => group.items.length), [permissions]);
  const hasPermission = (permission: string) => permissionGranted(permissions, permission);
  const allVisibleItems = visibleGroups.flatMap((group) => group.items.map((item) => ({ ...item, group: group.label })));
  const activeItem = [...allVisibleItems].sort((a, b) => b.href.length - a.href.length).find((item) =>
    pathname === item.href || pathname.startsWith(`${item.href}/`) || (item.href === "/site-visits" && pathname === "/calendar")
  );

  useEffect(() => {
    const media = window.matchMedia("(max-width: 820px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!isMobile || !menuOpen) return;
    closeButtonRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isMobile, menuOpen]);

  async function signOut() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  function closeMenu(restoreFocus = false) {
    setMenuOpen(false);
    if (restoreFocus) menuButtonRef.current?.focus();
  }

  return <div className="app-layout">
    <a className="skip-link" href="#workspace-content">Skip to main content</a>
    <ModalAccessibility />
    <button className={`scrim ${menuOpen ? "visible" : ""}`} onClick={() => closeMenu(true)} aria-label="Close navigation" tabIndex={menuOpen ? 0 : -1} />
    <aside className={`sidebar ${menuOpen ? "open" : ""}`} aria-label="Application navigation" inert={isMobile && !menuOpen ? true : undefined}>
      <div className="sidebar-head">
        <Link className="brand" href="/dashboard" onClick={() => closeMenu()}><span className="brand-mark" aria-hidden="true">E</span><span>EstateOps</span></Link>
        <button ref={closeButtonRef} className="icon-button sidebar-close" onClick={() => closeMenu(true)} aria-label="Close navigation">×</button>
      </div>
      <div className="workspace-switcher" title={session?.user.organization.name}>
        <span className="workspace-avatar" aria-hidden="true">{session?.user.organization.name.slice(0, 1).toUpperCase()}</span>
        <span><small>Workspace</small><strong>{session?.user.organization.name}</strong></span>
      </div>
      <nav className="main-nav" aria-label="Primary navigation">
        {visibleGroups.map((group) => <div className="nav-group" key={group.label}>
          <p>{group.label}</p>
          {group.items.map((item) => {
            const active = activeItem?.href === item.href;
            return <Link key={item.label} href={item.href} onClick={() => closeMenu()} className={active ? "active" : ""} aria-current={active ? "page" : undefined}><Icon name={item.icon} /><span>{item.label}</span></Link>;
          })}
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        {hasPermission("organization.view") && <Link href="/settings/organization" onClick={() => closeMenu()} className={pathname.startsWith("/settings/") && pathname !== "/settings/roles" ? "active" : ""}><Icon name="building" /><span>Organization settings</span></Link>}
        {hasPermission("roles.view") && <Link href="/settings/roles" onClick={() => closeMenu()} className={pathname === "/settings/roles" ? "active" : ""}><Icon name="shield" /><span>Roles & permissions</span></Link>}
        <Link href="/account/security" onClick={() => closeMenu()} className={pathname === "/account/security" ? "active" : ""}><Icon name="settings" /><span>Account security</span></Link>
        <div className="profile-summary">
          <span className="profile-avatar" aria-hidden="true">{session?.user.full_name.slice(0, 1).toUpperCase()}</span>
          <span><strong>{session?.user.full_name}</strong><small>{session?.user.email}</small></span>
          <button type="button" onClick={() => void signOut()} aria-label={`Sign out ${session?.user.full_name}`} title="Sign out">↗</button>
        </div>
      </div>
    </aside>
    <div className="app-main" id="workspace-content">
      <header className="topbar">
        <button ref={menuButtonRef} className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation" aria-expanded={menuOpen}>☰</button>
        <div className="topbar-context" aria-label="Current location"><small>{activeItem?.group ?? "EstateOps"}</small><strong>{pathname === activeItem?.href ? activeItem.label : routeLabel(pathname)}</strong></div>
        <div className="topbar-spacer" />
        {hasPermission("notifications.view") && <NotificationCenter canUpdate={hasPermission("notifications.update")} />}
        <span className="topbar-divider" aria-hidden="true" />
        <span className="topbar-user"><b>{session?.user.full_name}</b><small>{session?.user.organization.slug}</small></span>
      </header>
      {children}
    </div>
  </div>;
}
