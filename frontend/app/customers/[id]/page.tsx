"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  ActivityType, apiDownload, apiRequest, ApiError, Customer, Customer360, CustomerActivity,
  CustomerSalesRecord, CustomerStatus, permissionGranted
} from "@/lib/api";

type Tab = "overview" | "journey" | "sales" | "financials" | "documents" | "after-sales";
type EditDraft = {
  full_name: string; email: string; phone: string; alternate_phone: string; date_of_birth: string;
  gender: string; occupation: string; company_name: string; preferred_location: string;
  requirements: string; budget_min: string; budget_max: string; address_line1: string;
  address_line2: string; city: string; state: string; postal_code: string; country: string;
  status: CustomerStatus;
};

const statusLabels: Record<CustomerStatus, string> = { PROSPECT: "Prospect", ACTIVE: "Active", INACTIVE: "Inactive", BLOCKED: "Blocked" };

function money(value: string | null | undefined, currency = "INR") {
  if (value == null) return "Not captured";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
}
function dateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not available";
}
function message(reason: unknown) { return reason instanceof ApiError ? reason.message : "Customer profile is unavailable"; }
function empty(label: string) { return <div className="customer-empty"><span>+</span><strong>No {label} yet</strong><p>Linked records will appear here when live workflows create them.</p></div>; }
function editDraft(customer: Customer): EditDraft {
  return {
    full_name: customer.full_name, email: customer.email ?? "", phone: customer.phone ?? "",
    alternate_phone: customer.alternate_phone ?? "", date_of_birth: customer.date_of_birth ?? "",
    gender: customer.gender ?? "", occupation: customer.occupation ?? "", company_name: customer.company_name ?? "",
    preferred_location: customer.preferred_location ?? "", requirements: customer.requirements ?? "",
    budget_min: customer.budget_min ?? "", budget_max: customer.budget_max ?? "",
    address_line1: customer.address_line1 ?? "", address_line2: customer.address_line2 ?? "",
    city: customer.city ?? "", state: customer.state ?? "", postal_code: customer.postal_code ?? "",
    country: customer.country ?? "", status: customer.status
  };
}

