"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiRequest, ApiError, Booking, BookingOptions, permissionGranted } from "@/lib/api";

type JointApplicantDraft = { full_name: string; email: string; phone: string; relationship_to_primary: string; date_of_birth: string; tax_identifier: string };
const emptyApplicant: JointApplicantDraft = { full_name: "", email: "", phone: "", relationship_to_primary: "", date_of_birth: "", tax_identifier: "" };
const today = () => new Date().toISOString().slice(0, 10);
const money = (amount: string, currency: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(amount));

export default function CreateBookingPage() {
  const router = useRouter();
  const { session } = useAuth();
  const canCreate = permissionGranted(session?.user.permissions ?? [], "bookings.create");
  const [options, setOptions] = useState<BookingOptions>({ quotations: [], salespeople: [], brokers: [], approvers: [] });
  const [quotationId, setQuotationId] = useState("");
  const [bookingNumber, setBookingNumber] = useState("");
  const [salespersonId, setSalespersonId] = useState(session?.user.id ?? "");
  const [brokerId, setBrokerId] = useState("");
  const [planName, setPlanName] = useState("Standard payment plan");
  const [effectiveFrom, setEffectiveFrom] = useState(today());
  const [dueDate, setDueDate] = useState(today());
  const [financingUsed, setFinancingUsed] = useState(false);
  const [lender, setLender] = useState("");
  const [loanAmount, setLoanAmount] = useState("");
  const [applicationNumber, setApplicationNumber] = useState("");
  const [applicants, setApplicants] = useState<JointApplicantDraft[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = useMemo(() => options.quotations.find((item) => item.id === quotationId) ?? null, [options, quotationId]);

  useEffect(() => { if (!canCreate) return; apiRequest<BookingOptions>("/bookings/options").then((value) => { setOptions(value); if (value.salespeople.some((item) => item.id === session?.user.id)) setSalespersonId(session?.user.id ?? ""); }).catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "Booking options could not be loaded")); }, [canCreate, session?.user.id]);

  function selectQuote(id: string) {
    setQuotationId(id);
    const quote = options.quotations.find((item) => item.id === id);
    if (quote) setLoanAmount(quote.agreed_price);
  }
  function addApplicant() { setApplicants((items) => [...items, { ...emptyApplicant }]); }
  function setApplicant(index: number, key: keyof JointApplicantDraft, value: string) { setApplicants((items) => items.map((item, position) => position === index ? { ...item, [key]: value } : item)); }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSaving(true); setError(null);
    try {
      const booking = await apiRequest<Booking>("/bookings", { method: "POST", body: JSON.stringify({
        quotation_id: selected.id, unit_hold_id: selected.hold_id, booking_number: bookingNumber.trim().toUpperCase(),
        salesperson_user_id: salespersonId || null, channel_partner_id: brokerId || null,
        joint_applicants: applicants.map((item) => ({ ...item, email: item.email || null, phone: item.phone || null, date_of_birth: item.date_of_birth || null, tax_identifier: item.tax_identifier || null })),
        financing: financingUsed ? { status: "APPLIED", lender_name: lender, loan_amount: loanAmount, application_number: applicationNumber || null } : { status: "NOT_REQUIRED" },
        payment_plan: { name: planName, effective_from: effectiveFrom, installments: [{ name: "Agreed property value", due_date: dueDate, amount: selected.agreed_price }] }
      }) });
      router.push(`/bookings/${booking.id}`);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Booking could not be created"); }
    finally { setSaving(false); }
  }

  return <AppShell><main className="dashboard-content booking-content"><div className="management-heading"><div><p className="overline">New booking</p><h1>Start the controlled booking flow</h1><p>Commercial values come from the accepted quotation; the server validates the hold, KYC, and inventory lock.</p></div><Link href="/bookings" className="button button-secondary">Back to bookings</Link></div>{error && <div className="alert alert-error">{error}</div>}
    {!options.quotations.length ? <section className="panel booking-prerequisite"><span>01</span><div><h2>No eligible quotation</h2><p>An accepted quotation must have an active approved hold for the same customer and unit, current verified KYC, and no active booking.</p></div></section> : <form className="booking-create-grid" onSubmit={submit}><div className="booking-main-stack"><section className="panel"><div className="panel-heading"><div><p className="overline">Prerequisites</p><h2>Quotation and property</h2></div></div><label className="field"><span>Eligible accepted quotation</span><select required value={quotationId} onChange={(event) => selectQuote(event.target.value)}><option value="">Select quotation</option>{options.quotations.map((item) => <option value={item.id} key={item.id}>{item.quotation_number} v{item.version} · {item.customer_name} · Unit {item.unit_number}</option>)}</select></label>{selected && <div className="booking-selection"><div><span>Customer</span><strong>{selected.customer_name}</strong></div><div><span>Unit</span><strong>{selected.unit_number}</strong></div><div><span>Agreed value</span><strong>{money(selected.agreed_price, selected.currency)}</strong></div><div><span>Booking amount</span><strong>{money(selected.booking_amount, selected.currency)}</strong></div></div>}</section>
      <section className="panel"><div className="panel-heading"><div><p className="overline">Applicants</p><h2>Primary and joint applicants</h2><p>The quotation customer is always the primary applicant.</p></div><button type="button" className="button button-secondary" onClick={addApplicant}>Add joint applicant</button></div>{applicants.length === 0 && <p className="muted-copy">No joint applicants added.</p>}{applicants.map((item, index) => <div className="joint-applicant" key={index}><div className="joint-applicant-title"><strong>Joint applicant {index + 1}</strong><button type="button" onClick={() => setApplicants((values) => values.filter((_, position) => position !== index))}>Remove</button></div><div className="lead-form-grid"><label className="field"><span>Full name</span><input required minLength={2} value={item.full_name} onChange={(event) => setApplicant(index, "full_name", event.target.value)}/></label><label className="field"><span>Relationship</span><input required minLength={2} value={item.relationship_to_primary} onChange={(event) => setApplicant(index, "relationship_to_primary", event.target.value)}/></label><label className="field"><span>Email</span><input type="email" value={item.email} onChange={(event) => setApplicant(index, "email", event.target.value)}/></label><label className="field"><span>Phone</span><input value={item.phone} onChange={(event) => setApplicant(index, "phone", event.target.value)}/></label><label className="field"><span>Date of birth</span><input type="date" value={item.date_of_birth} onChange={(event) => setApplicant(index, "date_of_birth", event.target.value)}/></label><label className="field"><span>Tax identifier</span><input value={item.tax_identifier} onChange={(event) => setApplicant(index, "tax_identifier", event.target.value)}/></label></div></div>)}</section>
      <section className="panel"><div className="panel-heading"><div><p className="overline">Payment schedule</p><h2>Payment plan</h2></div></div><div className="lead-form-grid"><label className="field"><span>Plan name</span><input required minLength={2} value={planName} onChange={(event) => setPlanName(event.target.value)}/></label><label className="field"><span>Effective from</span><input required type="date" value={effectiveFrom} onChange={(event) => { setEffectiveFrom(event.target.value); if (dueDate < event.target.value) setDueDate(event.target.value); }}/></label><label className="field"><span>Installment due date</span><input required type="date" min={effectiveFrom} value={dueDate} onChange={(event) => setDueDate(event.target.value)}/></label><label className="field"><span>Scheduled total</span><input readOnly value={selected ? money(selected.agreed_price, selected.currency) : "Select a quotation"}/></label></div></section></div>
      <aside className="booking-side-stack"><section className="panel"><div className="panel-heading"><div><h2>Assignment</h2></div></div><div className="form-stack"><label className="field"><span>Booking number</span><input required minLength={2} maxLength={50} pattern="[A-Za-z0-9][A-Za-z0-9_/-]*" value={bookingNumber} onChange={(event) => setBookingNumber(event.target.value.toUpperCase())} placeholder="BK-2026-001"/></label><label className="field"><span>Salesperson</span><select value={salespersonId} onChange={(event) => setSalespersonId(event.target.value)}><option value="">Not assigned</option>{options.salespeople.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><label className="field"><span>Broker / channel partner</span><select value={brokerId} onChange={(event) => setBrokerId(event.target.value)}><option value="">Direct sale</option>{options.brokers.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label></div></section><section className="panel"><label className="check-row"><input type="checkbox" checked={financingUsed} onChange={(event) => setFinancingUsed(event.target.checked)}/><span><strong>Customer is using financing</strong><small>Sanction is required before booking approval.</small></span></label>{financingUsed && <div className="form-stack financing-fields"><label className="field"><span>Lender</span><input required minLength={2} value={lender} onChange={(event) => setLender(event.target.value)}/></label><label className="field"><span>Loan amount</span><input required type="number" min="0.01" step="0.01" value={loanAmount} onChange={(event) => setLoanAmount(event.target.value)}/></label><label className="field"><span>Application number</span><input value={applicationNumber} onChange={(event) => setApplicationNumber(event.target.value)}/></label></div>}</section><button className="button button-primary button-wide" disabled={saving || !selected}>{saving ? "Creating secure booking..." : "Create booking"}</button><p className="form-footnote">Creation atomically converts the hold and moves the unit to booking initiated.</p></aside></form>}
  </main></AppShell>;
}
