export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type Organization = { id: string; name: string; slug: string };
export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  organization_id: string;
  branch_id: string | null;
  department_id: string | null;
  is_active: boolean;
  created_at: string;
  organization: Organization;
  permissions: string[];
};

export type Session = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: CurrentUser;
};

export type MessageResponse = { message: string };
export type Permission = { id: string; code: string; description: string };
export type Role = {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permission_codes: string[];
  user_count: number;
  created_at: string;
  updated_at: string;
};
export type UserAccess = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role_ids: string[];
  role_names: string[];
};
export type PageResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};
export type DashboardKind = "EXECUTIVE" | "SALES" | "MARKETING" | "INVENTORY" | "COLLECTIONS" | "PARTNER" | "CUSTOMER";
export type DashboardMetricFormat = "NUMBER" | "CURRENCY" | "PERCENT";
export type DashboardCatalogItem = { kind: DashboardKind; label: string; description: string };
export type DashboardCatalog = { items: DashboardCatalogItem[]; default_dashboard: DashboardKind | null };
export type DashboardMetric = { key: string; label: string; value: string; format: DashboardMetricFormat; detail: string };
export type DashboardChartPoint = { label: string; value: string; total: string | null };
export type DashboardChart = { key: string; title: string; description: string; format: DashboardMetricFormat; points: DashboardChartPoint[]; empty_message: string };
export type DashboardView = { kind: DashboardKind; title: string; description: string; currency: string | null; as_of: string; metrics: DashboardMetric[]; charts: DashboardChart[] };
export type OrganizationManagement = {
  id: string;
  name: string;
  slug: string;
  legal_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  timezone: string | null;
  currency: string | null;
  date_format: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};