export default function CustomerProfilePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [data, setData] = useState<Customer360 | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [activity, setActivity] = useState({ activity_type: "CALL" as ActivityType, subject: "", notes: "", channel: "PHONE", direction: "OUTBOUND" });
  const [addingActivity, setAddingActivity] = useState(false);
  const canUpdate = permissionGranted(permissions, "customers.update");
  const canDelete = permissionGranted(permissions, "customers.delete");
  const canCreateActivity = permissionGranted(permissions, "activities.create");
  const canDeleteActivity = permissionGranted(permissions, "activities.delete");

  useEffect(() => {
    if (!session || !id) return;
    let active = true;
    void apiRequest<Customer360>(`/customers/${id}/360`)
      .then((value) => { if (active) { setData(value); setDraft(editDraft(value.customer)); } })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, refresh, session]);

  const sections = data?.available_sections ?? [];
  const tabs: Array<{ id: Tab; label: string; visible: boolean }> = [
    { id: "overview", label: "Overview", visible: true },
    { id: "journey", label: "Journey & timeline", visible: sections.includes("lead_history") || sections.includes("activities") },
    { id: "sales", label: "Sales journey", visible: sections.some((item) => ["visits", "quotations", "bookings"].includes(item)) },
    { id: "financials", label: "Financials", visible: sections.includes("payments") || sections.includes("agreements") },
    { id: "documents", label: "Documents", visible: sections.includes("documents") },
    { id: "after-sales", label: "After-sales", visible: sections.includes("possession") || sections.includes("service_requests") }
  ];

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!draft) return; setSaving(true); setError(null);
    const payload = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, value === "" ? null : value]));
    try {
      await apiRequest<Customer>(`/customers/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      setEditing(false); setNotice("Customer profile updated"); setRefresh((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function removeCustomer() {
    if (!confirm("Delete this customer? Linked transactional records will prevent deletion.")) return;
    try { await apiRequest<void>(`/customers/${id}`, { method: "DELETE" }); router.push("/customers"); }
    catch (reason) { setError(message(reason)); }
  }

  async function addActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAddingActivity(true); setError(null);
    try {
      await apiRequest<CustomerActivity>(`/customers/${id}/activities`, { method: "POST", body: JSON.stringify({ ...activity, notes: activity.notes || null }) });
      setActivity({ activity_type: "CALL", subject: "", notes: "", channel: "PHONE", direction: "OUTBOUND" });
      setNotice("Activity added to the communication timeline"); setRefresh((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setAddingActivity(false); }
  }

  async function removeActivity(activityId: string) {
    if (!confirm("Delete this activity?")) return;
    try { await apiRequest<void>(`/customers/${id}/activities/${activityId}`, { method: "DELETE" }); setRefresh((value) => value + 1); }
    catch (reason) { setError(message(reason)); }
  }

  async function downloadDocument(document: Customer360["documents"][number]) {
    if (!document.file_name) return;
    try {
      const blob = await apiDownload(`/documents/${document.id}/download`);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url; anchor.download = document.file_name; anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) { setError(message(reason)); }
  }

  if (loading) return <AppShell><main className="dashboard-content"><div className="center-inline"><span className="spinner" />Loading Customer 360...</div></main></AppShell>;
  if (!data) return <AppShell><main className="dashboard-content"><Link href="/customers">Back to customers</Link>{error && <div className="alert alert-error page-alert">{error}</div>}</main></AppShell>;
  const customer = data.customer;
  return <AppShell><main className="dashboard-content customer-content">
    <div className="customer-profile-head">
      <Link href="/customers" className="back-link">← Customers</Link>
      <div className="customer-identity"><span className="customer-avatar">{customer.full_name.slice(0, 1).toUpperCase()}</span><div><p className="overline">Customer 360</p><h1>{customer.full_name}</h1><p>{customer.phone ?? customer.email} · {customer.owner_name ?? "Unassigned"}</p></div></div>
      <div className="heading-actions"><span className={`customer-status status-${customer.status.toLowerCase()}`}>{statusLabels[customer.status]}</span>{canUpdate && <button className="button button-secondary" onClick={() => setEditing(true)}>Edit profile</button>}{canDelete && <button className="button button-danger" onClick={() => void removeCustomer()}>Delete</button>}</div>
    </div>
    {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}{notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
    <nav className="customer-tabs" aria-label="Customer profile sections">{tabs.filter((item) => item.visible).map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>{item.label}</button>)}</nav>

    {tab === "overview" && <div className="customer-overview-grid">
      <div className="customer-main-stack">
        <section className="panel"><div className="panel-heading"><div><h2>Personal information</h2><p>Core identity and professional context.</p></div></div><dl className="customer-facts"><div><dt>Date of birth</dt><dd>{customer.date_of_birth ? new Date(`${customer.date_of_birth}T00:00:00`).toLocaleDateString("en-IN", { dateStyle: "medium" }) : "Not captured"}</dd></div><div><dt>Gender</dt><dd>{customer.gender ?? "Not captured"}</dd></div><div><dt>Occupation</dt><dd>{customer.occupation ?? "Not captured"}</dd></div><div><dt>Company</dt><dd>{customer.company_name ?? "Not captured"}</dd></div></dl></section>
        <section className="panel"><div className="panel-heading"><div><h2>Requirements</h2><p>Current buying preferences and budget range.</p></div></div><div className="requirement-summary"><div><span>Preferred location</span><strong>{customer.preferred_location ?? "Not captured"}</strong></div><div><span>Budget range</span><strong>{customer.budget_min || customer.budget_max ? `${money(customer.budget_min)} – ${money(customer.budget_max)}` : "Not captured"}</strong></div><p>{customer.requirements ?? "No detailed requirements have been captured."}</p></div></section>
      </div>
      <aside className="customer-side-stack">
        <section className="panel"><div className="panel-heading"><div><h2>Contact details</h2></div></div><dl className="customer-side-facts"><div><dt>Email</dt><dd>{customer.email ?? "Not captured"}</dd></div><div><dt>Primary phone</dt><dd>{customer.phone ?? "Not captured"}</dd></div><div><dt>Alternate phone</dt><dd>{customer.alternate_phone ?? "Not captured"}</dd></div><div><dt>Address</dt><dd>{[customer.address_line1, customer.address_line2, customer.city, customer.state, customer.postal_code, customer.country].filter(Boolean).join(", ") || "Not captured"}</dd></div></dl></section>
        <section className="panel relationship-card"><div className="panel-heading"><div><h2>Relationship</h2></div></div><div className="relationship-metrics"><div><strong>{customer.booking_count}</strong><span>Bookings</span></div><div><strong>{customer.activity_count}</strong><span>Activities</span></div></div><p>Customer since {new Date(customer.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}</p></section>
      </aside>
    </div>}

    {tab === "journey" && <div className="customer-journey-grid">
      <section className="panel"><div className="panel-heading"><div><h2>Communication timeline</h2><p>Lead and customer touchpoints in one chronological stream.</p></div></div>{data.timeline.length ? <div className="customer-timeline">{data.timeline.map((item) => <article key={`${item.kind}-${item.id}`}><span className={`timeline-dot kind-${item.kind}`} /><div><strong>{item.title}</strong>{item.detail && <p>{item.detail}</p>}<small>{item.status?.replaceAll("_", " ")} · {dateTime(item.occurred_at)}</small></div></article>)}</div> : empty("communication history")}</section>
      <aside className="customer-side-stack">
        {sections.includes("lead_history") && <section className="panel"><div className="panel-heading"><div><h2>Lead history</h2></div></div>{data.lead_history.length ? data.lead_history.map((lead) => <Link href={`/leads/${lead.id}`} className="journey-lead" key={lead.id}><span><strong>{lead.source_name ?? "Unspecified source"}</strong><small>Created {dateTime(lead.created_at)}</small></span><span className="score-mini">{lead.score}</span></Link>) : empty("linked lead")}</section>}
        {sections.includes("activities") && <section className="panel"><div className="panel-heading"><div><h2>Activities</h2><p>Direct customer interactions.</p></div></div>{canCreateActivity && <form className="compact-activity-form" onSubmit={addActivity}><div><select value={activity.activity_type} onChange={(e) => setActivity({ ...activity, activity_type: e.target.value as ActivityType })}><option value="CALL">Call</option><option value="EMAIL">Email</option><option value="MEETING">Meeting</option><option value="NOTE">Note</option><option value="FOLLOW_UP">Follow-up</option></select><input required minLength={2} placeholder="Activity subject" value={activity.subject} onChange={(e) => setActivity({ ...activity, subject: e.target.value })} /></div><textarea rows={3} placeholder="Optional notes" value={activity.notes} onChange={(e) => setActivity({ ...activity, notes: e.target.value })} /><button className="button button-primary" disabled={addingActivity}>{addingActivity ? "Adding..." : "Add activity"}</button></form>}<div className="customer-activity-list">{data.activities.map((item) => <article key={item.id}><div><strong>{item.subject}</strong><p>{item.notes ?? item.activity_type.replaceAll("_", " ")}</p><small>{item.performed_by_name ?? "System"} · {dateTime(item.occurred_at)}</small></div>{canDeleteActivity && <button className="danger-link" onClick={() => void removeActivity(item.id)}>Delete</button>}</article>)}</div>{!data.activities.length && !canCreateActivity && empty("activities")}</section>}
      </aside>
    </div>}

    {tab === "sales" && <section className="panel customer-record-panel"><div className="panel-heading"><div><h2>Sales journey</h2><p>Site visits, quotations, and bookings are grouped without mixing their details.</p></div></div>{data.sales.length ? <div className="record-groups">{(["site_visit", "quotation", "booking"] as const).map((kind) => { const items = data.sales.filter((item) => item.kind === kind); return sections.includes(kind === "site_visit" ? "visits" : `${kind}s`) && <div key={kind}><h3>{kind === "site_visit" ? "Site visits" : `${kind[0].toUpperCase()}${kind.slice(1)}s`} <span>{items.length}</span></h3>{items.length ? items.map((item) => <SalesRow item={item} key={item.id} />) : empty(kind.replace("_", " "))}</div>; })}</div> : empty("sales records")}</section>}

    {tab === "financials" && <div className="financial-layout">
      <div className="customer-main-stack">{sections.includes("payments") && <section className="panel"><div className="panel-heading"><div><h2>Payment history</h2><p>Posted and pending customer payments.</p></div></div>{data.payments.length ? <div className="customer-record-list">{data.payments.map((item) => <article key={item.id}><span><strong>{money(item.amount, item.currency)}</strong><small>{item.method} · {item.booking_number ?? "No booking reference"}</small></span><span><em>{item.status.replaceAll("_", " ")}</em><small>{dateTime(item.paid_at ?? item.created_at)}</small></span></article>)}</div> : empty("payments")}</section>}{sections.includes("agreements") && <section className="panel"><div className="panel-heading"><div><h2>Agreements</h2></div></div>{data.agreements.length ? <div className="customer-record-list">{data.agreements.map((item) => <article key={item.id}><span><strong>{item.agreement_number}</strong><small>{item.booking_number}</small></span><span><em>{item.status}</em><small>{dateTime(item.registered_at ?? item.signed_at ?? item.issued_at)}</small></span></article>)}</div> : empty("agreements")}</section>}</div>
      {data.financial_summary && <aside className="panel outstanding-card"><p className="overline">Current balance</p><h2>{money(data.financial_summary.outstanding_amount, data.financial_summary.currency ?? "INR")}</h2><span>Outstanding amount</span><div><small>Payments received</small><strong>{money(data.financial_summary.paid_amount, data.financial_summary.currency ?? "INR")}</strong></div><p>Calculated from tenant-scoped ledger debits and credits.</p></aside>}
    </div>}

    {tab === "documents" && <section className="panel customer-record-panel"><div className="panel-heading"><div><h2>Documents</h2><p>Current KYC records. Downloads always pass through authenticated access control.</p></div><Link href={`/documents?customer_id=${id}`}>Open document center</Link></div>{data.documents.length ? <div className="document-grid">{data.documents.map((item) => <article key={item.id}><span className="document-icon">DOC</span><div><strong>{item.file_name ?? item.document_type.replaceAll("_", " ")}</strong><p>{item.document_type.replaceAll("_", " ")} · v{item.version} · {item.size_bytes == null ? "Awaiting upload" : `${(item.size_bytes / 1024).toFixed(1)} KB`}</p><small>{item.status} · {item.expiry_date ? `Expires ${item.expiry_date}` : dateTime(item.created_at)}</small>{item.rejection_reason && <small>{item.rejection_reason}</small>}{item.file_name && <button className="danger-link" onClick={() => void downloadDocument(item)}>Secure download</button>}</div></article>)}</div> : empty("documents")}</section>}

    {tab === "after-sales" && <div className="customer-overview-grid"><section className="panel"><div className="panel-heading"><div><h2>Possession</h2><p>Offer, scheduling, and completion status.</p></div></div>{data.possessions.length ? <div className="customer-record-list">{data.possessions.map((item) => <article key={item.id}><span><strong>Unit {item.unit_number}</strong><small>{item.booking_number}</small></span><span><em>{item.status}</em><small>{dateTime(item.completed_at ?? item.scheduled_at ?? item.offered_at)}</small></span></article>)}</div> : empty("possession records")}</section><section className="panel"><div className="panel-heading"><div><h2>Service requests</h2><p>Customer support cases and their resolution state.</p></div></div>{data.service_requests.length ? <div className="customer-record-list">{data.service_requests.map((item) => <article key={item.id}><span><strong>{item.subject}</strong><small>{item.request_number} · {item.category}</small></span><span><em>{item.status}</em><small>{item.priority} · {dateTime(item.opened_at)}</small></span></article>)}</div> : empty("service requests")}</section></div>}

    {editing && draft && <div className="modal-backdrop" role="presentation"><form className="modal-card customer-edit-modal" role="dialog" aria-modal="true" aria-label="Edit customer" onSubmit={saveProfile}><div className="modal-heading"><div><p className="overline">Customer profile</p><h2>Edit information</h2></div><button type="button" className="icon-button" onClick={() => setEditing(false)}>×</button></div><div className="customer-edit-scroll"><div className="lead-form-grid">{([ ["full_name", "Full name"], ["email", "Email"], ["phone", "Primary phone"], ["alternate_phone", "Alternate phone"], ["date_of_birth", "Date of birth"], ["gender", "Gender"], ["occupation", "Occupation"], ["company_name", "Company"], ["preferred_location", "Preferred location"], ["budget_min", "Minimum budget"], ["budget_max", "Maximum budget"], ["address_line1", "Address line 1"], ["address_line2", "Address line 2"], ["city", "City"], ["state", "State"], ["postal_code", "Postal code"], ["country", "Country"] ] as Array<[keyof EditDraft, string]>).map(([field, label]) => <label className={`field ${["full_name", "preferred_location", "address_line1", "address_line2"].includes(field) ? "span-two" : ""}`} key={field}><span>{label}</span><input type={field === "date_of_birth" ? "date" : field.includes("budget") ? "number" : field === "email" ? "email" : "text"} required={field === "full_name"} value={String(draft[field])} onChange={(e) => setDraft({ ...draft, [field]: e.target.value })} /></label>)}<label className="field span-two"><span>Requirements</span><textarea rows={4} value={draft.requirements} onChange={(e) => setDraft({ ...draft, requirements: e.target.value })} /></label><label className="field span-two"><span>Status</span><select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as CustomerStatus })}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div></div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setEditing(false)}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? "Saving..." : "Save changes"}</button></div></form></div>}
  </main></AppShell>;
}

function SalesRow({ item }: { item: CustomerSalesRecord }) {
  return <article className="sales-record"><span><strong>{item.reference}</strong><small>{item.project_name ?? item.unit_number ?? "No project detail"}</small></span><span>{item.amount ? money(item.amount, item.currency ?? "INR") : ""}</span><span><em>{item.status.replaceAll("_", " ")}</em><small>{dateTime(item.occurred_at)}</small></span></article>;
}
