"use client";

import { ChangeEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { LeadNavigation } from "@/components/lead-navigation";
import { apiRequest, ApiError, ImportBatch, ImportPreview } from "@/lib/api";

const supportedHeaders = ["full_name", "email", "phone", "source_code", "owner_email", "preferred_location", "budget_min", "budget_max", "requirements"];

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Import request failed";
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') { current += '"'; index += 1; }
      else quoted = !quoted;
    } else if (character === "," && !quoted) { values.push(current.trim()); current = ""; }
    else current += character;
  }
  values.push(current.trim());
  return values;
}

function parseCsv(text: string): Array<Record<string, string>> {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) throw new Error("CSV must contain a header and at least one data row");
  const headers = parseCsvLine(lines[0]).map((item) => item.trim().toLowerCase());
  if (!headers.includes("full_name")) throw new Error("CSV requires a full_name column");
  if (!headers.includes("email") && !headers.includes("phone")) throw new Error("CSV requires an email or phone column");
  const unsupported = headers.filter((header) => !supportedHeaders.includes(header));
  if (unsupported.length) throw new Error(`Unsupported columns: ${unsupported.join(", ")}`);
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]).filter(([, value]) => value !== ""));
  });
}

export default function LeadImportPage() {
  const [filename, setFilename] = useState("");
  const [rows, setRows] = useState<Array<Record<string, string>>>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    void apiRequest<ImportBatch[]>("/leads/imports")
      .then((data) => { if (active) setBatches(data); })
      .catch((reason: unknown) => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey]);

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null); setNotice(null); setPreview(null);
    try {
      const parsed = parseCsv(await file.text());
      if (parsed.length > 1000) throw new Error("A single import supports up to 1,000 rows");
      setFilename(file.name); setRows(parsed);
    } catch (reason) {
      setFilename(""); setRows([]);
      setError(reason instanceof Error ? reason.message : "Unable to parse CSV");
    }
  }

  async function validate() {
    if (!rows.length) return;
    setProcessing(true); setError(null); setNotice(null);
    try {
      const result = await apiRequest<ImportPreview>("/leads/imports/preview", { method: "POST", body: JSON.stringify({ filename, rows, skip_duplicates: skipDuplicates }) });
      setPreview(result);
    } catch (reason) { setError(message(reason)); } finally { setProcessing(false); }
  }

  async function commit() {
    if (!preview || preview.ready_rows === 0) return;
    setProcessing(true); setError(null); setNotice(null);
    try {
      const batch = await apiRequest<ImportBatch>("/leads/imports", { method: "POST", body: JSON.stringify({ filename, rows, skip_duplicates: skipDuplicates }) });
      setNotice(`${batch.imported_rows} leads imported; ${batch.skipped_rows} duplicates skipped; ${batch.error_rows} rows rejected.`);
      setFilename(""); setRows([]); setPreview(null); setRefreshKey((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setProcessing(false); }
  }

  return <AppShell>
    <main className="dashboard-content lead-content">
      <LeadNavigation />
      <div className="management-heading"><div><p className="overline">Controlled ingestion</p><h1>Import leads</h1><p>Validate CSV rows, contact duplicates, source codes, and owner emails before transactional import.</p></div><span className="organization-badge"><i className="state-dot active" />No automatic defaults</span></div>
      {error && <div className="alert alert-error page-alert" role="alert">{error}</div>}
      {notice && <div className="alert alert-success page-alert" role="status">{notice}</div>}
      <div className="import-layout">
        <section className="panel import-upload"><div className="panel-heading"><div><h2>1. Select CSV</h2><p>Up to 1,000 rows per reviewed batch.</p></div></div><label className="file-drop"><input type="file" accept=".csv,text/csv" onChange={(event) => void chooseFile(event)} /><span className="empty-icon">↑</span><strong>{filename || "Choose a CSV file"}</strong><small>{rows.length ? `${rows.length} data rows parsed` : "File data is processed only when you submit it to the API."}</small></label><div className="csv-contract"><strong>Supported columns</strong><code>{supportedHeaders.join(", ")}</code><p><b>full_name</b> and at least one of <b>email</b> or <b>phone</b> are required. Source codes and owner emails must already exist.</p></div>{rows.length > 0 && <><label className="toggle-field"><input type="checkbox" checked={skipDuplicates} onChange={(event) => setSkipDuplicates(event.target.checked)} /><span><strong>Skip duplicate contacts</strong><small>Recommended: do not import rows matching an existing lead or an earlier file row.</small></span></label><button className="button button-primary full-button" onClick={() => void validate()} disabled={processing}>{processing ? "Validating..." : "Validate rows"}</button></>}</section>
        <section className="panel import-preview"><div className="panel-heading"><div><h2>2. Review validation</h2><p>No leads are created during preview.</p></div></div>{preview ? <><div className="preview-metrics"><article><span>Ready</span><strong>{preview.ready_rows}</strong></article><article><span>Duplicates</span><strong>{preview.duplicate_rows}</strong></article><article><span>Errors</span><strong>{preview.error_rows}</strong></article></div><div className="import-row-results">{preview.rows.slice(0, 100).map((row) => <div key={row.row_number} className={`result-${row.status}`}><strong>Row {row.row_number}</strong><span>{row.status}</span><p>{row.message ?? "Ready to import"}</p></div>)}</div><button className="button button-primary full-button" onClick={() => void commit()} disabled={processing || preview.ready_rows === 0}>{processing ? "Importing..." : `Import ${preview.ready_rows} ready leads`}</button></> : <div className="empty-state compact"><span className="empty-icon">✓</span><h3>Awaiting validation</h3><p>Select a file and validate it to see row-level outcomes.</p></div>}</section>
      </div>
      <section className="panel import-history"><div className="panel-heading"><div><h2>Import history</h2><p>Audited batches retain counts and row-level errors, not raw source files.</p></div></div>{loading ? <div className="center-inline"><span className="spinner" /></div> : batches.length ? <div className="batch-list">{batches.map((batch) => <article key={batch.id}><div><strong>{batch.filename}</strong><small>{new Date(batch.created_at).toLocaleString()}</small></div><span className="status-pill">{batch.status.replaceAll("_", " ")}</span><p>{batch.imported_rows} imported · {batch.skipped_rows} skipped · {batch.error_rows} errors</p></article>)}</div> : <div className="empty-state compact"><h3>No import batches yet</h3><p>History appears only after a real import.</p></div>}</section>
    </main>
  </AppShell>;
}
