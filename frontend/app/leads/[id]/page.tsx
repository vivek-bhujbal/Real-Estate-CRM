"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { useConfirmDialog } from "@/components/confirm-dialog";
import { LeadNavigation } from "@/components/lead-navigation";
import {
  ActivityType,
  apiRequest,
  ApiError,
  Lead,
  LeadActivity,
  LeadAssignee,
  LeadNote,
  LeadSource,
  LeadStatus,
  LostReason,
  permissionGranted,
  TimelineItem
} from "@/lib/api";

const statusLabels: Record<LeadStatus, string> = {
  NEW: "New", ASSIGNED: "Assigned", ATTEMPTED: "Attempted", CONTACTED: "Contacted",
  QUALIFIED: "Qualified", DISQUALIFIED: "Disqualified", LOST: "Lost", CONVERTED: "Converted"
};

type LeadDraft = { full_name: string; email: string; phone: string; alternate_phone: string; company_name: string; source_id: string; preferred_location: string; requirements: string; budget_min: string; budget_max: string };
type ActivityDraft = { activity_type: ActivityType; subject: string; notes: string; occurred_at: string; due_at: string; outcome: string; is_completed: boolean };

function localDateTime(value = new Date()): string {
  const offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

const emptyActivity: ActivityDraft = { activity_type: "CALL", subject: "", notes: "", occurred_at: localDateTime(), due_at: "", outcome: "", is_completed: false };

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Lead request failed";
}

function leadDraft(lead: Lead): LeadDraft {
  return {
    full_name: lead.full_name, email: lead.email ?? "", phone: lead.phone ?? "",
    alternate_phone: lead.alternate_phone ?? "", company_name: lead.company_name ?? "",
    source_id: lead.source_id ?? "", preferred_location: lead.preferred_location ?? "",
    requirements: lead.requirements ?? "", budget_min: lead.budget_min ?? "",
    budget_max: lead.budget_max ?? ""
  };
}