export type Branch = {
  id: string; name: string; code: string; is_active: boolean;
  department_count: number; user_count: number; created_at: string; updated_at: string;
};
export type Department = {
  id: string; name: string; branch_id: string | null; branch_name: string | null;
  is_active: boolean; user_count: number; created_at: string; updated_at: string;
};
export type ManagedUser = {
  id: string; email: string; full_name: string; branch_id: string | null;
  branch_name: string | null; department_id: string | null; department_name: string | null;
  is_active: boolean; role_names: string[]; created_at: string; updated_at: string;
  last_login_at: string | null;
};
export type Team = {
  id: string; name: string; code: string; description: string | null;
  branch_id: string | null; branch_name: string | null; manager_user_id: string | null;
  manager_name: string | null; member_ids: string[]; member_names: string[];
  is_active: boolean; created_at: string; updated_at: string;
};
export type Territory = {
  id: string; name: string; code: string; description: string | null;
  branch_id: string | null; branch_name: string | null; parent_id: string | null;
  parent_name: string | null; manager_user_id: string | null; manager_name: string | null;
  is_active: boolean; created_at: string; updated_at: string;
};
export type AuditLog = {
  id: string; organization_id: string; organization_name: string;
  actor_user_id: string | null; actor_name: string | null; action: string;
  entity_type: string; entity_id: string; old_value: Record<string, unknown> | null;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null; request_id: string | null;
  ip_address: string | null; user_agent: string | null;
  device_metadata: Record<string, unknown> | null; created_at: string;
};
export type AuditActorOption = { id: string; name: string };
export type AuditFilterOptions = { actions: string[]; entity_types: string[]; actors: AuditActorOption[] };
export type NotificationStatus = "QUEUED" | "SENT" | "DELIVERED" | "FAILED" | "READ";
export type InAppNotification = {
  id: string; event_type: string; title: string; body: string; status: NotificationStatus;
  action_url: string | null; data: Record<string, unknown> | null;
  related_entity_type: string | null; related_entity_id: string | null;
  sent_at: string | null; read_at: string | null; created_at: string;
};
export type NotificationUnreadCount = { unread: number };
export type NotificationMarkAllResult = { marked_read: number };
export type LeadStatus = "NEW" | "ASSIGNED" | "ATTEMPTED" | "CONTACTED" | "QUALIFIED" | "DISQUALIFIED" | "LOST" | "CONVERTED";
export type ActivityType = "CALL" | "EMAIL" | "MEETING" | "NOTE" | "STATUS_CHANGE" | "FOLLOW_UP";
export type Lead = {
  id: string; full_name: string; email: string | null; phone: string | null;
  alternate_phone: string | null; company_name: string | null;
  source_id: string | null; source_name: string | null;
  owner_user_id: string | null; owner_name: string | null;
  branch_id: string | null; branch_name: string | null;
  preferred_location: string | null; requirements: string | null;
  budget_min: string | null; budget_max: string | null; status: LeadStatus;
  score: number; score_breakdown: { base?: Array<{label: string; points: number}>; rules?: Array<{label: string; points: number}>; raw_score?: number } | null;
  qualification_notes: string | null; lost_reason_id: string | null;
  lost_reason_name: string | null; lost_notes: string | null;
  duplicate_of_lead_id: string | null; qualified_at: string | null;
  converted_at: string | null; last_activity_at: string | null;
  next_follow_up_at: string | null; metadata_json: Record<string, unknown> | null;
  activity_count: number; created_at: string; updated_at: string;
};
export type LeadStats = { total: number; active: number; unassigned: number; follow_ups_due: number; converted: number; average_score: number };
export type LeadSource = { id: string; name: string; code: string; is_active: boolean; lead_count: number; created_at: string; updated_at: string };
export type LostReason = LeadSource;
export type LeadAssignee = { id: string; full_name: string; email: string; branch_id: string | null };
export type LeadActivity = {
  id: string; lead_id: string; performed_by_user_id: string | null;
  performed_by_name: string | null; activity_type: ActivityType; subject: string;
  notes: string | null; occurred_at: string; due_at: string | null;
  outcome: string | null; is_completed: boolean; completed_at: string | null;
  created_at: string; updated_at: string;
};
export type LeadNote = { id: string; lead_id: string; created_by_user_id: string | null; created_by_name: string | null; body: string; is_pinned: boolean; created_at: string; updated_at: string };
export type TimelineItem = { id: string; kind: "activity" | "assignment" | "note" | "audit" | "site_visit"; title: string; detail: string | null; actor_name: string | null; occurred_at: string };
export type DuplicateMatch = { lead: Lead; matched_on: Array<"email" | "phone"> };
export type DuplicateGroup = { key: string; matched_on: "email" | "phone"; leads: Lead[] };
export type ScoreRule = { id: string; name: string; field: string; operator: string; comparison_value: string | null; points: number; priority: number; is_active: boolean; created_at: string; updated_at: string };
export type ImportRowResult = { row_number: number; status: "ready" | "duplicate" | "error"; message: string | null; duplicate_lead_ids: string[] };
export type ImportPreview = { total_rows: number; ready_rows: number; duplicate_rows: number; error_rows: number; rows: ImportRowResult[] };
export type ImportBatch = { id: string; filename: string; status: string; total_rows: number; imported_rows: number; skipped_rows: number; error_rows: number; errors: Array<Record<string, unknown>>; completed_at: string | null; created_at: string };
export type AgeingBucket = { label: string; minimum_days: number; maximum_days: number | null; count: number };
export type KanbanColumn = { status: LeadStatus; total: number; items: Lead[] };
export type CustomerStatus = "PROSPECT" | "ACTIVE" | "INACTIVE" | "BLOCKED";
export type Customer = {
  id: string; converted_from_lead_id: string | null; full_name: string;
  email: string | null; phone: string | null; alternate_phone: string | null;
  date_of_birth: string | null; gender: string | null; occupation: string | null;
  company_name: string | null; address_line1: string | null; address_line2: string | null;
  city: string | null; state: string | null; postal_code: string | null; country: string | null;
  preferred_location: string | null; requirements: string | null;
  budget_min: string | null; budget_max: string | null; owner_user_id: string | null;
  owner_name: string | null; branch_id: string | null; branch_name: string | null;
  communication_preferences: Record<string, unknown> | null; status: CustomerStatus;
  activity_count: number; booking_count: number; created_at: string; updated_at: string;
};
export type CustomerStats = { total: number; prospects: number; active: number; inactive: number; blocked: number };
export type CustomerActivity = {
  id: string; activity_type: ActivityType; subject: string; notes: string | null;
  channel: string | null; direction: string | null; performed_by_user_id: string | null;
  performed_by_name: string | null; occurred_at: string; created_at: string; updated_at: string;
};
export type JourneyRecord = { id: string; status: string; source_name: string | null; score: number; created_at: string; converted_at: string | null };
export type CustomerSalesRecord = { id: string; kind: "site_visit" | "quotation" | "booking"; reference: string; status: string; project_name: string | null; unit_number: string | null; amount: string | null; currency: string | null; occurred_at: string; secondary_date: string | null };
export type CustomerDocument = { id: string; document_type: string; file_name: string | null; content_type: string | null; size_bytes: number | null; status: string; version: number; expiry_date: string | null; booking_id: string | null; rejection_reason: string | null; uploaded_by_name: string | null; created_at: string };
export type CustomerPayment = { id: string; booking_number: string | null; amount: string; currency: string; method: string; status: string; reference_number: string | null; paid_at: string | null; created_at: string };
export type CustomerAgreement = { id: string; booking_number: string; agreement_number: string; status: string; issued_at: string | null; signed_at: string | null; registered_at: string | null };
export type CustomerPossession = { id: string; booking_number: string; unit_number: string; status: string; offered_at: string | null; scheduled_at: string | null; completed_at: string | null };
export type CustomerServiceRequest = { id: string; request_number: string; category: string; priority: string; status: string; subject: string; opened_at: string; resolved_at: string | null };
export type CustomerTimelineRecord = { id: string; kind: string; title: string; detail: string | null; status: string | null; occurred_at: string };
export type Customer360 = {
  customer: Customer; available_sections: string[]; lead_history: JourneyRecord[];
  activities: CustomerActivity[]; sales: CustomerSalesRecord[]; documents: CustomerDocument[];
  payments: CustomerPayment[]; financial_summary: { currency: string | null; paid_amount: string; outstanding_amount: string } | null;
  agreements: CustomerAgreement[]; possessions: CustomerPossession[];
  service_requests: CustomerServiceRequest[]; timeline: CustomerTimelineRecord[];
};
export type ProjectStatus = "PLANNING" | "LAUNCHED" | "UNDER_CONSTRUCTION" | "COMPLETED" | "ON_HOLD" | "ARCHIVED";
export type UnitStatus = "AVAILABLE" | "SOFT_HOLD" | "HARD_HOLD" | "BOOKING_INITIATED" | "BOOKED" | "SOLD" | "CANCELLED_RELEASED";
export type Project = {
  id: string; name: string; code: string; description: string | null; project_type: string | null;
  address_line1: string | null; address_line2: string | null; city: string | null;
  state: string | null; postal_code: string | null; country: string | null; rera_number: string | null;
  launch_date: string | null; expected_possession_date: string | null; default_currency: string;
  amenities: string[] | null; configuration: Record<string, unknown> | null; status: ProjectStatus;
  tower_count: number; unit_count: number; available_unit_count: number; created_at: string; updated_at: string;
};
export type Tower = { id: string; project_id: string; name: string; code: string; is_active: boolean; floor_count: number; unit_count: number; created_at: string; updated_at: string };
export type Floor = { id: string; project_id: string; tower_id: string; tower_name: string; name: string; floor_number: number; is_active: boolean; unit_count: number; created_at: string; updated_at: string };
export type Unit = {
  id: string; project_id: string; project_name: string; tower_id: string | null; tower_name: string | null;
  floor_id: string | null; floor_name: string | null; floor_number: number | null; unit_number: string;
  unit_type: string | null; area_sqft: string | null; carpet_area_sqft: string | null;
  built_up_area_sqft: string | null; facing: string | null; bedrooms: number | null;
  bathrooms: number | null; balconies: number | null; status: UnitStatus; base_price: string | null;
  currency: string | null; amenities: string[] | null; price_components: Record<string, unknown> | null;
  configuration: Record<string, unknown> | null; active_hold_id: string | null; created_at: string; updated_at: string;
};
export type InventoryStats = { total: number; available: number; held: number; booking_initiated: number; booked: number; sold: number };
export type HoldStatus = "PENDING_APPROVAL" | "ACTIVE" | "REJECTED" | "RELEASED" | "EXPIRED" | "CONVERTED";
export type HoldType = "SOFT_HOLD" | "HARD_HOLD";
export type UnitHold = {
  id: string; unit_id: string; unit_number: string; project_id: string; project_name: string;
  hold_type: HoldType | null; hold_reason: string | null; customer_id: string | null;
  customer_name: string | null; lead_id: string | null; held_by_user_id: string;
  salesperson_name: string; approved_by_user_id: string | null; approver_name: string | null;
  status: HoldStatus; starts_at: string; expires_at: string; released_at: string | null;
  approved_at: string | null; rejected_at: string | null; approval_notes: string | null;
  release_reason: string | null; created_at: string; updated_at: string;
};
export type HoldStats = { total: number; pending_approval: number; active: number; released: number; expired: number; rejected: number; converted: number };
export type DocumentStatus = "PENDING" | "UPLOADED" | "UNDER_REVIEW" | "VERIFIED" | "REJECTED" | "EXPIRED";
export type ManagedDocument = {
  id: string; document_set_id: string; supersedes_document_id: string | null;
  customer_id: string; customer_name: string; booking_id: string | null; booking_number: string | null;
  document_type: string; version: number; is_current: boolean; file_name: string | null;
  content_type: string | null; size_bytes: number | null; status: DocumentStatus; expiry_date: string | null;
  uploaded_by_user_id: string | null; uploaded_by_name: string | null;
  reviewed_by_user_id: string | null; reviewer_name: string | null;
  rejection_reason: string | null; review_notes: string | null; uploaded_at: string | null;
  review_started_at: string | null; reviewed_at: string | null; created_at: string; updated_at: string;
};
export type DocumentStats = { total_current: number; pending: number; uploaded: number; under_review: number; verified: number; rejected: number; expired: number };
export type DocumentOptions = {
  customers: Array<{ id: string; full_name: string; email: string | null; phone: string | null }>;
  bookings: Array<{ id: string; customer_id: string; booking_number: string; status: string }>;
  reviewers: Array<{ id: string; full_name: string; email: string }>;
};
export type BookingStatus = "DRAFT" | "DOCUMENTATION_PENDING" | "PAYMENT_PENDING" | "SUBMITTED" | "VERIFICATION" | "APPROVAL" | "CONFIRMED" | "REJECTED" | "CANCELLED";
export type FinancingStatus = "NOT_REQUIRED" | "APPLIED" | "UNDER_REVIEW" | "SANCTIONED" | "REJECTED" | "DISBURSED";
export type BookingApplicant = {
  id: string; customer_id: string | null; sequence: number; is_primary: boolean;
  full_name: string; email: string | null; phone: string | null; date_of_birth: string | null;
  tax_identifier: string | null; relationship_to_primary: string | null;
};
export type BookingInstallment = {
  id: string; sequence: number; name: string; due_date: string; amount: string;
  paid_amount: string; status: string;
};
export type BookingPaymentPlan = {
  id: string; name: string; status: string; currency: string; total_amount: string;
  effective_from: string; installments: BookingInstallment[];
};
export type BookingFinancing = {
  id: string; status: FinancingStatus; lender_name: string | null; loan_amount: string | null;
  application_number: string | null; sanction_reference: string | null; notes: string | null;
};
export type BookingPayment = {
  id: string; installment_id: string | null; verified_by_user_id: string | null;
  verifier_name: string | null; amount: string; currency: string; method: string; status: string;
  reference_number: string | null; idempotency_key: string; paid_at: string | null;
  verified_at: string | null; created_at: string;
};
export type BookingApproval = {
  id: string; step_number: number; requested_by_user_id: string; requested_by_name: string | null;
  approver_user_id: string; approver_name: string | null; status: string; comments: string | null;
  decided_at: string | null; created_at: string;
};
export type Booking = {
  id: string; booking_number: string; status: BookingStatus; customer_id: string; customer_name: string;
  lead_id: string | null; quotation_id: string | null; quotation_number: string | null;
  unit_hold_id: string | null; unit_id: string; unit_number: string; project_id: string; project_name: string;
  salesperson_user_id: string | null; salesperson_name: string | null; channel_partner_id: string | null;
  broker_name: string | null; booked_by_user_id: string; booked_by_name: string; agreed_price: string | null;
  discount_amount: string; booking_amount: string; currency: string; paid_amount: string;
  applicants: BookingApplicant[]; payment_plan: BookingPaymentPlan | null; payments: BookingPayment[];
  documents: Array<{ id: string; document_type: string; version: number; status: string; file_name: string | null; expiry_date: string | null }>;
  financing: BookingFinancing | null; approvals: BookingApproval[]; submitted_at: string | null;
  verification_completed_at: string | null; approval_requested_at: string | null; booked_at: string | null;
  rejected_at: string | null; cancelled_at: string | null; rejection_reason: string | null;
  created_at: string; updated_at: string;
};
export type BookingStats = { total: number; documentation_pending: number; payment_pending: number; verification: number; approval: number; confirmed: number; rejected: number; cancelled: number };
export type EligibleBookingQuotation = {
  id: string; quotation_number: string; version: number; customer_id: string; customer_name: string;
  unit_id: string; unit_number: string; agreed_price: string; discount_amount: string;
  booking_amount: string; currency: string; hold_id: string;
};
export type BookingOptions = {
  quotations: EligibleBookingQuotation[];
  salespeople: Array<{ id: string; label: string }>;
  brokers: Array<{ id: string; label: string }>;
  approvers: Array<{ id: string; label: string }>;
};
export type FinanceSummary = { total_receivable: string; received: string; outstanding: string; overdue: string; unapplied_payments: string; pending_reconciliation: number; pending_refunds: number };
export type CollectionAccount = { booking_id: string; booking_number: string; booking_status: string; customer_id: string; customer_name: string; project_name: string; unit_number: string; currency: string; total_value: string; received: string; outstanding: string; overdue: string; next_due_date: string | null };
export type FinanceInstallment = { id: string; sequence: number; name: string; due_date: string; amount: string; paid_amount: string; outstanding: string; status: string };
export type FinanceDemand = { id: string; installment_id: string | null; demand_number: string; status: string; issue_date: string; due_date: string; amount: string; currency: string };
export type FinancePayment = { id: string; amount: string; allocated_amount: string; unallocated_amount: string; currency: string; method: string; status: string; reference_number: string | null; paid_at: string | null; verified_at: string | null; receipt_number: string | null; created_at: string };
export type FinanceReconciliation = { id: string; payment_id: string; status: string; expected_amount: string; received_amount: string; difference_amount: string; external_reference: string | null; notes: string | null; reconciled_at: string };
export type FinanceCharge = { id: string; installment_id: string; charge_type: string; status: string; principal_amount: string; rate_percent: string; days_calculated: number; amount: string; paid_amount: string; currency: string; calculation_date: string; reason: string; waived_reason: string | null };
export type FinanceRefund = { id: string; payment_id: string | null; amount: string; currency: string; status: string; reference_number: string | null; reason: string | null; decision_notes: string | null; requested_by_user_id: string | null; approved_by_user_id: string | null; requested_at: string; processed_at: string | null };
export type FinanceLedgerEntry = { id: string; entry_type: string; amount: string; currency: string; description: string; posted_at: string };
export type CollectionAccountDetail = { account: CollectionAccount; plan_name: string | null; installments: FinanceInstallment[]; demands: FinanceDemand[]; payments: FinancePayment[]; allocations: Array<{ id: string; payment_id: string; installment_id: string | null; demand_letter_id: string | null; amount: string; allocated_at: string; reversed_at: string | null }>; reconciliations: FinanceReconciliation[]; charges: FinanceCharge[]; refunds: FinanceRefund[]; ledger: FinanceLedgerEntry[] };
export type VisitStatus = "SCHEDULED" | "CONFIRMED" | "CHECKED_IN" | "COMPLETED" | "CANCELLED" | "NO_SHOW";
export type InterestedVisitUnit = { id: string; unit_number: string; unit_type: string | null; status: UnitStatus; tower_name: string | null; floor_name: string | null };
export type SiteVisit = {
  id: string; lead_id: string | null; lead_name: string | null;
  customer_id: string | null; customer_name: string | null;
  project_id: string; project_name: string; interested_units: InterestedVisitUnit[];
  assigned_user_id: string | null; assigned_user_name: string | null;
  created_by_user_id: string | null; created_by_user_name: string | null;
  scheduled_at: string; check_in_at: string | null; check_out_at: string | null;
  completed_at: string | null; status: VisitStatus; attendees: string[];
  notes: string | null; feedback: string | null; outcome: string | null;
  next_follow_up_at: string | null; created_at: string; updated_at: string;
};
export type SiteVisitStats = { total: number; upcoming: number; today: number; checked_in: number; completed: number };
export type SalespersonOption = { id: string; full_name: string; email: string };
export type RecordStatus = "DRAFT" | "ACTIVE" | "INACTIVE" | "ARCHIVED";
export type DiscountApprovalLevel = { name: string; minimum_discount_percent: string; maximum_discount_percent: string | null; approver_user_ids: string[]; approver_role_ids: string[] };
export type ApprovalMatrixOptions = { users: Array<{ id: string; name: string }>; roles: Array<{ id: string; name: string }> };
export type CostSheetStatus = "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "CONVERTED" | "VOIDED";
export type QuotationStatus = "DRAFT" | "SENT" | "ACCEPTED" | "REJECTED" | "EXPIRED" | "SUPERSEDED";
export type PricingLineRule = {
  code: string; label: string; calculation: "fixed" | "per_sqft" | "percentage";
  value: string; taxable: boolean; optional: boolean;
  match_field: "unit_type" | "facing" | "tower_id" | "floor_id" | null; match_value: string | null;
};
export type PricingRules = {
  base_rate_per_sqft: string | null;
  optional_premium_codes?: string[];
  unit_overrides: Record<string, { base_price?: string | null; adjustment?: string; label?: string }>;
  floor_rise: { label: string; start_floor: number; amount_per_floor: string | null; rate_per_sqft_per_floor: string | null; taxable: boolean } | null;
  premiums: PricingLineRule[]; parking_options: PricingLineRule[]; amenity_charges: PricingLineRule[];
  charges: PricingLineRule[];
  taxes: Array<{ code: string; label: string; rate_percent: string; applies_to: string[] }>;
  discount_policy: { self_approval_limit_percent: string; maximum_discount_percent: string | null; approval_matrix: DiscountApprovalLevel[] };
  booking_amount: { calculation: "fixed" | "percentage"; value: string } | null;
};
export type PriceList = {
  id: string; project_id: string; project_name: string; name: string; code: string; version: number;
  status: RecordStatus; currency: string; effective_from: string; effective_to: string | null;
  pricing_rules: PricingRules; cost_sheet_count: number; created_at: string; updated_at: string;
};
export type CostSheetItem = {
  id: string | null; sequence: number; category: string; label: string; quantity: string;
  rate: string; amount: string; taxable: boolean; metadata_json: Record<string, unknown> | null;
};
export type DiscountApproval = {
  id: string; status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  requested_by_user_id: string; requested_by_name: string | null; approver_user_id: string | null;
  approver_name: string | null; requested_discount_amount: string; requested_discount_percent: string;
  self_approval_limit_percent: string; request_notes: string | null; decision_notes: string | null;
  approval_level_name: string; required_approver_user_ids: string[]; required_approver_role_ids: string[];
  previous_value: string; final_approved_value: string | null;
  decided_at: string | null; created_at: string;
};
export type CostSheet = {
  id: string | null; customer_id: string; customer_name: string; lead_id: string | null; lead_name: string | null;
  unit_id: string; unit_number: string; project_id: string; project_name: string; price_list_id: string;
  price_list_name: string; price_list_version: number; created_by_user_id: string; created_by_name: string;
  status: CostSheetStatus; currency: string; base_price: string; gross_value: string; discount_amount: string;
  tax_amount: string; final_agreed_value: string; booking_amount: string; pricing_snapshot: Record<string, unknown>;
  items: CostSheetItem[]; approval: DiscountApproval | null; quotation_id: string | null;
  created_at: string | null; updated_at: string | null;
};
export type QuotationItem = {
  id: string; sequence: number; category: string | null; description: string; quantity: string;
  unit_price: string; discount_amount: string; tax_amount: string; total: string;
};
export type QuotationHistory = { id: string; version: number; status: QuotationStatus; total: string; valid_until: string; created_at: string };
export type Quotation = {
  id: string; lead_id: string | null; lead_name: string | null; customer_id: string | null; customer_name: string | null;
  project_id: string; project_name: string; unit_id: string | null; unit_number: string | null;
  cost_sheet_id: string | null; parent_quotation_id: string | null; created_by_user_id: string;
  created_by_name: string; quotation_number: string; version: number; status: QuotationStatus; currency: string;
  subtotal: string; discount_amount: string; tax_amount: string; total: string; final_agreed_value: string | null;
  booking_amount: string | null; pricing_snapshot: Record<string, unknown> | null; valid_until: string;
  issued_at: string | null; items: QuotationItem[]; history: QuotationHistory[]; created_at: string; updated_at: string;
};
export type QuotationStats = { total: number; drafts: number; sent: number; accepted: number; pending_discount_approvals: number };
export type WorkflowStatus = "REQUESTED" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "COMPLETED" | "CANCELLED";
export type RefundSummary = { id: string; status: string; amount: string; reference_number: string | null };
export type Cancellation = {
  id: string; booking_id: string; booking_number: string; customer_id: string; customer_name: string;
  unit_id: string; unit_number: string; status: WorkflowStatus; reason: string; review_notes: string | null;
  decision_notes: string | null; paid_amount_snapshot: string; deduction_amount: string; refund_amount: string;
  currency: string; requested_by_name: string; reviewed_by_name: string | null; approved_by_name: string | null;
  requested_at: string; reviewed_at: string | null; decided_at: string | null; unit_released_at: string | null;
  document_number: string | null; document_generated_at: string | null; refund: RefundSummary | null;
  created_at: string; updated_at: string;
};
export type UnitTransfer = {
  id: string; booking_id: string; booking_number: string; customer_id: string; customer_name: string;
  from_unit_id: string; from_unit_number: string; to_unit_id: string; to_unit_number: string;
  quotation_id: string; quotation_number: string; status: WorkflowStatus; reason: string;
  review_notes: string | null; decision_notes: string | null; old_agreed_price: string; new_agreed_price: string;
  price_difference: string; paid_amount_snapshot: string; currency: string;
  commission_snapshot: Record<string, unknown> | null; requested_by_name: string; reviewed_by_name: string | null;
  approved_by_name: string | null; requested_at: string; reviewed_at: string | null; decided_at: string | null;
  document_number: string | null; document_generated_at: string | null; completed_at: string | null;
  created_at: string; updated_at: string;
};
export type PostSalesStats = { cancellation_requested: number; cancellation_under_review: number; cancellation_approved: number; refunds_processing: number; transfer_requested: number; transfer_under_review: number; transfer_approved: number };
export type PostSalesOptions = {
  bookings: Array<{ id: string; booking_number: string; customer_id: string; customer_name: string; unit_number: string; currency: string; agreed_price: string }>;
  transfer_quotations: Array<{ id: string; quotation_number: string; customer_id: string; unit_id: string; unit_number: string; final_agreed_value: string; currency: string }>;
};
export type PartnerStatus = "PENDING" | "APPLICATION" | "DOCUMENT_VERIFICATION" | "AGREEMENT_PENDING" | "APPROVAL_PENDING" | "APPROVED" | "ACTIVE" | "REJECTED" | "SUSPENDED" | "INACTIVE";
export type PartnerSummary = {
  id: string; code: string; name: string; legal_name: string | null; partner_type: string | null;
  contact_name: string | null; email: string | null; phone: string | null; city: string | null;
  status: PartnerStatus; manager_name: string | null; active_leads: number; confirmed_bookings: number;
  payable_commission: string; currency: string | null; created_at: string; updated_at: string;
};
export type PartnerStats = { total: number; applications: number; verification: number; approval_queue: number; active: number; suspended: number; payable_commission: string };
export type PartnerOptions = { managers: Array<{id: string; label: string}>; territories: Array<{id: string; label: string}>; projects: Array<{id: string; label: string}> };
export type PartnerDocument = { id: string; document_type: string; status: string; file_name: string | null; content_type: string | null; size_bytes: number | null; expiry_date: string | null; rejection_reason: string | null; review_notes: string | null; uploaded_at: string | null; reviewed_at: string | null };
export type PartnerAgreement = { id: string; agreement_number: string; status: string; effective_from: string; effective_until: string | null; commission_percent: string; terms_summary: string | null; file_name: string | null; issued_at: string | null; signed_at: string | null };
export type PartnerCommission = { id: string; booking_id: string; booking_number: string; status: string; rate_percent: string; amount: string; currency: string; commission_payout_id: string | null };
export type PartnerPayout = { id: string; payout_number: string; status: string; amount: string; currency: string; reference_number: string | null; notes: string | null; decision_notes: string | null; requested_at: string; approved_at: string | null; paid_at: string | null; commission_ids: string[] };
export type PartnerDetail = {
  partner: PartnerSummary; registration_number: string | null; registration_date: string | null; website: string | null;
  address: Record<string, string | null>; tax: Record<string, string | null>; bank: Record<string, string | null>;
  lead_protection_days: number; application_notes: string | null; review_notes: string | null; rejection_reason: string | null;
  territory_ids: string[]; project_ids: string[];
  contacts: Array<{id: string; full_name: string; designation: string | null; email: string | null; phone: string | null; is_primary: boolean; is_active: boolean}>;
  documents: PartnerDocument[]; agreements: PartnerAgreement[];
  commission_structures: Array<{id: string; project_id: string | null; project_name: string | null; name: string; rate_percent: string; calculation_basis: string; effective_from: string; effective_until: string | null; is_active: boolean}>;
  leads: Array<{id: string; lead_id: string; lead_name: string; email: string | null; phone: string | null; status: string; registered_at: string; protected_until: string | null; registration_notes: string | null}>;
  commissions: PartnerCommission[]; payouts: PartnerPayout[];
  disputes: Array<{id: string; dispute_number: string; category: string; status: string; description: string; resolution: string | null; related_type: string; related_id: string; assigned_to_name: string | null; raised_at: string; resolved_at: string | null}>;
  lifecycle: Record<string, string | null>;
};

