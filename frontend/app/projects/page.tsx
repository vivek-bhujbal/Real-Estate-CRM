"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiRequest, ApiError, PageResponse, permissionGranted, Project, ProjectStatus } from "@/lib/api";

const statuses: ProjectStatus[] = ["PLANNING", "LAUNCHED", "UNDER_CONSTRUCTION", "COMPLETED", "ON_HOLD", "ARCHIVED"];
const blank = { name: "", code: "", project_type: "", city: "", state: "", country: "India", rera_number: "", launch_date: "", expected_possession_date: "", default_currency: "INR", description: "", amenities: "" };
function message(reason: unknown) { return reason instanceof ApiError ? reason.message : "Project data is unavailable"; }

export default function ProjectsPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [result, setResult] = useState<PageResponse<Project> | null>(null);
  const [queryInput, setQueryInput] = useState(""); const [query, setQuery] = useState("");
  const [status, setStatus] = useState(""); const [page, setPage] = useState(1);
  const [draft, setDraft] = useState(blank); const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null); const [refresh, setRefresh] = useState(0);
  const canCreate = permissionGranted(permissions, "projects.create");

  useEffect(() => {
    if (!session) return; let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "12" });
    if (query) params.set("q", query); if (status) params.set("status", status);
    void apiRequest<PageResponse<Project>>(`/projects?${params}`).then((data) => { if (active) setResult(data); }).catch((reason: unknown) => { if (active) setError(message(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, query, refresh, session, status]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError(null);
    try {
      await apiRequest<Project>("/projects", { method: "POST", body: JSON.stringify({ ...draft, launch_date: draft.launch_date || null, expected_possession_date: draft.expected_possession_date || null, project_type: draft.project_type || null, city: draft.city || null, state: draft.state || null, country: draft.country || null, rera_number: draft.rera_number || null, description: draft.description || null, amenities: draft.amenities.split(",").map((item) => item.trim()).filter(Boolean) }) });
      setDraft(blank); setOpen(false); setRefresh((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }
  return <AppShell><main className="dashboard-content inventory-content">
    <div className="management-heading"><div><p className="overline">Property portfolio</p><h1>Projects</h1><p>Configure project identity and manage its tower, floor, and unit hierarchy.</p></div>{canCreate && <button className="button button-primary" onClick={() => setOpen(true)}>Create project</button>}</div>
    <div className="management-toolbar"><form className="search-box" onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }}><span>/</span><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search project, code, or city..." /></form><select value={status} onChange={(event) => { setPage(1); setStatus(event.target.value); }}><option value="">All statuses</option>{statuses.map((item) => <option value={item} key={item}>{item.replaceAll("_", " ")}</option>)}</select><span className="result-count">{result?.total ?? 0} projects</span></div>
    {error && <div className="alert alert-error page-alert">{error}</div>}
    {loading ? <div className="center-inline"><span className="spinner" />Loading projects...</div> : result?.items.length ? <section className="project-grid">{result.items.map((item) => <article className="project-card" key={item.id}><header><span className="project-code">{item.code}</span><span className={`inventory-status status-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</span></header><h2>{item.name}</h2><p>{[item.project_type, item.city, item.state].filter(Boolean).join(" · ") || "Project details not configured"}</p><div className="project-counts"><span><strong>{item.tower_count}</strong>Towers</span><span><strong>{item.unit_count}</strong>Units</span><span><strong>{item.available_unit_count}</strong>Available</span></div><footer><span>{item.rera_number ? `RERA ${item.rera_number}` : "RERA not captured"}</span><Link href={`/projects/${item.id}`}>Manage project →</Link></footer></article>)}</section> : <div className="panel empty-state"><span className="empty-icon">+</span><h3>No projects found</h3><p>Create the first project when your real inventory is ready.</p></div>}
    <div className="pagination project-pagination"><button disabled={!result || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>
    {open && <div className="modal-backdrop"><form className="modal-card project-modal" onSubmit={create}><div className="modal-heading"><div><p className="overline">New portfolio asset</p><h2>Create project</h2></div><button type="button" className="icon-button" onClick={() => setOpen(false)}>×</button></div><div className="customer-edit-scroll"><div className="lead-form-grid"><label className="field span-two"><span>Project name</span><input required minLength={2} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label><label className="field"><span>Code</span><input required pattern="[A-Za-z0-9][A-Za-z0-9_-]*" value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })} /></label><label className="field"><span>Project type</span><input value={draft.project_type} onChange={(e) => setDraft({ ...draft, project_type: e.target.value })} placeholder="Residential" /></label><label className="field"><span>City</span><input value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} /></label><label className="field"><span>State</span><input value={draft.state} onChange={(e) => setDraft({ ...draft, state: e.target.value })} /></label><label className="field"><span>Country</span><input value={draft.country} onChange={(e) => setDraft({ ...draft, country: e.target.value })} /></label><label className="field"><span>RERA number</span><input value={draft.rera_number} onChange={(e) => setDraft({ ...draft, rera_number: e.target.value })} /></label><label className="field"><span>Launch date</span><input type="date" value={draft.launch_date} onChange={(e) => setDraft({ ...draft, launch_date: e.target.value })} /></label><label className="field"><span>Expected possession</span><input type="date" value={draft.expected_possession_date} onChange={(e) => setDraft({ ...draft, expected_possession_date: e.target.value })} /></label><label className="field"><span>Default currency</span><input required minLength={3} maxLength={3} value={draft.default_currency} onChange={(e) => setDraft({ ...draft, default_currency: e.target.value.toUpperCase() })} /></label><label className="field span-two"><span>Amenities</span><input value={draft.amenities} onChange={(e) => setDraft({ ...draft, amenities: e.target.value })} placeholder="Pool, Gym, Clubhouse" /></label><label className="field span-two"><span>Description</span><textarea rows={4} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label></div></div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? "Creating..." : "Create project"}</button></div></form></div>}
  </main></AppShell>;
}
