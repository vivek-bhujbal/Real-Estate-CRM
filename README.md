# Real Estate CRM & Revenue Management Platform

Production-oriented multi-tenant CRM built as small, verified vertical slices. The repository contains a Next.js frontend, FastAPI API, MySQL persistence, Redis infrastructure, Alembic migrations, and Docker Compose orchestration.

## Current scope: foundation through finance and collections management

- Organization onboarding with an initial administrator (a user-initiated transaction, never seed data)
- Issuer/audience-bound JWT access tokens, rotating refresh families, Argon2id password hashing,
  immediate session revocation, and one-time password recovery
- Organization-scoped users, branches, departments, teams, territories, roles, and permissions
- Backend-enforced tenant boundaries and permission dependencies
- 15 built-in role templates and 272 granular module/action permissions
- Tenant-safe, audited role CRUD and user-role assignment with anti-escalation checks
- Audited organization settings and branch, department, user, team, and territory CRUD with
  validation, search, filters, and server-side pagination
- Complete audited lead lifecycle: sources, allocation, duplicate protection, qualification,
  scoring rules, activities, follow-ups, notes, status transitions, lost reasons, conversion,
  timeline, CSV import validation, kanban, unattended leads, and ageing analysis
- Customer 360 with profile, requirements, lead history, sales journey, documents, payment
  history, outstanding balance, after-sales records, and a consolidated communication timeline
- Audited project, tower/block, floor, and unit CRUD with configurable area, facing, pricing,
  amenities, and structured metadata
- Tenant-safe availability search; approval-aware soft/hard holds with customer, salesperson,
  reason, expiry, release, history and audit trails; locked booking initiation; and
  database-enforced protection against competing holds or duplicate active bookings
- Automatic hold-expiry worker plus idempotent read-time reconciliation so valid holds are never
  exposed as available and overdue holds recover safely if the worker is delayed
- Audited site visit scheduling and salesperson assignment with multiple interested units,
  attendees, check-in/check-out, feedback, outcomes, next follow-up, and calendar views
- Versioned project price lists with unit overrides, floor rise, premiums, parking, amenities,
  charges, taxes, configurable booking amounts, and backend-calculated cost sheets
- Matrix-enforced discount requests with requester/approver separation, eligible user/role checks,
  reasons, previous/final values, decision timestamps, and immutable audit records
- Versioned quotations with lifecycle controls, history, authenticated PDF generation, and
  database-locked revision sequencing
- Private document requests and signature-validated PDF/JPEG/PNG uploads with customer/booking
  links, expiry reconciliation, assigned review, verified/rejected KYC decisions, immutable
  version history, authenticated downloads, and lifecycle audit records
- Transactional booking creation from accepted quotations and approved holds, with verified-KYC
  gates, primary/joint applicants, quote-derived pricing, payment plans, broker and salesperson
  assignment, financing readiness, idempotent payment submission, independent payment verification,
  ordered approvals, cancellation/rejection release, audit trails, and database-level unit uniqueness
- Server-calculated collection accounts with installment ageing, demand letters, partial payments,
  reconciliation evidence, controlled allocation, receipt issuance, append-only customer ledger,
  outstanding/overdue analysis, interest and penalty snapshots, audited waivers, and two-person
  refund approval with allocation and ledger reversal
- Structured errors, request IDs, audit-log schema, health endpoints, and storage abstraction
- API-backed dashboard summary that returns real zero counts for an empty organization
- Responsive authenticated application shell and onboarding/login experiences
- Permission-aware navigation and responsive organization, role, lead, customer, project,
  inventory, site-visit, calendar, pricing, approval, cost-sheet, quotation, document, booking, and collections workspaces

Role and permission rows created during onboarding are technical access metadata. No business seed data, default/demo users, or fabricated statistics are created. Later phases are described in [docs/roadmap.md](docs/roadmap.md).

## Run with Docker

1. Copy `.env.example` to `.env` and replace every secret/password value.
2. Run `docker compose up --build`.
3. Open `http://localhost:3000`; API docs are at `http://localhost:8000/docs` in development.

Database migrations run in the backend container before the API starts. On the first visit, create an organization and administrator through the onboarding screen.

## Local verification

```powershell
cd backend
pip install -e ".[dev]"
ruff check .
mypy app
pytest

cd ../frontend
npm install
npm run lint
npm run typecheck
npm run build
```
