"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiRequest, ApiError, Booking, BookingOptions, FinancingStatus, permissionGranted } from "@/lib/api";

type Tab = "overview" | "applicants" | "payments" | "documents" | "approvals";
const flow = ["PAYMENT_PENDING", "VERIFICATION", "APPROVAL", "CONFIRMED"];
const money = (amount: string | null, currency: string) => amount == null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(amount));
const dateTime = (value: string | null) => value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
const message = (reason: unknown) => reason instanceof ApiError ? reason.message : "The booking operation could not be completed";

export default function BookingDetailPage() {
  const id = String(useParams().id);
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const canUpdate = permissionGranted(permissions, "bookings.update");
  const canApprove = permissionGranted(permissions, "bookings.approve");
  const canCreatePayment = permissionGranted(permissions, "payments.create") || canUpdate;
  const canApprovePayment = permissionGranted(permissions, "payments.approve") || canApprove;
  const [booking, setBooking] = useState<Booking | null>(null);
  const [options, setOptions] = useState<BookingOptions | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [payment, setPayment] = useState({ amount: "", method: "BANK_TRANSFER", reference_number: "", installment_id: "" });
  const [financing, setFinancing] = useState({ status: "NOT_REQUIRED" as FinancingStatus, lender_name: "", loan_amount: "", application_number: "", sanction_reference: "", notes: "" });
  const [approvers, setApprovers] = useState<string[]>([]);
  const [approvalComment, setApprovalComment] = useState("");

  useEffect(() => {
    let live = true;
    apiRequest<Booking>(`/bookings/${id}`).then((value) => {
      if (!live) return;
      setBooking(value); setPayment((draft) => ({ ...draft, amount: draft.amount || value.booking_amount }));
      setFinancing({ status: value.financing?.status ?? "NOT_REQUIRED", lender_name: value.financing?.lender_name ?? "", loan_amount: value.financing?.loan_amount ?? "", application_number: value.financing?.application_number ?? "", sanction_reference: value.financing?.sanction_reference ?? "", notes: value.financing?.notes ?? "" });
      setError(null);
    }).catch((reason: unknown) => { if (live) setError(message(reason)); });
    return () => { live = false; };
  }, [id]);
  useEffect(() => { if (!canUpdate) return; apiRequest<BookingOptions>("/bookings/options").then(setOptions).catch(() => undefined); }, [canUpdate]);

  async function mutate(path: string, body: unknown, success: string) {
    setBusy(true); setError(null); setNotice(null);
    try { const value = await apiRequest<Booking>(path, { method: "POST", body: JSON.stringify(body) }); setBooking(value); setNotice(success); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function submitPayment(event: FormEvent) {
    event.preventDefault();
    await mutate(`/bookings/${id}/payments`, { ...payment, installment_id: payment.installment_id || null, reference_number: payment.reference_number || null, idempotency_key: crypto.randomUUID() }, "Payment submitted for independent verification");
    setPayment((draft) => ({ ...draft, reference_number: "" }));
  }
  async function saveFinancing(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const value = await apiRequest<Booking>(`/bookings/${id}/financing`, { method: "PUT", body: JSON.stringify({ ...financing, lender_name: financing.status === "NOT_REQUIRED" ? null : financing.lender_name, loan_amount: financing.status === "NOT_REQUIRED" ? null : financing.loan_amount, application_number: financing.application_number || null, sanction_reference: financing.sanction_reference || null, notes: financing.notes || null }) });
      setBooking(value); setNotice("Financing details updated");
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }
  async function requestApproval(event: FormEvent) {
    event.preventDefault(); await mutate(`/bookings/${id}/approval-request`, { approver_user_ids: approvers, comments: approvalComment || null }, "Booking submitted to the approval chain");
  }

  if (!booking) return <AppShell><main className="dashboard-content"><div className="center-inline"><span className="spinner"/>{error ?? "Loading booking..."}</div></main></AppShell>;
  const currentIndex = flow.indexOf(booking.status);
  const pendingApprovals = booking.approvals.filter((item) => item.status === "PENDING");

  return <AppShell><main className="dashboard-content booking-content"><div className="management-heading"><div><p className="overline">Booking {booking.booking_number}</p><h1>{booking.customer_name}</h1><p>{booking.project_name} · Unit {booking.unit_number} · {booking.quotation_number ? `Quotation ${booking.quotation_number}` : "Legacy booking"}</p></div><div className="heading-actions"><span className={`quote-status status-${booking.status.toLowerCase()}`}>{booking.status.replaceAll("_", " ")}</span><Link href="/bookings" className="button button-secondary">All bookings</Link></div></div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    <section className="booking-flow" aria-label="Booking progress">{flow.map((step, index) => <div className={`${index < currentIndex || booking.status === "CONFIRMED" ? "complete" : ""} ${index === currentIndex ? "current" : ""}`} key={step}><span>{index < currentIndex || booking.status === "CONFIRMED" ? "✓" : index + 1}</span><strong>{step.replaceAll("_", " ")}</strong></div>)}</section>
    <nav className="customer-tabs booking-tabs">{(["overview", "applicants", "payments", "documents", "approvals"] as Tab[]).map((item) => <button className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item}>{item[0].toUpperCase() + item.slice(1)}{item === "payments" ? ` (${booking.payments.length})` : item === "documents" ? ` (${booking.documents.length})` : item === "approvals" ? ` (${booking.approvals.length})` : ""}</button>)}</nav>

    {tab === "overview" && <div className="booking-detail-grid"><div className="booking-main-stack"><section className="panel"><div className="panel-heading"><div><h2>Commercial summary</h2><p>All values are locked from the accepted quotation.</p></div></div><dl className="booking-summary"><div><dt>Agreed property value</dt><dd>{money(booking.agreed_price, booking.currency)}</dd></div><div><dt>Approved discount</dt><dd>{money(booking.discount_amount, booking.currency)}</dd></div><div><dt>Booking amount</dt><dd>{money(booking.booking_amount, booking.currency)}</dd></div><div><dt>Verified paid amount</dt><dd>{money(booking.paid_amount, booking.currency)}</dd></div></dl></section><section className="panel"><div className="panel-heading"><div><h2>Payment plan</h2><p>{booking.payment_plan?.name ?? "No schedule"}</p></div></div>{booking.payment_plan ? <div className="installment-list">{booking.payment_plan.installments.map((item) => <div key={item.id}><span><strong>{item.name}</strong><small>Due {new Date(item.due_date).toLocaleDateString("en-IN")}</small></span><span><strong>{money(item.amount, booking.currency)}</strong><small>{item.status.replaceAll("_", " ")} · paid {money(item.paid_amount, booking.currency)}</small></span></div>)}</div> : <p className="muted-copy">No payment plan.</p>}</section></div><aside className="booking-side-stack"><section className="panel"><h2>Ownership</h2><dl className="key-value-list"><div><dt>Salesperson</dt><dd>{booking.salesperson_name ?? "Unassigned"}</dd></div><div><dt>Broker</dt><dd>{booking.broker_name ?? "Direct sale"}</dd></div><div><dt>Created by</dt><dd>{booking.booked_by_name}</dd></div><div><dt>Created</dt><dd>{dateTime(booking.created_at)}</dd></div></dl></section><section className="panel"><h2>Financing</h2><p className={`quote-status status-${(booking.financing?.status ?? "not_required").toLowerCase()}`}>{(booking.financing?.status ?? "NOT_REQUIRED").replaceAll("_", " ")}</p>{booking.financing?.lender_name && <dl className="key-value-list"><div><dt>Lender</dt><dd>{booking.financing.lender_name}</dd></div><div><dt>Loan</dt><dd>{money(booking.financing.loan_amount, booking.currency)}</dd></div><div><dt>Sanction</dt><dd>{booking.financing.sanction_reference ?? "Pending"}</dd></div></dl>}</section>{canUpdate && !["CONFIRMED", "CANCELLED", "REJECTED"].includes(booking.status) && <button className="button button-danger button-wide" disabled={busy} onClick={() => { const reason = window.prompt("Cancellation reason"); if (reason) void mutate(`/bookings/${id}/cancel`, { reason }, "Booking cancelled and unit released"); }}>Cancel booking</button>}</aside></div>}

    {tab === "applicants" && <section className="panel"><div className="panel-heading"><div><h2>Applicants</h2><p>The primary customer and every joint applicant are retained as booking snapshots.</p></div></div><div className="applicant-grid">{booking.applicants.map((item) => <article key={item.id}><span>{item.is_primary ? "Primary" : `Applicant ${item.sequence}`}</span><strong>{item.full_name}</strong><p>{item.relationship_to_primary ?? "Primary buyer"}</p><small>{[item.email, item.phone].filter(Boolean).join(" · ") || "No contact supplied"}</small>{item.tax_identifier && <small>Tax ID: {item.tax_identifier}</small>}</article>)}</div></section>}

    {tab === "payments" && <div className="booking-detail-grid"><section className="panel"><div className="panel-heading"><div><h2>Payment history</h2><p>Submitted payments do not count until an authorized user verifies them.</p></div></div><div className="payment-list">{booking.payments.length ? booking.payments.map((item) => <article key={item.id}><span><strong>{money(item.amount, item.currency)}</strong><small>{item.method.replaceAll("_", " ")} · {item.reference_number ?? "No reference"}</small></span><span><em className={`quote-status status-${item.status.toLowerCase()}`}>{item.status}</em><small>{item.verifier_name ? `Verified by ${item.verifier_name}` : dateTime(item.paid_at ?? item.created_at)}</small></span>{item.status === "SUBMITTED" && canApprovePayment && <span className="row-actions"><button disabled={busy} onClick={() => void mutate(`/bookings/${id}/payments/${item.id}/decision`, { status: "COMPLETED", notes: "Payment proof verified" }, "Payment verified")}>Verify</button><button disabled={busy} onClick={() => void mutate(`/bookings/${id}/payments/${item.id}/decision`, { status: "FAILED", notes: "Payment verification failed" }, "Payment rejected")}>Reject</button></span>}</article>) : <p className="muted-copy">No payments submitted.</p>}</div></section>{canCreatePayment && !["CONFIRMED", "CANCELLED", "REJECTED"].includes(booking.status) && <form className="panel booking-action-form" onSubmit={submitPayment}><h2>Submit payment</h2><label className="field"><span>Installment</span><select value={payment.installment_id} onChange={(event) => setPayment({ ...payment, installment_id: event.target.value })}><option value="">Unallocated payment</option>{booking.payment_plan?.installments.map((item) => <option value={item.id} key={item.id}>{item.name} · {money(item.amount, booking.currency)}</option>)}</select></label><label className="field"><span>Amount</span><input required type="number" min="0.01" step="0.01" value={payment.amount} onChange={(event) => setPayment({ ...payment, amount: event.target.value })}/></label><label className="field"><span>Method</span><select value={payment.method} onChange={(event) => setPayment({ ...payment, method: event.target.value })}><option value="BANK_TRANSFER">Bank transfer</option><option value="CHEQUE">Cheque</option><option value="CARD">Card</option><option value="UPI">UPI</option><option value="CASH">Cash</option></select></label><label className="field"><span>Reference</span><input value={payment.reference_number} onChange={(event) => setPayment({ ...payment, reference_number: event.target.value })}/></label><button className="button button-primary" disabled={busy}>Submit for verification</button></form>}</div>}

    {tab === "documents" && <section className="panel"><div className="panel-heading"><div><h2>KYC and booking documents</h2><p>Only current secure document metadata is shown here; downloads remain permission checked.</p></div><Link href="/documents" className="button button-secondary">Open document vault</Link></div><div className="document-summary-list">{booking.documents.length ? booking.documents.map((item) => <div key={item.id}><span><strong>{item.document_type.replaceAll("_", " ")}</strong><small>{item.file_name ?? "Upload pending"} · Version {item.version}</small></span><em className={`quote-status status-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</em></div>) : <p className="muted-copy">No documents linked to this booking. Customer-level verified KYC was still required at creation.</p>}</div></section>}

    {tab === "approvals" && <div className="booking-detail-grid"><section className="panel"><div className="panel-heading"><div><h2>Approval chain</h2><p>Every decision is assigned, timestamped, and audited.</p></div></div><div className="approval-list">{booking.approvals.length ? booking.approvals.map((item) => <article key={item.id}><span>{item.step_number}</span><div><strong>{item.approver_name ?? "Assigned approver"}</strong><small>Requested by {item.requested_by_name ?? "User"} · {dateTime(item.created_at)}</small><p>{item.comments ?? "No comments"}</p></div><em className={`quote-status status-${item.status.toLowerCase()}`}>{item.status}</em>{item.status === "PENDING" && item.approver_user_id === session?.user.id && canApprove && <div className="row-actions"><button disabled={busy} onClick={() => void mutate(`/bookings/${id}/approvals/${item.id}/decision`, { status: "APPROVED", comments: "Booking checks approved" }, "Approval recorded")}>Approve</button><button disabled={busy} onClick={() => void mutate(`/bookings/${id}/approvals/${item.id}/decision`, { status: "REJECTED", comments: "Booking approval rejected" }, "Booking rejected")}>Reject</button></div>}</article>) : <p className="muted-copy">Approval has not been requested.</p>}</div></section><aside className="booking-side-stack">{canUpdate && booking.status === "VERIFICATION" && pendingApprovals.length === 0 && <form className="panel booking-action-form" onSubmit={requestApproval}><h2>Request approval</h2><p>Choose the ordered approval chain. You cannot approve your own request.</p><div className="approver-options">{options?.approvers.filter((item) => item.id !== session?.user.id).map((item) => <label key={item.id}><input type="checkbox" checked={approvers.includes(item.id)} onChange={(event) => setApprovers((values) => event.target.checked ? [...values, item.id] : values.filter((idValue) => idValue !== item.id))}/><span>{item.label}</span></label>)}</div><label className="field"><span>Request note</span><textarea rows={3} value={approvalComment} onChange={(event) => setApprovalComment(event.target.value)}/></label><button className="button button-primary" disabled={busy || approvers.length === 0}>Start approval chain</button></form>}{canUpdate && !["APPROVAL", "CONFIRMED", "CANCELLED", "REJECTED"].includes(booking.status) && <form className="panel booking-action-form" onSubmit={saveFinancing}><h2>Financing verification</h2><label className="field"><span>Status</span><select value={financing.status} onChange={(event) => setFinancing({ ...financing, status: event.target.value as FinancingStatus })}>{["NOT_REQUIRED", "APPLIED", "UNDER_REVIEW", "SANCTIONED", "REJECTED", "DISBURSED"].map((item) => <option value={item} key={item}>{item.replaceAll("_", " ")}</option>)}</select></label>{financing.status !== "NOT_REQUIRED" && <><label className="field"><span>Lender</span><input required value={financing.lender_name} onChange={(event) => setFinancing({ ...financing, lender_name: event.target.value })}/></label><label className="field"><span>Loan amount</span><input required type="number" min="0.01" step="0.01" value={financing.loan_amount} onChange={(event) => setFinancing({ ...financing, loan_amount: event.target.value })}/></label><label className="field"><span>Sanction reference</span><input value={financing.sanction_reference} onChange={(event) => setFinancing({ ...financing, sanction_reference: event.target.value })}/></label></>}<button className="button button-secondary" disabled={busy}>Save financing</button></form>}</aside></div>}
  </main></AppShell>;
}
