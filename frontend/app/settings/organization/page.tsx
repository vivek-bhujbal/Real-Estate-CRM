"use client";

import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { SettingsNavigation } from "@/components/settings-navigation";
import {
  apiRequest,
  ApiError,
  AuditLog,
  OrganizationManagement,
  PageResponse,
  permissionGranted
} from "@/lib/api";

type FormState = {
  name: string; legal_name: string; contact_email: string; contact_phone: string;
  timezone: string; currency: string; date_format: string;
};

const emptyForm: FormState = {
  name: "", legal_name: "", contact_email: "", contact_phone: "",
  timezone: "", currency: "", date_format: ""
};

export default function OrganizationPage() {
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const [organization, setOrganization] = useState<OrganizationManagement | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [audits, setAudits] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const canUpdate = permissionGranted(permissions, "organization.update");
  const canViewAudit = permissionGranted(permissions, "audit.view");

  useEffect(() => {
    if (!session) return;
    let active = true;
    const requests: Promise<unknown>[] = [
      apiRequest<OrganizationManagement>("/organization").then((data) => {
        if (!active) return;
        setOrganization(data);
        setForm({
          name: data.name,
          legal_name: data.legal_name ?? "",
          contact_email: data.contact_email ?? "",
          contact_phone: data.contact_phone ?? "",
          timezone: data.timezone ?? "",
          currency: data.currency ?? "",
          date_format: data.date_format ?? ""
        });
      })
    ];
    if (canViewAudit) {
      requests.push(apiRequest<PageResponse<AuditLog>>("/organization/audit-logs?page_size=8")
        .then((data) => { if (active) setAudits(data.items); }));
    }
    void Promise.all(requests)
      .catch((reason: unknown) => { if (active) setError(reason instanceof ApiError ? reason.message : "Organization settings are unavailable"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [canViewAudit, session]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canUpdate) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiRequest<OrganizationManagement>("/organization", {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name,
          legal_name: form.legal_name || null,
          contact_email: form.contact_email || null,
          contact_phone: form.contact_phone || null,
          timezone: form.timezone || null,
          currency: form.currency || null,
          date_format: form.date_format || null
        })
      });
      setOrganization(updated);
      setNotice("Organization settings updated");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to save organization settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <main className="dashboard-content management-content">
        <SettingsNavigation />
        <div className="management-heading"><div><p className="overline">Organization management</p><h1>Organization</h1><p>Maintain the legal identity, contact profile, and workspace preferences.</p></div>{organization && <span className="organization-badge"><i className="state-dot active"/>Active workspace</span>}</div>
        {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
        {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
        {loading ? <div className="center-inline" aria-busy="true"><span className="spinner"/><span>Loading organization…</span></div> : organization && <div className="organization-layout">
          <section className="panel organization-profile-card">
            <div className="organization-identity"><span>{organization.name.slice(0, 1).toUpperCase()}</span><div><h2>{organization.name}</h2><p>{organization.slug}</p></div></div>
            <dl><div><dt>Workspace ID</dt><dd>{organization.id}</dd></div><div><dt>Created</dt><dd>{new Date(organization.created_at).toLocaleDateString()}</dd></div><div><dt>Status</dt><dd>{organization.is_active ? "Active" : "Inactive"}</dd></div></dl>
            <p className="profile-note">The workspace slug and identity are stable tenant boundaries and cannot be edited here.</p>
          </section>
          <section className="panel organization-form-card">
            <div className="panel-heading"><div><h2>Profile & preferences</h2><p>Settings are applied across this organization.</p></div></div>
            <form className="organization-form" onSubmit={save}>
              <label className="field"><span>Display name</span><input value={form.name} onChange={(event) => setForm({...form, name: event.target.value})} required minLength={2} maxLength={160} disabled={!canUpdate}/></label>
              <label className="field"><span>Legal name</span><input value={form.legal_name} onChange={(event) => setForm({...form, legal_name: event.target.value})} maxLength={200} disabled={!canUpdate}/></label>
              <label className="field"><span>Contact email</span><input type="email" value={form.contact_email} onChange={(event) => setForm({...form, contact_email: event.target.value})} disabled={!canUpdate}/></label>
              <label className="field"><span>Contact phone</span><input value={form.contact_phone} onChange={(event) => setForm({...form, contact_phone: event.target.value})} maxLength={30} disabled={!canUpdate}/></label>
              <label className="field"><span>Timezone</span><input value={form.timezone} onChange={(event) => setForm({...form, timezone: event.target.value})} placeholder="Asia/Kolkata" disabled={!canUpdate}/><small>Use an IANA timezone such as Asia/Kolkata.</small></label>
              <label className="field"><span>Currency</span><input value={form.currency} onChange={(event) => setForm({...form, currency: event.target.value.toUpperCase()})} placeholder="INR" minLength={3} maxLength={3} disabled={!canUpdate}/></label>
              <label className="field"><span>Date format</span><select value={form.date_format} onChange={(event) => setForm({...form, date_format: event.target.value})} disabled={!canUpdate}><option value="">Not configured</option><option value="DD/MM/YYYY">DD/MM/YYYY</option><option value="MM/DD/YYYY">MM/DD/YYYY</option><option value="YYYY-MM-DD">YYYY-MM-DD</option></select></label>
              {canUpdate && <div className="form-actions"><button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save settings"}</button></div>}
            </form>
          </section>
        </div>}
        {canViewAudit && !loading && <section className="panel audit-panel"><div className="panel-heading"><div><h2>Recent administration activity</h2><p>Immutable audit events for organization changes.</p></div><span className="status-pill">Audited</span></div>{audits.length ? <div className="audit-list">{audits.map((audit) => <article key={audit.id}><span className="audit-mark" aria-hidden="true">✓</span><div><strong>{audit.action.replaceAll(".", " · ")}</strong><p>{audit.actor_name ?? "System actor"} · {new Date(audit.created_at).toLocaleString()}</p></div><small>{audit.entity_type}</small></article>)}</div> : <div className="empty-state compact"><h3>No audit activity found</h3></div>}</section>}
      </main>
    </AppShell>
  );
}
