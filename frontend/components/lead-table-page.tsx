"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { LeadConfiguration } from "@/components/lead-configuration";
import { LeadNavigation } from "@/components/lead-navigation";
import {
  AgeingBucket,
  apiRequest,
  ApiError,
  Lead,
  LeadAssignee,
  LeadSource,
  LeadStats,
  LeadStatus,
  PageResponse,
  permissionGranted
} from "@/lib/api";

type Mode = "all" | "allocation" | "unattended" | "ageing";

const statusLabels: Record<LeadStatus, string> = {
  NEW: "New", ASSIGNED: "Assigned", ATTEMPTED: "Attempted", CONTACTED: "Contacted",
  QUALIFIED: "Qualified", DISQUALIFIED: "Disqualified", LOST: "Lost", CONVERTED: "Converted"
};

const modeCopy = {
  all: { overline: "Lead management", title: "Leads", description: "Search, qualify, and progress every enquiry from first contact to conversion." },
  allocation: { overline: "Lead operations", title: "Lead allocation", description: "Review unassigned leads and distribute ownership in controlled batches." },
  unattended: { overline: "Lead operations", title: "Unattended leads", description: "Surface active leads with no recent activity before opportunities become stale." },
  ageing: { overline: "Pipeline health", title: "Lead ageing", description: "Inspect active opportunities by time spent in the pipeline." }
} as const;

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Lead data is unavailable";
}

function formatMoney(value: string | null): string {
  if (!value) return "Not captured";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Number(value));
}

