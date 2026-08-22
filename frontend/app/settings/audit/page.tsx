"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { SettingsNavigation } from "@/components/settings-navigation";
import {
  apiDownload,
  apiRequest,
  ApiError,
  AuditFilterOptions,
  AuditLog,
  PageResponse,
  permissionGranted
} from "@/lib/api";

const emptyOptions: AuditFilterOptions = { actions: [], entity_types: [], actors: [] };

function label(value: string) {
  return value.split(/[._]/).filter(Boolean).map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`).join(" · ");
}

function json(value: Record<string, unknown> | null) {
  return value ? JSON.stringify(value, null, 2) : "No value";
}

export default function AuditPage() {
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const canExport = permissionGranted(permissions, "audit.export");
  const [rows, setRows] = useState<PageResponse<AuditLog> | null>(null);
  const [options, setOptions] = useState<AuditFilterOptions>(emptyOptions);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [actorId, setActorId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const params = useCallback((includePage: boolean) => {
    const value = new URLSearchParams();
    if (includePage) {
      value.set("page", String(page));
      value.set("page_size", "25");
    }
    if (query) value.set("q", query);
    if (action) value.set("action", action);
    if (entityType) value.set("entity_type", entityType);
    if (actorId) value.set("actor_user_id", actorId);
    if (dateFrom) value.set("date_from", new Date(`${dateFrom}T00:00:00`).toISOString());
    if (dateTo) value.set("date_to", new Date(`${dateTo}T23:59:59.999`).toISOString());
    return value.toString();
  }, [action, actorId, dateFrom, dateTo, entityType, page, query]);

  useEffect(() => {
    if (!session) return;
    let active = true;
    void apiRequest<AuditFilterOptions>("/organization/audit-logs/options")
      .then((data) => { if (active) setOptions(data); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof ApiError ? reason.message : "Audit filters could not be loaded"); });
    return () => { active = false; };
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let active = true;
    void apiRequest<PageResponse<AuditLog>>(`/organization/audit-logs?${params(true)}`)
      .then((data) => { if (active) { setRows(data); setError(null); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof ApiError ? reason.message : "Audit trail could not be loaded"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [params, session]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setQuery(queryDraft.trim());
  }

  function resetFilters() {
    setQueryDraft("");
    setQuery("");
    setAction("");
    setEntityType("");
    setActorId("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  async function download() {
    if (!canExport) return;
    setExporting(true);
    setError(null);
    try {
      const blob = await apiDownload(`/organization/audit-logs/export?${params(false)}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Audit export could not be generated");
    } finally {
      setExporting(false);
    }
  }

  return (
    <AppShell>
      <main className="dashboard-content management-content audit-content">
        <SettingsNavigation />
        <div className="management-heading">
          <div><p className="overline">Governance</p><h1>Audit trail</h1><p>Read-only history of security-sensitive and business-critical changes in this organization.</p></div>
          {canExport && <button className="button" type="button" onClick={download} disabled={exporting}>{exporting ? "Preparing…" : "Export CSV"}</button>}
        </div>
        {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}

        <section className="panel audit-filter-panel" aria-label="Audit filters">
          <form className="audit-search" onSubmit={search}>
            <label className="search-box"><span aria-hidden="true">⌕</span><input value={queryDraft} onChange={(event) => setQueryDraft(event.target.value)} placeholder="Search action, entity, ID, request, or actor" maxLength={100}/></label>
            <button className="button button-primary" type="submit">Search</button>
          </form>
          <div className="audit-filter-grid">
            <label className="field"><span>Action</span><select value={action} onChange={(event) => { setAction(event.target.value); setPage(1); }}><option value="">All actions</option>{options.actions.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label>
            <label className="field"><span>Entity</span><select value={entityType} onChange={(event) => { setEntityType(event.target.value); setPage(1); }}><option value="">All entities</option>{options.entity_types.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label>
            <label className="field"><span>Actor</span><select value={actorId} onChange={(event) => { setActorId(event.target.value); setPage(1); }}><option value="">All actors</option>{options.actors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="field"><span>From</span><input type="date" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }}/></label>
            <label className="field"><span>To</span><input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => { setDateTo(event.target.value); setPage(1); }}/></label>
            <button className="filter-reset" type="button" onClick={resetFilters}>Clear filters</button>
          </div>
        </section>

        <section className="data-card audit-data-card" aria-busy={loading}>
          <div className="audit-table data-table">
            <div className="data-row data-head"><span>Timestamp</span><span>Actor</span><span>Action</span><span>Entity</span><span>Origin</span><span/></div>
            {!loading && rows?.items.map((row) => <button className="data-row audit-row" type="button" key={row.id} onClick={() => setSelected(row)}>
              <span className="primary-cell"><strong>{new Date(row.created_at).toLocaleDateString()}</strong><small>{new Date(row.created_at).toLocaleTimeString()}</small></span>
              <span className="primary-cell"><strong>{row.actor_name ?? "System"}</strong><small>{row.actor_user_id ?? "Automated process"}</small></span>
              <span><b className="audit-action">{label(row.action)}</b></span>
              <span className="primary-cell"><strong>{label(row.entity_type)}</strong><small>{row.entity_id}</small></span>
              <span className="primary-cell"><strong>{row.ip_address ?? "Internal"}</strong><small>{row.request_id ?? "No request ID"}</small></span>
              <span className="audit-open">View</span>
            </button>)}
          </div>
          {loading && <div className="center-inline"><span className="spinner"/><span>Loading audit records…</span></div>}
          {!loading && !rows?.items.length && <div className="empty-state table-empty"><h3>No audit records match</h3><p>New records appear only when real protected actions occur.</p></div>}
          {rows && rows.pages > 0 && <div className="pagination"><span>{rows.total} immutable record{rows.total === 1 ? "" : "s"}</span><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><strong>{page} / {rows.pages}</strong><button type="button" disabled={page >= rows.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>}
        </section>

        {selected && <div className="drawer-layer" role="presentation"><button className="drawer-scrim" type="button" onClick={() => setSelected(null)} aria-label="Close audit detail"/><aside className="editor-drawer audit-drawer" aria-label="Audit record detail">
          <div className="drawer-heading"><div><p className="overline">Immutable record</p><h2>{label(selected.action)}</h2></div><button className="icon-button" type="button" onClick={() => setSelected(null)} aria-label="Close">×</button></div>
          <dl className="audit-facts">
            <div><dt>Organization</dt><dd>{selected.organization_name}<small>{selected.organization_id}</small></dd></div>
            <div><dt>Actor</dt><dd>{selected.actor_name ?? "System"}<small>{selected.actor_user_id ?? "Automated process"}</small></dd></div>
            <div><dt>Entity</dt><dd>{label(selected.entity_type)}<small>{selected.entity_id}</small></dd></div>
            <div><dt>Timestamp</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd></div>
            <div><dt>Request</dt><dd>{selected.request_id ?? "Not request-bound"}<small>{selected.ip_address ?? "No client IP"}</small></dd></div>
          </dl>
          <div className="audit-values"><section><h3>Previous value</h3><pre>{json(selected.old_value)}</pre></section><section><h3>New value</h3><pre>{json(selected.new_value)}</pre></section></div>
          <section className="audit-device"><h3>Device context</h3><p>{selected.user_agent ?? "No user-agent was available for this event."}</p>{selected.device_metadata && <pre>{JSON.stringify(selected.device_metadata, null, 2)}</pre>}</section>
        </aside></div>}
      </main>
    </AppShell>
  );
}
