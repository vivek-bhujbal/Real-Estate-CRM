"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";

const navigation = [
  { label: "Overview", icon: "grid", active: true },
  { label: "Leads", icon: "users" },
  { label: "Customers", icon: "contact" },
  { label: "Projects", icon: "building" },
  { label: "Inventory", icon: "home" },
  { label: "Bookings", icon: "file" },
  { label: "Collections", icon: "wallet" }
];

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    contact: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M15 8h3M15 12h3M6 16h12"/></>,
    building: <><path d="M3 21h18M6 21V3h12v18M9 7h2M13 7h2M9 11h2M13 11h2M10 21v-5h4v5"/></>,
    home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v11h14V10M9 21v-6h6v6"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/></>,
    wallet: <><path d="M20 7V5a2 2 0 0 0-2-2H5a3 3 0 0 0 0 6h15v12H5a3 3 0 0 1-3-3V6"/><path d="M16 13h4"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1v.1h-4V21a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4h-.1v-4H3a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1v-.1h4V3a1.7 1.7 0 0 0 1.1 1.6 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.15.37.36.7.6 1 .28.27.63.4 1 .4h.1v4H21a1.7 1.7 0 0 0-1.6.6z"/></>
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { session, logout } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  async function signOut() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="app-layout">
      <button className={`scrim ${menuOpen ? "visible" : ""}`} onClick={() => setMenuOpen(false)} aria-label="Close navigation" />
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="sidebar-head">
          <div className="brand"><span className="brand-mark" aria-hidden="true">E</span><span>EstateOps</span></div>
          <button className="icon-button sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation">×</button>
        </div>
        <div className="workspace-switcher">
          <span className="workspace-avatar">{session?.user.organization.name.slice(0, 1).toUpperCase()}</span>
          <span><small>Workspace</small><strong>{session?.user.organization.name}</strong></span>
        </div>
        <nav className="main-nav" aria-label="Primary navigation">
          <p>Workspace</p>
          {navigation.map((item) => (
            <button key={item.label} className={item.active ? "active" : ""} disabled={!item.active} title={!item.active ? "Available in a later delivery phase" : undefined}>
              <Icon name={item.icon} /><span>{item.label}</span>{!item.active && <small>Soon</small>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button onClick={() => router.push("/account/security")}><Icon name="settings" /><span>Account security</span></button>
          <button className="profile-button" onClick={signOut} title="Sign out">
            <span className="profile-avatar">{session?.user.full_name.slice(0, 1).toUpperCase()}</span>
            <span><strong>{session?.user.full_name}</strong><small>{session?.user.email}</small></span>
          </button>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation">☰</button>
          <div className="topbar-spacer" />
          <button className="icon-button notification-button" aria-label="Notifications" disabled title="Notifications are not yet available">
            <span aria-hidden="true">○</span>
          </button>
          <span className="topbar-divider" />
          <span className="topbar-user">{session?.user.full_name}</span>
        </header>
        {children}
      </div>
    </div>
  );
}
