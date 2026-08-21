"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { QuotationNavigation } from "@/components/quotation-navigation";
import { apiRequest, ApiError, CostSheet, PageResponse } from "@/lib/api";

const money = (amount: string, currency: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(amount));

export default function DiscountApprovalQueuePage() {
  const { session } = useAuth(); const [result, setResult] = useState<PageResponse<CostSheet> | null>(null); const [page, setPage] = useState(1); const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!session) return; let active = true; void apiRequest<PageResponse<CostSheet>>(`/cost-sheets?status=PENDING_APPROVAL&page=${page}&page_size=20`).then((data) => { if (active) setResult(data); }).catch((reason: unknown) => { if (active) setError(reason instanceof ApiError ? reason.message : "Approval queue is unavailable"); }); return () => { active = false; }; }, [page, session]);
  return <AppShell><main className="dashboard-content quote-content"><div className="management-heading"><div><p className="overline">Controlled discounts</p><h1>Approval queue</h1><p>Only matrix-eligible approvers can decide a request; requester self-approval is blocked.</p></div></div><QuotationNavigation />{error && <div className="alert alert-error page-alert">{error}</div>}<section className="data-card"><div className="quote-table approval-table"><div className="quote-row head"><span>Requester</span><span>Customer & unit</span><span>Previous value</span><span>Discount</span><span>Requested final</span><span>Approval level</span></div>{result?.items.length ? result.items.map((sheet) => <Link className="quote-row" href={`/cost-sheets/${sheet.id}`} key={sheet.id}><span><strong>{sheet.approval?.requested_by_name}</strong><small>{sheet.approval?.created_at ? new Date(sheet.approval.created_at).toLocaleString("en-IN") : "—"}</small></span><span><strong>{sheet.customer_name}</strong><small>{sheet.project_name} · {sheet.unit_number}</small></span><span>{money(sheet.approval?.previous_value ?? sheet.gross_value, sheet.currency)}</span><span><strong>{money(sheet.discount_amount, sheet.currency)}</strong><small>{sheet.approval?.requested_discount_percent}%</small></span><span>{money(sheet.final_agreed_value, sheet.currency)}</span><span><strong>{sheet.approval?.approval_level_name}</strong><small>Reason: {sheet.approval?.request_notes}</small></span></Link>) : <div className="empty-state"><strong>No approvals pending</strong><p>New requests appear here only when they exceed their configured self-approval limit.</p></div>}</div>{result && result.pages > 1 && <div className="pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {page} of {result.pages}</span><button disabled={page >= result.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>}</section></main></AppShell>;
}
