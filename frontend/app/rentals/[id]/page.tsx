"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiDownload, apiRequest, ApiError, permissionGranted, RentalLeaseDetail } from "@/lib/api";

type Tab = "overview" | "documents" | "rent" | "lifecycle" | "maintenance";
type FormMode = "document" | "invoice" | "payment" | "renewal" | "move" | "complete_move" | "maintenance" | null;

function money(amount: string, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(Number(amount));
}

export default function RentalLeasePage() {
  const id = useParams<{ id: string }>().id;
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const canApprove = permissionGranted(permissions, "leases.approve");
  const canManage = permissionGranted(permissions, "leases.update");
  const canPay = permissionGranted(permissions, "payments.create");
  const [detail, setDetail] = useState<RentalLeaseDetail | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [mode, setMode] = useState<FormMode>(null);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setDetail(await apiRequest<RentalLeaseDetail>(`/rentals/leases/${id}`)); setError(null); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Lease could not be loaded"); }
  }, [id]);
  useEffect(() => { const timer = setTimeout(() => void load(), 0); return () => clearTimeout(timer); }, [load]);

  async function mutate(path: string, body: unknown, message: string) {
    setBusy(true);
    try {
      setDetail(await apiRequest<RentalLeaseDetail>(`/rentals/leases/${id}${path}`, { method: "POST", body: JSON.stringify(body) }));
      setMode(null); setNotice(message); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Rental action failed"); }
    finally { setBusy(false); }
  }

  async function decision(path: string, status: "APPROVED" | "REJECTED" | "VERIFIED" | "COMPLETED" | "FAILED") {
    const notes = window.prompt(`Add review notes for ${status.toLowerCase()}:`);
    if (!notes?.trim()) return;
    await mutate(path, { status, notes: notes.trim() }, `Decision recorded: ${status.toLowerCase()}`);
  }

  async function upload(documentId: string, file: File) {
    const form = new FormData(); form.append("file", file); setBusy(true);
    try {
      setDetail(await apiRequest<RentalLeaseDetail>(`/rentals/leases/${id}/documents/${documentId}/upload`, { method: "POST", body: form }));
      setNotice("Private lease document uploaded for independent review"); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Document upload failed"); }
    finally { setBusy(false); }
  }

  async function download(documentId: string, filename: string) {
    try { const blob = await apiDownload(`/rentals/leases/${id}/documents/${documentId}/download`); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Secure download failed"); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    if (mode === "document") await mutate("/documents", { document_type: values.document_type, is_required: values.is_required === "on" }, "Document requirement added");
    if (mode === "invoice") {
      const schedule = detail?.schedule.find((item) => item.id === values.schedule_item_id);
      await mutate("/invoices", { schedule_item_id: values.schedule_item_id, invoice_number: values.invoice_number, issue_date: values.issue_date, due_date: values.due_date || schedule?.due_date, tax_amount: values.tax_amount || "0" }, "Rent invoice issued from the server schedule");
    }
    if (mode === "payment") await mutate(`/invoices/${selectedId}/payments`, { amount: values.amount, method: values.method, reference_number: values.reference_number || null, idempotency_key: crypto.randomUUID() }, "Rent payment submitted for verification");
    if (mode === "renewal") await mutate("/renewals", { proposed_end_date: values.proposed_end_date, proposed_monthly_rent: values.proposed_monthly_rent, reason: values.reason }, "Lease renewal requested");
    if (mode === "move") await mutate("/moves", { move_type: values.move_type, scheduled_at: new Date(String(values.scheduled_at)).toISOString(), notes: values.notes || null }, "Move workflow requested");
    if (mode === "complete_move") await mutate(`/moves/${selectedId}/complete`, { checklist: { keys_confirmed: values.keys_confirmed === "on", inspection_completed: values.inspection_completed === "on" }, meter_readings: values.meter_reading ? { utility: values.meter_reading } : {}, notes: values.notes || null }, "Move checklist completed");
    if (mode === "maintenance") {
      setBusy(true);
      try {
        const updated = await apiRequest<RentalLeaseDetail>("/rentals/maintenance", { method: "POST", body: JSON.stringify({ lease_id: id, title: values.title, description: values.description, scheduled_at: values.scheduled_at ? new Date(String(values.scheduled_at)).toISOString() : null }) });
        setDetail(updated); setMode(null); setNotice("Maintenance request opened"); setError(null);
      } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Maintenance request failed"); }
      finally { setBusy(false); }
    }
  }

  if (!detail) return <AppShell><main className="dashboard-content"><Link href="/rentals" className="back-link">← Rental management</Link>{error ? <div className="alert alert-error">{error}</div> : <div className="loading-card">Loading rental lease…</div>}</main></AppShell>;
  const lease = detail.lease;
  const nextSchedule = detail.schedule.find((item) => item.status === "SCHEDULED" || item.status === "OVERDUE");
  return <AppShell><main className="dashboard-content rental-detail">
    <Link href="/rentals" className="back-link">← Rental management</Link>
    <section className="rental-hero"><div><div className="rental-hero-meta"><span>{lease.lease_number}</span><em className={`rental-status status-${lease.status.toLowerCase()}`}>{lease.status.replaceAll("_", " ")}</em></div><h1>{lease.property_name}</h1><p>{lease.tenant_name} · {lease.property_code}</p></div><div className="rental-hero-value"><small>Monthly rent</small><strong>{money(lease.monthly_rent, lease.currency)}</strong><span>{new Date(lease.start_date).toLocaleDateString()} — {new Date(lease.end_date).toLocaleDateString()}</span></div></section>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    <nav className="detail-tabs">{(["overview", "documents", "rent", "lifecycle", "maintenance"] as Tab[]).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item === "rent" ? "Rent & payments" : item === "lifecycle" ? "Renewal & moves" : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>

    {tab === "overview" && <div className="rental-detail-grid"><section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Contract</p><h2>Lease terms</h2></div></div><dl className="rental-key-values"><div><dt>Security deposit</dt><dd>{money(detail.security_deposit, lease.currency)}</dd></div><div><dt>Rent due</dt><dd>Day {detail.rent_due_day} monthly</dd></div><div><dt>Notice period</dt><dd>{detail.notice_period_days} days</dd></div><div><dt>Outstanding</dt><dd>{money(lease.outstanding, lease.currency)}</dd></div></dl><div className="terms-block"><span>Terms</span><p>{detail.terms || "No additional lease terms recorded."}</p></div></section><aside className="data-card rental-section"><p className="overline">Next steps</p><h2>Governed workflow</h2><div className="rental-actions">{canApprove && lease.status === "DRAFT" && <button className="button button-primary" onClick={() => void mutate("/transition", { status: "PENDING_SIGNATURE", notes: "Lease issued for signature" }, "Lease sent for signature")}>Send for signature</button>}{canApprove && lease.status === "PENDING_SIGNATURE" && <button className="button button-primary" onClick={() => void mutate("/transition", { status: "SIGNED", notes: "Verified documents and signed lease" }, "Lease signed; property reserved")}>Confirm signed lease</button>}{lease.status === "MOVE_IN_PENDING" && <button className="button button-primary" onClick={() => { setMode("move"); }}>Request move-in</button>}{lease.status === "ACTIVE" && <><button className="button button-primary" onClick={() => setMode("renewal")}>Request renewal</button><button className="button button-secondary" onClick={() => setMode("move")}>Request move-out</button></>}<button className="button button-secondary" onClick={() => setMode("maintenance")}>Report maintenance</button></div><p className="governance-note">A signed lease reserves only this rental property. No sales inventory or booking status is touched.</p></aside></div>}

    {tab === "documents" && <section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Private storage</p><h2>Lease documents</h2></div><button className="button button-secondary" onClick={() => setMode("document")}>Add requirement</button></div><div className="rental-document-list">{detail.documents.map((item) => <article key={item.id}><span className="document-icon">DOC</span><div><strong>{item.document_type.replaceAll("_", " ")}</strong><small>Version {item.version} · {item.is_required ? "Required" : "Optional"}</small></div><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em><div className="document-actions">{item.file_name && <button onClick={() => void download(item.id, item.file_name!)}>Download</button>}<label className="upload-action">{item.file_name ? "Replace" : "Upload"}<input type="file" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(item.id, file); }}/></label>{canApprove && item.status === "UPLOADED" && <><button onClick={() => void decision(`/documents/${item.id}/decision`, "VERIFIED")}>Verify</button><button className="danger-link" onClick={() => void decision(`/documents/${item.id}/decision`, "REJECTED")}>Reject</button></>}</div></article>)}</div></section>}

    {tab === "rent" && <div className="rental-detail-stack"><section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Server-calculated</p><h2>Rent schedule</h2></div>{canManage && nextSchedule && <button className="button button-primary" onClick={() => setMode("invoice")}>Issue next invoice</button>}</div><div className="schedule-list">{detail.schedule.map((item) => <div key={item.id}><span><strong>#{item.sequence} · {new Date(item.period_start).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</strong><small>Due {new Date(item.due_date).toLocaleDateString()}</small></span><strong>{money(item.amount, item.currency)}</strong><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em></div>)}</div></section><section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Rent ledger</p><h2>Invoices & payments</h2></div></div><div className="invoice-list">{detail.invoices.length ? detail.invoices.map((item) => <article key={item.id}><div><strong>{item.invoice_number}</strong><small>Due {new Date(item.due_date).toLocaleDateString()} · {item.status}</small></div><div><strong>{money(item.total, item.currency)}</strong><small>{money(item.outstanding, item.currency)} outstanding</small></div>{canPay && item.status !== "PAID" && item.status !== "VOIDED" && <button className="button button-secondary" onClick={() => { setSelectedId(item.id); setMode("payment"); }}>Record payment</button>}</article>) : <p className="empty-inline">No rental invoice has been issued.</p>}</div>{detail.payments.length > 0 && <div className="payment-history"><h3>Payment verification</h3>{detail.payments.map((item) => <div key={item.id}><span><strong>{money(item.amount, item.currency)}</strong><small>{item.method} · {item.reference_number ?? "No reference"}</small></span><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em>{canApprove && item.status === "PENDING" && <span className="inline-actions"><button onClick={() => void decision(`/payments/${item.id}/decision`, "COMPLETED")}>Verify</button><button onClick={() => void decision(`/payments/${item.id}/decision`, "FAILED")}>Reject</button></span>}</div>)}</div>}</section></div>}

    {tab === "lifecycle" && <div className="rental-detail-grid"><section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Extension</p><h2>Lease renewals</h2></div>{lease.status === "ACTIVE" && <button className="button button-secondary" onClick={() => setMode("renewal")}>Request renewal</button>}</div><div className="workflow-list">{detail.renewals.length ? detail.renewals.map((item) => <article key={item.id}><div><strong>Until {new Date(item.proposed_end_date).toLocaleDateString()}</strong><small>{money(item.proposed_monthly_rent, lease.currency)} monthly · {item.reason}</small></div><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em>{canApprove && item.status === "REQUESTED" && <span className="inline-actions"><button onClick={() => void decision(`/renewals/${item.id}/decision`, "APPROVED")}>Approve</button><button onClick={() => void decision(`/renewals/${item.id}/decision`, "REJECTED")}>Reject</button></span>}</article>) : <p className="empty-inline">No renewal requests.</p>}</div></section><section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Occupancy control</p><h2>Move-in / move-out</h2></div></div><div className="workflow-list">{detail.moves.length ? detail.moves.map((item) => <article key={item.id}><div><strong>{item.move_type.replace("_", "-")}</strong><small>{new Date(item.scheduled_at).toLocaleString()} · {item.notes}</small></div><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em>{canApprove && item.status === "REQUESTED" && <span className="inline-actions"><button onClick={() => void decision(`/moves/${item.id}/decision`, "APPROVED")}>Approve</button><button onClick={() => void decision(`/moves/${item.id}/decision`, "REJECTED")}>Reject</button></span>}{canApprove && item.status === "APPROVED" && <button onClick={() => { setSelectedId(item.id); setMode("complete_move"); }}>Complete checklist</button>}</article>) : <p className="empty-inline">No move workflow recorded.</p>}</div></section></div>}

    {tab === "maintenance" && <section className="data-card rental-section"><div className="section-heading"><div><p className="overline">Rental property care</p><h2>Maintenance requests</h2></div><button className="button button-primary" onClick={() => setMode("maintenance")}>Report issue</button></div><div className="maintenance-grid">{detail.maintenance.length ? detail.maintenance.map((item) => <article key={item.id}><div><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em><small>{new Date(item.created_at).toLocaleDateString()}</small></div><h3>{item.title}</h3><p>{item.description}</p>{canManage && !["CLOSED", "CANCELLED"].includes(item.status) && <button onClick={() => void mutate(`/maintenance/${item.id}`, { status: "RESOLVED" }, "Maintenance marked resolved")}>Mark resolved</button>}</article>) : <p className="empty-inline">No maintenance issues reported.</p>}</div></section>}

    {mode && <ActionModal mode={mode} detail={detail} selectedId={selectedId} busy={busy} onClose={() => setMode(null)} onSubmit={submit} />}
  </main></AppShell>;
}

function ActionModal({ mode, detail, selectedId, busy, onClose, onSubmit }: { mode: Exclude<FormMode, null>; detail: RentalLeaseDetail; selectedId: string; busy: boolean; onClose: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const next = detail.schedule.find((item) => item.status === "SCHEDULED" || item.status === "OVERDUE");
  const invoice = detail.invoices.find((item) => item.id === selectedId);
  return <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={onSubmit}><div className="modal-heading"><div><p className="overline">Rental workflow</p><h2>{({ document: "Add lease document", invoice: "Issue rent invoice", payment: "Record rent payment", renewal: "Request renewal", move: "Schedule a move", complete_move: "Complete move checklist", maintenance: "Report maintenance" })[mode]}</h2></div><button type="button" className="icon-button" onClick={onClose}>×</button></div><div className="rental-form-grid single-form">
    {mode === "document" && <><label className="field"><span>Document type</span><input name="document_type" required placeholder="Tenant ID, addendum…"/></label><label className="check-field"><input name="is_required" type="checkbox" defaultChecked/><span>Required before lease activation</span></label></>}
    {mode === "invoice" && <><label className="field"><span>Schedule period</span><select name="schedule_item_id" defaultValue={next?.id} required>{detail.schedule.filter((item) => item.status === "SCHEDULED" || item.status === "OVERDUE").map((item) => <option value={item.id} key={item.id}>#{item.sequence} · {item.period_start} · {money(item.amount, item.currency)}</option>)}</select></label><label className="field"><span>Invoice number</span><input name="invoice_number" required/></label><label className="field"><span>Issue date</span><input name="issue_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required/></label><label className="field"><span>Due date</span><input name="due_date" type="date" defaultValue={next?.due_date} required/></label><label className="field"><span>Tax amount</span><input name="tax_amount" type="number" min="0" step="0.01" defaultValue="0"/></label></>}
    {mode === "payment" && <><label className="field"><span>Amount</span><input name="amount" type="number" min="0.01" step="0.01" max={invoice?.outstanding} required/></label><label className="field"><span>Payment method</span><select name="method" required><option>BANK_TRANSFER</option><option>UPI</option><option>CHEQUE</option><option>CARD</option><option>CASH</option></select></label><label className="field"><span>Reference number</span><input name="reference_number"/></label></>}
    {mode === "renewal" && <><label className="field"><span>New end date</span><input name="proposed_end_date" type="date" min={detail.lease.end_date} required/></label><label className="field"><span>Proposed monthly rent</span><input name="proposed_monthly_rent" type="number" min="0.01" step="0.01" defaultValue={detail.lease.monthly_rent} required/></label><label className="field"><span>Reason</span><textarea name="reason" rows={3} required/></label></>}
    {mode === "move" && <><label className="field"><span>Move type</span><select name="move_type" defaultValue={detail.lease.status === "MOVE_IN_PENDING" ? "MOVE_IN" : "MOVE_OUT"}><option value="MOVE_IN">Move-in</option><option value="MOVE_OUT">Move-out</option></select></label><label className="field"><span>Scheduled date & time</span><input name="scheduled_at" type="datetime-local" required/></label><label className="field"><span>Notes</span><textarea name="notes" rows={3}/></label></>}
    {mode === "complete_move" && <><label className="check-field"><input name="keys_confirmed" type="checkbox" required/><span>Keys handover / return confirmed</span></label><label className="check-field"><input name="inspection_completed" type="checkbox" required/><span>Property inspection completed</span></label><label className="field"><span>Utility meter reading</span><input name="meter_reading"/></label><label className="field"><span>Completion notes</span><textarea name="notes" rows={3} required/></label></>}
    {mode === "maintenance" && <><label className="field"><span>Issue title</span><input name="title" required/></label><label className="field"><span>Description</span><textarea name="description" rows={4} required/></label><label className="field"><span>Preferred visit</span><input name="scheduled_at" type="datetime-local"/></label></>}
  </div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancel</button><button disabled={busy} className="button button-primary">{busy ? "Saving…" : "Continue"}</button></div></form></div>;
}
