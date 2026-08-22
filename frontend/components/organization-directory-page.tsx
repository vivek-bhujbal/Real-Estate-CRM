"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { useConfirmDialog } from "@/components/confirm-dialog";
import { SettingsNavigation } from "@/components/settings-navigation";
import {
  apiRequest,
  ApiError,
  Branch,
  Department,
  ManagedUser,
  PageResponse,
  permissionGranted,
  Team,
  Territory
} from "@/lib/api";

type EntityKind = "branches" | "departments" | "teams" | "territories";
type DirectoryEntity = Branch | Department | Team | Territory;
type Draft = {
  name: string;
  code: string;
  description: string;
  branch_id: string;
  manager_user_id: string;
  parent_id: string;
  member_ids: string[];
  is_active: boolean;
};

const config = {
  branches: { title: "Branches", singular: "branch", description: "Manage operating locations and branch-level ownership." },
  departments: { title: "Departments", singular: "department", description: "Structure functions within the organization and its branches." },
  teams: { title: "Teams", singular: "team", description: "Group users around managers, branches, and operating responsibilities." },
  territories: { title: "Territories", singular: "territory", description: "Define hierarchical geographic coverage and accountable managers." }
} as const;

const emptyDraft: Draft = {
  name: "", code: "", description: "", branch_id: "", manager_user_id: "",
  parent_id: "", member_ids: [], is_active: true
};

function message(reason: unknown) {
  return reason instanceof ApiError ? reason.message : "The request could not be completed";
}

