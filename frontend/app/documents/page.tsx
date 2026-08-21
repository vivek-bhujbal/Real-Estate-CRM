"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiDownload,
  apiRequest,
  ApiError,
  DocumentOptions,
  DocumentStats,
  DocumentStatus,
  ManagedDocument,
  PageResponse,
  permissionGranted
} from "@/lib/api";

const statuses: DocumentStatus[] = ["PENDING", "UPLOADED", "UNDER_REVIEW", "VERIFIED", "REJECTED", "EXPIRED"];
type ActionKind = "upload" | "version" | "start-review" | "decision";
type Action = { kind: ActionKind; document: ManagedDocument };

function message(reason: unknown) {
  return reason instanceof ApiError ? reason.message : "The document operation could not be completed";
}

function dateTime(value: string | null) {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function bytes(value: number | null) {
  if (value == null) return "Awaiting upload";
  return value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KB` : `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const { session } = useAuth();
  const permissions = useMemo(() => session?.user.permissions ?? [], [session]);
  const canCreate = permissionGranted(permissions, "documents.create");
  const canApprove = permissionGranted(permissions, "documents.approve");
  const [result, setResult] = useState<PageResponse<ManagedDocument> | null>(null);
  const [stats, setStats] = useState<DocumentStats | null>(null);
  const [options, setOptions] = useState<DocumentOptions>({ customers: [], bookings: [], reviewers: [] });
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createDraft, setCreateDraft] = useState({ customer_id: "", booking_id: "", document_type: "", expiry_date: "" });
  const [createFile, setCreateFile] = useState<File | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [actionFile, setActionFile] = useState<File | null>(null);
  const [actionDraft, setActionDraft] = useState({ reviewer_user_id: "", notes: "", decision: "VERIFIED", rejection_reason: "" });
  const [history, setHistory] = useState<{ id: string; items: ManagedDocument[] } | null>(null);

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("customer_id") ?? "";
    const timer = window.setTimeout(() => setCustomerId(value), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!session) return;
    let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    if (documentType) params.set("document_type", documentType);
    if (customerId) params.set("customer_id", customerId);
    void Promise.all([
      apiRequest<PageResponse<ManagedDocument>>(`/documents?${params}`).then((data) => { if (active) setResult(data); }),
      apiRequest<DocumentStats>("/documents/stats").then((data) => { if (active) setStats(data); })
    ]).catch((reason: unknown) => { if (active) setError(message(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [customerId, documentType, page, query, refresh, session, status]);

  useEffect(() => {
    if (!session || (!canCreate && !canApprove)) return;
    let active = true;
    void apiRequest<DocumentOptions>("/documents/options")
      .then((data) => { if (active) setOptions(data); })
      .catch((reason: unknown) => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [canApprove, canCreate, session]);

  function resetFeedback() { setError(null); setNotice(null); }

  async function uploadFile(documentId: string, file: File, version = false) {
    const body = new FormData();
    body.append("file", file);
    return apiRequest<ManagedDocument>(`/documents/${documentId}/${version ? "versions" : "upload"}`, { method: "POST", body });
  }

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true); resetFeedback();
    try {
      const requested = await apiRequest<ManagedDocument>("/documents/requests", {
        method: "POST",
        body: JSON.stringify({ ...createDraft, booking_id: createDraft.booking_id || null, expiry_date: createDraft.expiry_date || null })
      });
      if (createFile) await uploadFile(requested.id, createFile);
      setCreating(false); setCreateFile(null);
      setCreateDraft({ customer_id: "", booking_id: "", document_type: "", expiry_date: "" });
      setNotice(createFile ? "Document uploaded and ready for review" : "Pending document request created");
      setRefresh((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  function openAction(kind: ActionKind, document: ManagedDocument) {
    setActionFile(null);
    setActionDraft({ reviewer_user_id: session?.user.id ?? "", notes: "", decision: "VERIFIED", rejection_reason: "" });
    setAction({ kind, document }); resetFeedback();
  }

  async function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!action) return;
    setSaving(true); resetFeedback();
    try {
      if (action.kind === "upload" || action.kind === "version") {
        if (!actionFile) throw new Error("Select a document file");
        await uploadFile(action.document.id, actionFile, action.kind === "version");
      } else if (action.kind === "start-review") {
        await apiRequest(`/documents/${action.document.id}/review/start`, {
          method: "POST", body: JSON.stringify({ reviewer_user_id: actionDraft.reviewer_user_id || null, notes: actionDraft.notes || null })
        });
      } else {
        await apiRequest(`/documents/${action.document.id}/review`, {
          method: "POST",
          body: JSON.stringify({ status: actionDraft.decision, notes: actionDraft.notes || null, rejection_reason: actionDraft.decision === "REJECTED" ? actionDraft.rejection_reason : null })
        });
      }
      const labels: Record<ActionKind, string> = { upload: "Document uploaded", version: "New version uploaded", "start-review": "Document moved under review", decision: actionDraft.decision === "VERIFIED" ? "Document verified" : "Document rejected" };
      setNotice(labels[action.kind]); setAction(null); setRefresh((value) => value + 1);
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }

  async function download(document: ManagedDocument) {
    try {
      resetFeedback();
      const blob = await apiDownload(`/documents/${document.id}/download`);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url; anchor.download = document.file_name ?? "document"; anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) { setError(message(reason)); }
  }

  async function showHistory(document: ManagedDocument) {
    try {
      if (history?.id === document.id) { setHistory(null); return; }
      const items = await apiRequest<ManagedDocument[]>(`/documents/${document.id}/versions`);
      setHistory({ id: document.id, items });
    } catch (reason) { setError(message(reason)); }
  }

  const filteredBookings = options.bookings.filter((item) => item.customer_id === createDraft.customer_id);
  const actionTitle = action?.kind === "upload" ? "Upload requested document" : action?.kind === "version" ? "Upload new version" : action?.kind === "start-review" ? "Start KYC review" : "Complete KYC review";

  return <AppShell><main className="dashboard-content document-content">
    <div className="management-heading"><div><p className="overline">Private records</p><h1>Document management</h1><p>Secure KYC intake, controlled review, immutable versions, and authenticated downloads.</p></div>{canCreate && <button className="button button-primary" onClick={() => { resetFeedback(); setCreating(true); }}>New document</button>}</div>
    {stats && <section className="document-metrics"><article><span>Current records</span><strong>{stats.total_current}</strong></article><article><span>Awaiting upload</span><strong>{stats.pending}</strong></article><article><span>Ready for review</span><strong>{stats.uploaded}</strong></article><article><span>Under review</span><strong>{stats.under_review}</strong></article><article><span>Verified</span><strong>{stats.verified}</strong></article><article><span>Needs attention</span><strong>{stats.rejected + stats.expired}</strong></article></section>}
    <section className="inventory-filter-panel document-filters"><form className="inventory-search" onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Search customer, booking, type, or file..."/><button className="button button-primary">Search</button></form><div className="inventory-filters"><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All workflow states</option>{statuses.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select><input value={documentType} onChange={(event) => { setDocumentType(event.target.value); setPage(1); }} placeholder="Document type"/><button type="button" onClick={() => { setQuery(""); setQueryInput(""); setStatus(""); setDocumentType(""); setCustomerId(""); setPage(1); }}>Clear</button></div></section>
    {error && <div className="alert alert-error page-alert">{error}</div>}{notice && <div className="alert alert-success page-alert">{notice}</div>}
    <section className="data-card document-table-card"><div className="document-table"><div className="document-row head"><span>Document</span><span>Customer</span><span>Workflow</span><span>Review</span><span>Updated</span><span/></div>{loading ? <div className="center-inline"><span className="spinner"/>Loading secure records...</div> : result?.items.length ? result.items.map((item) => <div key={item.id} className="document-row-wrap"><div className="document-row"><span><strong>{item.document_type.replaceAll("_", " ")}</strong><small>{item.file_name ?? "Upload pending"} · v{item.version} · {bytes(item.size_bytes)}</small></span><span><strong>{item.customer_name}</strong><small>{item.booking_number ? `Booking ${item.booking_number}` : "Customer document"}</small></span><span><em className={`document-status document-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</em><small>{item.expiry_date ? `Expires ${item.expiry_date}` : "No expiry date"}</small></span><span><strong>{item.reviewer_name ?? "Not assigned"}</strong><small>{item.rejection_reason ?? item.review_notes ?? "No review note"}</small></span><span>{dateTime(item.updated_at)}<small>{item.uploaded_by_name ? `Uploaded by ${item.uploaded_by_name}` : "File not received"}</small></span><span className="document-actions">{item.file_name && <button onClick={() => void download(item)}>Download</button>}{item.status === "PENDING" && canCreate && <button onClick={() => openAction("upload", item)}>Upload</button>}{item.status === "UPLOADED" && canApprove && <button onClick={() => openAction("start-review", item)}>Review</button>}{item.status === "UNDER_REVIEW" && canApprove && <button onClick={() => openAction("decision", item)}>Decide</button>}{item.file_name && canCreate && <button onClick={() => openAction("version", item)}>New version</button>}<button onClick={() => void showHistory(item)}>History</button></span></div>{history?.id === item.id && <div className="document-history"><strong>Version history</strong>{history.items.map((version) => <span key={version.id}><b>v{version.version}</b><em className={`document-status document-${version.status.toLowerCase()}`}>{version.status.replaceAll("_", " ")}</em><small>{version.file_name ?? "Pending upload"} · {dateTime(version.updated_at)}</small>{version.file_name && <button onClick={() => void download(version)}>Download</button>}</span>)}</div>}</div>) : <div className="customer-empty"><span>DOC</span><strong>No documents found</strong><p>Create a KYC request when the customer is ready. No files are generated automatically.</p></div>}</div><div className="pagination"><button disabled={!result || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {result?.page ?? 1} of {Math.max(result?.pages ?? 0, 1)}</span><button disabled={!result || page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>

    {creating && <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={submitCreate}><div className="modal-heading"><div><p className="overline">KYC intake</p><h2>New document request</h2></div><button type="button" className="icon-button" onClick={() => setCreating(false)}>×</button></div><div className="customer-edit-scroll form-stack"><label className="field"><span>Customer</span><select required value={createDraft.customer_id} onChange={(event) => setCreateDraft({ ...createDraft, customer_id: event.target.value, booking_id: "" })}><option value="">Select customer</option>{options.customers.map((item) => <option key={item.id} value={item.id}>{item.full_name} · {item.phone ?? item.email ?? "No contact"}</option>)}</select></label><label className="field"><span>Booking (optional)</span><select value={createDraft.booking_id} disabled={!createDraft.customer_id} onChange={(event) => setCreateDraft({ ...createDraft, booking_id: event.target.value })}><option value="">Customer-level document</option>{filteredBookings.map((item) => <option key={item.id} value={item.id}>{item.booking_number} · {item.status.replaceAll("_", " ")}</option>)}</select></label><label className="field"><span>Document type</span><input required minLength={2} maxLength={80} value={createDraft.document_type} onChange={(event) => setCreateDraft({ ...createDraft, document_type: event.target.value })} placeholder="PAN card, passport, address proof..."/></label><label className="field"><span>Expiry date (optional)</span><input type="date" min={new Date().toISOString().slice(0, 10)} value={createDraft.expiry_date} onChange={(event) => setCreateDraft({ ...createDraft, expiry_date: event.target.value })}/></label><label className="field"><span>File (optional)</span><input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => setCreateFile(event.target.files?.[0] ?? null)}/><small>PDF, JPEG, or PNG. Maximum size is controlled by server policy.</small></label></div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setCreating(false)}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? "Saving..." : createFile ? "Create and upload" : "Create pending request"}</button></div></form></div>}

    {action && <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={submitAction}><div className="modal-heading"><div><p className="overline">{action.document.customer_name} · v{action.document.version}</p><h2>{actionTitle}</h2></div><button type="button" className="icon-button" onClick={() => setAction(null)}>×</button></div><div className="customer-edit-scroll form-stack">{(action.kind === "upload" || action.kind === "version") && <label className="field"><span>Secure document file</span><input required type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => setActionFile(event.target.files?.[0] ?? null)}/><small>The server verifies file signatures and stores files under opaque private keys.</small></label>}{action.kind === "start-review" && <><label className="field"><span>Reviewer</span><select required value={actionDraft.reviewer_user_id} onChange={(event) => setActionDraft({ ...actionDraft, reviewer_user_id: event.target.value })}><option value="">Select reviewer</option>{options.reviewers.map((item) => <option key={item.id} value={item.id}>{item.full_name} · {item.email}</option>)}</select></label><label className="field"><span>Review note (optional)</span><textarea rows={3} maxLength={2000} value={actionDraft.notes} onChange={(event) => setActionDraft({ ...actionDraft, notes: event.target.value })}/></label></>}{action.kind === "decision" && <><label className="field"><span>Decision</span><select value={actionDraft.decision} onChange={(event) => setActionDraft({ ...actionDraft, decision: event.target.value })}><option value="VERIFIED">Verified</option><option value="REJECTED">Rejected</option></select></label>{actionDraft.decision === "REJECTED" && <label className="field"><span>Rejection reason</span><textarea required minLength={2} maxLength={1000} rows={3} value={actionDraft.rejection_reason} onChange={(event) => setActionDraft({ ...actionDraft, rejection_reason: event.target.value })}/></label>}<label className="field"><span>Reviewer notes (optional)</span><textarea rows={3} maxLength={2000} value={actionDraft.notes} onChange={(event) => setActionDraft({ ...actionDraft, notes: event.target.value })}/></label></>}</div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setAction(null)}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? "Saving..." : "Confirm"}</button></div></form></div>}
  </main></AppShell>;
}
