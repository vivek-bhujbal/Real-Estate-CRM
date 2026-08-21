"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  apiRequest,
  ApiError,
  LeadSource,
  LostReason,
  ScoreRule
} from "@/lib/api";

type Tab = "sources" | "lost-reasons" | "score-rules";
type ConfigItem = LeadSource | LostReason | ScoreRule;
type Draft = {
  name: string; code: string; is_active: boolean; field: string; operator: string;
  comparison_value: string; points: string; priority: string;
};

const emptyDraft: Draft = {
  name: "", code: "", is_active: true, field: "email_present", operator: "present",
  comparison_value: "", points: "10", priority: "100"
};

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Configuration request failed";
}

export function LeadConfiguration({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("sources");
  const [sources, setSources] = useState<LeadSource[]>([]);
  const [reasons, setReasons] = useState<LostReason[]>([]);
  const [rules, setRules] = useState<ScoreRule[]>([]);
  const [editing, setEditing] = useState<ConfigItem | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    void Promise.all([
      apiRequest<LeadSource[]>("/leads/sources"),
      apiRequest<LostReason[]>("/leads/lost-reasons"),
      apiRequest<ScoreRule[]>("/leads/score-rules")
    ]).then(([nextSources, nextReasons, nextRules]) => {
      if (!active) return;
      setSources(nextSources);
      setReasons(nextReasons);
      setRules(nextRules);
    }).catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey]);

  const items: ConfigItem[] = tab === "sources" ? sources : tab === "lost-reasons" ? reasons : rules;

  function startNew() {
    setDraft(emptyDraft);
    setEditing("new");
    setError(null);
  }

  function startEdit(item: ConfigItem) {
    if ("field" in item) {
      setDraft({
        name: item.name, code: "", is_active: item.is_active, field: item.field,
        operator: item.operator, comparison_value: item.comparison_value ?? "",
        points: String(item.points), priority: String(item.priority)
      });
    } else {
      setDraft({ ...emptyDraft, name: item.name, code: item.code, is_active: item.is_active });
    }
    setEditing(item);
    setError(null);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const creating = editing === "new";
      const payload = tab === "score-rules" ? {
        name: draft.name,
        field: draft.field,
        operator: draft.operator,
        comparison_value: draft.operator === "present" ? null : draft.comparison_value,
        points: Number(draft.points),
        priority: Number(draft.priority),
        is_active: draft.is_active
      } : { name: draft.name, code: draft.code, is_active: draft.is_active };
      const editingId = typeof editing === "object" && editing ? editing.id : "";
      const path = creating ? `/leads/${tab}` : `/leads/${tab}/${editingId}`;
      await apiRequest(path, { method: creating ? "POST" : "PUT", body: JSON.stringify(payload) });
      setEditing(null);
      setNotice(creating ? "Configuration created" : "Configuration updated");
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: ConfigItem) {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    setError(null);
    try {
      await apiRequest<void>(`/leads/${tab}/${item.id}`, { method: "DELETE" });
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(message(reason));
    }
  }

  async function recompute() {
    setSaving(true);
    setError(null);
    try {
      const response = await apiRequest<{ updated: number }>("/leads/score-rules/recompute", { method: "POST" });
      setNotice(`${response.updated} lead scores recomputed`);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  }

  return <div className="drawer-layer" role="presentation">
    <button className="drawer-scrim" onClick={onClose} aria-label="Close lead configuration" />
    <aside className="editor-drawer configuration-drawer" aria-label="Lead configuration">
      <div className="drawer-heading"><div><p className="overline">Lead administration</p><h2>Configuration</h2></div><button className="icon-button" onClick={onClose} aria-label="Close">x</button></div>
      <div className="configuration-tabs"><button className={tab === "sources" ? "active" : ""} onClick={() => { setTab("sources"); setEditing(null); }}>Sources</button><button className={tab === "lost-reasons" ? "active" : ""} onClick={() => { setTab("lost-reasons"); setEditing(null); }}>Lost reasons</button><button className={tab === "score-rules" ? "active" : ""} onClick={() => { setTab("score-rules"); setEditing(null); }}>Scoring</button></div>
      {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
      {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
      {!editing && <>
        <div className="config-toolbar"><p>{tab === "score-rules" ? "Custom rules add to the built-in completeness and engagement score." : "No default records are added; maintain only the values your organization uses."}</p><button className="button button-primary" onClick={startNew}>Add</button></div>
        {tab === "score-rules" && <button className="button button-secondary recompute-button" onClick={() => void recompute()} disabled={saving}>Recompute all scores</button>}
        <div className="config-list">{loading ? <div className="center-inline"><span className="spinner" /></div> : items.length ? items.map((item) => <article key={item.id}><div><strong>{item.name}</strong><small>{"field" in item ? `${item.field} ${item.operator} · ${item.points > 0 ? "+" : ""}${item.points} points` : `${item.code} · ${item.lead_count} leads`}</small></div><span className={`state-dot ${item.is_active ? "active" : "inactive"}`} /><button onClick={() => startEdit(item)}>Edit</button><button className="danger-link" onClick={() => void remove(item)}>Delete</button></article>) : <div className="empty-state compact"><h3>No configuration yet</h3><p>Add the first record explicitly.</p></div>}</div>
      </>}
      {editing && <form className="drawer-form config-form" onSubmit={save}>
        <button type="button" className="back-link" onClick={() => setEditing(null)}>Back to list</button>
        <label className="field"><span>Name</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} required minLength={2} maxLength={120} autoFocus /></label>
        {tab !== "score-rules" ? <label className="field"><span>Code</span><input value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value.toUpperCase() })} required minLength={2} maxLength={50} /></label> : <>
          <label className="field"><span>Field</span><select value={draft.field} onChange={(event) => setDraft({ ...draft, field: event.target.value })}><option value="email_present">Email present</option><option value="phone_present">Phone present</option><option value="source_code">Source code</option><option value="budget_min">Minimum budget</option><option value="budget_max">Maximum budget</option><option value="status">Status</option><option value="activity_count">Activity count</option><option value="days_since_created">Days since created</option><option value="assigned">Assigned</option></select></label>
          <label className="field"><span>Operator</span><select value={draft.operator} onChange={(event) => setDraft({ ...draft, operator: event.target.value })}><option value="present">Is present</option><option value="eq">Equals</option><option value="neq">Does not equal</option><option value="gte">Greater than or equal</option><option value="lte">Less than or equal</option><option value="contains">Contains</option></select></label>
          {draft.operator !== "present" && <label className="field"><span>Comparison value</span><input value={draft.comparison_value} onChange={(event) => setDraft({ ...draft, comparison_value: event.target.value })} required /></label>}
          <div className="field-row"><label className="field"><span>Points</span><input type="number" min={-100} max={100} value={draft.points} onChange={(event) => setDraft({ ...draft, points: event.target.value })} required /></label><label className="field"><span>Priority</span><input type="number" min={0} max={10000} value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: event.target.value })} required /></label></div>
        </>}
        <label className="toggle-field"><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} /><span><strong>Active</strong><small>Inactive configuration remains available in history.</small></span></label>
        <div className="drawer-actions"><button type="button" className="button" onClick={() => setEditing(null)}>Cancel</button><button type="submit" className="button button-primary" disabled={saving}>{saving ? "Saving..." : "Save"}</button></div>
      </form>}
    </aside>
  </div>;
}