export default function LeadDetailPage() {
  const confirmDialog = useConfirmDialog();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const leadId = params.id;
  const [lead, setLead] = useState<Lead | null>(null);
  const [activities, setActivities] = useState<LeadActivity[]>([]);
  const [notes, setNotes] = useState<LeadNote[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [sources, setSources] = useState<LeadSource[]>([]);
  const [reasons, setReasons] = useState<LostReason[]>([]);
  const [assignees, setAssignees] = useState<LeadAssignee[]>([]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<LeadDraft | null>(null);
  const [activityDraft, setActivityDraft] = useState<ActivityDraft>(emptyActivity);
  const [editingActivityId, setEditingActivityId] = useState<string | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [notePinned, setNotePinned] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [qualificationNotes, setQualificationNotes] = useState("");
  const [lostReasonId, setLostReasonId] = useState("");
  const [lostNotes, setLostNotes] = useState("");
  const [statusTarget, setStatusTarget] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const canUpdate = permissionGranted(permissions, "leads.update");
  const canDelete = permissionGranted(permissions, "leads.delete");
  const canAssign = permissionGranted(permissions, "leads.assign");
  const canConvert = permissionGranted(permissions, "leads.approve") && permissionGranted(permissions, "customers.create");
  const canCreateActivity = permissionGranted(permissions, "activities.create");
  const canUpdateActivity = permissionGranted(permissions, "activities.update");
  const canDeleteActivity = permissionGranted(permissions, "activities.delete");

  useEffect(() => {
    if (!session) return;
    let active = true;
    const requests: Promise<unknown>[] = [
      apiRequest<Lead>(`/leads/${leadId}`).then((data) => { if (active) { setLead(data); setDraft(leadDraft(data)); } }),
      apiRequest<LeadSource[]>("/leads/sources").then((data) => { if (active) setSources(data); }),
      apiRequest<LostReason[]>("/leads/lost-reasons").then((data) => { if (active) setReasons(data.filter((item) => item.is_active)); }),
      apiRequest<TimelineItem[]>(`/leads/${leadId}/timeline`).then((data) => { if (active) setTimeline(data); })
    ];
    if (permissionGranted(permissions, "activities.view")) {
      requests.push(apiRequest<LeadActivity[]>(`/leads/${leadId}/activities`).then((data) => { if (active) setActivities(data); }));
      requests.push(apiRequest<LeadNote[]>(`/leads/${leadId}/notes`).then((data) => { if (active) setNotes(data); }));
    }
    if (canAssign) requests.push(apiRequest<LeadAssignee[]>("/leads/assignees").then((data) => { if (active) setAssignees(data); }));
    void Promise.all(requests).catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [canAssign, leadId, permissions, refreshKey, session]);

  function refreshed(noticeText: string) {
    setNotice(noticeText);
    setLoading(true);
    setRefreshKey((value) => value + 1);
  }

  async function saveLead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !canUpdate) return;
    setSaving(true); setError(null); setNotice(null);
    try {
      await apiRequest<Lead>(`/leads/${leadId}`, { method: "PATCH", body: JSON.stringify({
        full_name: draft.full_name, email: draft.email || null, phone: draft.phone || null,
        alternate_phone: draft.alternate_phone || null, company_name: draft.company_name || null,
        source_id: draft.source_id || null, preferred_location: draft.preferred_location || null,
        requirements: draft.requirements || null, budget_min: draft.budget_min || null,
        budget_max: draft.budget_max || null
      }) });
      setEditing(false); refreshed("Lead details updated");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function assign(ownerId: string) {
    setSaving(true); setError(null);
    try {
      await apiRequest<Lead>(`/leads/${leadId}/assignment`, { method: "POST", body: JSON.stringify({ assigned_user_id: ownerId || null }) });
      refreshed(ownerId ? "Lead assigned" : "Lead unassigned");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function changeStatus() {
    if (!statusTarget) return;
    setSaving(true); setError(null);
    try {
      await apiRequest<Lead>(`/leads/${leadId}/status`, { method: "POST", body: JSON.stringify({ status: statusTarget }) });
      setStatusTarget(""); refreshed("Lead status updated");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function qualify() {
    if (!qualificationNotes.trim()) return;
    setSaving(true); setError(null);
    try {
      await apiRequest<Lead>(`/leads/${leadId}/qualify`, { method: "POST", body: JSON.stringify({ notes: qualificationNotes }) });
      setQualificationNotes(""); refreshed("Lead qualified");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function markLost() {
    if (!lostReasonId) return;
    setSaving(true); setError(null);
    try {
      await apiRequest<Lead>(`/leads/${leadId}/lost`, { method: "POST", body: JSON.stringify({ reason_id: lostReasonId, notes: lostNotes || null }) });
      setLostReasonId(""); setLostNotes(""); refreshed("Lead marked as lost");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function convert() {
    if (!(await confirmDialog({ title: "Convert lead to customer?", message: "A customer profile will be created from this qualified lead. The lead will move to converted status.", confirmLabel: "Convert lead" }))) return;
    setSaving(true); setError(null);
    try {
      const result = await apiRequest<{ customer_id: string }>(`/leads/${leadId}/convert`, { method: "POST", body: "{}" });
      refreshed(`Customer created (${result.customer_id.slice(0, 8)})`);
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function removeLead() {
    if (!canDelete || !(await confirmDialog({ title: "Delete lead?", message: `${lead?.full_name ?? "This lead"} and its non-transactional history will be permanently removed.`, confirmLabel: "Delete lead", tone: "danger" }))) return;
    setSaving(true); setError(null);
    try { await apiRequest<void>(`/leads/${leadId}`, { method: "DELETE" }); router.push("/leads"); }
    catch (reason) { setError(message(reason)); setSaving(false); }
  }

  function editActivity(item: LeadActivity) {
    setEditingActivityId(item.id);
    setActivityDraft({ activity_type: item.activity_type, subject: item.subject, notes: item.notes ?? "", occurred_at: localDateTime(new Date(item.occurred_at)), due_at: item.due_at ? localDateTime(new Date(item.due_at)) : "", outcome: item.outcome ?? "", is_completed: item.is_completed });
  }

  async function saveActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError(null);
    try {
      await apiRequest<LeadActivity>(editingActivityId ? `/leads/${leadId}/activities/${editingActivityId}` : `/leads/${leadId}/activities`, { method: editingActivityId ? "PUT" : "POST", body: JSON.stringify({ ...activityDraft, occurred_at: new Date(activityDraft.occurred_at).toISOString(), due_at: activityDraft.due_at ? new Date(activityDraft.due_at).toISOString() : null, notes: activityDraft.notes || null, outcome: activityDraft.outcome || null }) });
      setEditingActivityId(null); setActivityDraft({ ...emptyActivity, occurred_at: localDateTime() }); refreshed(editingActivityId ? "Activity updated" : "Activity added");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function completeFollowUp(item: LeadActivity) {
    const outcome = window.prompt("Follow-up outcome");
    if (!outcome) return;
    try { await apiRequest(`/leads/${leadId}/activities/${item.id}/complete`, { method: "POST", body: JSON.stringify({ outcome }) }); refreshed("Follow-up completed"); }
    catch (reason) { setError(message(reason)); }
  }

  async function removeActivity(item: LeadActivity) {
    if (!(await confirmDialog({ title: "Delete activity?", message: `${item.subject} will be removed from the lead timeline.`, confirmLabel: "Delete activity", tone: "danger" }))) return;
    try { await apiRequest<void>(`/leads/${leadId}/activities/${item.id}`, { method: "DELETE" }); refreshed("Activity deleted"); }
    catch (reason) { setError(message(reason)); }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!noteBody.trim()) return; setSaving(true); setError(null);
    try { await apiRequest(editingNoteId ? `/leads/${leadId}/notes/${editingNoteId}` : `/leads/${leadId}/notes`, { method: editingNoteId ? "PUT" : "POST", body: JSON.stringify({ body: noteBody, is_pinned: notePinned }) }); setNoteBody(""); setNotePinned(false); setEditingNoteId(null); refreshed(editingNoteId ? "Note updated" : "Note added"); }
    catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function removeNote(note: LeadNote) {
    if (!(await confirmDialog({ title: "Delete note?", message: "This internal note will be permanently removed from the lead.", confirmLabel: "Delete note", tone: "danger" }))) return;
    try { await apiRequest<void>(`/leads/${leadId}/notes/${note.id}`, { method: "DELETE" }); refreshed("Note deleted"); }
    catch (reason) { setError(message(reason)); }
  }

  if (loading && !lead) return <AppShell><main className="center-inline lead-loading"><span className="spinner" /><span>Loading lead...</span></main></AppShell>;
  if (!lead || !draft) return <AppShell><main className="dashboard-content">{error && <div className="alert alert-error">{error}</div>}</main></AppShell>;

  const scoreItems = [...(lead.score_breakdown?.base ?? []), ...(lead.score_breakdown?.rules ?? [])];

  return <AppShell>
    <main className="dashboard-content lead-content">
      <LeadNavigation />
      <div className="lead-detail-heading"><div><Link href="/leads" className="back-link">Back to leads</Link><div className="lead-title-line"><span className="lead-avatar">{lead.full_name.slice(0, 1).toUpperCase()}</span><div><p className="overline">Lead profile</p><h1>{lead.full_name}</h1><p>{lead.phone ?? lead.email} · Created {new Date(lead.created_at).toLocaleDateString()}</p></div></div></div><div className="lead-detail-actions"><span className={`lead-status status-${lead.status.toLowerCase()}`}>{statusLabels[lead.status]}</span>{canUpdate && lead.status !== "CONVERTED" && <button className="button button-secondary" onClick={() => setEditing((value) => !value)}>{editing ? "Close editor" : "Edit lead"}</button>}{canDelete && lead.status !== "CONVERTED" && <button className="button button-danger" onClick={() => void removeLead()} disabled={saving}>Delete</button>}</div></div>
      {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
      {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}

      {editing && <section className="panel lead-edit-panel"><form className="lead-form-grid" onSubmit={saveLead}><label className="field"><span>Full name</span><input value={draft.full_name} onChange={(event) => setDraft({ ...draft, full_name: event.target.value })} required /></label><label className="field"><span>Email</span><input type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label><label className="field"><span>Phone</span><input value={draft.phone} onChange={(event) => setDraft({ ...draft, phone: event.target.value })} /></label><label className="field"><span>Alternate phone</span><input value={draft.alternate_phone} onChange={(event) => setDraft({ ...draft, alternate_phone: event.target.value })} /></label><label className="field"><span>Company</span><input value={draft.company_name} onChange={(event) => setDraft({ ...draft, company_name: event.target.value })} /></label><label className="field"><span>Source</span><select value={draft.source_id} onChange={(event) => setDraft({ ...draft, source_id: event.target.value })}><option value="">Unspecified</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}</select></label><label className="field span-two"><span>Preferred location</span><input value={draft.preferred_location} onChange={(event) => setDraft({ ...draft, preferred_location: event.target.value })} /></label><label className="field"><span>Minimum budget</span><input type="number" min="0" value={draft.budget_min} onChange={(event) => setDraft({ ...draft, budget_min: event.target.value })} /></label><label className="field"><span>Maximum budget</span><input type="number" min="0" value={draft.budget_max} onChange={(event) => setDraft({ ...draft, budget_max: event.target.value })} /></label><label className="field span-two"><span>Requirements</span><textarea rows={4} value={draft.requirements} onChange={(event) => setDraft({ ...draft, requirements: event.target.value })} /></label><div className="form-actions span-two"><button className="button button-primary" disabled={saving}>{saving ? "Saving..." : "Save changes"}</button></div></form></section>}

      <div className="lead-detail-grid">
        <div className="lead-detail-main">
          <section className="panel lead-overview-card"><div className="panel-heading"><div><h2>Opportunity overview</h2><p>Current qualification and requirement context.</p></div><span className="score-large">{lead.score}<small>/100</small></span></div><dl className="lead-facts"><div><dt>Source</dt><dd>{lead.source_name ?? "Unspecified"}</dd></div><div><dt>Owner</dt><dd>{lead.owner_name ?? "Unassigned"}</dd></div><div><dt>Branch</dt><dd>{lead.branch_name ?? "Organization-wide"}</dd></div><div><dt>Preferred location</dt><dd>{lead.preferred_location ?? "Not captured"}</dd></div><div><dt>Budget range</dt><dd>{lead.budget_min || lead.budget_max ? `${lead.budget_min ?? "0"} – ${lead.budget_max ?? "Open"}` : "Not captured"}</dd></div><div><dt>Activities</dt><dd>{lead.activity_count}</dd></div></dl>{lead.requirements && <div className="requirement-copy"><strong>Requirements</strong><p>{lead.requirements}</p></div>}{lead.qualification_notes && <div className="qualification-copy"><strong>Qualification notes</strong><p>{lead.qualification_notes}</p></div>}{lead.lost_reason_name && <div className="lost-copy"><strong>Lost: {lead.lost_reason_name}</strong><p>{lead.lost_notes ?? "No additional notes"}</p></div>}</section>

          {canCreateActivity && <section className="panel activity-composer"><div className="panel-heading"><div><h2>{editingActivityId ? "Edit activity" : "Log activity or follow-up"}</h2><p>Every interaction becomes part of the lead timeline.</p></div></div><form className="activity-form" onSubmit={saveActivity}><div className="field-row"><label className="field"><span>Type</span><select value={activityDraft.activity_type} onChange={(event) => setActivityDraft({ ...activityDraft, activity_type: event.target.value as ActivityType })}><option value="CALL">Call</option><option value="EMAIL">Email</option><option value="MEETING">Meeting</option><option value="FOLLOW_UP">Follow-up</option><option value="NOTE">General activity</option></select></label><label className="field"><span>Occurred at</span><input type="datetime-local" value={activityDraft.occurred_at} onChange={(event) => setActivityDraft({ ...activityDraft, occurred_at: event.target.value })} required /></label></div><label className="field"><span>Subject</span><input value={activityDraft.subject} onChange={(event) => setActivityDraft({ ...activityDraft, subject: event.target.value })} required minLength={2} /></label>{activityDraft.activity_type === "FOLLOW_UP" && <label className="field"><span>Follow-up due</span><input type="datetime-local" value={activityDraft.due_at} onChange={(event) => setActivityDraft({ ...activityDraft, due_at: event.target.value })} required /></label>}<label className="field"><span>Notes</span><textarea rows={3} value={activityDraft.notes} onChange={(event) => setActivityDraft({ ...activityDraft, notes: event.target.value })} /></label><div className="composer-actions">{editingActivityId && <button type="button" className="button button-secondary" onClick={() => { setEditingActivityId(null); setActivityDraft({ ...emptyActivity, occurred_at: localDateTime() }); }}>Cancel edit</button>}<button className="button button-primary" disabled={saving}>{saving ? "Saving..." : editingActivityId ? "Update activity" : "Add activity"}</button></div></form></section>}

          <section className="panel activity-history"><div className="panel-heading"><div><h2>Activities & follow-ups</h2><p>Calls, emails, meetings, and scheduled next steps.</p></div></div><div className="activity-list">{activities.length ? activities.map((item) => <article key={item.id}><span className={`activity-icon type-${item.activity_type.toLowerCase()}`}>{item.activity_type.slice(0, 1)}</span><div><div className="activity-title"><strong>{item.subject}</strong>{item.is_completed && <span className="completed-pill">Completed</span>}</div><p>{item.notes ?? item.outcome ?? "No notes"}</p><small>{item.performed_by_name ?? "System"} · {new Date(item.occurred_at).toLocaleString()}{item.due_at ? ` · Due ${new Date(item.due_at).toLocaleString()}` : ""}</small></div><div className="activity-actions">{item.activity_type === "FOLLOW_UP" && !item.is_completed && canUpdateActivity && <button onClick={() => void completeFollowUp(item)}>Complete</button>}{canUpdateActivity && <button onClick={() => editActivity(item)}>Edit</button>}{canDeleteActivity && <button className="danger-link" onClick={() => void removeActivity(item)}>Delete</button>}</div></article>) : <div className="empty-state compact"><h3>No activity yet</h3><p>Log the first genuine interaction.</p></div>}</div></section>

          <section className="panel notes-panel"><div className="panel-heading"><div><h2>Lead notes</h2><p>Internal context, decisions, and reminders.</p></div></div>{canCreateActivity && <form className="note-composer" onSubmit={addNote}><textarea rows={3} value={noteBody} onChange={(event) => setNoteBody(event.target.value)} placeholder="Write an internal note..." required /><div><label><input type="checkbox" checked={notePinned} onChange={(event) => setNotePinned(event.target.checked)} /> Pin note</label><span className="note-form-actions">{editingNoteId && <button type="button" className="button button-secondary" onClick={() => { setEditingNoteId(null); setNoteBody(""); setNotePinned(false); }}>Cancel</button>}<button className="button button-primary" disabled={saving}>{editingNoteId ? "Update note" : "Add note"}</button></span></div></form>}<div className="note-list">{notes.map((note) => <article key={note.id} className={note.is_pinned ? "pinned" : ""}><div><strong>{note.is_pinned ? "Pinned note" : note.created_by_name ?? "Note"}</strong><p>{note.body}</p><small>{new Date(note.created_at).toLocaleString()}</small></div><span className="note-actions">{canUpdateActivity && <button onClick={() => { setEditingNoteId(note.id); setNoteBody(note.body); setNotePinned(note.is_pinned); }}>Edit</button>}{canDeleteActivity && <button className="danger-link" onClick={() => void removeNote(note)}>Delete</button>}</span></article>)}</div></section>
        </div>

        <aside className="lead-detail-aside">
          <section className="panel action-card"><p className="overline">Lead controls</p><h2>Progress this lead</h2>{canAssign && lead.status !== "CONVERTED" && <label className="field"><span>Owner</span><select value={lead.owner_user_id ?? ""} onChange={(event) => void assign(event.target.value)} disabled={saving}><option value="">Unassigned</option>{assignees.map((user) => <option key={user.id} value={user.id}>{user.full_name}</option>)}</select></label>}{canUpdate && lead.status !== "CONVERTED" && <div className="workflow-block"><strong>Status transition</strong><div className="inline-action"><select value={statusTarget} onChange={(event) => setStatusTarget(event.target.value)}><option value="">Choose status</option>{(["ASSIGNED", "ATTEMPTED", "CONTACTED", "DISQUALIFIED"] as LeadStatus[]).filter((item) => item !== lead.status).map((item) => <option key={item} value={item}>{statusLabels[item]}</option>)}</select><button onClick={() => void changeStatus()} disabled={!statusTarget || saving}>Apply</button></div></div>}{canUpdate && !["QUALIFIED", "CONVERTED", "LOST"].includes(lead.status) && <div className="workflow-block"><strong>Qualification</strong><textarea rows={3} value={qualificationNotes} onChange={(event) => setQualificationNotes(event.target.value)} placeholder="Confirmed budget, need, authority, and timeline..." /><button className="button button-primary" onClick={() => void qualify()} disabled={!qualificationNotes.trim() || saving}>Mark qualified</button></div>}{canUpdate && lead.status !== "CONVERTED" && lead.status !== "LOST" && <div className="workflow-block"><strong>Mark as lost</strong><select value={lostReasonId} onChange={(event) => setLostReasonId(event.target.value)}><option value="">Choose reason</option>{reasons.map((reason) => <option key={reason.id} value={reason.id}>{reason.name}</option>)}</select><textarea rows={2} value={lostNotes} onChange={(event) => setLostNotes(event.target.value)} placeholder="Optional context" /><button className="button button-danger" onClick={() => void markLost()} disabled={!lostReasonId || saving}>Mark lost</button></div>}{canConvert && lead.status === "QUALIFIED" && <div className="conversion-block"><strong>Ready to convert</strong><p>Creates one customer transactionally and locks the lead as converted.</p><button className="button button-primary" onClick={() => void convert()} disabled={saving}>Convert to customer</button></div>}</section>

          <section className="panel score-card"><div className="panel-heading"><div><h2>Lead score</h2><p>Backend-calculated, capped at 100.</p></div><strong>{lead.score}</strong></div><div className="score-bar"><span style={{ width: `${lead.score}%` }} /></div><ul>{scoreItems.length ? scoreItems.map((item, index) => <li key={`${item.label}-${index}`}><span>{item.label}</span><strong>{item.points > 0 ? "+" : ""}{item.points}</strong></li>) : <li><span>No score signals</span><strong>0</strong></li>}</ul></section>

          <section className="panel timeline-panel"><div className="panel-heading"><div><h2>Timeline</h2><p>Audited lead history.</p></div></div><div className="lead-timeline">{timeline.map((item) => <article key={`${item.kind}-${item.id}`}><span className={`timeline-dot kind-${item.kind}`} /><div><strong>{item.title}</strong>{item.detail && <p>{item.detail}</p>}<small>{item.actor_name ?? "System"} · {new Date(item.occurred_at).toLocaleString()}</small></div></article>)}</div></section>
        </aside>
      </div>
    </main>
  </AppShell>;
}