export type PostBookingStage = "AGREEMENT_PENDING" | "CONSTRUCTION" | "POSSESSION_READINESS" | "FINAL_DEMAND" | "FINAL_PAYMENT" | "NO_DUES" | "SNAGGING" | "POSSESSION" | "HANDOVER" | "COMPLETED";
export type LifecycleReadiness = {
  ready: boolean; financially_ready: boolean; documents_ready: boolean; outstanding_amount: string;
  currency: string; active_override_id: string | null;
  conditions: Array<{ code: string; label: string; complete: boolean; blocking: boolean; detail: string | null }>;
};
export type PropertyLifecycleSummary = {
  id: string; booking_id: string; booking_number: string; customer_name: string; project_name: string;
  unit_number: string; stage: PostBookingStage; readiness: LifecycleReadiness; updated_at: string;
};
export type PropertyLifecycleStats = { total: number; readiness_blocked: number; ready_for_possession: number; possession_scheduled: number; handed_over: number };
export type PropertyLifecycleDetail = {
  case: PropertyLifecycleSummary;
  agreement: null | { id: string; agreement_number: string; status: string; registration_number: string | null; file_name: string | null; issued_at: string | null; signed_at: string | null; registered_at: string | null; notes: string | null };
  construction_updates: Array<{ id: string; project_id: string; tower_id: string | null; title: string; description: string; progress_percent: string; status: string; update_date: string; published_at: string | null }>;
  final_demand: null | { id: string; demand_number: string; issue_date: string; due_date: string; amount: string; currency: string; status: string };
  no_dues: null | { id: string; certificate_number: string; issued_at: string; financial_snapshot: Record<string, unknown> };
  snags: Array<{ id: string; area: string; description: string; severity: string; status: string; resolution_notes: string | null; reported_at: string; resolved_at: string | null; accepted_at: string | null }>;
  overrides: Array<{ id: string; status: WorkflowStatus; reason: string; missing_conditions: string[]; requested_by_name: string; decided_by_name: string | null; decision_notes: string | null; requested_at: string; decided_at: string | null }>;
  possession: null | { id: string; status: string; offered_at: string | null; scheduled_at: string | null; completed_at: string | null; readiness_override_id: string | null; notes: string | null };
  handover: null | { id: string; status: WorkflowStatus; handover_at: string | null; notes: string | null; customer_acknowledgement_name: string | null; customer_acknowledgement_notes: string | null; customer_acknowledged_at: string | null; documents: Array<{ id: string; document_type: string; is_required: boolean; file_name: string | null; uploaded_at: string | null }> };
};
export type PropertyLifecycleOption = { id: string; booking_number: string; customer_name: string; project_name: string; unit_number: string };

