"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiDownload,
  apiRequest,
  ApiError,
  permissionGranted,
  ServiceTicketDetail,
  TicketOptions,
  TicketStatus,
} from "@/lib/api";

type Modal = "assign" | "status" | "escalate" | "feedback" | null;

function dateTime(value: string | null) {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function duration(minutes: number | null) {
  if (minutes == null) return "Not configured";
  if (minutes < 0) return `${Math.abs(minutes)}m overdue`;
  if (minutes < 60) return `${minutes}m remaining`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m remaining`;
}

export default function ServiceRequestDetailPage() {
  const id = useParams<{ id: string }>().id;
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const isAgent = permissionGranted(permissions, "service_requests.assign");
  const canManage = permissionGranted(permissions, "service_requests.manage");
  const [detail, setDetail] = useState<ServiceTicketDetail | null>(null);
  const [options, setOptions] = useState<TicketOptions | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [targetStatus, setTargetStatus] = useState<TicketStatus | null>(null);
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ticket, ticketOptions] = await Promise.all([
        apiRequest<ServiceTicketDetail>(`/service-requests/${id}`),
        apiRequest<TicketOptions>("/service-requests/options"),
      ]);
      setDetail(ticket); setOptions(ticketOptions); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Ticket could not be loaded"); }
  }, [id]);
  useEffect(() => { const timer = setTimeout(() => void load(), 0); return () => clearTimeout(timer); }, [load]);

  async function mutate(path: string, body: unknown, message: string) {
    setSaving(true);
    try {
      setDetail(await apiRequest<ServiceTicketDetail>(`/service-requests/${id}${path}`, { method: "POST", body: JSON.stringify(body) }));
      setModal(null); setNotice(message); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Ticket action failed"); }
    finally { setSaving(false); }
  }

  async function addComment(event: FormEvent) {
    event.preventDefault(); if (!comment.trim()) return;
    await mutate("/comments", { body: comment.trim(), is_internal: isAgent && internal }, internal ? "Internal note added" : "Reply sent");
    setComment(""); setInternal(false);
  }

  async function uploadAttachment() {
    if (!attachment) return; const body = new FormData(); body.append("file", attachment); setSaving(true);
    try {
      setDetail(await apiRequest<ServiceTicketDetail>(`/service-requests/${id}/attachments`, { method: "POST", body }));
      setAttachment(null); setNotice("Private attachment uploaded"); setError(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Attachment upload failed"); }
    finally { setSaving(false); }
  }

  async function download(attachmentId: string, filename: string) {
    try { const blob = await apiDownload(`/service-requests/${id}/attachments/${attachmentId}/download`); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Secure download failed"); }
  }

  async function submitModal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    if (modal === "assign") await mutate("/assignment", { assigned_user_id: values.assigned_user_id, notes: values.notes || null }, "Ticket ownership updated");
    if (modal === "escalate") await mutate("/escalations", { to_user_id: values.to_user_id, reason: values.reason }, "Ticket escalated with accountable ownership");
    if (modal === "feedback") await mutate("/feedback", { rating: Number(values.rating), comments: values.comments || null }, "Thank you for your feedback");
    if (modal === "status" && targetStatus) await mutate("/status", { status: targetStatus, notes: values.notes, resolution_summary: targetStatus === "RESOLVED" ? values.resolution_summary : null }, `Ticket moved to ${targetStatus.replaceAll("_", " ").toLowerCase()}`);
  }

  if (!detail) return <AppShell><main className="dashboard-content"><Link href="/service-requests" className="back-link">← Service desk</Link>{error ? <div className="alert alert-error">{error}</div> : <div className="loading-card">Loading service ticket…</div>}</main></AppShell>;
  const ticket = detail.ticket;
  const activeEscalation = detail.escalations.find((item) => item.status !== "RESOLVED");
  const actions: Array<{ label: string; status: TicketStatus; primary?: boolean }> = [];
  if (ticket.status === "ASSIGNED" && isAgent) actions.push({ label: "Start progress", status: "IN_PROGRESS", primary: true });
  if (ticket.status === "IN_PROGRESS" && isAgent) actions.push({ label: "Wait for customer", status: "WAITING_FOR_CUSTOMER" }, { label: "Resolve ticket", status: "RESOLVED", primary: true });
  if (ticket.status === "WAITING_FOR_CUSTOMER" && isAgent) actions.push({ label: "Resume progress", status: "IN_PROGRESS", primary: true }, { label: "Resolve ticket", status: "RESOLVED" });
  if (ticket.status === "RESOLVED") {
    if (isAgent) actions.push({ label: "Reopen", status: "IN_PROGRESS" });
    actions.push({ label: "Confirm closure", status: "CLOSED", primary: true });
  }

  return <AppShell><main className="dashboard-content service-detail">
    <Link href="/service-requests" className="back-link">← Service desk</Link>
    <section className="ticket-hero"><div><div className="ticket-hero-meta"><span>{ticket.request_number}</span><em className={`ticket-priority priority-${ticket.priority.toLowerCase()}`}>{ticket.priority}</em><em className={`ticket-status status-${ticket.status.toLowerCase()}`}>{ticket.status.replaceAll("_", " ")}</em></div><h1>{ticket.subject}</h1><p>{ticket.requester_name} · {ticket.category_name} · Opened {dateTime(ticket.opened_at)}</p></div><div className="ticket-owner"><small>Assigned owner</small><strong>{ticket.assigned_user_name ?? "Unassigned"}</strong><span>{ticket.is_escalated ? "Escalated" : "Standard queue"}</span></div></section>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    <section className="ticket-command-bar"><div>{isAgent && ticket.status !== "CLOSED" && <button className="button button-secondary" onClick={() => setModal("assign")}>{ticket.assigned_user_id ? "Reassign" : "Assign"}</button>}{isAgent && !activeEscalation && !["RESOLVED", "CLOSED"].includes(ticket.status) && <button className="button button-secondary" onClick={() => setModal("escalate")}>Escalate</button>}</div><div>{actions.map((action) => <button key={action.status} className={`button ${action.primary ? "button-primary" : "button-secondary"}`} onClick={() => { setTargetStatus(action.status); setModal("status"); }}>{action.label}</button>)}</div></section>
    <div className="ticket-layout"><div className="ticket-main-column">
      <section className="data-card ticket-section"><div className="section-heading"><div><p className="overline">Customer request</p><h2>Description</h2></div></div><p className="ticket-description">{detail.description}</p>{(detail.project_name || detail.unit_number) && <div className="ticket-context"><span><small>Project</small><strong>{detail.project_name ?? "—"}</strong></span><span><small>Unit</small><strong>{detail.unit_number ?? "—"}</strong></span></div>}{detail.resolution_summary && <div className="resolution-panel"><span>Resolution</span><strong>{detail.resolution_summary}</strong><small>{detail.closure_notes ?? "Awaiting customer closure confirmation"}</small></div>}</section>
      <section className="data-card ticket-section"><div className="section-heading"><div><p className="overline">Conversation</p><h2>Comments & internal notes</h2></div><span>{detail.comments.length} entries</span></div><div className="ticket-conversation">{detail.comments.length ? detail.comments.map((item) => <article className={item.is_internal ? "internal" : ""} key={item.id}><div><span className="comment-avatar">{item.author_name.slice(0, 1)}</span><span><strong>{item.author_name}</strong><small>{dateTime(item.created_at)}</small></span>{item.is_internal && <em>Internal note</em>}</div><p>{item.body}</p></article>) : <p className="empty-inline">No replies yet.</p>}</div>{ticket.status !== "CLOSED" && <form className="ticket-reply" onSubmit={addComment}><textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={4} placeholder={internal ? "Write a private internal note…" : "Write a reply to the requester…"} required/>{isAgent && <label><input type="checkbox" checked={internal} onChange={(event) => setInternal(event.target.checked)}/><span>Internal note — hidden from requester</span></label>}<button disabled={saving || !comment.trim()} className="button button-primary">Send {internal ? "note" : "reply"}</button></form>}</section>
      <section className="data-card ticket-section"><div className="section-heading"><div><p className="overline">Private files</p><h2>Attachments</h2></div></div><div className="ticket-files">{detail.attachments.length ? detail.attachments.map((item) => <article key={item.id}><span className="document-icon">FILE</span><span><strong>{item.file_name}</strong><small>{(item.size_bytes / 1024).toFixed(1)} KB · {item.uploaded_by_name} · {dateTime(item.created_at)}</small></span><button onClick={() => void download(item.id, item.file_name)}>Download</button></article>) : <p className="empty-inline">No attachments uploaded.</p>}</div>{ticket.status !== "CLOSED" && <div className="ticket-upload"><input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => setAttachment(event.target.files?.[0] ?? null)}/><button className="button button-secondary" disabled={!attachment || saving} onClick={() => void uploadAttachment()}>Upload securely</button></div>}</section>
    </div><aside className="ticket-side-column">
      <section className="data-card ticket-section sla-card"><p className="overline">SLA measurement</p><h2>{ticket.sla.configured ? "Policy snapshot" : "Not configured"}</h2><div><span><small>First response</small><strong className={`sla-state state-${ticket.sla.response_state.toLowerCase()}`}>{ticket.sla.response_state.replaceAll("_", " ")}</strong><em>{duration(ticket.sla.response_remaining_minutes)}</em></span><span><small>Resolution</small><strong className={`sla-state state-${ticket.sla.resolution_state.toLowerCase()}`}>{ticket.sla.resolution_state.replaceAll("_", " ")}</strong><em>{duration(ticket.sla.resolution_remaining_minutes)}</em></span><span><small>Escalation deadline</small><strong>{dateTime(ticket.sla.escalation_due_at)}</strong><em>{ticket.sla.escalation_due ? "Escalation due" : "Not due"}</em></span></div><p>Deadlines are stored when the ticket is opened, so later policy changes do not rewrite history.</p></section>
      <section className="data-card ticket-section"><div className="section-heading"><div><p className="overline">Escalations</p><h2>Ownership history</h2></div></div><div className="escalation-list">{detail.escalations.length ? detail.escalations.map((item) => <article key={item.id}><div><em className={`ticket-status status-${item.status.toLowerCase()}`}>{item.status}</em><small>{dateTime(item.escalated_at)}</small></div><strong>{item.from_user_name ?? "Queue"} → {item.to_user_name}</strong><p>{item.reason}</p>{item.status === "OPEN" && (item.to_user_id === session?.user.id || canManage) && <button onClick={() => void mutate(`/escalations/${item.id}`, { action: "ACKNOWLEDGE", notes: "Escalation acknowledged" }, "Escalation acknowledged")}>Acknowledge</button>}{item.status === "ACKNOWLEDGED" && (item.to_user_id === session?.user.id || canManage) && <button onClick={() => void mutate(`/escalations/${item.id}`, { action: "RESOLVE", notes: "Escalation resolved" }, "Escalation resolved")}>Resolve escalation</button>}</article>) : <p className="empty-inline">No escalations.</p>}</div></section>
      {ticket.status === "CLOSED" && <section className="data-card ticket-section feedback-card"><p className="overline">Customer feedback</p>{detail.feedback ? <><div className="feedback-stars">{"★".repeat(detail.feedback.rating)}{"☆".repeat(5 - detail.feedback.rating)}</div><p>{detail.feedback.comments ?? "No written feedback"}</p><small>{detail.feedback.submitted_by_name} · {dateTime(detail.feedback.submitted_at)}</small></> : isAgent ? <p>Awaiting requester feedback.</p> : <><h2>How did we do?</h2><button className="button button-primary" onClick={() => setModal("feedback")}>Rate support</button></>}</section>}
    </aside></div>
    {modal && <div className="modal-backdrop"><form className="modal-card compact-modal" onSubmit={submitModal}><div className="modal-heading"><div><p className="overline">{ticket.request_number}</p><h2>{modal === "assign" ? "Assign ticket" : modal === "escalate" ? "Escalate ticket" : modal === "feedback" ? "Customer feedback" : `${targetStatus?.replaceAll("_", " ")} ticket`}</h2></div><button type="button" className="icon-button" onClick={() => setModal(null)}>×</button></div><div className="form-stack service-action-form">{modal === "assign" && <><label className="field"><span>Service agent</span><select name="assigned_user_id" defaultValue={ticket.assigned_user_id ?? ""} required><option value="">Select agent</option>{options?.agents.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><label className="field"><span>Internal assignment note</span><textarea name="notes" rows={3}/></label></>}{modal === "escalate" && <><label className="field"><span>Escalate to</span><select name="to_user_id" required><option value="">Select accountable owner</option>{options?.agents.filter((item) => item.id !== ticket.assigned_user_id).map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><label className="field"><span>Escalation reason</span><textarea name="reason" rows={4} required minLength={5}/></label></>}{modal === "feedback" && <><label className="field"><span>Rating</span><select name="rating" defaultValue="5"><option value="5">5 — Excellent</option><option value="4">4 — Good</option><option value="3">3 — Average</option><option value="2">2 — Poor</option><option value="1">1 — Very poor</option></select></label><label className="field"><span>Comments</span><textarea name="comments" rows={4}/></label></>}{modal === "status" && <>{targetStatus === "RESOLVED" && <label className="field"><span>Resolution summary</span><textarea name="resolution_summary" rows={4} required minLength={2}/></label>}<label className="field"><span>{targetStatus === "CLOSED" ? "Closure confirmation" : "Workflow note"}</span><textarea name="notes" rows={3} required minLength={2}/></label></>}</div><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setModal(null)}>Cancel</button><button disabled={saving} className="button button-primary">{saving ? "Saving…" : "Confirm"}</button></div></form></div>}
  </main></AppShell>;
}
