"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiRequest, ApiError, PageResponse, permissionGranted, PostBookingStage, PropertyLifecycleOption, PropertyLifecycleStats, PropertyLifecycleSummary } from "@/lib/api";

const stages: PostBookingStage[] = ["AGREEMENT_PENDING", "CONSTRUCTION", "POSSESSION_READINESS", "FINAL_DEMAND", "FINAL_PAYMENT", "NO_DUES", "SNAGGING", "POSSESSION", "HANDOVER", "COMPLETED"];

export default function PropertyLifecyclePage() {
  const router = useRouter();
  const { session } = useAuth();
  const canCreate = permissionGranted(session?.user.permissions ?? [], "possession.create");
  const [rows, setRows] = useState<PageResponse<PropertyLifecycleSummary> | null>(null);
  const [stats, setStats] = useState<PropertyLifecycleStats | null>(null);
  const [options, setOptions] = useState<PropertyLifecycleOption[]>([]);
  const [queryInput, setQueryInput] = useState(""); const [query, setQuery] = useState("");
  const [stage, setStage] = useState(""); const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false); const [bookingId, setBookingId] = useState("");
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) params.set("q", query); if (stage) params.set("stage", stage);
    try {
      const [list, totals, eligible] = await Promise.all([
        apiRequest<PageResponse<PropertyLifecycleSummary>>(`/property-lifecycle?${params}`),
        apiRequest<PropertyLifecycleStats>("/property-lifecycle/stats"),
        canCreate ? apiRequest<PropertyLifecycleOption[]>("/property-lifecycle/options") : Promise.resolve([]),
      ]);
      setRows(list); setStats(totals); setOptions(eligible); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Property lifecycle queue could not be loaded"); }
  }, [canCreate, page, query, stage]);
  useEffect(() => { const timer = setTimeout(() => void load(), 0); return () => clearTimeout(timer); }, [load]);
  async function create(event: FormEvent) { event.preventDefault(); setBusy(true); try { const created = await apiRequest<{case: PropertyLifecycleSummary}>(`/property-lifecycle/bookings/${bookingId}`, { method: "POST", body: JSON.stringify({}) }); router.push(`/property-lifecycle/${created.case.id}`); } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Lifecycle could not be started"); } finally { setBusy(false); } }
  return <AppShell><main className="dashboard-content lifecycle-content"><div className="management-heading"><div><p className="overline">Post-booking operations</p><h1>Property lifecycle</h1><p>Agreement, construction, final settlement, possession readiness, snagging, and governed handover.</p></div>{canCreate && <button className="button button-primary" onClick={() => setOpen(true)}>Start lifecycle</button>}</div>{error && <div className="alert alert-error">{error}</div>}
    {stats && <section className="lifecycle-metrics"><article><span>Active records</span><strong>{stats.total}</strong></article><article><span>Readiness blocked</span><strong>{stats.readiness_blocked}</strong></article><article><span>Possession ready</span><strong>{stats.ready_for_possession}</strong></article><article><span>Scheduled</span><strong>{stats.possession_scheduled}</strong></article><article><span>Handed over</span><strong>{stats.handed_over}</strong></article></section>}
    <section className="inventory-filter-panel lifecycle-filters"><form className="inventory-search" onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search booking, customer, or unit..."/><button className="button button-primary">Search</button></form><select value={stage} onChange={(event) => { setStage(event.target.value); setPage(1); }}><option value="">All lifecycle stages</option>{stages.map((item) => <option key={item}>{item}</option>)}</select></section>
    <section className="data-card lifecycle-table-card"><div className="lifecycle-table"><div className="lifecycle-row head"><span>Booking / customer</span><span>Property</span><span>Stage</span><span>Readiness</span><span>Outstanding</span><span/></div>{rows?.items.length ? rows.items.map((item) => <Link className="lifecycle-row" key={item.id} href={`/property-lifecycle/${item.id}`}><span><strong>{item.booking_number}</strong><small>{item.customer_name}</small></span><span><strong>{item.project_name}</strong><small>Unit {item.unit_number}</small></span><span><em className={`post-sales-status status-${item.stage.toLowerCase()}`}>{item.stage.replaceAll("_", " ")}</em></span><span><strong>{item.readiness.conditions.filter((condition) => condition.complete).length}/{item.readiness.conditions.length} gates</strong><small>{item.readiness.ready ? "Ready for possession" : "Action required"}</small></span><span><strong>{new Intl.NumberFormat("en-IN", { style: "currency", currency: item.readiness.currency }).format(Number(item.readiness.outstanding_amount))}</strong><small>{item.readiness.financially_ready ? "Financially clear" : "Pending settlement"}</small></span><span>View →</span></Link>) : <div className="customer-empty"><span>PL</span><strong>No post-booking records</strong><p>A lifecycle appears only after a confirmed real booking is selected.</p></div>}</div><div className="pagination"><button disabled={!rows || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {rows?.page ?? 1} of {Math.max(rows?.pages ?? 0, 1)}</span><button disabled={!rows || page >= rows.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>
    {open && <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={create}><div className="modal-heading"><div><p className="overline">Confirmed booking</p><h2>Start property lifecycle</h2></div><button type="button" className="icon-button" onClick={() => setOpen(false)}>×</button></div><div className="post-sales-modal-body"><label className="field"><span>Eligible booking</span><select required value={bookingId} onChange={(event) => setBookingId(event.target.value)}><option value="">Select confirmed booking</option>{options.map((item) => <option value={item.id} key={item.id}>{item.booking_number} · {item.customer_name} · {item.project_name} / {item.unit_number}</option>)}</select></label><p className="governance-note">No lifecycle or possession record is generated until a real confirmed booking is selected.</p></div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setOpen(false)}>Cancel</button><button disabled={busy || !bookingId} className="button button-primary">Start lifecycle</button></div></form></div>}
  </main></AppShell>;
}
