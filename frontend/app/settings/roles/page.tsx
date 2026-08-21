"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { SettingsNavigation } from "@/components/settings-navigation";
import {
  apiRequest,
  ApiError,
  Permission,
  permissionGranted,
  Role,
  UserAccess
} from "@/lib/api";

type Draft = { name: string; description: string; permission_codes: string[] };

const emptyDraft: Draft = { name: "", description: "", permission_codes: [] };

function errorMessage(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "The role settings could not be loaded";
}

export default function RolesPage() {
  const { session } = useAuth();
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [users, setUsers] = useState<UserAccess[]>([]);
  const [selectedId, setSelectedId] = useState<string | "new" | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [assignedRoleIds, setAssignedRoleIds] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const granted = session?.user.permissions ?? [];
  const canCreate = permissionGranted(granted, "roles.create");
  const canUpdate = permissionGranted(granted, "roles.update");
  const canDelete = permissionGranted(granted, "roles.delete");
  const canViewUsers = permissionGranted(granted, "users.view");
  const canAssign = permissionGranted(granted, "users.assign") && permissionGranted(granted, "roles.assign");
  const userId = session?.user.id;

  useEffect(() => {
    if (!userId) return;
    let active = true;
    void Promise.all([
      apiRequest<Role[]>("/rbac/roles"),
      apiRequest<Permission[]>("/rbac/permissions"),
      canViewUsers ? apiRequest<UserAccess[]>("/rbac/users") : Promise.resolve([])
    ])
      .then(([nextRoles, nextPermissions, nextUsers]) => {
        if (!active) return;
        setRoles(nextRoles);
        setPermissions(nextPermissions);
        setUsers(nextUsers);
        const firstRole = nextRoles[0];
        setSelectedId(firstRole?.id ?? (canCreate ? "new" : null));
        setDraft(firstRole ? {
          name: firstRole.name,
          description: firstRole.description ?? "",
          permission_codes: firstRole.permission_codes
        } : emptyDraft);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [canCreate, canViewUsers, userId]);

  const selectedRole = useMemo(
    () => roles.find((role) => role.id === selectedId) ?? null,
    [roles, selectedId]
  );
  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedUserId) ?? null,
    [selectedUserId, users]
  );
  const administratorRoleSelected = selectedRole?.name === "Organization Administrator";
  const draftIsDelegable = draft.permission_codes.every((code) => permissionGranted(granted, code));

  function canDelegateRole(role: Role) {
    return role.permission_codes.every((code) => permissionGranted(granted, code));
  }

  function selectRole(role: Role) {
    setSelectedId(role.id);
    setDraft({
      name: role.name,
      description: role.description ?? "",
      permission_codes: role.permission_codes
    });
    setError(null);
    setNotice(null);
  }

  function startNewRole() {
    setSelectedId("new");
    setDraft(emptyDraft);
    setError(null);
    setNotice(null);
  }

  const permissionGroups = useMemo(() => {
    const groups = new Map<string, Permission[]>();
    for (const permission of permissions) {
      const group = permission.code.split(".")[0];
      groups.set(group, [...(groups.get(group) ?? []), permission]);
    }
    return [...groups.entries()];
  }, [permissions]);

  function togglePermission(code: string) {
    setDraft((current) => ({
      ...current,
      permission_codes: current.permission_codes.includes(code)
        ? current.permission_codes.filter((item) => item !== code)
        : [...current.permission_codes, code]
    }));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if ((selectedId === "new" && !canCreate) || (selectedId !== "new" && !canUpdate) || administratorRoleSelected || !draftIsDelegable) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const payload = {
        name: draft.name,
        description: draft.description || null,
        permission_codes: draft.permission_codes
      };
      const saved = selectedId === "new"
        ? await apiRequest<Role>("/rbac/roles", { method: "POST", body: JSON.stringify(payload) })
        : await apiRequest<Role>(`/rbac/roles/${selectedId}`, { method: "PATCH", body: JSON.stringify(payload) });
      setRoles((current) => [...current.filter((role) => role.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)));
      setUsers((current) => current.map((user) => ({
        ...user,
        role_names: user.role_ids.map((roleId, index) => roleId === saved.id
          ? saved.name
          : roles.find((role) => role.id === roleId)?.name ?? user.role_names[index] ?? "Role")
      })));
      setSelectedId(saved.id);
      setDraft({ name: saved.name, description: saved.description ?? "", permission_codes: saved.permission_codes });
      setNotice(selectedId === "new" ? "Role created" : "Role updated");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  async function removeRole() {
    if (!selectedRole || selectedRole.is_system || !canDelete) return;
    if (!window.confirm(`Delete the “${selectedRole.name}” role?`)) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiRequest<void>(`/rbac/roles/${selectedRole.id}`, { method: "DELETE" });
      const remaining = roles.filter((role) => role.id !== selectedRole.id);
      setRoles(remaining);
      if (remaining[0]) selectRole(remaining[0]);
      else startNewRole();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  function selectUser(user: UserAccess) {
    setSelectedUserId(user.id);
    setAssignedRoleIds(user.role_ids);
    setError(null);
    setNotice(null);
  }

  function toggleAssignedRole(roleId: string) {
    setAssignedRoleIds((current) => current.includes(roleId)
      ? current.filter((item) => item !== roleId)
      : [...current, roleId]);
  }

  async function saveAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser || !canAssign || selectedUser.id === userId) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const response = await apiRequest<{ user_id: string; role_ids: string[] }>(
        `/rbac/users/${selectedUser.id}/roles`,
        { method: "PUT", body: JSON.stringify({ role_ids: assignedRoleIds }) }
      );
      const assignedRoles = roles.filter((role) => response.role_ids.includes(role.id));
      setUsers((current) => current.map((user) => user.id === response.user_id ? {
        ...user,
        role_ids: response.role_ids,
        role_names: assignedRoles.map((role) => role.name).sort()
      } : user));
      setAssignedRoleIds(response.role_ids);
      setNotice(`Roles updated for ${selectedUser.full_name}`);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <main className="dashboard-content roles-content">
        <SettingsNavigation />
        <div className="page-heading">
          <div>
            <p className="overline">Organization access</p>
            <h1>Roles & permissions</h1>
            <p>Control capabilities with explicit, tenant-scoped permission grants.</p>
          </div>
          {canCreate && <button className="button button-primary" onClick={startNewRole}>Create role</button>}
        </div>

        {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
        {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}

        {loading ? (
          <div className="center-inline" aria-busy="true"><span className="spinner"/><span>Loading access controls…</span></div>
        ) : (
          <>
          <div className="roles-layout">
            <aside className="roles-list" aria-label="Organization roles">
              <div className="roles-list-heading"><strong>{roles.length} roles</strong><small>System and custom</small></div>
              {roles.map((role) => (
                <button key={role.id} className={selectedId === role.id ? "selected" : ""} onClick={() => selectRole(role)}>
                  <span><strong>{role.name}</strong><small>{role.permission_codes.length} permissions · {role.user_count} users</small></span>
                  {role.is_system && <em>System</em>}
                </button>
              ))}
              {canCreate && (
                <button className={selectedId === "new" ? "selected create-role-row" : "create-role-row"} onClick={startNewRole}>
                  <span aria-hidden="true">＋</span><strong>New custom role</strong>
                </button>
              )}
            </aside>

            <section className="panel role-editor">
              {selectedId === null ? (
                <div className="empty-state compact"><h3>No roles available</h3></div>
              ) : (
                <form onSubmit={save}>
                  <div className="role-editor-heading">
                    <div>
                      <p className="overline">{selectedId === "new" ? "Custom role" : selectedRole?.is_system ? "Built-in role" : "Custom role"}</p>
                      <h2>{selectedId === "new" ? "Create a role" : selectedRole?.name}</h2>
                    </div>
                    {selectedRole?.is_system && <span className="status-pill">{administratorRoleSelected ? "Protected" : "Built-in"}</span>}
                  </div>
                  <div className="role-fields">
                    <label className="field">
                      <span>Role name</span>
                      <input value={draft.name} onChange={(event) => setDraft({...draft, name: event.target.value})} minLength={2} maxLength={100} required disabled={selectedRole?.is_system || (selectedId === "new" ? !canCreate : !canUpdate)}/>
                    </label>
                    <label className="field">
                      <span>Description</span>
                      <input value={draft.description} onChange={(event) => setDraft({...draft, description: event.target.value})} maxLength={255} disabled={administratorRoleSelected || (selectedId === "new" ? !canCreate : !canUpdate)}/>
                    </label>
                  </div>
                  <div className="permission-heading"><div><h3>Permissions</h3><p>Select only the capabilities this role requires.</p></div><strong>{draft.permission_codes.length} selected</strong></div>
                  <div className="permission-groups">
                    {permissionGroups.map(([group, items]) => (
                      <fieldset key={group} disabled={administratorRoleSelected || (selectedId === "new" ? !canCreate : !canUpdate)}>
                        <legend>{group}</legend>
                        {items.map((permission) => (
                          <label key={permission.code} className="permission-option">
                            <input type="checkbox" checked={draft.permission_codes.includes(permission.code)} onChange={() => togglePermission(permission.code)} disabled={!permissionGranted(granted, permission.code)}/>
                            <span><strong>{permission.code}</strong><small>{permission.description}</small></span>
                          </label>
                        ))}
                      </fieldset>
                    ))}
                  </div>
                  {draftIsDelegable && ((selectedId === "new" && canCreate) || (selectedId !== "new" && canUpdate && !administratorRoleSelected)) && (
                    <div className="role-actions">
                      {selectedId !== "new" && !selectedRole?.is_system && canDelete && <button className="button button-danger" type="button" onClick={removeRole} disabled={submitting}>Delete role</button>}
                      <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Saving…" : selectedId === "new" ? "Create role" : "Save changes"}</button>
                    </div>
                  )}
                </form>
              )}
            </section>
          </div>
          {canViewUsers && (
            <section className="access-assignments">
              <div className="section-heading">
                <div><p className="overline">User access</p><h2>Role assignments</h2><p>Assign one or more roles to existing organization users.</p></div>
                <span className="status-pill">{users.length} users</span>
              </div>
              <div className="assignments-layout">
                <aside className="assignment-users" aria-label="Organization users">
                  {users.map((user) => (
                    <button key={user.id} className={selectedUserId === user.id ? "selected" : ""} onClick={() => selectUser(user)}>
                      <span className="profile-avatar">{user.full_name.slice(0, 1).toUpperCase()}</span>
                      <span><strong>{user.full_name}</strong><small>{user.email}</small><em>{user.role_names.join(", ") || "No role assigned"}</em></span>
                    </button>
                  ))}
                </aside>
                <div className="panel assignment-editor">
                  {!selectedUser ? (
                    <div className="empty-state compact"><span className="empty-icon" aria-hidden="true">↗</span><h3>Select a user</h3><p>Choose an existing user to review role assignments.</p></div>
                  ) : (
                    <form onSubmit={saveAssignment}>
                      <div className="role-editor-heading"><div><p className="overline">Access assignment</p><h2>{selectedUser.full_name}</h2><p>{selectedUser.email}</p></div>{selectedUser.id === userId && <span className="status-pill">Your account</span>}</div>
                      {selectedUser.id === userId && <div className="assignment-note">Your own assignments cannot be changed from this session, preventing accidental administrator lockout.</div>}
                      <div className="assignment-role-grid">
                        {roles.map((role) => (
                          <label key={role.id} className="assignment-role-option">
                            <input type="checkbox" checked={assignedRoleIds.includes(role.id)} onChange={() => toggleAssignedRole(role.id)} disabled={!canAssign || selectedUser.id === userId || !canDelegateRole(role)}/>
                            <span><strong>{role.name}</strong><small>{role.permission_codes.length} permissions{role.is_system ? " · Built-in" : " · Custom"}{!canDelegateRole(role) ? " · Restricted" : ""}</small></span>
                          </label>
                        ))}
                      </div>
                      {canAssign && selectedUser.id !== userId && <div className="role-actions"><button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Saving…" : "Save assignments"}</button></div>}
                    </form>
                  )}
                </div>
              </div>
            </section>
          )}
          </>
        )}
      </main>
    </AppShell>
  );
}
