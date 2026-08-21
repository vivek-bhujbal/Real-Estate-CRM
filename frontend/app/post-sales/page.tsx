"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiDownload,
  apiRequest,
  ApiError,
  Cancellation,
  PageResponse,
  permissionGranted,
  PostSalesOptions,
  PostSalesStats,
  UnitTransfer,
  WorkflowStatus
} from "@/lib/api";

type Tab = "cancellations" | "transfers";
type Action = { kind: "review" | "decision" | "complete"; record: Cancellation | UnitTransfer; decision?: "APPROVED" | "REJECTED" };
type InstallmentDraft = { name: string; due_date: string; amount: string };

const money = (value: string, currency: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));
const when = (value: string | null) => value ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not recorded";
const today = () => new Date().toISOString().slice(0, 10);

export default function PostSalesPage() {
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const canRequest = permissionGranted(permissions, "bookings.update");
  const canReview = permissionGranted(permissions, "bookings.update") || permissionGranted(permissions, "collections.update");
  const canApprove = permissionGranted(permissions, "bookings.approve") || permissionGranted(permissions, "collections.approve");
  const [tab, setTab] = useState<Tab>("cancellations");
  const [stats, setStats] = useState<PostSalesStats | null>(null);
  const [cancellations, setCancellations] = useState<PageResponse<Cancellation> | null>(null);
  const [transfers, setTransfers] = useState<PageResponse<UnitTransfer> | null>(null);
  const [options, setOptions] = useState<PostSalesOptions>({ bookings: [], transfer_quotations: [] });
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<WorkflowStatus | "">("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [createMode, setCreateMode] = useState<"cancellation" | "transfer" | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    try {
      const [totals, list, choices] = await Promise.all([
        apiRequest<PostSalesStats>("/post-sales/stats"),
        tab === "cancellations"
          ? apiRequest<PageResponse<Cancellation>>(`/post-sales/cancellations?${params}`)
          : apiRequest<PageResponse<UnitTransfer>>(`/post-sales/transfers?${params}`),
        canRequest ? apiRequest<PostSalesOptions>("/post-sales/options") : Promise.resolve({ bookings: [], transfer_quotations: [] })
      ]);
      setStats(totals);
      if (tab === "cancellations") setCancellations(list as PageResponse<Cancellation>);
      else setTransfers(list as PageResponse<UnitTransfer>);
      setOptions(choices);
      setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Post-sales workflows could not be loaded");
    } finally { setLoading(false); }
  }, [canRequest, page, query, status, tab]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function switchTab(next: Tab) { setTab(next); setPage(1); setStatus(""); setLoading(true); }

  async function mutate(path: string, payload?: unknown, message = "Workflow updated") {
    setBusy(true);
    try {
      await apiRequest(path, { method: "POST", body: payload === undefined ? undefined : JSON.stringify(payload) });
      setNotice(message); setError(null); setAction(null); setCreateMode(null); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "The workflow action failed"); }
    finally { setBusy(false); }
  }

  async function download(kind: Tab, id: string, documentNumber: string | null) {
    try {
      const blob = await apiDownload(`/post-sales/${kind}/${id}/document`);
      const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${documentNumber ?? "workflow-document"}.pdf`; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Document download failed"); }
  }

  function search(event: FormEvent) { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }
  const result = tab === "cancellations" ? cancellations : transfers;

  return <AppShell><main className="dashboard-content post-sales-content">
    <div className="management-heading"><div><p className="overline">Governed post-sales operations</p><h1>Cancellations & transfers</h1><p>Four-eyes approvals, server-side financial calculations, locked inventory transitions, and private documents.</p></div>{canRequest && <div className="heading-actions"><button className="button button-secondary" onClick={() => setCreateMode("transfer")}>Request transfer</button><button className="button button-primary" onClick={() => setCreateMode("cancellation")}>Request cancellation</button></div>}</div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    {stats && <section className="post-sales-metrics"><article><span>Cancellation requests</span><strong>{stats.cancellation_requested}</strong></article><article><span>Under review</span><strong>{stats.cancellation_under_review + stats.transfer_under_review}</strong></article><article><span>Approved to finalize</span><strong>{stats.cancellation_approved + stats.transfer_approved}</strong></article><article><span>Refunds processing</span><strong>{stats.refunds_processing}</strong></article><article><span>Transfer requests</span><strong>{stats.transfer_requested}</strong></article></section>}
    <div className="post-sales-tabs"><button className={tab === "cancellations" ? "active" : ""} onClick={() => switchTab("cancellations")}>Cancellations</button><button className={tab === "transfers" ? "active" : ""} onClick={() => switchTab("transfers")}>Unit transfers</button></div>
    <section className="inventory-filter-panel post-sales-filters"><form className="inventory-search" onSubmit={search}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search booking, customer, or unit..."/><button className="button button-primary">Search</button></form><select value={status} onChange={(event) => { setStatus(event.target.value as WorkflowStatus | ""); setPage(1); }}><option value="">All workflow states</option>{["REQUESTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "COMPLETED"].map((item) => <option key={item}>{item}</option>)}</select></section>
    <section className="data-card post-sales-table-card"><div className="post-sales-table"><div className={`post-sales-row head ${tab}`}><span>Booking / customer</span><span>{tab === "cancellations" ? "Unit" : "Unit movement"}</span><span>{tab === "cancellations" ? "Calculation" : "Price recalculation"}</span><span>Workflow</span><span>Ownership</span><span>Actions</span></div>
      {loading ? <div className="customer-empty"><span className="spinner"/><strong>Loading workflow queue</strong></div> : result?.items.length ? tab === "cancellations" ? (cancellations?.items ?? []).map((item) => <CancellationRow key={item.id} item={item} canReview={canReview} canApprove={canApprove} onAction={setAction} onDownload={() => void download("cancellations", item.id, item.document_number)}/>) : (transfers?.items ?? []).map((item) => <TransferRow key={item.id} item={item} canReview={canReview} canApprove={canApprove} onAction={setAction} onDownload={() => void download("transfers", item.id, item.document_number)}/>) : <div className="customer-empty"><span>↻</span><strong>No {tab === "cancellations" ? "cancellation" : "transfer"} records</strong><p>Records appear only after a user creates a real request. No transactions are generated automatically.</p></div>}
    </div><div className="pagination"><button disabled={!result || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>
    {createMode === "cancellation" && <CancellationCreateModal options={options} busy={busy} onClose={() => setCreateMode(null)} onSubmit={(bookingId, reason) => void mutate(`/post-sales/bookings/${bookingId}/cancellations`, { reason }, "Cancellation request submitted")}/>} 
    {createMode === "transfer" && <TransferCreateModal options={options} busy={busy} onClose={() => setCreateMode(null)} onSubmit={(bookingId, payload) => void mutate(`/post-sales/bookings/${bookingId}/transfers`, payload, "Unit transfer request submitted")}/>} 
    {action && <ActionModal tab={tab} action={action} busy={busy} onClose={() => setAction(null)} onSubmit={(payload) => { const base = `/post-sales/${tab}/${action.record.id}`; void mutate(`${base}/${action.kind}`, payload, action.kind === "complete" ? "Workflow finalized" : "Workflow updated"); }}/>} 
  </main></AppShell>;
}

function Status({ value }: { value: WorkflowStatus }) { return <em className={`post-sales-status status-${value.toLowerCase()}`}>{value.replaceAll("_", " ")}</em>; }

function CancellationRow({ item, canReview, canApprove, onAction, onDownload }: { item: Cancellation; canReview: boolean; canApprove: boolean; onAction: (action: Action) => void; onDownload: () => void }) {
  return <div className="post-sales-row cancellations"><span><strong>{item.booking_number}</strong><small>{item.customer_name}</small></span><span><strong>Unit {item.unit_number}</strong><small>{item.reason}</small></span><span><strong>{money(item.refund_amount, item.currency)} refund</strong><small>Paid {money(item.paid_amount_snapshot, item.currency)} · deduction {money(item.deduction_amount, item.currency)}</small></span><span><Status value={item.status}/><small>{when(item.updated_at)}</small></span><span><strong>{item.requested_by_name}</strong><small>{item.approved_by_name ? `Approved by ${item.approved_by_name}` : item.reviewed_by_name ? `Reviewed by ${item.reviewed_by_name}` : "Awaiting review"}</small></span><span className="post-sales-actions">{item.status === "REQUESTED" && canReview && <button onClick={() => onAction({ kind: "review", record: item })}>Review</button>}{item.status === "UNDER_REVIEW" && canApprove && <><button onClick={() => onAction({ kind: "decision", decision: "APPROVED", record: item })}>Approve</button><button className="danger" onClick={() => onAction({ kind: "decision", decision: "REJECTED", record: item })}>Reject</button></>}{item.status === "APPROVED" && canApprove && <button onClick={() => onAction({ kind: "complete", record: item })}>Finalize</button>}{item.status === "COMPLETED" && item.document_number && <button onClick={onDownload}>Document</button>}</span></div>;
}

function TransferRow({ item, canReview, canApprove, onAction, onDownload }: { item: UnitTransfer; canReview: boolean; canApprove: boolean; onAction: (action: Action) => void; onDownload: () => void }) {
  return <div className="post-sales-row transfers"><span><strong>{item.booking_number}</strong><small>{item.customer_name}</small></span><span><strong>{item.from_unit_number} → {item.to_unit_number}</strong><small>{item.quotation_number}</small></span><span><strong>{money(item.new_agreed_price, item.currency)}</strong><small>{Number(item.price_difference) >= 0 ? "+" : ""}{money(item.price_difference, item.currency)} adjustment</small></span><span><Status value={item.status}/><small>{when(item.updated_at)}</small></span><span><strong>{item.requested_by_name}</strong><small>{item.approved_by_name ? `Approved by ${item.approved_by_name}` : item.reviewed_by_name ? `Reviewed by ${item.reviewed_by_name}` : "Awaiting review"}</small></span><span className="post-sales-actions">{item.status === "REQUESTED" && canReview && <button onClick={() => onAction({ kind: "review", record: item })}>Review</button>}{item.status === "UNDER_REVIEW" && canApprove && <><button onClick={() => onAction({ kind: "decision", decision: "APPROVED", record: item })}>Approve</button><button className="danger" onClick={() => onAction({ kind: "decision", decision: "REJECTED", record: item })}>Reject</button></>}{item.status === "APPROVED" && canApprove && <button onClick={() => onAction({ kind: "complete", record: item })}>Finalize</button>}{item.status === "COMPLETED" && item.document_number && <button onClick={onDownload}>Document</button>}</span></div>;
}

function CancellationCreateModal({ options, busy, onClose, onSubmit }: { options: PostSalesOptions; busy: boolean; onClose: () => void; onSubmit: (bookingId: string, reason: string) => void }) {
  const [bookingId, setBookingId] = useState(""); const [reason, setReason] = useState("");
  return <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={(event) => { event.preventDefault(); onSubmit(bookingId, reason); }}><div className="modal-heading"><div><p className="overline">Customer request</p><h2>Request cancellation</h2></div><button type="button" className="icon-button" onClick={onClose}>×</button></div><div className="post-sales-modal-body"><label className="field"><span>Confirmed booking</span><select required value={bookingId} onChange={(event) => setBookingId(event.target.value)}><option value="">Select booking</option>{options.bookings.map((item) => <option key={item.id} value={item.id}>{item.booking_number} · {item.customer_name} · Unit {item.unit_number}</option>)}</select></label><label className="field"><span>Customer request / reason</span><textarea required minLength={5} maxLength={2000} rows={5} value={reason} onChange={(event) => setReason(event.target.value)}/></label><p className="governance-note">Submitting does not release the unit. Review, approval, server calculation, and finalization remain separate controlled steps.</p></div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancel</button><button disabled={busy || !bookingId} className="button button-primary">Submit request</button></div></form></div>;
}

function TransferCreateModal({ options, busy, onClose, onSubmit }: { options: PostSalesOptions; busy: boolean; onClose: () => void; onSubmit: (bookingId: string, payload: unknown) => void }) {
  const [bookingId, setBookingId] = useState(""); const [quotationId, setQuotationId] = useState(""); const [reason, setReason] = useState(""); const [planName, setPlanName] = useState("Revised transfer schedule"); const [effective, setEffective] = useState(today()); const [installments, setInstallments] = useState<InstallmentDraft[]>([{ name: "Revised balance", due_date: today(), amount: "" }]);
  const booking = options.bookings.find((item) => item.id === bookingId); const quotes = options.transfer_quotations.filter((item) => item.customer_id === booking?.customer_id); const quote = quotes.find((item) => item.id === quotationId);
  const total = useMemo(() => installments.reduce((sum, item) => sum + Number(item.amount || 0), 0), [installments]);
  function patchRow(index: number, patch: Partial<InstallmentDraft>) { setInstallments((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row)); }
  return <div className="modal-backdrop"><form className="modal-card transfer-modal" onSubmit={(event) => { event.preventDefault(); onSubmit(bookingId, { quotation_id: quotationId, reason, revised_payment_plan: { name: planName, effective_from: effective, installments } }); }}><div className="modal-heading"><div><p className="overline">Inventory reassignment</p><h2>Request unit transfer</h2></div><button type="button" className="icon-button" onClick={onClose}>×</button></div><div className="post-sales-modal-body"><div className="post-sales-form-grid"><label className="field"><span>Confirmed booking</span><select required value={bookingId} onChange={(event) => { setBookingId(event.target.value); setQuotationId(""); setInstallments([{ name: "Revised balance", due_date: effective, amount: "" }]); }}><option value="">Select booking</option>{options.bookings.map((item) => <option key={item.id} value={item.id}>{item.booking_number} · Unit {item.unit_number} · {item.customer_name}</option>)}</select></label><label className="field"><span>Accepted target quotation</span><select required disabled={!bookingId} value={quotationId} onChange={(event) => { const nextId = event.target.value; const nextQuote = quotes.find((item) => item.id === nextId); setQuotationId(nextId); setInstallments([{ name: "Revised balance", due_date: effective, amount: nextQuote?.final_agreed_value ?? "" }]); }}><option value="">Select priced target unit</option>{quotes.map((item) => <option key={item.id} value={item.id}>{item.quotation_number} · Unit {item.unit_number} · {money(item.final_agreed_value, item.currency)}</option>)}</select></label><label className="field span-two"><span>Transfer reason</span><textarea required minLength={5} maxLength={2000} rows={3} value={reason} onChange={(event) => setReason(event.target.value)}/></label><label className="field"><span>Revised plan name</span><input required minLength={2} value={planName} onChange={(event) => setPlanName(event.target.value)}/></label><label className="field"><span>Effective from</span><input required type="date" value={effective} onChange={(event) => setEffective(event.target.value)}/></label></div><div className="installment-editor"><header><div><strong>Revised installments</strong><small>Must equal the accepted target value. Existing verified payments are reallocated FIFO at finalization.</small></div><button type="button" onClick={() => setInstallments((rows) => [...rows, { name: "", due_date: effective, amount: "" }])}>+ Add milestone</button></header>{installments.map((row, index) => <div className="installment-draft" key={index}><input required placeholder="Milestone" value={row.name} onChange={(event) => patchRow(index, { name: event.target.value })}/><input required min={effective} type="date" value={row.due_date} onChange={(event) => patchRow(index, { due_date: event.target.value })}/><input required min="0.01" step="0.01" type="number" placeholder="Amount" value={row.amount} onChange={(event) => patchRow(index, { amount: event.target.value })}/><button type="button" disabled={installments.length === 1} onClick={() => setInstallments((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>×</button></div>)}<footer><span>Schedule total</span><strong>{money(String(total), quote?.currency ?? booking?.currency ?? "INR")}</strong><small className={quote && Math.abs(total - Number(quote.final_agreed_value)) < .01 ? "match" : "mismatch"}>{quote ? `Target ${money(quote.final_agreed_value, quote.currency)}` : "Choose a target quotation"}</small></footer></div></div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancel</button><button disabled={busy || !quote || Math.abs(total - Number(quote.final_agreed_value)) >= .01} className="button button-primary">Submit transfer</button></div></form></div>;
}

function ActionModal({ tab, action, busy, onClose, onSubmit }: { tab: Tab; action: Action; busy: boolean; onClose: () => void; onSubmit: (payload?: unknown) => void }) {
  const [notes, setNotes] = useState(""); const [deductionType, setDeductionType] = useState<"FIXED" | "PERCENTAGE">("FIXED"); const [deductionValue, setDeductionValue] = useState("0"); const isCancellationReview = tab === "cancellations" && action.kind === "review";
  const title = action.kind === "review" ? `Review ${tab === "cancellations" ? "cancellation" : "transfer"}` : action.kind === "decision" ? `${action.decision === "APPROVED" ? "Approve" : "Reject"} request` : `Finalize ${tab === "cancellations" ? "cancellation" : "unit transfer"}`;
  function submit(event: FormEvent) { event.preventDefault(); if (action.kind === "complete") onSubmit(); else if (isCancellationReview) onSubmit({ deduction_type: deductionType, deduction_value: deductionValue, notes }); else if (action.kind === "review") onSubmit({ notes }); else onSubmit({ status: action.decision, notes }); }
  return <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={submit}><div className="modal-heading"><div><p className="overline">Controlled workflow step</p><h2>{title}</h2></div><button type="button" className="icon-button" onClick={onClose}>×</button></div><div className="post-sales-modal-body"><div className="workflow-record-summary"><strong>{action.record.booking_number}</strong><span>{action.record.customer_name}</span><small>{"unit_number" in action.record ? `Unit ${action.record.unit_number}` : `${action.record.from_unit_number} → ${action.record.to_unit_number}`}</small></div>{isCancellationReview && <div className="post-sales-form-grid"><label className="field"><span>Deduction method</span><select value={deductionType} onChange={(event) => setDeductionType(event.target.value as "FIXED" | "PERCENTAGE")}><option value="FIXED">Fixed amount</option><option value="PERCENTAGE">Percentage of paid amount</option></select></label><label className="field"><span>Deduction value</span><input required min="0" max={deductionType === "PERCENTAGE" ? "100" : undefined} step="0.01" type="number" value={deductionValue} onChange={(event) => setDeductionValue(event.target.value)}/></label></div>}{action.kind !== "complete" ? <label className="field"><span>{action.kind === "review" ? "Review notes" : "Decision notes"}</span><textarea required minLength={2} maxLength={2000} rows={4} value={notes} onChange={(event) => setNotes(event.target.value)}/></label> : <p className="governance-note danger-note">Finalization atomically changes inventory and financial records, then generates a private document. This step cannot be treated as a visual-only status change.</p>}</div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Back</button><button disabled={busy} className={`button ${action.decision === "REJECTED" ? "button-danger" : "button-primary"}`}>{action.kind === "complete" ? "Confirm finalization" : title}</button></div></form></div>;
}
