"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { ProtectedRoute } from "@/components/protected-route";
import { apiRequest, ApiError, Branch, Customer, LeadAssignee, PageResponse, permissionGranted } from "@/lib/api";

type Draft = {
  full_name: string; email: string; phone: string; alternate_phone: string;
  date_of_birth: string; gender: string; occupation: string; company_name: string;
  address_line1: string; address_line2: string; city: string; state: string;
  postal_code: string; country: string; preferred_location: string; requirements: string;
  budget_min: string; budget_max: string; owner_user_id: string; branch_id: string;
  email_opt_in: boolean; sms_opt_in: boolean; phone_opt_in: boolean;
};

const emptyDraft: Draft = {
  full_name: "", email: "", phone: "", alternate_phone: "", date_of_birth: "",
  gender: "", occupation: "", company_name: "", address_line1: "", address_line2: "",
  city: "", state: "", postal_code: "", country: "", preferred_location: "",
  requirements: "", budget_min: "", budget_max: "", owner_user_id: "", branch_id: "",
  email_opt_in: false, sms_opt_in: false, phone_opt_in: false
};

function compact(draft: Draft): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(draft)) {
    if (key.endsWith("_opt_in")) continue;
    payload[key] = value === "" ? null : value;
  }
  payload.communication_preferences = {
    email: draft.email_opt_in, sms: draft.sms_opt_in, phone: draft.phone_opt_in
  };
  return payload;
}

