"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  apiRequest,
  ApiError,
  PageResponse,
  permissionGranted,
  RentalLease,
  RentalOptions,
  RentalProperty,
  RentalPropertyStatus,
  RentalStats,
  RentalTenant,
} from "@/lib/api";

type View = "leases" | "properties" | "tenants";
type Dialog = "property" | "tenant" | "lease" | null;
const propertyStatuses: RentalPropertyStatus[] = ["AVAILABLE", "RESERVED", "OCCUPIED", "MAINTENANCE", "INACTIVE"];

function money(amount: string, currency = "INR") {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(amount));
}

export default function RentalsPage() {
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const canManage = permissionGranted(permissions, "leases.create");
  const canManageProperties = permissionGranted(permissions, "properties.create");
  const canManageTenants = permissionGranted(permissions, "tenants.create");
  const [view, setView] = useState<View>("leases");
  const [stats, setStats] = useState<RentalStats | null>(null);
  const [leases, setLeases] = useState<PageResponse<RentalLease> | null>(null);
  const [properties, setProperties] = useState<PageResponse<RentalProperty> | null>(null);
  const [tenants, setTenants] = useState<PageResponse<RentalTenant> | null>(null);
  const [options, setOptions] = useState<RentalOptions | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const base = { page: String(page), page_size: "20" };
    const leaseParams = new URLSearchParams(base);
    const propertyParams = new URLSearchParams(base);
    const tenantParams = new URLSearchParams(base);
    if (query) { leaseParams.set("q", query); propertyParams.set("q", query); tenantParams.set("q", query); }
    if (status && view === "leases") leaseParams.set("status", status);
    if (status && view === "properties") propertyParams.set("status", status);
    try {
      const [totals, leaseRows, propertyRows, tenantRows, optionRows] = await Promise.all([
        apiRequest<RentalStats>("/rentals/stats"),
        apiRequest<PageResponse<RentalLease>>(`/rentals/leases?${leaseParams}`),
        apiRequest<PageResponse<RentalProperty>>(`/rentals/properties?${propertyParams}`),
        canManageTenants ? apiRequest<PageResponse<RentalTenant>>(`/rentals/tenants?${tenantParams}`) : Promise.resolve(null),
        canManage ? apiRequest<RentalOptions>("/rentals/options") : Promise.resolve(null),
      ]);
      setStats(totals); setLeases(leaseRows); setProperties(propertyRows); setTenants(tenantRows); setOptions(optionRows); setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Rental workspace could not be loaded");
    }
  }, [canManage, canManageTenants, page, query, status, view]);

  useEffect(() => { const timer = setTimeout(() => void load(), 0); return () => clearTimeout(timer); }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    try {
      if (dialog === "property") {
        await apiRequest("/rentals/properties", { method: "POST", body: JSON.stringify({
          code: values.code, name: values.name, property_type: values.property_type,
          address_line1: values.address_line1, city: values.city, state: values.state,
          postal_code: values.postal_code, country: values.country,
          bedrooms: values.bedrooms ? Number(values.bedrooms) : null,
          bathrooms: values.bathrooms ? Number(values.bathrooms) : null,
          area_sqft: values.area_sqft || null, amenities: [],
          default_monthly_rent: values.default_monthly_rent,
          default_security_deposit: values.default_security_deposit,
          currency: values.currency, manager_user_id: values.manager_user_id || null,
        }) });
        setNotice("Rental property added. It is independent from sales inventory.");
      } else if (dialog === "tenant") {
        await apiRequest("/rentals/tenants", { method: "POST", body: JSON.stringify({
          full_name: values.full_name, email: values.email || null, phone: values.phone,
          identity_type: values.identity_type || null, identity_reference: values.identity_reference || null,
          address: values.address || null,
        }) });
        setNotice("Tenant profile created");
      } else if (dialog === "lease") {
        await apiRequest("/rentals/leases", { method: "POST", body: JSON.stringify({
          lease_number: values.lease_number, tenant_id: values.tenant_id, property_id: values.property_id,
          start_date: values.start_date, end_date: values.end_date, monthly_rent: values.monthly_rent,
          security_deposit: values.security_deposit, currency: values.currency,
          rent_due_day: Number(values.rent_due_day), notice_period_days: Number(values.notice_period_days),
          terms: values.terms || null,
        }) });
        setNotice("Draft lease created with a required agreement document");
      }
      setDialog(null); setError(null); await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Rental record could not be created");
    } finally { setBusy(false); }
  }

  const rows = view === "leases" ? leases : view === "properties" ? properties : tenants;
  return <AppShell><main className="dashboard-content rental-content">
    <div className="management-heading"><div><p className="overline">Property operations</p><h1>Rental management</h1><p>Tenancies, recurring rent, move workflows, and maintenance—kept separate from sales bookings.</p></div><div className="heading-actions">{canManageProperties && <button className="button button-secondary" onClick={() => setDialog("property")}>Add property</button>}{canManageTenants && <button className="button button-secondary" onClick={() => setDialog("tenant")}>Add tenant</button>}{canManage && <button className="button button-primary" onClick={() => setDialog("lease")}>Create lease</button>}</div></div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    {stats && <section className="rental-metrics"><article><span>Rental properties</span><strong>{stats.total_properties}</strong><small>{stats.available_properties} available</small></article><article><span>Occupied</span><strong>{stats.occupied_properties}</strong><small>{stats.active_leases} active leases</small></article><article><span>Outstanding rent</span><strong>{money(stats.outstanding_rent)}</strong><small>{stats.overdue_invoices} overdue invoices</small></article><article><span>Open maintenance</span><strong>{stats.open_maintenance}</strong><small>Across rental properties</small></article></section>}
    <section className="rental-toolbar"><div className="segmented-control"><button className={view === "leases" ? "active" : ""} onClick={() => { setView("leases"); setPage(1); setStatus(""); }}>Leases</button><button className={view === "properties" ? "active" : ""} onClick={() => { setView("properties"); setPage(1); setStatus(""); }}>Properties</button>{canManageTenants && <button className={view === "tenants" ? "active" : ""} onClick={() => { setView("tenants"); setPage(1); setStatus(""); }}>Tenants</button>}</div><form onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }}><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder={`Search ${view}...`}/><button className="button button-primary">Search</button></form>{view !== "tenants" && <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option>{(view === "properties" ? propertyStatuses : ["DRAFT", "PENDING_SIGNATURE", "MOVE_IN_PENDING", "ACTIVE", "NOTICE_GIVEN", "MOVE_OUT_PENDING", "TERMINATED"]).map((item) => <option key={item}>{item}</option>)}</select>}</section>
    <section className="data-card rental-list">
      {view === "leases" && <div className="rental-table"><div className="rental-row head"><span>Lease / tenant</span><span>Rental property</span><span>Term</span><span>Rent</span><span>Status</span><span /></div>{leases?.items.length ? leases.items.map((item) => <Link href={`/rentals/${item.id}`} className="rental-row" key={item.id}><span><strong>{item.lease_number}</strong><small>{item.tenant_name}</small></span><span><strong>{item.property_name}</strong><small>{item.property_code}</small></span><span><strong>{new Date(item.start_date).toLocaleDateString()}</strong><small>to {new Date(item.end_date).toLocaleDateString()}</small></span><span><strong>{money(item.monthly_rent, item.currency)}</strong><small>{money(item.outstanding, item.currency)} outstanding</small></span><span><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</em></span><span>View →</span></Link>) : <Empty title="No leases yet" text="A lease appears only after a manager creates it for a real tenant and rental property." />}</div>}
      {view === "properties" && <div className="property-grid">{properties?.items.length ? properties.items.map((item) => <article className="rental-property-card" key={item.id}><div><span className="property-code">{item.code}</span><em className={`rental-status status-${item.status.toLowerCase()}`}>{item.status}</em></div><h3>{item.name}</h3><p>{item.property_type} · {item.city}</p><dl><div><dt>Monthly rent</dt><dd>{money(item.default_monthly_rent, item.currency)}</dd></div><div><dt>Deposit</dt><dd>{money(item.default_security_deposit, item.currency)}</dd></div></dl><small>{item.manager_name ?? "Manager not assigned"}</small></article>) : <Empty title="No rental properties" text="Add a rental property without creating a sales project or unit." />}</div>}
      {view === "tenants" && <div className="rental-table tenant-table"><div className="rental-row head"><span>Tenant</span><span>Contact</span><span>Identity</span><span>Active leases</span><span>Outstanding</span></div>{tenants?.items.length ? tenants.items.map((item) => <div className="rental-row" key={item.id}><span><strong>{item.full_name}</strong><small>{item.status}</small></span><span><strong>{item.phone}</strong><small>{item.email ?? "No email"}</small></span><span><strong>{item.identity_type ?? "Not recorded"}</strong><small>{item.identity_reference ?? "—"}</small></span><span><strong>{item.active_leases}</strong></span><span><strong>{money(item.outstanding_rent)}</strong></span></div>) : <Empty title="No tenants" text="Create tenant profiles and optionally link them to tenant portal users." />}</div>}
      <div className="pagination"><button disabled={!rows || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {rows?.page ?? 1} of {Math.max(rows?.pages ?? 0, 1)}</span><button disabled={!rows || page >= rows.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>
    </section>
    {dialog && <div className="modal-backdrop"><form className="modal-card rental-modal" onSubmit={submit}><div className="modal-heading"><div><p className="overline">Rental operations</p><h2>{dialog === "property" ? "Add rental property" : dialog === "tenant" ? "Add tenant" : "Create draft lease"}</h2></div><button type="button" className="icon-button" onClick={() => setDialog(null)}>×</button></div><div className="rental-form-grid">
      {dialog === "property" && <><Field name="code" label="Property code" required/><Field name="name" label="Property name" required/><Field name="property_type" label="Property type" placeholder="Apartment, villa, office" required/><Field name="address_line1" label="Address" required/><Field name="city" label="City" required/><Field name="state" label="State" required/><Field name="postal_code" label="Postal code" required/><Field name="country" label="Country" defaultValue="India" required/><Field name="bedrooms" label="Bedrooms" type="number"/><Field name="bathrooms" label="Bathrooms" type="number"/><Field name="area_sqft" label="Area (sq ft)" type="number"/><Field name="default_monthly_rent" label="Monthly rent" type="number" required/><Field name="default_security_deposit" label="Security deposit" type="number" required/><Field name="currency" label="Currency" defaultValue="INR" required/><label className="field"><span>Property manager</span><select name="manager_user_id"><option value="">Unassigned</option>{options?.managers.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label></>}
      {dialog === "tenant" && <><Field name="full_name" label="Full name" required/><Field name="email" label="Email" type="email"/><Field name="phone" label="Phone" required/><Field name="identity_type" label="Identity type"/><Field name="identity_reference" label="Identity reference"/><label className="field span-two"><span>Address</span><textarea name="address" rows={3}/></label></>}
      {dialog === "lease" && <><Field name="lease_number" label="Lease number" required/><label className="field"><span>Tenant</span><select name="tenant_id" required><option value="">Select tenant</option>{options?.tenants.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></label><label className="field"><span>Rental property</span><select name="property_id" required><option value="">Select available property</option>{options?.properties.map((item) => <option value={item.id} key={item.id}>{item.code} · {item.name}</option>)}</select></label><Field name="start_date" label="Start date" type="date" required/><Field name="end_date" label="End date" type="date" required/><Field name="monthly_rent" label="Monthly rent" type="number" required/><Field name="security_deposit" label="Security deposit" type="number" required/><Field name="currency" label="Currency" defaultValue="INR" required/><Field name="rent_due_day" label="Rent due day" type="number" defaultValue="5" required/><Field name="notice_period_days" label="Notice period (days)" type="number" defaultValue="30" required/><label className="field span-two"><span>Lease terms</span><textarea name="terms" rows={3}/></label></>}
    </div><p className="governance-note">Rental records use a dedicated property and rent ledger. Sales units, bookings, and customer ledgers are never changed by this workflow.</p><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setDialog(null)}>Cancel</button><button disabled={busy} className="button button-primary">{busy ? "Saving…" : "Save"}</button></div></form></div>}
  </main></AppShell>;
}

function Field(props: { name: string; label: string; type?: string; placeholder?: string; defaultValue?: string; required?: boolean }) {
  const { label, ...input } = props;
  return <label className="field"><span>{label}</span><input {...input} /></label>;
}

function Empty({ title, text }: { title: string; text: string }) {
  return <div className="customer-empty"><span>R</span><strong>{title}</strong><p>{text}</p></div>;
}
