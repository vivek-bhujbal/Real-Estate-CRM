"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiRequest,
  ApiError,
  PageResponse,
  permissionGranted,
  ServiceCategory,
  ServicePriority,
  ServiceSLAPolicy,
  ServiceTicket,
  TicketOptions,
  TicketStats,
  TicketStatus,
} from "@/lib/api";

const statuses: TicketStatus[] = ["OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED", "CLOSED"];
const priorities: ServicePriority[] = ["LOW", "MEDIUM", "HIGH", "URGENT"];
type Modal = "ticket" | "settings" | null;

function dateTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function slaLabel(ticket: ServiceTicket) {
  if (!ticket.sla.configured) return "No SLA policy";
  if (ticket.sla.response_state === "BREACHED" || ticket.sla.resolution_state === "BREACHED") return "SLA breached";
  if (ticket.status === "RESOLVED" || ticket.status === "CLOSED") return "SLA measured";
  const minutes = ticket.sla.resolution_remaining_minutes;
  if (minutes == null) return "On track";
  if (minutes < 60) return `${Math.max(minutes, 0)}m remaining`;
  return `${Math.ceil(minutes / 60)}h remaining`;
}

export default function ServiceRequestsPage() {
  const router = useRouter();
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const canCreate = permissionGranted(permissions, "service_requests.create");
  const canAssign = permissionGranted(permissions, "service_requests.assign");
  const canManage = permissionGranted(permissions, "service_requests.manage");
  const [rows, setRows] = useState<PageResponse<ServiceTicket> | null>(null);
  const [stats, setStats] = useState<TicketStats | null>(null);
  const [options, setOptions] = useState<TicketOptions | null>(null);
  const [policies, setPolicies] = useState<ServiceSLAPolicy[]>([]);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [slaBreached, setSlaBreached] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<Modal>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    if (priority) params.set("priority", priority);
    if (categoryId) params.set("category_id", categoryId);
    if (slaBreached) params.set("sla_breached", slaBreached);
    try {
      const [tickets, totals, ticketOptions, slaPolicies] = await Promise.all([
        apiRequest<PageResponse<ServiceTicket>>(`/service-requests?${params}`),
        apiRequest<TicketStats>("/service-requests/stats"),
        apiRequest<TicketOptions>("/service-requests/options"),
        canManage ? apiRequest<ServiceSLAPolicy[]>("/service-requests/sla-policies") : Promise.resolve([]),
      ]);
      setRows(tickets); setStats(totals); setOptions(ticketOptions); setPolicies(slaPolicies); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Service desk could not be loaded"); }
  }, [canManage, categoryId, page, priority, query, slaBreached, status]);
  useEffect(() => { const timer = setTimeout(() => void load(), 0); return () => clearTimeout(timer); }, [load]);

  async function createTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); setSaving(true);
    try {
      const created = await apiRequest<{ ticket: ServiceTicket }>("/service-requests", { method: "POST", body: JSON.stringify({
        category_id: values.category_id, priority: values.priority, subject: values.subject,
        description: values.description, customer_id: values.customer_id || null,
        tenant_id: values.tenant_id || null, project_id: values.project_id || null,
        unit_id: values.unit_id || null, assigned_user_id: values.assigned_user_id || null,
      }) });
      router.push(`/service-requests/${created.ticket.id}`);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Ticket could not be created"); setSaving(false); }
  }

  async function createCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); setSaving(true);
    try {
      await apiRequest<ServiceCategory>("/service-requests/categories", { method: "POST", body: JSON.stringify({ code: values.code, name: values.name, description: values.description || null }) });
      event.currentTarget.reset(); setNotice("Service category created. No SLA applies until a policy is configured."); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Category could not be created"); }
    finally { setSaving(false); }
  }

  async function createPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); setSaving(true);
    try {
      await apiRequest<ServiceSLAPolicy>("/service-requests/sla-policies", { method: "POST", body: JSON.stringify({ category_id: values.category_id, priority: values.priority, first_response_minutes: Number(values.first_response_minutes), escalation_minutes: Number(values.escalation_minutes), resolution_minutes: Number(values.resolution_minutes) }) });
      event.currentTarget.reset(); setNotice("SLA policy activated for future tickets"); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "SLA policy could not be created"); }
    finally { setSaving(false); }
  }

  return <AppShell><main className="dashboard-content service-content">
    <div className="management-heading"><div><p className="overline">Customer care</p><h1>Service desk</h1><p>Customer tickets, accountable ownership, measured SLAs, escalations, and verified closure.</p></div><div className="heading-actions">{canManage && <button className="button button-secondary" onClick={() => setModal("settings")}>Categories & SLA</button>}{canCreate && <button className="button button-primary" onClick={() => setModal("ticket")}>New ticket</button>}</div></div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    {stats && <section className="service-metrics"><article><span>Open tickets</span><strong>{stats.total_open}</strong><small>{stats.unassigned} unassigned</small></article><article><span>In progress</span><strong>{stats.in_progress}</strong><small>{stats.waiting_for_customer} waiting for customer</small></article><article><span>SLA breached</span><strong>{stats.sla_breached}</strong><small>{stats.escalated} actively escalated</small></article><article><span>Resolved queue</span><strong>{stats.resolved}</strong><small>{stats.average_feedback == null ? "No customer ratings" : `${stats.average_feedback.toFixed(1)} / 5 average`}</small></article></section>}
    <section className="service-filter-bar"><form onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()); setPage(1); }}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search ticket number, subject, or category..."/><button className="button button-primary">Search</button></form><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select><select value={priority} onChange={(event) => { setPriority(event.target.value); setPage(1); }}><option value="">All priorities</option>{priorities.map((item) => <option key={item}>{item}</option>)}</select><select value={categoryId} onChange={(event) => { setCategoryId(event.target.value); setPage(1); }}><option value="">All categories</option>{options?.categories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><select value={slaBreached} onChange={(event) => { setSlaBreached(event.target.value); setPage(1); }}><option value="">All SLA states</option><option value="true">Breached only</option><option value="false">On-track / measured</option></select></section>
    <section className="data-card service-table-card"><div className="service-table"><div className="service-row head"><span>Ticket / requester</span><span>Category</span><span>Priority</span><span>Owner</span><span>SLA</span><span>Status</span><span /></div>{rows?.items.length ? rows.items.map((item) => <Link href={`/service-requests/${item.id}`} className="service-row" key={item.id}><span><strong>{item.request_number}</strong><small>{item.subject} · {item.requester_name}</small></span><span><strong>{item.category_name}</strong><small>{dateTime(item.opened_at)}</small></span><span><em className={`ticket-priority priority-${item.priority.toLowerCase()}`}>{item.priority}</em></span><span><strong>{item.assigned_user_name ?? "Unassigned"}</strong><small>{item.is_escalated ? "Escalated ownership" : "Standard ownership"}</small></span><span><strong className={item.sla.response_state === "BREACHED" || item.sla.resolution_state === "BREACHED" ? "sla-breach-text" : ""}>{slaLabel(item)}</strong><small>{item.sla.configured ? "Policy snapshot" : "Configure category policy"}</small></span><span><em className={`ticket-status status-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</em></span><span>View →</span></Link>) : <div className="customer-empty"><span>SR</span><strong>No tickets found</strong><p>Tickets appear only when an authenticated user creates one. No sample cases are generated.</p></div>}</div><div className="pagination"><button disabled={!rows || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {rows?.page ?? 1} of {Math.max(rows?.pages ?? 0, 1)}</span><button disabled={!rows || page >= rows.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>
    {modal === "ticket" && <div className="modal-backdrop"><form className="modal-card service-ticket-modal" onSubmit={createTicket}><div className="modal-heading"><div><p className="overline">Customer support</p><h2>Create service ticket</h2></div><button type="button" className="icon-button" onClick={() => setModal(null)}>×</button></div><div className="service-form-grid"><label className="field"><span>Category</span><select name="category_id" required><option value="">Select category</option>{options?.categories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="field"><span>Priority</span><select name="priority" defaultValue="MEDIUM">{priorities.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field span-two"><span>Subject</span><input name="subject" required minLength={3} maxLength={200}/></label><label className="field span-two"><span>Description</span><textarea name="description" rows={5} required minLength={5}/></label>{canAssign && <><label className="field"><span>Customer (optional)</span><select name="customer_id"><option value="">Portal requester</option>{options?.customers.map((item) => <option value={item.id} key={item.id}>{item.label} · {item.secondary}</option>)}</select></label><label className="field"><span>Tenant (optional)</span><select name="tenant_id"><option value="">Not a rental tenant</option>{options?.tenants.map((item) => <option value={item.id} key={item.id}>{item.label} · {item.secondary}</option>)}</select></label><label className="field"><span>Project (optional)</span><select name="project_id"><option value="">No project</option>{options?.projects.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><label className="field"><span>Unit (optional)</span><select name="unit_id"><option value="">No unit</option>{options?.units.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><label className="field"><span>Initial assignee</span><select name="assigned_user_id"><option value="">Leave unassigned</option>{options?.agents.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label></>}</div><p className="governance-note">SLA deadlines are calculated by the backend from the selected category and priority. If no policy exists, the ticket remains valid and clearly shows “No SLA policy”.</p><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setModal(null)}>Cancel</button><button disabled={saving || !options?.categories.length} className="button button-primary">{saving ? "Creating…" : "Create ticket"}</button></div></form></div>}
    {modal === "settings" && <div className="modal-backdrop"><div className="modal-card service-settings-modal"><div className="modal-heading"><div><p className="overline">Service governance</p><h2>Categories & SLA policies</h2></div><button type="button" className="icon-button" onClick={() => setModal(null)}>×</button></div><div className="service-settings-grid"><form onSubmit={createCategory}><h3>New category</h3><label className="field"><span>Code</span><input name="code" required/></label><label className="field"><span>Name</span><input name="name" required/></label><label className="field"><span>Description</span><textarea name="description" rows={3}/></label><button disabled={saving} className="button button-secondary">Add category</button><div className="config-list">{options?.categories.map((item) => <span key={item.id}><strong>{item.name}</strong><small>{item.code} · {item.policy_count} policies · {item.ticket_count} tickets</small></span>)}</div></form><form onSubmit={createPolicy}><h3>New SLA policy</h3><label className="field"><span>Category</span><select name="category_id" required><option value="">Select category</option>{options?.categories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="field"><span>Priority</span><select name="priority">{priorities.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>First response (minutes)</span><input name="first_response_minutes" type="number" min="1" required/></label><label className="field"><span>Escalation (minutes)</span><input name="escalation_minutes" type="number" min="1" required/></label><label className="field"><span>Resolution (minutes)</span><input name="resolution_minutes" type="number" min="1" required/></label><button disabled={saving} className="button button-primary">Activate policy</button><div className="config-list">{policies.map((item) => <span key={item.id}><strong>{item.category_name} · {item.priority}</strong><small>Response {item.first_response_minutes}m · Escalate {item.escalation_minutes}m · Resolve {item.resolution_minutes}m</small></span>)}</div></form></div></div></div>}
  </main></AppShell>;
}