export type RentalPropertyStatus = "AVAILABLE" | "RESERVED" | "OCCUPIED" | "MAINTENANCE" | "INACTIVE";
export type RentalProperty = {
  id: string; code: string; name: string; property_type: string; address: string; city: string;
  bedrooms: number | null; bathrooms: number | null; area_sqft: string | null; amenities: string[];
  default_monthly_rent: string; default_security_deposit: string; currency: string;
  status: RentalPropertyStatus; manager_user_id: string | null; manager_name: string | null;
  active_lease_id: string | null; created_at: string; updated_at: string;
};
export type RentalTenant = {
  id: string; user_id: string | null; full_name: string; email: string | null; phone: string | null;
  alternate_phone: string | null; identity_type: string | null; identity_reference: string | null;
  address: string | null; emergency_contact_name: string | null; emergency_contact_phone: string | null;
  status: string; active_leases: number; outstanding_rent: string; created_at: string; updated_at: string;
};
export type LeaseStatus = "DRAFT" | "PENDING_SIGNATURE" | "SIGNED" | "MOVE_IN_PENDING" | "ACTIVE" | "NOTICE_GIVEN" | "MOVE_OUT_PENDING" | "EXPIRED" | "TERMINATED" | "RENEWED";
export type RentalLease = {
  id: string; lease_number: string; status: LeaseStatus; tenant_id: string; tenant_name: string;
  property_id: string; property_name: string; property_code: string; start_date: string; end_date: string;
  monthly_rent: string; currency: string; outstanding: string; overdue_invoices: number; updated_at: string;
};
export type RentalDocument = { id: string; document_type: string; version: number; is_required: boolean; status: DocumentStatus; file_name: string | null; rejection_reason: string | null; uploaded_at: string | null; reviewed_at: string | null };
export type RentScheduleItem = { id: string; sequence: number; period_start: string; period_end: string; due_date: string; amount: string; currency: string; status: string };
export type RentalInvoice = { id: string; rent_schedule_item_id: string | null; invoice_number: string; status: string; period_start: string; period_end: string; issue_date: string; due_date: string; amount: string; tax_amount: string; total: string; paid_amount: string; outstanding: string; currency: string };
export type RentPayment = { id: string; rental_invoice_id: string; status: string; amount: string; currency: string; method: string; reference_number: string | null; paid_at: string | null; verified_at: string | null; rejection_reason: string | null };
export type LeaseRenewal = { id: string; status: WorkflowStatus; previous_end_date: string; proposed_end_date: string; previous_monthly_rent: string; proposed_monthly_rent: string; reason: string; decision_notes: string | null; requested_at: string; decided_at: string | null; applied_at: string | null };
export type LeaseMove = { id: string; move_type: "MOVE_IN" | "MOVE_OUT"; status: WorkflowStatus; scheduled_at: string; checklist: Record<string, unknown> | null; meter_readings: Record<string, unknown> | null; notes: string | null; requested_at: string; approved_at: string | null; completed_at: string | null };
export type RentalMaintenance = { id: string; lease_id: string | null; rental_property_id: string | null; title: string; description: string | null; status: string; assigned_user_id: string | null; scheduled_at: string | null; completed_at: string | null; cost: string | null; currency: string | null; created_at: string };
export type RentalLeaseDetail = {
  lease: RentalLease; security_deposit: string; rent_due_day: number; notice_period_days: number;
  terms: string | null; documents: RentalDocument[]; schedule: RentScheduleItem[];
  invoices: RentalInvoice[]; payments: RentPayment[]; renewals: LeaseRenewal[];
  moves: LeaseMove[]; maintenance: RentalMaintenance[];
};
export type RentalStats = { total_properties: number; available_properties: number; occupied_properties: number; active_leases: number; overdue_invoices: number; outstanding_rent: string; open_maintenance: number };
export type RentalOptions = { properties: RentalProperty[]; tenants: RentalTenant[]; managers: Array<{id: string; label: string}> };