export function OrganizationDirectoryPage({ kind }: { kind: EntityKind }) {
  const { session } = useAuth();
  const confirmDialog = useConfirmDialog();
  const permissions = session?.user.permissions ?? [];
  const settings = config[kind];
  const [result, setResult] = useState<PageResponse<DirectoryEntity> | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [editing, setEditing] = useState<DirectoryEntity | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canCreate = permissionGranted(permissions, `${kind}.create`);
  const canUpdate = permissionGranted(permissions, `${kind}.update`);
  const canDelete = permissionGranted(permissions, `${kind}.delete`);
  const canAssign = permissionGranted(permissions, `${kind}.assign`);

  useEffect(() => {
    if (!session) return;
    let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "12" });
    if (query) params.set("q", query);
    if (activeFilter) params.set("is_active", activeFilter);
    if (branchFilter && kind !== "branches") params.set("branch_id", branchFilter);
    void apiRequest<PageResponse<DirectoryEntity>>(`/organization/${kind}?${params}`)
      .then((data) => { if (active) setResult(data); })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [activeFilter, branchFilter, kind, page, query, refreshKey, session]);

  useEffect(() => {
    if (!session || kind === "branches") return;
    let active = true;
    const requests: Promise<unknown>[] = [
      apiRequest<PageResponse<Branch>>("/organization/branches?page_size=100&is_active=true")
        .then((data) => { if (active) setBranches(data.items); })
    ];
    if (kind === "teams" || kind === "territories") {
      requests.push(
        apiRequest<PageResponse<ManagedUser>>("/organization/users?page_size=100&is_active=true")
          .then((data) => { if (active) setUsers(data.items); })
      );
    }
    if (kind === "territories") {
      requests.push(
        apiRequest<PageResponse<Territory>>("/organization/territories?page_size=100")
          .then((data) => { if (active) setTerritories(data.items); })
      );
    }
    void Promise.all(requests).catch((reason: unknown) => {
      if (active) setError(message(reason));
    });
    return () => { active = false; };
  }, [kind, refreshKey, session]);

  const editingId = editing && editing !== "new" ? editing.id : null;
  const availableParents = useMemo(
    () => territories.filter((territory) => territory.id !== editingId),
    [editingId, territories]
  );

  function openNew() {
    setDraft(emptyDraft);
    setEditing("new");
    setError(null);
  }

  function openEdit(entity: DirectoryEntity) {
    setDraft({
      name: entity.name,
      code: "code" in entity ? entity.code : "",
      description: "description" in entity ? entity.description ?? "" : "",
      branch_id: "branch_id" in entity ? entity.branch_id ?? "" : "",
      manager_user_id: "manager_user_id" in entity ? entity.manager_user_id ?? "" : "",
      parent_id: "parent_id" in entity ? entity.parent_id ?? "" : "",
      member_ids: "member_ids" in entity ? entity.member_ids : [],
      is_active: entity.is_active
    });
    setEditing(entity);
    setError(null);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if ((editing === "new" && !canCreate) || (editing !== "new" && !canUpdate)) return;
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { name: draft.name, is_active: draft.is_active };
      if (kind !== "departments") payload.code = draft.code;
      if (kind !== "branches") payload.branch_id = draft.branch_id || null;
      if (kind === "teams" || kind === "territories") {
        payload.description = draft.description || null;
        payload.manager_user_id = draft.manager_user_id || null;
      }
      if (kind === "teams") payload.member_ids = draft.member_ids;
      if (kind === "territories") payload.parent_id = draft.parent_id || null;
      const path = editing === "new" ? `/organization/${kind}` : `/organization/${kind}/${editing?.id}`;
      await apiRequest(path, {
        method: editing === "new" ? "POST" : "PUT",
        body: JSON.stringify(payload)
      });
      setEditing(null);
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  }

  async function remove(entity: DirectoryEntity) {
    if (!canDelete || !(await confirmDialog({ title: `Delete ${settings.singular}?`, message: `${entity.name} will be permanently removed if it is not referenced by other records.`, confirmLabel: "Delete", tone: "danger" }))) return;
    setError(null);
    try {
      await apiRequest<void>(`/organization/${kind}/${entity.id}`, { method: "DELETE" });
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(message(reason));
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setPage(1);
    setQuery(search.trim());
  }

  return (
    <AppShell>
      <main className="dashboard-content management-content">
        <SettingsNavigation />
        <div className="management-heading">
          <div><p className="overline">Organization management</p><h1>{settings.title}</h1><p>{settings.description}</p></div>
          {canCreate && <button className="button button-primary" onClick={openNew}>Add {settings.singular}</button>}
        </div>
        <div className="management-toolbar">
          <form className="search-box" onSubmit={submitSearch}>
            <span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${settings.title.toLowerCase()}…`} aria-label={`Search ${settings.title}`}/>
          </form>
          <select value={activeFilter} onChange={(event) => { setLoading(true); setPage(1); setActiveFilter(event.target.value); }} aria-label="Filter by status">
            <option value="">All statuses</option><option value="true">Active</option><option value="false">Inactive</option>
          </select>
          {kind !== "branches" && branches.length > 0 && <select value={branchFilter} onChange={(event) => { setLoading(true); setPage(1); setBranchFilter(event.target.value); }} aria-label="Filter by branch">
            <option value="">All branches</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
          </select>}
          <span className="result-count">{result?.total ?? 0} records</span>
        </div>
        {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
        <section className="data-card">
          <div className="data-table directory-table" role="table" aria-label={settings.title}>
            <div className="data-row data-head" role="row"><span>Name</span><span>Scope</span><span>Details</span><span>Status</span><span aria-label="Actions" /></div>
            {loading ? <div className="center-inline" aria-busy="true"><span className="spinner"/><span>Loading {settings.title.toLowerCase()}…</span></div> : result?.items.length ? result.items.map((entity) => (
              <div className="data-row" role="row" key={entity.id}>
                <span className="primary-cell"><strong>{entity.name}</strong><small>{"code" in entity ? entity.code : "Department"}</small></span>
                <span>{"branch_name" in entity ? entity.branch_name ?? "Organization-wide" : `${entity.department_count} departments`}</span>
                <span>{kind === "branches" && "user_count" in entity ? `${entity.user_count} users` : kind === "departments" && "user_count" in entity ? `${entity.user_count} users` : kind === "teams" && "member_names" in entity ? `${entity.member_names.length} members · ${entity.manager_name ?? "No manager"}` : kind === "territories" && "parent_name" in entity ? entity.parent_name ? `Within ${entity.parent_name}` : "Top-level territory" : "—"}</span>
                <span><i className={`state-dot ${entity.is_active ? "active" : "inactive"}`}/>{entity.is_active ? "Active" : "Inactive"}</span>
                <span className="row-actions">{canUpdate && <button onClick={() => openEdit(entity)}>Edit</button>}{canDelete && <button className="danger-link" onClick={() => void remove(entity)}>Delete</button>}</span>
              </div>
            )) : <div className="empty-state table-empty"><span className="empty-icon" aria-hidden="true">◇</span><h3>No {settings.title.toLowerCase()} found</h3><p>Adjust the filters or add the first {settings.singular}.</p></div>}
          </div>
          <div className="pagination"><button disabled={!result || page <= 1} onClick={() => { setLoading(true); setPage((value) => value - 1); }}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => { setLoading(true); setPage((value) => value + 1); }}>Next</button></div>
        </section>

        {editing && <div className="drawer-layer" role="presentation"><button className="drawer-scrim" onClick={() => setEditing(null)} aria-label="Close editor"/><aside className="editor-drawer" aria-label={`${editing === "new" ? "Create" : "Edit"} ${settings.singular}`}>
          <div className="drawer-heading"><div><p className="overline">{editing === "new" ? "New record" : "Edit record"}</p><h2>{editing === "new" ? `Add ${settings.singular}` : draft.name}</h2></div><button className="icon-button" onClick={() => setEditing(null)} aria-label="Close">×</button></div>
          <form className="drawer-form" onSubmit={save}>
            <label className="field"><span>Name</span><input value={draft.name} onChange={(event) => setDraft({...draft, name: event.target.value})} required minLength={2} maxLength={160}/></label>
            {kind !== "departments" && <label className="field"><span>Code</span><input value={draft.code} onChange={(event) => setDraft({...draft, code: event.target.value.toUpperCase()})} required minLength={2} maxLength={40}/><small>Uppercase letters, numbers, hyphens, and underscores.</small></label>}
            {kind !== "branches" && <label className="field"><span>Branch</span><select value={draft.branch_id} onChange={(event) => setDraft({...draft, branch_id: event.target.value})} disabled={!canAssign}><option value="">Organization-wide</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select>{!canAssign && <small>Branch assignment requires additional permission.</small>}</label>}
            {(kind === "teams" || kind === "territories") && <label className="field"><span>Description</span><textarea value={draft.description} onChange={(event) => setDraft({...draft, description: event.target.value})} maxLength={500} rows={3}/></label>}
            {(kind === "teams" || kind === "territories") && <label className="field"><span>Manager</span><select value={draft.manager_user_id} onChange={(event) => setDraft({...draft, manager_user_id: event.target.value})} disabled={!canAssign}><option value="">No manager</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name}</option>)}</select></label>}
            {kind === "teams" && <label className="field"><span>Members</span><select multiple value={draft.member_ids} onChange={(event) => setDraft({...draft, member_ids: Array.from(event.target.selectedOptions, (option) => option.value)})} size={Math.min(Math.max(users.length, 3), 8)} disabled={!canAssign}>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>)}</select><small>{canAssign ? "Hold Ctrl or Command to select multiple users." : "Team assignment requires additional permission."}</small></label>}
            {kind === "territories" && <label className="field"><span>Parent territory</span><select value={draft.parent_id} onChange={(event) => setDraft({...draft, parent_id: event.target.value})}><option value="">Top-level territory</option>{availableParents.map((territory) => <option key={territory.id} value={territory.id}>{territory.name}</option>)}</select></label>}
            <label className="toggle-field"><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({...draft, is_active: event.target.checked})}/><span><strong>Active</strong><small>Inactive records remain visible in filtered history.</small></span></label>
            <div className="drawer-actions"><button className="button" type="button" onClick={() => setEditing(null)}>Cancel</button><button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</button></div>
          </form>
        </aside></div>}
      </main>
    </AppShell>
  );
}
