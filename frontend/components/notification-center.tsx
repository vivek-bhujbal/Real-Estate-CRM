"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiRequest,
  InAppNotification,
  NotificationMarkAllResult,
  NotificationUnreadCount,
  PageResponse
} from "@/lib/api";

export function NotificationCenter({ canUpdate }: { canUpdate: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<InAppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const [count, recent] = await Promise.all([
      apiRequest<NotificationUnreadCount>("/notifications/unread-count"),
      apiRequest<PageResponse<InAppNotification>>("/notifications?page=1&page_size=6")
    ]);
    setUnread(count.unread);
    setItems(recent.items);
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh().catch(() => undefined), 0);
    const timer = window.setInterval(() => void refresh().catch(() => undefined), 45_000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", dismiss);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function togglePopover() {
    setOpen((value) => {
      const next = !value;
      if (next) window.requestAnimationFrame(() => popoverRef.current?.focus());
      return next;
    });
  }

  async function openNotification(item: InAppNotification) {
    if (!item.read_at && canUpdate) {
      const updated = await apiRequest<InAppNotification>(`/notifications/${item.id}/read`, { method: "PATCH" });
      setItems((current) => current.map((row) => row.id === item.id ? updated : row));
      setUnread((value) => Math.max(0, value - 1));
    }
    setOpen(false);
    router.push(item.action_url ?? "/notifications");
  }

  async function markAll() {
    if (!canUpdate) return;
    await apiRequest<NotificationMarkAllResult>("/notifications/read-all", { method: "POST" });
    setItems((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? new Date().toISOString(), status: "READ" })));
    setUnread(0);
  }

  return <div className="notification-center" ref={containerRef}>
    <button ref={buttonRef} className="icon-button notification-button" type="button" onClick={togglePopover} aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} aria-expanded={open} aria-controls="notification-popover">
      <svg className="notification-bell" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></svg>{unread > 0 && <b>{unread > 99 ? "99+" : unread}</b>}
    </button>
    {open && <div ref={popoverRef} id="notification-popover" className="notification-popover" role="dialog" aria-label="Notifications" tabIndex={-1}>
      <header><div><strong>Notifications</strong><small>{unread ? `${unread} unread` : "You're caught up"}</small></div>{canUpdate && unread > 0 && <button type="button" onClick={() => void markAll()}>Mark all read</button>}</header>
      <div className="notification-preview-list">
        {items.map((item) => <button type="button" className={item.read_at ? "" : "unread"} key={item.id} onClick={() => void openNotification(item)}><i/><span><strong>{item.title}</strong><p>{item.body}</p><small>{new Date(item.created_at).toLocaleString()}</small></span></button>)}
        {!items.length && <div className="notification-empty"><strong>No notifications</strong><p>Real activity alerts will appear here.</p></div>}
      </div>
      <Link href="/notifications" onClick={() => setOpen(false)}>View all notifications</Link>
    </div>}
  </div>;
}
