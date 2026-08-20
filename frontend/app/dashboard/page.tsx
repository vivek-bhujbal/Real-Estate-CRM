"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { apiRequest, ApiError } from "@/lib/api";

type Summary = { leads: number; projects: number; available_units: number; bookings: number };

const metrics = [
  { key: "leads", label: "Active leads", detail: "Across your sales pipeline" },
  { key: "projects", label: "Projects", detail: "Visible to your workspace" },
  { key: "available_units", label: "Available units", detail: "Ready for matching" },
  { key: "bookings", label: "Bookings", detail: "All booking stages" }
] as const;

export default function DashboardPage() {
  const { session } = useAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    let active = true;
    void apiRequest<Summary>("/dashboard/summary")
      .then((data) => active && setSummary(data))
      .catch((reason) => active && setError(reason instanceof ApiError ? reason.message : "Dashboard data is unavailable"));
    return () => { active = false; };
  }, [session]);

  if (!session) {
    return <main className="center-page" aria-busy="true"><span className="spinner" /><span>Loading workspace…</span></main>;
  }

  return (
    <AppShell>
      <main className="dashboard-content">
        <div className="page-heading">
          <div><p className="overline">Workspace overview</p><h1>Good to see you, {session.user.full_name.split(" ")[0]}</h1><p>Here is the current picture from your organization’s records.</p></div>
          <button className="button button-primary" disabled title="Lead creation arrives in the lead-management phase">Add lead</button>
        </div>

        {error && <div className="alert alert-error" role="alert">{error}</div>}

        <section className="metrics" aria-label="Organization summary">
          {metrics.map((metric) => (
            <article className="metric" key={metric.key}>
              <div className="metric-top"><span>{metric.label}</span><span className="metric-dot" aria-hidden="true" /></div>
              {summary ? <strong>{summary[metric.key].toLocaleString()}</strong> : <span className="skeleton skeleton-number" />}
              <p>{metric.detail}</p>
            </article>
          ))}
        </section>

        <section className="dashboard-grid">
          <article className="panel pipeline-panel">
            <div className="panel-heading"><div><h2>Sales pipeline</h2><p>Lead movement will appear as your team begins working.</p></div><span className="status-pill">Live data</span></div>
            {summary && summary.leads === 0 ? (
              <div className="empty-state compact"><span className="empty-icon" aria-hidden="true">↗</span><h3>No leads yet</h3><p>Add your first lead in the lead-management phase to start tracking qualification and conversion.</p></div>
            ) : !summary ? <div className="panel-skeleton"><span className="skeleton"/><span className="skeleton"/><span className="skeleton"/></div> : null}
          </article>

          <article className="panel activity-panel">
            <div className="panel-heading"><div><h2>Recent activity</h2><p>Important organization events</p></div></div>
            <div className="empty-state compact"><span className="empty-icon" aria-hidden="true">≡</span><h3>No activity yet</h3><p>Audited business actions will be listed here as your team gets started.</p></div>
          </article>
        </section>

        <section className="getting-started">
          <div><p className="overline">Getting started</p><h2>Build your operating foundation</h2><p>Your workspace is clean and ready. Future phases will unlock each setup step without adding sample records.</p></div>
          <ol>
            <li><span>1</span><div><strong>Configure your organization</strong><small>Add branches, departments, and project teams.</small></div><em>Next phase</em></li>
            <li><span>2</span><div><strong>Invite your team</strong><small>Assign explicit roles and data visibility.</small></div><em>Next phase</em></li>
            <li><span>3</span><div><strong>Add projects and inventory</strong><small>Create the units your sales team can offer.</small></div><em>Planned</em></li>
          </ol>
        </section>
      </main>
    </AppShell>
  );
}