export type ServicePriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type TicketStatus = "OPEN" | "ASSIGNED" | "IN_PROGRESS" | "WAITING_FOR_CUSTOMER" | "RESOLVED" | "CLOSED";
export type ServiceCategory = { id: string; code: string; name: string; description: string | null; is_active: boolean; policy_count: number; ticket_count: number; created_at: string; updated_at: string };
export type ServiceSLAPolicy = { id: string; category_id: string; category_name: string; priority: ServicePriority; first_response_minutes: number; escalation_minutes: number; resolution_minutes: number; is_active: boolean; created_at: string; updated_at: string };
export type TicketSLA = { configured: boolean; response_state: "NOT_CONFIGURED" | "ON_TRACK" | "MET" | "BREACHED"; resolution_state: "NOT_CONFIGURED" | "ON_TRACK" | "MET" | "BREACHED"; response_due_at: string | null; resolution_due_at: string | null; escalation_due_at: string | null; first_responded_at: string | null; response_remaining_minutes: number | null; resolution_remaining_minutes: number | null; escalation_due: boolean };
export type ServiceTicket = { id: string; request_number: string; subject: string; category_id: string | null; category_name: string; priority: ServicePriority; status: TicketStatus; requester_name: string; requester_type: string; assigned_user_id: string | null; assigned_user_name: string | null; is_escalated: boolean; sla: TicketSLA; opened_at: string; updated_at: string; resolved_at: string | null; closed_at: string | null };
export type TicketComment = { id: string; author_user_id: string; author_name: string; body: string; is_internal: boolean; created_at: string };
export type TicketAttachment = { id: string; comment_id: string | null; file_name: string; content_type: string; size_bytes: number; uploaded_by_name: string; created_at: string };
export type TicketEscalation = { id: string; status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED"; from_user_name: string | null; to_user_id: string; to_user_name: string; escalated_by_name: string | null; acknowledged_by_name: string | null; reason: string; escalated_at: string; acknowledged_at: string | null; resolved_at: string | null };
export type TicketFeedback = { id: string; rating: number; comments: string | null; submitted_by_name: string; submitted_at: string };
export type ServiceTicketDetail = { ticket: ServiceTicket; description: string; customer_id: string | null; tenant_id: string | null; project_id: string | null; project_name: string | null; unit_id: string | null; unit_number: string | null; resolution_summary: string | null; closure_notes: string | null; comments: TicketComment[]; attachments: TicketAttachment[]; escalations: TicketEscalation[]; feedback: TicketFeedback | null };
export type TicketStats = { total_open: number; unassigned: number; in_progress: number; waiting_for_customer: number; resolved: number; sla_breached: number; escalated: number; average_feedback: number | null };
export type TicketOptions = { categories: ServiceCategory[]; agents: Array<{id: string; label: string}>; customers: Array<{id: string; label: string; secondary: string | null}>; tenants: Array<{id: string; label: string; secondary: string | null}>; projects: Array<{id: string; label: string}>; units: Array<{id: string; label: string; project_id: string}> };

export function permissionGranted(granted: string[], required: string): boolean {
  if (granted.includes(required)) return true;
  const separator = required.indexOf(".");
  if (separator < 1) return false;
  return granted.includes(`${required.slice(0, separator)}.manage`);
}

type ApiErrorBody = { error?: { code?: string; message?: string; request_id?: string } };
type SessionListener = (session: Session | null) => void;
type RequestOptions = { authenticated?: boolean; retryAuthentication?: boolean };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly requestId?: string
  ) {
    super(message);
  }
}

