"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiRequest, ApiError, Customer, CustomerStats, CustomerStatus,
  LeadAssignee, PageResponse, permissionGranted
} from "@/lib/api";

const labels: Record<CustomerStatus, string> = {
  PROSPECT: "Prospect", ACTIVE: "Active", INACTIVE: "Inactive", BLOCKED: "Blocked"
};

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Customer data is unavailable";
}

export default function CustomersPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [result, setResult] = useState<PageResponse<Customer> | null>(null);
  const [stats, setStats] = useState<CustomerStats | null>(null);
  const [assignees, setAssignees] = useState<LeadAssignee[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const canCreate = permissionGranted(permissions, "customers.create");
  const canAssign = permissionGranted(permissions, "customers.assign");

  useEffect(() => {
    if (!session) return;
    let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "15" });
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    if (owner) params.set("owner_user_id", owner);
    void apiRequest<PageResponse<Customer>>(`/customers?${params}`)
      .then((data) => { if (active) setResult(data); })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [owner, page, query, session, status]);

  useEffect(() => {
    if (!session) return;
    let active = true;
    const requests: Promise<unknown>[] = [
      apiRequest<CustomerStats>("/customers/stats").then((data) => { if (active) setStats(data); })
    ];
    if (canAssign) requests.push(apiRequest<LeadAssignee[]>("/customers/assignees").then((data) => { if (active) setAssignees(data); }));
    void Promise.all(requests).catch((reason: unknown) => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [canAssign, session]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPage(1); setQuery(searchInput.trim());
  }

  return <AppShell><main className="dashboard-content customer-content">
    <div className="management-heading">
      <div><p className="overline">Customer 360</p><h1>Customers</h1><p>One uncluttered view of every customer relationship, transaction, and service touchpoint.</p></div>
      {canCreate && <Link href="/customers/create" className="button button-primary">Create customer</Link>}
    </div>
    {stats && <section className="customer-metrics" aria-label="Customer summary">
      <article><span>Total customers</span><strong>{stats.total}</strong></article>
      <article><span>Prospects</span><strong>{stats.prospects}</strong></article>
      <article><span>Active</span><strong>{stats.active}</strong></article>
      <article><span>Inactive</span><strong>{stats.inactive}</strong></article>
    </section>}
    <div className="management-toolbar customer-toolbar">
      <form className="search-box" onSubmit={search}><span aria-hidden="true">/</span><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search name, contact, or company..." aria-label="Search customers" /></form>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filter by status"><option value="">All statuses</option>{Object.entries(labels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>
      {assignees.length > 0 && <select value={owner} onChange={(event) => { setOwner(event.target.value); setPage(1); }} aria-label="Filter by owner"><option value="">All owners</option>{assignees.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select>}
      <span className="result-count">{result?.total ?? 0} records</span>
    </div>
    {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
    <section className="data-card customer-data-card">
      <div className="data-table customer-table" role="table" aria-label="Customers">
        <div className="data-row data-head" role="row"><span>Customer</span><span>Status</span><span>Requirement</span><span>Owner</span><span>Relationship</span><span /></div>
        {loading ? <div className="center-inline"><span className="spinner" />Loading customers...</div> : result?.items.length ? result.items.map((item) => <div className="data-row" role="row" key={item.id}>
          <span className="primary-cell"><strong>{item.full_name}</strong><small>{item.phone ?? item.email}{item.company_name ? ` · ${item.company_name}` : ""}</small></span>
          <span><span className={`customer-status status-${item.status.toLowerCase()}`}>{labels[item.status]}</span></span>
          <span className="primary-cell"><strong>{item.preferred_location ?? "Not captured"}</strong><small>{item.budget_max ? `Budget up to ${new Intl.NumberFormat("en-IN").format(Number(item.budget_max))}` : "Budget not captured"}</small></span>
          <span>{item.owner_name ?? <span className="muted-copy">Unassigned</span>}</span>
          <span className="primary-cell"><strong>{item.booking_count} booking{item.booking_count === 1 ? "" : "s"}</strong><small>{item.activity_count} direct activities</small></span>
          <span className="row-actions"><Link href={`/customers/${item.id}`}>Open 360</Link></span>
        </div>) : <div className="empty-state table-empty"><span className="empty-icon">+</span><h3>No customers found</h3><p>Create a customer or adjust the current filters.</p></div>}
      </div>
      <div className="pagination"><button disabled={!result || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>
    </section>
  </main></AppShell>;
}
