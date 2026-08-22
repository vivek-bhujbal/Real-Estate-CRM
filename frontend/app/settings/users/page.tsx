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
  permissionGranted
} from "@/lib/api";

type UserDraft = {
  email: string;
  full_name: string;
  password: string;
  branch_id: string;
  department_id: string;
  is_active: boolean;
};

const emptyDraft: UserDraft = {
  email: "",
  full_name: "",
  password: "",
  branch_id: "",
  department_id: "",
  is_active: true
};

function errorMessage(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "The request could not be completed";
}

export default function UsersPage() {
  const { session } = useAuth();
  const confirmDialog = useConfirmDialog();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [result, setResult] = useState<PageResponse<ManagedUser> | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [editing, setEditing] = useState<ManagedUser | "new" | null>(null);
  const [draft, setDraft] = useState<UserDraft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const canCreate = permissionGranted(permissions, "users.create");
  const canUpdate = permissionGranted(permissions, "users.update");
  const canDelete = permissionGranted(permissions, "users.delete");
  const canAssign = permissionGranted(permissions, "users.assign");

  useEffect(() => {
    if (!session) return;
    let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "12" });
    if (query) params.set("q", query);
    if (statusFilter) params.set("is_active", statusFilter);
    if (branchFilter) params.set("branch_id", branchFilter);
    if (departmentFilter) params.set("department_id", departmentFilter);
    void apiRequest<PageResponse<ManagedUser>>(`/organization/users?${params}`)
      .then((data) => {
        if (active) setResult(data);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [branchFilter, departmentFilter, page, query, refreshKey, session, statusFilter]);

  useEffect(() => {
    if (!session) return;
    let active = true;
    void Promise.all([
      permissionGranted(permissions, "branches.view")
        ? apiRequest<PageResponse<Branch>>("/organization/branches?page_size=100&is_active=true")
        : Promise.resolve({ items: [] } as unknown as PageResponse<Branch>),
      permissionGranted(permissions, "departments.view")
        ? apiRequest<PageResponse<Department>>("/organization/departments?page_size=100&is_active=true")
        : Promise.resolve({ items: [] } as unknown as PageResponse<Department>)
    ])
      .then(([branchPage, departmentPage]) => {
        if (!active) return;
        setBranches(branchPage.items);
        setDepartments(departmentPage.items);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => { active = false; };
  }, [permissions, refreshKey, session]);

  const availableDepartments = useMemo(
    () => departments.filter((department) => !draft.branch_id || department.branch_id === draft.branch_id),
    [departments, draft.branch_id]
  );

  function openNew() {
    setDraft(emptyDraft);
    setEditing("new");
    setError(null);
    setNotice(null);
  }

  function openEdit(user: ManagedUser) {
    setDraft({
      email: user.email,
      full_name: user.full_name,
      password: "",
      branch_id: user.branch_id ?? "",
      department_id: user.department_id ?? "",
      is_active: user.is_active
    });
    setEditing(user);
    setError(null);
    setNotice(null);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const creating = editing === "new";
    if ((creating && !canCreate) || (!creating && !canUpdate)) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload: Record<string, unknown> = {
        email: draft.email,
        full_name: draft.full_name,
        branch_id: draft.branch_id || null,
        department_id: draft.department_id || null,
        is_active: draft.is_active
      };
      if (creating) payload.password = draft.password;
      await apiRequest(creating ? "/organization/users" : `/organization/users/${editing?.id}`, {
        method: creating ? "POST" : "PUT",
        body: JSON.stringify(payload)
      });
      setEditing(null);
      setNotice(creating ? "User created" : "User updated");
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  async function deactivate(user: ManagedUser) {
    if (!canDelete || !(await confirmDialog({ title: "Deactivate user?", message: `${user.full_name} will lose access and all active sessions will be revoked.`, confirmLabel: "Deactivate", tone: "danger" }))) return;
    setError(null);
    setNotice(null);
    try {
      await apiRequest<void>(`/organization/users/${user.id}`, { method: "DELETE" });
      setNotice(`${user.full_name} deactivated`);
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setPage(1);
    setQuery(search.trim());
  }

  function updateBranchFilter(value: string) {
    setLoading(true);
    setPage(1);
    setBranchFilter(value);
    if (departmentFilter && departments.find((department) => department.id === departmentFilter)?.branch_id !== value) {
      setDepartmentFilter("");
    }
  }

  return (
    <AppShell>
      <main className="dashboard-content management-content">
        <SettingsNavigation />
        <div className="management-heading">
          <div>
            <p className="overline">Organization management</p>
            <h1>Users</h1>
            <p>Control staff identities, reporting scope, and account status.</p>
          </div>
          {canCreate && <button className="button button-primary" onClick={openNew}>Add user</button>}
        </div>

        <div className="management-toolbar user-filters">
          <form className="search-box" onSubmit={submitSearch}>
            <span aria-hidden="true">/</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or email..." aria-label="Search users" />
          </form>
          <select value={statusFilter} onChange={(event) => { setLoading(true); setPage(1); setStatusFilter(event.target.value); }} aria-label="Filter by status">
            <option value="">All statuses</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
          {branches.length > 0 && <select value={branchFilter} onChange={(event) => updateBranchFilter(event.target.value)} aria-label="Filter by branch">
            <option value="">All branches</option>
            {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
          </select>}
          {departments.length > 0 && <select value={departmentFilter} onChange={(event) => { setLoading(true); setPage(1); setDepartmentFilter(event.target.value); }} aria-label="Filter by department">
            <option value="">All departments</option>
            {departments.filter((department) => !branchFilter || department.branch_id === branchFilter).map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
          </select>}
          <span className="result-count">{result?.total ?? 0} records</span>
        </div>

        {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
        {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
        <section className="data-card">
          <div className="data-table users-table" role="table" aria-label="Users">
            <div className="data-row data-head" role="row"><span>User</span><span>Assignment</span><span>Roles</span><span>Last sign-in</span><span>Status</span><span aria-label="Actions" /></div>
            {loading ? <div className="center-inline" aria-busy="true"><span className="spinner" /><span>Loading users...</span></div> : result?.items.length ? result.items.map((user) => (
              <div className="data-row" role="row" key={user.id}>
                <span className="primary-cell"><strong>{user.full_name}</strong><small>{user.email}</small></span>
                <span className="primary-cell"><strong>{user.department_name ?? "No department"}</strong><small>{user.branch_name ?? "Organization-wide"}</small></span>
                <span>{user.role_names.length ? <span className="role-summary">{user.role_names.join(", ")}</span> : <span className="muted-copy">No role assigned</span>}</span>
                <span>{user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : "Never"}</span>
                <span><i className={`state-dot ${user.is_active ? "active" : "inactive"}`} />{user.is_active ? "Active" : "Inactive"}</span>
                <span className="row-actions">
                  {canUpdate && <button onClick={() => openEdit(user)}>Edit</button>}
                  {canDelete && user.is_active && user.id !== session?.user.id && <button className="danger-link" onClick={() => void deactivate(user)}>Deactivate</button>}
                </span>
              </div>
            )) : <div className="empty-state table-empty"><span className="empty-icon" aria-hidden="true">+</span><h3>No users found</h3><p>Adjust the filters or add the first user explicitly.</p></div>}
          </div>
          <div className="pagination">
            <button disabled={!result || page <= 1} onClick={() => { setLoading(true); setPage((value) => value - 1); }}>Previous</button>
            <span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span>
            <button disabled={!result || page >= result.pages} onClick={() => { setLoading(true); setPage((value) => value + 1); }}>Next</button>
          </div>
        </section>

        {editing && <div className="drawer-layer" role="presentation">
          <button className="drawer-scrim" onClick={() => setEditing(null)} aria-label="Close editor" />
          <aside className="editor-drawer" aria-label={`${editing === "new" ? "Create" : "Edit"} user`}>
            <div className="drawer-heading">
              <div><p className="overline">{editing === "new" ? "New account" : "Edit account"}</p><h2>{editing === "new" ? "Add user" : draft.full_name}</h2></div>
              <button className="icon-button" onClick={() => setEditing(null)} aria-label="Close">x</button>
            </div>
            <form className="drawer-form" onSubmit={save}>
              <label className="field"><span>Full name</span><input value={draft.full_name} onChange={(event) => setDraft({ ...draft, full_name: event.target.value })} required minLength={2} maxLength={160} autoFocus /></label>
              <label className="field"><span>Email address</span><input type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} required /></label>
              {editing === "new" && <label className="field"><span>Temporary password</span><input type="password" value={draft.password} onChange={(event) => setDraft({ ...draft, password: event.target.value })} required minLength={12} maxLength={128} autoComplete="new-password" /><small>At least 12 characters with upper/lowercase letters, a number, and a symbol. No password is generated automatically.</small></label>}
              {branches.length > 0 && <label className="field"><span>Branch</span><select value={draft.branch_id} onChange={(event) => setDraft({ ...draft, branch_id: event.target.value, department_id: "" })} disabled={!canAssign}><option value="">Organization-wide</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select>{!canAssign && <small>Branch assignment requires additional permission.</small>}</label>}
              {departments.length > 0 && <label className="field"><span>Department</span><select value={draft.department_id} onChange={(event) => setDraft({ ...draft, department_id: event.target.value })} disabled={!canAssign}><option value="">No department</option>{availableDepartments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>}
              <label className="toggle-field"><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} /><span><strong>Active account</strong><small>Inactive users cannot sign in.</small></span></label>
              <div className="drawer-actions"><button type="button" className="button" onClick={() => setEditing(null)}>Cancel</button><button type="submit" className="button button-primary" disabled={saving}>{saving ? "Saving..." : editing === "new" ? "Create user" : "Save changes"}</button></div>
            </form>
          </aside>
        </div>}
      </main>
    </AppShell>
  );
}