export default function CreateCustomerPage() {
  const router = useRouter();
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [assignees, setAssignees] = useState<LeadAssignee[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAssign = permissionGranted(permissions, "customers.assign");

  useEffect(() => {
    if (!session) return;
    let active = true;
    const requests: Promise<unknown>[] = [];
    if (canAssign) requests.push(apiRequest<LeadAssignee[]>("/customers/assignees").then((data) => { if (active) setAssignees(data); }));
    if (canAssign && permissionGranted(permissions, "branches.view")) requests.push(apiRequest<PageResponse<Branch>>("/organization/branches?page_size=100&is_active=true").then((data) => { if (active) setBranches(data.items); }));
    void Promise.all(requests).catch((reason: unknown) => { if (active) setError(reason instanceof ApiError ? reason.message : "Form options are unavailable"); });
    return () => { active = false; };
  }, [canAssign, permissions, session]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError(null);
    try {
      const customer = await apiRequest<Customer>("/customers", { method: "POST", body: JSON.stringify(compact(draft)) });
      router.push(`/customers/${customer.id}`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to create customer");
    } finally { setSaving(false); }
  }

  const set = (field: keyof Draft, value: string | boolean) => setDraft((current) => ({ ...current, [field]: value }));
  return <ProtectedRoute permission="customers.create"><AppShell><main className="dashboard-content customer-content">
    <div className="management-heading"><div><p className="overline">Customer 360</p><h1>Create customer</h1><p>Start with identity and requirement essentials. Transactional history will build from live workflows.</p></div><Link href="/customers" className="button button-secondary">Back to customers</Link></div>
    {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
    <form className="customer-form-layout" onSubmit={submit}>
      <div className="customer-form-stack">
        <section className="panel customer-form-section"><div className="panel-heading"><div><h2>Personal & contact</h2><p>Only email or phone is mandatory; keep optional fields genuinely useful.</p></div></div>
          <div className="lead-form-grid">
            <label className="field span-two"><span>Full name</span><input autoFocus required minLength={2} maxLength={160} value={draft.full_name} onChange={(e) => set("full_name", e.target.value)} /></label>
            <label className="field"><span>Email</span><input type="email" value={draft.email} onChange={(e) => set("email", e.target.value)} /></label>
            <label className="field"><span>Primary phone</span><input value={draft.phone} onChange={(e) => set("phone", e.target.value)} /></label>
            <label className="field"><span>Alternate phone</span><input value={draft.alternate_phone} onChange={(e) => set("alternate_phone", e.target.value)} /></label>
            <label className="field"><span>Date of birth</span><input type="date" max={new Date().toISOString().slice(0, 10)} value={draft.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} /></label>
            <label className="field"><span>Gender</span><input value={draft.gender} onChange={(e) => set("gender", e.target.value)} /></label>
            <label className="field"><span>Occupation</span><input value={draft.occupation} onChange={(e) => set("occupation", e.target.value)} /></label>
            <label className="field span-two"><span>Company</span><input value={draft.company_name} onChange={(e) => set("company_name", e.target.value)} /></label>
          </div>
        </section>
        <section className="panel customer-form-section"><div className="panel-heading"><div><h2>Requirement</h2><p>Capture the buying brief without turning the form into a questionnaire.</p></div></div>
          <div className="lead-form-grid">
            <label className="field span-two"><span>Preferred location</span><input value={draft.preferred_location} onChange={(e) => set("preferred_location", e.target.value)} /></label>
            <label className="field"><span>Minimum budget</span><input type="number" min="0" step="0.01" value={draft.budget_min} onChange={(e) => set("budget_min", e.target.value)} /></label>
            <label className="field"><span>Maximum budget</span><input type="number" min="0" step="0.01" value={draft.budget_max} onChange={(e) => set("budget_max", e.target.value)} /></label>
            <label className="field span-two"><span>Requirements</span><textarea rows={5} maxLength={5000} value={draft.requirements} onChange={(e) => set("requirements", e.target.value)} /></label>
          </div>
        </section>
        <section className="panel customer-form-section"><div className="panel-heading"><div><h2>Address</h2><p>Optional correspondence address.</p></div></div>
          <div className="lead-form-grid">
            <label className="field span-two"><span>Address line 1</span><input value={draft.address_line1} onChange={(e) => set("address_line1", e.target.value)} /></label>
            <label className="field span-two"><span>Address line 2</span><input value={draft.address_line2} onChange={(e) => set("address_line2", e.target.value)} /></label>
            <label className="field"><span>City</span><input value={draft.city} onChange={(e) => set("city", e.target.value)} /></label>
            <label className="field"><span>State</span><input value={draft.state} onChange={(e) => set("state", e.target.value)} /></label>
            <label className="field"><span>Postal code</span><input value={draft.postal_code} onChange={(e) => set("postal_code", e.target.value)} /></label>
            <label className="field"><span>Country</span><input value={draft.country} onChange={(e) => set("country", e.target.value)} /></label>
          </div>
        </section>
      </div>
      <aside className="customer-form-aside">
        {canAssign && <section className="panel"><div className="panel-heading"><div><h2>Ownership</h2><p>Control who manages this relationship.</p></div></div>
          <label className="field"><span>Owner</span><select value={draft.owner_user_id} onChange={(e) => set("owner_user_id", e.target.value)}><option value="">Unassigned</option>{assignees.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></label>
          {branches.length > 0 && <label className="field customer-aside-field"><span>Branch</span><select value={draft.branch_id} onChange={(e) => set("branch_id", e.target.value)}><option value="">Organization-wide</option>{branches.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>}
        </section>}
        <section className="panel preference-card"><div className="panel-heading"><div><h2>Communication consent</h2><p>Store explicit channel preferences.</p></div></div>
          {(["email", "sms", "phone"] as const).map((channel) => <label className="toggle-field" key={channel}><input type="checkbox" checked={draft[`${channel}_opt_in`]} onChange={(e) => set(`${channel}_opt_in`, e.target.checked)} /><span><strong>{channel.toUpperCase()}</strong><small>Customer has opted in</small></span></label>)}
        </section>
        <div className="sticky-form-actions"><Link href="/customers" className="button button-secondary">Cancel</Link><button className="button button-primary" disabled={saving}>{saving ? "Creating..." : "Create customer"}</button></div>
      </aside>
    </form>
  </main></AppShell></ProtectedRoute>;
}