export function LeadTablePage({ mode }: { mode: Mode }) {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [result, setResult] = useState<PageResponse<Lead> | null>(null);
  const [stats, setStats] = useState<LeadStats | null>(null);
  const [sources, setSources] = useState<LeadSource[]>([]);
  const [assignees, setAssignees] = useState<LeadAssignee[]>([]);
  const [buckets, setBuckets] = useState<AgeingBucket[]>([]);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [minimumScore, setMinimumScore] = useState("");
  const [days, setDays] = useState("2");
  const [ageingRange, setAgeingRange] = useState("0:");
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkOwner, setBulkOwner] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const canCreate = permissionGranted(permissions, "leads.create");
  const canAssign = permissionGranted(permissions, "leads.assign");
  const canManage = permissionGranted(permissions, "leads.manage");
  const copy = modeCopy[mode];

  useEffect(() => {
    if (!session) return;
    let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "15" });
    if (query) params.set("q", query);
    if (mode === "all") {
      if (status) params.set("status", status);
      if (sourceId) params.set("source_id", sourceId);
      if (ownerId) params.set("owner_user_id", ownerId);
      if (minimumScore) params.set("min_score", minimumScore);
    }
    if (mode === "unattended") params.set("days", days);
    if (mode === "ageing") {
      const [minimum, maximum] = ageingRange.split(":");
      params.set("min_days", minimum);
      if (maximum) params.set("max_days", maximum);
    }
    const base = mode === "all" ? "/leads" : `/leads/${mode}`;
    void apiRequest<PageResponse<Lead>>(`${base}?${params}`)
      .then((data) => {
        if (!active) return;
        setResult(data);
        setSelected((current) => current.filter((id) => data.items.some((lead) => lead.id === id)));
      })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [ageingRange, days, minimumScore, mode, ownerId, page, query, refreshKey, session, sourceId, status]);

  useEffect(() => {
    if (!session) return;
    let active = true;
    const requests: Promise<unknown>[] = [
      apiRequest<LeadSource[]>("/leads/sources").then((data) => { if (active) setSources(data); })
    ];
    if (mode === "all") requests.push(
      apiRequest<LeadStats>("/leads/stats").then((data) => { if (active) setStats(data); })
    );
    if (canAssign) requests.push(
      apiRequest<LeadAssignee[]>("/leads/assignees").then((data) => { if (active) setAssignees(data); })
    );
    if (mode === "ageing") requests.push(
      apiRequest<AgeingBucket[]>("/leads/ageing/buckets").then((data) => { if (active) setBuckets(data); })
    );
    void Promise.all(requests).catch((reason: unknown) => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [canAssign, mode, refreshKey, session]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setPage(1);
    setQuery(searchInput.trim());
  }

  function toggleLead(id: string) {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  async function assignSelected() {
    if (!bulkOwner || selected.length === 0 || !canAssign) return;
    setAssigning(true);
    setError(null);
    try {
      await apiRequest<Lead[]>("/leads/bulk-assign", {
        method: "POST",
        body: JSON.stringify({ lead_ids: selected, assigned_user_id: bulkOwner })
      });
      setNotice(`${selected.length} lead${selected.length === 1 ? "" : "s"} assigned`);
      setSelected([]);
      setBulkOwner("");
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setAssigning(false);
    }
  }

  const allVisibleSelected = Boolean(result?.items.length) && result?.items.every((lead) => selected.includes(lead.id));

  return (
    <AppShell>
      <main className="dashboard-content lead-content">
        <LeadNavigation />
        <div className="management-heading lead-heading">
          <div><p className="overline">{copy.overline}</p><h1>{copy.title}</h1><p>{copy.description}</p></div>
          <div className="heading-actions">
            {mode === "all" && canManage && <button className="button button-secondary" onClick={() => setConfigurationOpen(true)}>Configure</button>}
            {canCreate && <Link className="button button-primary" href="/leads/create">Create lead</Link>}
          </div>
        </div>

        {mode === "all" && stats && <section className="lead-metrics" aria-label="Lead summary">
          <article><span>Total leads</span><strong>{stats.total}</strong></article>
          <article><span>Active pipeline</span><strong>{stats.active}</strong></article>
          <article><span>Unassigned</span><strong>{stats.unassigned}</strong></article>
          <article><span>Follow-ups due</span><strong>{stats.follow_ups_due}</strong></article>
          <article><span>Average score</span><strong>{stats.average_score}</strong></article>
        </section>}

        {mode === "ageing" && buckets.length > 0 && <section className="ageing-buckets">
          {buckets.map((bucket) => <button key={bucket.label} className={ageingRange === `${bucket.minimum_days}:${bucket.maximum_days ?? ""}` ? "active" : ""} onClick={() => { setPage(1); setLoading(true); setAgeingRange(`${bucket.minimum_days}:${bucket.maximum_days ?? ""}`); }}><span>{bucket.label}</span><strong>{bucket.count}</strong></button>)}
        </section>}

        <div className="management-toolbar lead-toolbar">
          <form className="search-box" onSubmit={submitSearch}><span aria-hidden="true">/</span><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search name, email, phone, or company..." aria-label="Search leads" /></form>
          {mode === "all" && <>
            <select value={status} onChange={(event) => { setLoading(true); setPage(1); setStatus(event.target.value); }} aria-label="Filter by status"><option value="">All statuses</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <select value={sourceId} onChange={(event) => { setLoading(true); setPage(1); setSourceId(event.target.value); }} aria-label="Filter by source"><option value="">All sources</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}</select>
            {assignees.length > 0 && <select value={ownerId} onChange={(event) => { setLoading(true); setPage(1); setOwnerId(event.target.value); }} aria-label="Filter by owner"><option value="">All owners</option>{assignees.map((user) => <option key={user.id} value={user.id}>{user.full_name}</option>)}</select>}
            <select value={minimumScore} onChange={(event) => { setLoading(true); setPage(1); setMinimumScore(event.target.value); }} aria-label="Filter by minimum score"><option value="">Any score</option><option value="25">25+</option><option value="50">50+</option><option value="75">75+</option></select>
          </>}
          {mode === "unattended" && <select value={days} onChange={(event) => { setLoading(true); setPage(1); setDays(event.target.value); }} aria-label="Inactivity window"><option value="1">1+ days</option><option value="2">2+ days</option><option value="3">3+ days</option><option value="7">7+ days</option><option value="14">14+ days</option></select>}
          <span className="result-count">{result?.total ?? 0} records</span>
        </div>

        {mode === "allocation" && canAssign && <div className="bulk-action-bar">
          <span>{selected.length} selected</span>
          <select value={bulkOwner} onChange={(event) => setBulkOwner(event.target.value)} aria-label="Select assignee"><option value="">Choose an owner</option>{assignees.map((user) => <option key={user.id} value={user.id}>{user.full_name}</option>)}</select>
          <button className="button button-primary" onClick={() => void assignSelected()} disabled={!bulkOwner || selected.length === 0 || assigning}>{assigning ? "Assigning..." : "Assign selected"}</button>
        </div>}

        {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
        {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
        <section className="data-card lead-data-card">
          <div className={`data-table lead-table ${mode === "allocation" ? "selectable" : ""}`} role="table" aria-label={copy.title}>
            <div className="data-row data-head" role="row">
              {mode === "allocation" && <span><input type="checkbox" checked={allVisibleSelected} onChange={() => setSelected(allVisibleSelected ? [] : result?.items.map((lead) => lead.id) ?? [])} aria-label="Select all visible leads" /></span>}
              <span>Lead</span><span>Status & score</span><span>Source</span><span>Owner</span><span>Next action</span><span aria-label="Open" />
            </div>
            {loading ? <div className="center-inline" aria-busy="true"><span className="spinner" /><span>Loading leads...</span></div> : result?.items.length ? result.items.map((lead) => (
              <div className="data-row" role="row" key={lead.id}>
                {mode === "allocation" && <span><input type="checkbox" checked={selected.includes(lead.id)} onChange={() => toggleLead(lead.id)} aria-label={`Select ${lead.full_name}`} /></span>}
                <span className="primary-cell"><strong>{lead.full_name}</strong><small>{lead.phone ?? lead.email ?? "No contact"}{lead.company_name ? ` · ${lead.company_name}` : ""}</small></span>
                <span className="lead-status-cell"><span className={`lead-status status-${lead.status.toLowerCase()}`}>{statusLabels[lead.status]}</span><span className="score-ring" style={{ "--score": `${lead.score * 3.6}deg` } as React.CSSProperties}><b>{lead.score}</b></span></span>
                <span>{lead.source_name ?? "Unspecified"}</span>
                <span>{lead.owner_name ?? <span className="muted-copy">Unassigned</span>}</span>
                <span className="primary-cell"><strong>{lead.next_follow_up_at ? new Date(lead.next_follow_up_at).toLocaleDateString() : "No follow-up"}</strong><small>Budget up to {formatMoney(lead.budget_max)}</small></span>
                <span className="row-actions"><Link href={`/leads/${lead.id}`}>Open</Link></span>
              </div>
            )) : <div className="empty-state table-empty"><span className="empty-icon" aria-hidden="true">+</span><h3>No leads found</h3><p>{mode === "all" ? "Create a lead or adjust the current filters." : "There are no leads requiring attention in this view."}</p></div>}
          </div>
          <div className="pagination"><button disabled={!result || page <= 1} onClick={() => { setLoading(true); setPage((value) => value - 1); }}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => { setLoading(true); setPage((value) => value + 1); }}>Next</button></div>
        </section>

        {configurationOpen && <LeadConfiguration onClose={() => { setConfigurationOpen(false); setRefreshKey((value) => value + 1); }} />}
      </main>
    </AppShell>
  );
}