let activeSession: Session | null = null;
let refreshPromise: Promise<Session> | null = null;
const sessionListeners = new Set<SessionListener>();

export function setApiSession(session: Session | null): void {
  activeSession = session;
  for (const listener of sessionListeners) listener(session);
}

export function subscribeToApiSession(listener: SessionListener): () => void {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

export async function refreshSession(): Promise<Session> {
  if (!refreshPromise) {
    refreshPromise = requestOnce<Session>("/auth/refresh", { method: "POST" })
      .then((session) => {
        setApiSession(session);
        return session;
      })
      .catch((reason: unknown) => {
        setApiSession(null);
        throw reason;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {}
): Promise<T> {
  const authenticated = options.authenticated ?? true;
  const retryAuthentication = options.retryAuthentication ?? true;
  const headers = new Headers(init.headers);
  if (authenticated && activeSession) {
    headers.set("Authorization", `Bearer ${activeSession.access_token}`);
  }

  try {
    return await requestOnce<T>(path, { ...init, headers });
  } catch (reason) {
    const canRefresh =
      reason instanceof ApiError &&
      reason.status === 401 &&
      authenticated &&
      retryAuthentication &&
      activeSession !== null &&
      path !== "/auth/refresh";
    if (!canRefresh) throw reason;

    const restored = await refreshSession();
    headers.set("Authorization", `Bearer ${restored.access_token}`);
    return requestOnce<T>(path, { ...init, headers });
  }
}

export async function apiDownload(path: string): Promise<Blob> {
  const perform = async (token: string | null): Promise<Response> => fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}, credentials: "include", cache: "no-store"
  });
  let response = await perform(activeSession?.access_token ?? null);
  if (response.status === 401 && activeSession) {
    const restored = await refreshSession();
    response = await perform(restored.access_token);
  }
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try { body = (await response.json()) as ApiErrorBody; } catch { /* Safe generic error below. */ }
    throw new ApiError(body.error?.message ?? "The download could not be completed", response.status, body.error?.code, body.error?.request_id);
  }
  return response.blob();
}

async function requestOnce<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  headers.set("Accept", "application/json");

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Invalid/non-JSON upstream responses use a safe generic message.
    }
    throw new ApiError(
      body.error?.message ?? "The request could not be completed",
      response.status,
      body.error?.code,
      body.error?.request_id
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
