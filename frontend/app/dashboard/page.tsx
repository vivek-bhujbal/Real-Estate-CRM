"use client";

import { CSSProperties, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiRequest,
  ApiError,
  DashboardCatalog,
  DashboardChart,
  DashboardKind,
  DashboardMetricFormat,
  DashboardView,
} from "@/lib/api";

function formatValue(value: string, format: DashboardMetricFormat, currency: string | null) {
  const number = Number(value);
  if (format === "PERCENT") {
    return `${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(number)}%`;
  }
  if (format === "CURRENCY" && currency && /^[A-Z]{3}$/.test(currency)) {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(number);
  }
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: format === "CURRENCY" ? 2 : 0,
  }).format(number);
}

function DashboardChartCard({ chart, currency }: { chart: DashboardChart; currency: string | null }) {
  const values = chart.points.map((point) => Number(point.value));
  const maximum = Math.max(...values, 0);
  const hasData = chart.points.length > 0 && values.some((value) => value !== 0);

  return (
    <article className="panel analytics-chart-card">
      <div className="panel-heading">
        <div><h2>{chart.title}</h2><p>{chart.description}</p></div>
        <span className="status-pill">Database</span>
      </div>
      {!hasData ? (
        <div className="dashboard-empty-chart">
          <div className="empty-chart-grid" aria-hidden="true"><i /><i /><i /><i /></div>
          <div className="empty-state compact">
            <span className="empty-icon" aria-hidden="true">0</span>
            <h3>No recorded data</h3>
            <p>{chart.empty_message}</p>
          </div>
        </div>
      ) : (
        <div className="analytics-bars" role="img" aria-label={`${chart.description}. ${chart.points.map((point) => `${point.label}: ${formatValue(point.value, chart.format, currency)}`).join(", ")}`}>
          {chart.points.map((point) => {
            const numericValue = Number(point.value);
            const height = maximum > 0 ? Math.max((numericValue / maximum) * 100, numericValue ? 3 : 0) : 0;
            const style = { "--bar-height": `${height}%` } as CSSProperties;
            return (
              <div className="analytics-bar-column" key={point.label}>
                <div className="analytics-bar-value">
                  <strong>{formatValue(point.value, chart.format, currency)}</strong>
                  {point.total !== null && <small>of {Number(point.total).toLocaleString("en-IN")}</small>}
                </div>
                <div className="analytics-bar-track"><span style={style} /></div>
                <small title={point.label}>{point.label}</small>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

export default function DashboardPage() {
  const { session } = useAuth();
  const [catalog, setCatalog] = useState<DashboardCatalog | null>(null);
  const [selected, setSelected] = useState<DashboardKind | null>(null);
  const [view, setView] = useState<DashboardView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    let active = true;
    void apiRequest<DashboardCatalog>("/dashboard/catalog")
      .then((result) => {
        if (!active) return;
        setCatalog(result);
        setSelected(result.default_dashboard);
        setError(null);
        if (!result.default_dashboard) setLoading(false);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof ApiError ? reason.message : "Dashboard catalog is unavailable");
        setLoading(false);
      });
    return () => { active = false; };
  }, [session]);

  const loadDashboard = useCallback(async (kind: DashboardKind) => {
    setLoading(true);
    try {
      const result = await apiRequest<DashboardView>(`/dashboard/${kind}`);
      setView(result);
      setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Dashboard data is unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selected) return;
    const timer = setTimeout(() => void loadDashboard(selected), 0);
    return () => clearTimeout(timer);
  }, [loadDashboard, selected]);

  if (!session) {
    return <main className="center-page" aria-busy="true"><span className="spinner" /><span>Loading workspace…</span></main>;
  }

  return (
    <AppShell>
      <main className="dashboard-content analytics-dashboard">
        <div className="page-heading analytics-heading">
          <div>
            <p className="overline">Live business intelligence</p>
            <h1>{view?.title ?? `Welcome, ${session.user.full_name.split(" ")[0]}`}</h1>
            <p>{view?.description ?? "Select an authorized dashboard to inspect your organization’s recorded data."}</p>
          </div>
          {selected && <button className="button button-secondary" disabled={loading} onClick={() => void loadDashboard(selected)}>{loading ? "Refreshing…" : "Refresh data"}</button>}
        </div>

        {error && <div className="alert alert-error" role="alert">{error}</div>}

        {catalog && catalog.items.length > 0 && (
          <nav className="dashboard-switcher" aria-label="Dashboard views">
            {catalog.items.map((item) => (
              <button
                className={selected === item.kind ? "active" : ""}
                aria-pressed={selected === item.kind}
                key={item.kind}
                onClick={() => { setView(null); setSelected(item.kind); }}
                title={item.description}
              >
                <span>{item.label}</span><small>{item.kind === catalog.default_dashboard ? "Default" : "View"}</small>
              </button>
            ))}
          </nav>
        )}

        {catalog && catalog.items.length === 0 ? (
          <section className="panel dashboard-no-access">
            <div className="empty-state compact"><span className="empty-icon" aria-hidden="true">—</span><h3>No analytics view assigned</h3><p>Your account is active, but its permissions do not include the underlying records required by any dashboard.</p></div>
          </section>
        ) : loading && !view ? (
          <><section className="analytics-metrics">{Array.from({ length: 5 }, (_, index) => <article key={index}><span className="skeleton" /><span className="skeleton skeleton-number" /><span className="skeleton" /></article>)}</section><section className="analytics-chart-grid"><div className="panel panel-skeleton"><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></div><div className="panel panel-skeleton"><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></div></section></>
        ) : view ? (
          <>
            <section className="analytics-metrics" aria-label={`${view.title} metrics`}>
              {view.metrics.map((metric) => (
                <article key={metric.key}>
                  <div><span>{metric.label}</span><i aria-hidden="true" /></div>
                  <strong>{formatValue(metric.value, metric.format, view.currency)}</strong>
                  <p>{metric.detail}</p>
                </article>
              ))}
            </section>
            <section className="analytics-chart-grid">
              {view.charts.map((chart) => <DashboardChartCard chart={chart} currency={view.currency} key={chart.key} />)}
            </section>
            <footer className="dashboard-provenance">
              <span><i aria-hidden="true" /> Live database calculations</span>
              <p>No seeded or placeholder statistics. Calculated as of {new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(view.as_of))}.</p>
            </footer>
          </>
        ) : null}
      </main>
    </AppShell>
  );
}
