"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { QuotationNavigation } from "@/components/quotation-navigation";
import { apiRequest, ApiError, CostSheet, PageResponse, permissionGranted, Quotation, QuotationStats } from "@/lib/api";

const statuses = ["DRAFT", "SENT", "ACCEPTED", "REJECTED", "EXPIRED", "SUPERSEDED"];
const errorText = (reason: unknown) => reason instanceof ApiError ? reason.message : "Quotation data is unavailable";
const money = (amount: string, currency: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(amount));

export default function QuotationsPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [result, setResult] = useState<PageResponse<Quotation> | null>(null);
  const [costSheets, setCostSheets] = useState<CostSheet[]>([]);
  const [stats, setStats] = useState<QuotationStats | null>(null);
  const [queryInput, setQueryInput] = useState(""); const [query, setQuery] = useState("");
  const [status, setStatus] = useState(""); const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return; let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) params.set("q", query); if (status) params.set("status", status);
    void Promise.all([
      apiRequest<PageResponse<Quotation>>(`/quotations?${params}`),
      apiRequest<QuotationStats>("/quotations/stats"),
      apiRequest<PageResponse<CostSheet>>("/cost-sheets?status=PENDING_APPROVAL&page_size=5")
    ]).then(([quotes, quoteStats, sheets]) => { if (active) { setResult(quotes); setStats(quoteStats); setCostSheets(sheets.items); } }).catch((reason: unknown) => { if (active) setError(errorText(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, query, session, status]);

  function search(event: FormEvent) { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }
  return <AppShell><main className="dashboard-content quote-content">
    <div className="management-heading"><div><p className="overline">Commercial desk</p><h1>Quotations & cost sheets</h1><p>Controlled pricing, discount approvals and an immutable quotation trail.</p></div>{permissionGranted(permissions, "quotations.create") && <Link className="button button-primary" href="/quotations/create">Build cost sheet</Link>}</div>
    <QuotationNavigation />
    {stats && <section className="quote-metrics"><article><span>Total quotations</span><strong>{stats.total}</strong></article><article><span>Draft</span><strong>{stats.drafts}</strong></article><article><span>Sent</span><strong>{stats.sent}</strong></article><article><span>Accepted</span><strong>{stats.accepted}</strong></article><article><span>Approval queue</span><strong>{stats.pending_discount_approvals}</strong></article></section>}
    {error && <div className="alert alert-error page-alert">{error}</div>}
    {costSheets.length > 0 && <section className="approval-strip"><div><strong>Discount approvals awaiting review</strong><span>{costSheets.length} shown from the current queue</span></div><div>{costSheets.map((sheet) => <Link key={sheet.id} href={`/cost-sheets/${sheet.id}`}>{sheet.customer_name} · {sheet.unit_number}<b>{money(sheet.discount_amount, sheet.currency)}</b></Link>)}</div></section>}
    <section className="data-card"><div className="quote-toolbar"><form onSubmit={search}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Quotation no., customer or unit"/><button className="button button-primary">Search</button></form><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select></div>
      <div className="quote-table"><div className="quote-row head"><span>Quotation</span><span>Customer</span><span>Property</span><span>Value</span><span>Validity</span><span>Status</span></div>
        {loading ? <div className="center-inline"><span className="spinner"/>Loading quotations...</div> : result?.items.length ? result.items.map((quote) => <Link href={`/quotations/${quote.id}`} className="quote-row" key={quote.id}><span><strong>{quote.quotation_number}</strong><small>Version {quote.version}</small></span><span><strong>{quote.customer_name ?? quote.lead_name ?? "—"}</strong><small>Created by {quote.created_by_name}</small></span><span><strong>{quote.project_name}</strong><small>Unit {quote.unit_number ?? "—"}</small></span><span><strong>{money(quote.total, quote.currency)}</strong><small>Booking {money(quote.booking_amount ?? "0", quote.currency)}</small></span><span>{new Date(quote.valid_until).toLocaleDateString("en-IN")}</span><span><em className={`quote-status status-${quote.status.toLowerCase()}`}>{quote.status}</em></span></Link>) : <div className="empty-state"><strong>No quotations found</strong><p>Create a cost sheet from an active price list; no placeholder records are generated.</p></div>}
      </div>
      {result && result.pages > 1 && <div className="pagination"><button disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {page} of {result.pages}</span><button disabled={page === result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>}
    </section>
  </main></AppShell>;
}
