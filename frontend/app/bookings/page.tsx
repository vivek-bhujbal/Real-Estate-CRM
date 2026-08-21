"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiRequest, ApiError, Booking, BookingStats, PageResponse, permissionGranted } from "@/lib/api";

const statuses = ["DOCUMENTATION_PENDING", "PAYMENT_PENDING", "VERIFICATION", "APPROVAL", "CONFIRMED", "REJECTED", "CANCELLED"];
const money = (amount: string | null, currency = "INR") => amount == null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(amount));
const date = (value: string) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value));

export default function BookingsPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [result, setResult] = useState<PageResponse<Booking> | null>(null);
  const [stats, setStats] = useState<BookingStats | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    Promise.all([apiRequest<PageResponse<Booking>>(`/bookings?${params}`), apiRequest<BookingStats>("/bookings/stats")])
      .then(([items, summary]) => { if (live) { setResult(items); setStats(summary); setError(null); } })
      .catch((reason: unknown) => { if (live) setError(reason instanceof ApiError ? reason.message : "Bookings could not be loaded"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [page, query, status]);

  function search(event: FormEvent) { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }

  return <AppShell><main className="dashboard-content booking-content">
    <div className="management-heading"><div><p className="overline">Controlled sales lifecycle</p><h1>Bookings</h1><p>Track KYC, payment verification, approvals, and confirmed inventory in one workflow.</p></div>{permissionGranted(permissions, "bookings.create") && <Link href="/bookings/create" className="button button-primary">Create booking</Link>}</div>
    {error && <div className="alert alert-error">{error}</div>}
    {stats && <section className="inventory-metrics booking-metrics"><article><span>All bookings</span><strong>{stats.total}</strong></article><article><span>Payment pending</span><strong>{stats.payment_pending}</strong></article><article><span>Verification</span><strong>{stats.verification}</strong></article><article><span>Awaiting approval</span><strong>{stats.approval}</strong></article><article><span>Confirmed</span><strong>{stats.confirmed}</strong></article></section>}
    <section className="inventory-filter-panel"><form className="inventory-search" onSubmit={search}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search booking, customer, project, or unit..."/><button className="button button-primary">Search</button></form><div className="inventory-filters"><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option>{statuses.map((item) => <option value={item} key={item}>{item.replaceAll("_", " ")}</option>)}</select><button type="button" onClick={() => { setStatus(""); setQuery(""); setQueryInput(""); setPage(1); }}>Clear</button></div></section>
    <section className="data-card booking-table-card"><div className="booking-table"><div className="booking-row head"><span>Booking</span><span>Customer</span><span>Property</span><span>Commercials</span><span>Progress</span><span>Created</span></div>{loading ? <div className="center-inline"><span className="spinner"/>Loading bookings...</div> : result?.items.length ? result.items.map((item) => <Link href={`/bookings/${item.id}`} className="booking-row" key={item.id}><span><strong>{item.booking_number}</strong><small>{item.quotation_number ? `Quote ${item.quotation_number}` : "No quotation"}</small></span><span><strong>{item.customer_name}</strong><small>{item.applicants.length} applicant{item.applicants.length === 1 ? "" : "s"}</small></span><span><strong>{item.project_name}</strong><small>Unit {item.unit_number}</small></span><span><strong>{money(item.agreed_price, item.currency)}</strong><small>Paid {money(item.paid_amount, item.currency)}</small></span><span><em className={`quote-status status-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</em><small>{item.salesperson_name ?? "Unassigned"}</small></span><span>{date(item.created_at)}<small>{item.broker_name ?? "Direct sale"}</small></span></Link>) : <div className="customer-empty"><span>BK</span><strong>No bookings found</strong><p>A booking appears only after an accepted quotation, approved unit hold, and verified KYC are available.</p></div>}</div><div className="pagination"><button disabled={!result || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>
  </main></AppShell>;
}
