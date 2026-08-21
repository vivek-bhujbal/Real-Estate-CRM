"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { apiRequest, ApiError, CollectionAccount, FinanceSummary, PageResponse } from "@/lib/api";

const money = (value: string, currency = "INR") => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));

export default function CollectionsPage() {
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [result, setResult] = useState<PageResponse<CollectionAccount> | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const params = new URLSearchParams({ page: String(page), page_size: "20", overdue_only: String(overdue) });
    if (query) params.set("q", query);
    Promise.all([apiRequest<FinanceSummary>("/collections/summary"), apiRequest<PageResponse<CollectionAccount>>(`/collections/accounts?${params}`)]).then(([totals, accounts]) => { if (live) { setSummary(totals); setResult(accounts); setError(null); } }).catch((reason: unknown) => { if (live) setError(reason instanceof ApiError ? reason.message : "Collections could not be loaded"); });
    return () => { live = false; };
  }, [overdue, page, query]);
  function search(event: FormEvent) { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }
  return <AppShell><main className="dashboard-content collections-content"><div className="management-heading"><div><p className="overline">Finance control center</p><h1>Collections</h1><p>Server-calculated receivables, payment allocation, reconciliation, and refund governance.</p></div></div>{error && <div className="alert alert-error">{error}</div>}
    {summary && <section className="collection-metrics"><article><span>Total receivable</span><strong>{money(summary.total_receivable)}</strong></article><article><span>Received</span><strong>{money(summary.received)}</strong></article><article><span>Outstanding</span><strong>{money(summary.outstanding)}</strong></article><article className="overdue"><span>Overdue</span><strong>{money(summary.overdue)}</strong></article><article><span>Unapplied credit</span><strong>{money(summary.unapplied_payments)}</strong></article><article><span>Review queue</span><strong>{summary.pending_reconciliation + summary.pending_refunds}</strong></article></section>}
    <section className="inventory-filter-panel"><form className="inventory-search" onSubmit={search}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search booking or customer..."/><button className="button button-primary">Search</button></form><label className="collection-toggle"><input type="checkbox" checked={overdue} onChange={(event) => { setOverdue(event.target.checked); setPage(1); }}/><span>Overdue accounts only</span></label></section>
    <section className="data-card collection-table-card"><div className="collection-table"><div className="collection-row head"><span>Account</span><span>Customer</span><span>Property</span><span>Receivable</span><span>Outstanding</span><span>Next milestone</span></div>{result?.items.length ? result.items.map((item) => <Link href={`/collections/${item.booking_id}`} className="collection-row" key={item.booking_id}><span><strong>{item.booking_number}</strong><small>{item.booking_status.replaceAll("_", " ")}</small></span><span><strong>{item.customer_name}</strong><small>{item.customer_id.slice(0, 8)}</small></span><span><strong>{item.project_name}</strong><small>Unit {item.unit_number}</small></span><span><strong>{money(item.total_value, item.currency)}</strong><small>Received {money(item.received, item.currency)}</small></span><span><strong className={Number(item.overdue) > 0 ? "danger-copy" : ""}>{money(item.outstanding, item.currency)}</strong><small>{money(item.overdue, item.currency)} overdue</small></span><span>{item.next_due_date ? new Date(item.next_due_date).toLocaleDateString("en-IN", { dateStyle: "medium" }) : "Cleared"}</span></Link>) : <div className="customer-empty"><span>₹</span><strong>No collection accounts</strong><p>Accounts appear only from real bookings; no financial data is generated automatically.</p></div>}</div><div className="pagination"><button disabled={!result || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>
  </main></AppShell>;
}
