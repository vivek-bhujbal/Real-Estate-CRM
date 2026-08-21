"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { LeadNavigation } from "@/components/lead-navigation";
import { apiRequest, ApiError, KanbanColumn, LeadStatus, permissionGranted } from "@/lib/api";

const statusLabels: Record<LeadStatus, string> = {
  NEW: "New", ASSIGNED: "Assigned", ATTEMPTED: "Attempted", CONTACTED: "Contacted",
  QUALIFIED: "Qualified", DISQUALIFIED: "Disqualified", LOST: "Lost", CONVERTED: "Converted"
};
const directStatuses = new Set<LeadStatus>(["ASSIGNED", "ATTEMPTED", "CONTACTED", "DISQUALIFIED"]);

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Kanban data is unavailable";
}

export default function LeadKanbanPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const [columns, setColumns] = useState<KanbanColumn[]>([]);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const canUpdate = permissionGranted(permissions, "leads.update");
  const canCreate = permissionGranted(permissions, "leads.create");

  useEffect(() => {
    if (!session) return;
    let active = true;
    void apiRequest<KanbanColumn[]>("/leads/kanban")
      .then((data) => { if (active) setColumns(data); })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey, session]);

  async function moveLead(status: LeadStatus) {
    if (!draggedId || !canUpdate) return;
    if (!directStatuses.has(status)) {
      setError("Qualification, lost, and conversion require their controlled workflow on the lead profile.");
      setDraggedId(null);
      return;
    }
    setError(null);
    try {
      await apiRequest(`/leads/${draggedId}/status`, { method: "POST", body: JSON.stringify({ status }) });
      setLoading(true);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setDraggedId(null);
    }
  }

  return <AppShell>
    <main className="dashboard-content lead-content kanban-content">
      <LeadNavigation />
      <div className="management-heading"><div><p className="overline">Pipeline board</p><h1>Lead kanban</h1><p>Move leads through ordinary contact stages; controlled outcomes stay on the lead profile.</p></div>{canCreate && <Link className="button button-primary" href="/leads/create">Create lead</Link>}</div>
      {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
      {loading ? <div className="center-inline"><span className="spinner" /><span>Loading pipeline...</span></div> : <div className="kanban-board">
        {columns.map((column) => <section key={column.status} className={`kanban-column column-${column.status.toLowerCase()}`} onDragOver={(event) => event.preventDefault()} onDrop={() => void moveLead(column.status)}>
          <header><span className={`state-dot status-dot-${column.status.toLowerCase()}`} /><h2>{statusLabels[column.status]}</h2><strong>{column.total}</strong></header>
          <div className="kanban-stack">{column.items.map((lead) => <article key={lead.id} draggable={canUpdate && lead.status !== "CONVERTED"} onDragStart={() => setDraggedId(lead.id)} onDragEnd={() => setDraggedId(null)} className={draggedId === lead.id ? "dragging" : ""}><div className="kanban-card-top"><span>{lead.source_name ?? "Direct"}</span><span className="score-mini">{lead.score}</span></div><Link href={`/leads/${lead.id}`}>{lead.full_name}</Link><p>{lead.phone ?? lead.email ?? "No contact"}</p><footer><span>{lead.owner_name ?? "Unassigned"}</span><small>{new Date(lead.created_at).toLocaleDateString()}</small></footer></article>)}{column.items.length === 0 && <div className="kanban-empty">No leads</div>}</div>
        </section>)}
      </div>}
    </main>
  </AppShell>;
}
