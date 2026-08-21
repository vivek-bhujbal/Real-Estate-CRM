"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { LeadNavigation } from "@/components/lead-navigation";
import { apiRequest, ApiError, DuplicateGroup, permissionGranted } from "@/lib/api";

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Duplicate review is unavailable";
}

export default function LeadDuplicatesPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [primaryByGroup, setPrimaryByGroup] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const canResolve = permissionGranted(permissions, "leads.approve");

  useEffect(() => {
    if (!session) return;
    let active = true;
    void apiRequest<DuplicateGroup[]>("/leads/duplicates")
      .then((data) => {
        if (!active) return;
        setGroups(data);
        setPrimaryByGroup(Object.fromEntries(data.map((group) => [group.key, group.leads[0]?.id ?? ""])));
      })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey, session]);

  async function resolve(group: DuplicateGroup) {
    const primary = primaryByGroup[group.key];
    if (!primary || !canResolve) return;
    setResolving(group.key); setError(null); setNotice(null);
    try {
      await apiRequest<void>("/leads/duplicates/resolve", { method: "POST", body: JSON.stringify({ primary_lead_id: primary, duplicate_lead_ids: group.leads.filter((lead) => lead.id !== primary).map((lead) => lead.id) }) });
      setNotice("Duplicate records linked to the selected primary lead");
      setRefreshKey((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setResolving(null); }
  }

  return <AppShell>
    <main className="dashboard-content lead-content">
      <LeadNavigation />
      <div className="management-heading"><div><p className="overline">Data quality</p><h1>Duplicate leads</h1><p>Potential matches use tenant-normalized email and phone values. Resolution links records without destructive merging.</p></div><span className="organization-badge"><i className={`state-dot ${groups.length ? "inactive" : "active"}`} />{groups.length} groups</span></div>
      {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
      {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
      {loading ? <div className="center-inline"><span className="spinner" /></div> : groups.length ? <div className="duplicate-groups">{groups.map((group) => <section className="panel duplicate-group" key={`${group.matched_on}-${group.key}`}><header><div><span className="match-label">Matched {group.matched_on}</span><h2>{group.key}</h2></div><strong>{group.leads.length} records</strong></header><div className="duplicate-records">{group.leads.map((lead) => <label key={lead.id} className={primaryByGroup[group.key] === lead.id ? "selected" : ""}><input type="radio" name={group.key} value={lead.id} checked={primaryByGroup[group.key] === lead.id} onChange={() => setPrimaryByGroup((current) => ({ ...current, [group.key]: lead.id }))} disabled={!canResolve} /><span className="lead-avatar small">{lead.full_name.slice(0, 1)}</span><span><strong>{lead.full_name}</strong><small>{lead.email ?? lead.phone} · {lead.status} · Score {lead.score}</small><em>Created {new Date(lead.created_at).toLocaleDateString()}</em></span><Link href={`/leads/${lead.id}`}>Review</Link></label>)}</div>{canResolve ? <footer><p>The selected primary stays in active lists. Other records remain auditable and are linked as duplicates.</p><button className="button button-primary" onClick={() => void resolve(group)} disabled={resolving === group.key}>{resolving === group.key ? "Resolving..." : "Resolve group"}</button></footer> : <footer><p>Lead approval permission is required to resolve a group.</p></footer>}</section>)}</div> : <div className="panel empty-state duplicate-empty"><span className="empty-icon">✓</span><h3>No unresolved duplicates</h3><p>New leads are still checked at creation and import time.</p></div>}
    </main>
  </AppShell>;
}
