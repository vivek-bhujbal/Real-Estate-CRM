"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { LeadNavigation } from "@/components/lead-navigation";
import {
  apiRequest,
  ApiError,
  Branch,
  DuplicateMatch,
  Lead,
  LeadAssignee,
  LeadSource,
  PageResponse,
  permissionGranted
} from "@/lib/api";

type Draft = {
  full_name: string; email: string; phone: string; alternate_phone: string;
  company_name: string; source_id: string; owner_user_id: string; branch_id: string;
  preferred_location: string; requirements: string; budget_min: string; budget_max: string;
  duplicate_override: boolean;
};

const emptyDraft: Draft = {
  full_name: "", email: "", phone: "", alternate_phone: "", company_name: "",
  source_id: "", owner_user_id: "", branch_id: "", preferred_location: "",
  requirements: "", budget_min: "", budget_max: "", duplicate_override: false
};

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Unable to create lead";
}

export default function CreateLeadPage() {
  const router = useRouter();
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [sources, setSources] = useState<LeadSource[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [assignees, setAssignees] = useState<LeadAssignee[]>([]);
  const [matches, setMatches] = useState<DuplicateMatch[]>([]);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAssign = permissionGranted(permissions, "leads.assign");
  const canApprove = permissionGranted(permissions, "leads.approve");
  const canViewBranches = permissionGranted(permissions, "branches.view");

  useEffect(() => {
    if (!session) return;
    let active = true;
    const requests: Promise<unknown>[] = [
      apiRequest<LeadSource[]>("/leads/sources").then((data) => { if (active) setSources(data.filter((item) => item.is_active)); })
    ];
    if (canAssign) requests.push(apiRequest<LeadAssignee[]>("/leads/assignees").then((data) => { if (active) setAssignees(data); }));
    if (canViewBranches) requests.push(apiRequest<PageResponse<Branch>>("/organization/branches?page_size=100&is_active=true").then((data) => { if (active) setBranches(data.items); }));
    void Promise.all(requests).catch((reason: unknown) => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [canAssign, canViewBranches, session]);

  useEffect(() => {
    if (!session || (!draft.email.trim() && !draft.phone.trim())) {
      return;
    }
    let active = true;
    const timeout = window.setTimeout(() => {
      setChecking(true);
      void apiRequest<DuplicateMatch[]>("/leads/duplicate-check", {
        method: "POST",
        body: JSON.stringify({ email: draft.email || null, phone: draft.phone || null })
      }).then((data) => { if (active) setMatches(data); })
        .catch(() => { if (active) setMatches([]); })
        .finally(() => { if (active) setChecking(false); });
    }, 450);
    return () => { active = false; window.clearTimeout(timeout); };
  }, [draft.email, draft.phone, session]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const lead = await apiRequest<Lead>("/leads", {
        method: "POST",
        body: JSON.stringify({
          full_name: draft.full_name,
          email: draft.email || null,
          phone: draft.phone || null,
          alternate_phone: draft.alternate_phone || null,
          company_name: draft.company_name || null,
          source_id: draft.source_id || null,
          owner_user_id: canAssign ? draft.owner_user_id || null : null,
          branch_id: draft.branch_id || null,
          preferred_location: draft.preferred_location || null,
          requirements: draft.requirements || null,
          budget_min: draft.budget_min || null,
          budget_max: draft.budget_max || null,
          duplicate_override: draft.duplicate_override
        })
      });
      router.push(`/leads/${lead.id}`);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  }

  return <AppShell>
    <main className="dashboard-content lead-content">
      <LeadNavigation />
      <div className="lead-form-heading"><div><Link href="/leads" className="back-link">Back to leads</Link><p className="overline">New enquiry</p><h1>Create lead</h1><p>Capture only real prospect information. Nothing is prefilled with sample data.</p></div><span className="form-progress">Contact and requirement</span></div>
      {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
      <form className="lead-create-layout" onSubmit={submit}>
        <section className="panel lead-form-panel">
          <div className="panel-heading"><div><h2>Contact identity</h2><p>Email or phone is required for duplicate protection.</p></div></div>
          <div className="lead-form-grid">
            <label className="field span-two"><span>Full name</span><input value={draft.full_name} onChange={(event) => setDraft({ ...draft, full_name: event.target.value })} required minLength={2} maxLength={160} autoFocus /></label>
            <label className="field"><span>Email</span><input type="email" value={draft.email} onChange={(event) => { setMatches([]); setDraft({ ...draft, email: event.target.value }); }} /></label>
            <label className="field"><span>Primary phone</span><input value={draft.phone} onChange={(event) => { setMatches([]); setDraft({ ...draft, phone: event.target.value }); }} /></label>
            <label className="field"><span>Alternate phone</span><input value={draft.alternate_phone} onChange={(event) => setDraft({ ...draft, alternate_phone: event.target.value })} /></label>
            <label className="field"><span>Company</span><input value={draft.company_name} onChange={(event) => setDraft({ ...draft, company_name: event.target.value })} /></label>
          </div>
          <div className="form-section-divider" />
          <div className="panel-heading"><div><h2>Requirement & ownership</h2><p>Capture buying context for qualification and scoring.</p></div></div>
          <div className="lead-form-grid">
            <label className="field"><span>Lead source</span><select value={draft.source_id} onChange={(event) => setDraft({ ...draft, source_id: event.target.value })}><option value="">Unspecified</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}</select></label>
            {branches.length > 0 && <label className="field"><span>Branch</span><select value={draft.branch_id} onChange={(event) => setDraft({ ...draft, branch_id: event.target.value })}><option value="">Organization-wide</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></label>}
            {canAssign && <label className="field span-two"><span>Owner</span><select value={draft.owner_user_id} onChange={(event) => setDraft({ ...draft, owner_user_id: event.target.value })}><option value="">Leave unassigned</option>{assignees.map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>)}</select></label>}
            <label className="field span-two"><span>Preferred location</span><input value={draft.preferred_location} onChange={(event) => setDraft({ ...draft, preferred_location: event.target.value })} /></label>
            <label className="field"><span>Minimum budget</span><input type="number" min="0" step="0.01" value={draft.budget_min} onChange={(event) => setDraft({ ...draft, budget_min: event.target.value })} /></label>
            <label className="field"><span>Maximum budget</span><input type="number" min="0" step="0.01" value={draft.budget_max} onChange={(event) => setDraft({ ...draft, budget_max: event.target.value })} /></label>
            <label className="field span-two"><span>Requirements</span><textarea rows={5} value={draft.requirements} onChange={(event) => setDraft({ ...draft, requirements: event.target.value })} maxLength={5000} /></label>
          </div>
        </section>
        <aside className="lead-create-aside">
          <section className={`panel duplicate-panel ${matches.length ? "has-matches" : ""}`}>
            <div className="panel-heading"><div><h2>Duplicate protection</h2><p>{checking ? "Checking contact details..." : matches.length ? `${matches.length} possible duplicate${matches.length === 1 ? "" : "s"} found.` : "No matching lead detected."}</p></div><span className={`state-dot ${matches.length ? "inactive" : "active"}`} /></div>
            {matches.map((match) => <Link href={`/leads/${match.lead.id}`} key={match.lead.id} className="duplicate-match"><strong>{match.lead.full_name}</strong><small>Matched on {match.matched_on.join(" and ")} · {match.lead.status}</small></Link>)}
            {matches.length > 0 && canApprove && <label className="toggle-field override-toggle"><input type="checkbox" checked={draft.duplicate_override} onChange={(event) => setDraft({ ...draft, duplicate_override: event.target.checked })} /><span><strong>Create as a separate lead</strong><small>I reviewed these matches and confirm this is a different person.</small></span></label>}
          </section>
          <section className="panel score-preview"><p className="overline">Scoring architecture</p><h2>Initial score signals</h2><ul><li><span>Email captured</span><strong>{draft.email ? "+10" : "—"}</strong></li><li><span>Phone captured</span><strong>{draft.phone ? "+15" : "—"}</strong></li><li><span>Budget captured</span><strong>{draft.budget_min || draft.budget_max ? "+10" : "—"}</strong></li><li><span>Owner assigned</span><strong>{draft.owner_user_id ? "+5" : "—"}</strong></li></ul><p>Active organization scoring rules are evaluated by the backend after save.</p></section>
          <div className="sticky-form-actions"><Link href="/leads" className="button button-secondary">Cancel</Link><button type="submit" className="button button-primary" disabled={saving || (matches.length > 0 && !draft.duplicate_override)}>{saving ? "Creating..." : "Create lead"}</button></div>
        </aside>
      </form>
    </main>
  </AppShell>;
}
