# Production Readiness Audit

Audit date: 2026-08-22  
Release assessment: **CONDITIONAL — application checks pass; external deployment gates pending**

The codebase passes its local production build, static analysis, application startup, API,
authorization, validation, transaction, and workflow tests. It must not be promoted until the
same Alembic chain and Compose stack are smoke-tested against an isolated MySQL/Redis environment
with production environment variables, because this workstation has no running Docker engine and
the existing local MySQL service is not available with project credentials.

## Executive status

| Area | Status | Evidence |
|---|---|---|
| Frontend build | Pass | Next.js production build generated 47 nonce-CSP-compatible dynamic routes |
| TypeScript | Pass | `tsc --noEmit` |
| Frontend lint | Pass | ESLint |
| Frontend tests | Pass | 7 files / 14 component tests; 10 Playwright desktop/mobile tests |
| Responsive baseline | Pass, code-level | Responsive breakpoints from 1100 px through 480 px; mobile shell and overflow handling |
| Accessibility baseline | Pass for automated smoke scope | axe-core, keyboard, desktop/mobile auth, 404, protected routing, shell and empty dashboard; full manual screen-reader matrix remains |
| Backend startup | Pass | Application lifespan, live health, docs and OpenAPI regression test |
| Backend static analysis | Pass | Ruff and strict mypy across 94 source files |
| Backend tests | Pass | 80 tests; full isolated suite with no persistent fixture data |
| API documentation | Pass | Swagger/OpenAPI in development/test; intentionally disabled in production |
| Migration chain | Pass, static/offline | One Alembic head, 19 ordered revisions, complete MySQL offline SQL generation |
| Live MySQL migration | Pending release gate | Docker daemon unavailable; local MySQL credentials unavailable |
| Docker configuration | Pass | Compose interpolation/config validation; non-root application images |
| Container health smoke | Automated, not locally executed | Isolated Compose CI job covers build, health, empty DB, restart and persistence; local Docker engine remains unavailable |
| Redis connectivity | Pending live smoke | Authenticated Redis and readiness checks are configured but could not be contacted locally |
| Demo/sample business data | Pass | No runtime seed path, migration insert, business bootstrap, or hardcoded dashboard statistics found |
| Security | Pass with documented residual work | No open critical/high finding; nonce CSP, encrypted S3 adapter and fail-closed malware scanning added; see `SECURITY_AUDIT.md` |

## Completed modules

- Authentication, organization onboarding, password recovery, refresh-token rotation and session
  revocation.
- Granular RBAC, built-in role templates, custom roles, permission-aware navigation and audited
  role assignment.
- Organization, branches, departments, users, teams, territories and organization settings.
- Lead lifecycle: creation, sources, assignment, duplicate detection, qualification, scoring,
  activities, follow-ups, notes, timeline, conversion, lost reasons, import, kanban, unattended
  and ageing views.
- Customer 360 profiles, activity and sales history, documents, payments, outstanding balances,
  agreements, possession and service history.
- Project/tower/floor/unit inventory, availability search, transactional soft/hard holds and
  automatic hold expiry worker.
- Site visits and calendar, including lead/customer linkage, check-in/out and follow-up.
- Price lists, server-calculated cost sheets, discount approval matrices, versioned quotations
  and authenticated PDF output.
- Private document/KYC upload, review, versioning, expiry and secure download.
- Booking state machine, applicants, verified KYC/payment gates, financing, approvals and
  duplicate-unit prevention.
- Finance and collections: plans, installments, demands, partial payments, reconciliation,
  allocation, receipts, ledger, penalties, refunds and audit records.
- Cancellation, refund and unit-transfer workflows.
- Channel partner lifecycle, documents, lead protection, commissions, payouts and disputes.
- Agreement/construction/no-dues/snagging/possession/handover lifecycle with explicit override
  approval when prerequisites are incomplete.
- Separate rental property, tenant, lease, rent, renewal, move and maintenance domain.
- Service requests, SLA policies, assignment, comments, private attachments, escalation,
  resolution, closure and feedback.
- Real-data executive, sales, marketing, inventory, collections, partner and customer dashboards.
- Append-only audit records and recipient-scoped in-app notifications with provider-neutral
  external transport interfaces.

## Business lifecycle verification

| Link | Status | Verification |
|---|---|---|
| Lead → Customer | Pass | Qualified-only conversion creates a tenant-scoped customer and audit/timeline records |
| Customer → Site Visit | Pass | Visit validates and persists customer/project/interested-unit relationships |
| Site Visit → Quotation | Pass with process linkage | Both use the same customer/project/unit domain; quotation does not require a visit ID |
| Quotation → Hold | Pass with process linkage | Booking requires accepted quotation and matching approved active hold for customer/unit |
| Hold → Booking | Pass | Locked transaction converts the hold and prevents competing booking |
| Booking → Payment | Pass | Server-derived amount/plan, idempotent submission and independent verification |
| Payment → Collection | Pass | Reconciliation, allocation, receipt, ledger and outstanding calculations are backend-owned |
| Collection → Possession | Pass | Financial/document/agreement/no-dues readiness gates possession; override requires approval |
| Possession → Service | Pass with process linkage | Customer/booking-scoped service ticket can be opened after handover; no automatic ticket is fabricated |

Every stage has API/service coverage, but there is not yet one browser-driven test that executes
the entire chain in a single scenario. That test remains a pre-release task.

## Frontend audit

### Passed

- Production compilation, TypeScript and ESLint.
- Permission-aware routes and navigation; backend remains authoritative.
- Responsive grids/tables/forms and mobile navigation at multiple breakpoints.
- Visible focus styles, skip navigation, reduced-motion support, alert/status live semantics,
  labeled navigation, keyboard-operable tabs, modal focus trapping, Escape handling and focus
  restoration.
- Empty and zero states use API results; no records/statistics are manufactured for presentation.

### Incomplete

- Automated axe-core and Playwright desktop/mobile smoke coverage now exists, but there is no
  Lighthouse performance budget, cross-browser visual-regression matrix, or completed manual
  screen-reader test across every business page.
- There is not yet one browser test that creates and executes the entire Lead-to-Service domain
  chain against the real backend; backend API/service tests remain authoritative for that chain.

## Backend audit

### Passed

- Lifespan startup and health endpoint.
- Structured validation and generic unexpected-error envelope with request IDs.
- JWT/session authentication, backend permissions, organization isolation and portal-role BOLA
  regression tests.
- Swagger/OpenAPI contract generation in non-production environments. Production docs are
  deliberately disabled to reduce public attack surface.
- Transaction rollback, idempotency, row locking, state transitions and duplicate-booking tests.
- Private upload/download controls and append-only audit behavior.

### Incomplete

- Authenticated Prometheus metrics and JSON stdout logs are implemented. A tracing exporter and
  the target environment's log/metric collector still need deployment configuration.
- No durable general-purpose outbox/queue worker; notifications define provider abstraction and
  hold expiry has a worker, but the target architecture's full outbox model remains future work.
- Customer and Channel Partner portal identities need explicit record bindings before broader
  self-service permissions can safely be restored.

## Database and migration status

- Alembic head: `20260822_0019`.
- Ordered revisions: 19, with no branches or multiple heads.
- MySQL offline SQL generation: passed through head.
- ORM inventory: 93 tables; 92 tenant-owned and one global organization table.
- Schema metadata: 227 indexes, 359 foreign-key constraints, 174 unique constraints and 123
  check constraints.
- Tenant-owned tables require `organization_id`, timestamps and `(organization_id, id)` identity.
- Domain foreign keys are composite tenant-scoped foreign keys.
- Critical financial and workflow commands use database row locks, idempotency keys, uniqueness
  constraints, rollback handling and server-side state validation.
- Migrations contain schema changes and normalization `UPDATE` statements only. No migration
  contains `INSERT INTO`, Alembic `bulk_insert`, `create_all` or business seed execution.

### Migration release gate

Run `alembic upgrade head` against a new MySQL 8.4 database, inspect the resulting schema, verify
`alembic current`, then perform a tested backup/restore. Offline generation does not replace this
live-dialect test.

## Infrastructure and deployment status

### Passed configuration review

- Frontend and backend runtime containers use non-root users.
- MySQL, Redis and private uploads use named persistent volumes.
- MySQL and Redis stay on the internal Compose network in the base deployment.
- Redis requires authentication and enables append-only persistence.
- MySQL, Redis, backend and frontend define health checks; backend readiness checks both database
  and Redis.
- A one-shot migration service gates API startup; API replicas never execute Alembic. The
  hold-expiry worker exposes a successful-cycle heartbeat health check.
- Production settings require encrypted S3-compatible private storage and ClamAV scanning;
  temporary object downloads are deleted after authenticated responses.
- Authenticated Prometheus metrics and structured JSON stdout logs are ready for collection.
- CI definitions cover live MySQL migration/drift, backup/restore, Compose restart/persistence,
  empty-database assertions, browser accessibility, dependencies and container images.
- Compose configuration validation passes.
- Production SMTP variables are now forwarded to backend and worker containers. Blank optional
  SMTP values normalize safely in development, while incomplete production SMTP configuration
  fails closed.
- JWT secret, database passwords and Redis password remain environment-supplied and are not
  committed.

### Deployment blockers / known issues

1. A live Compose startup was not possible on this workstation because the Docker engine is not
   available. Container build/start, health and restart behavior must be rerun in CI or the target
   host.
2. The target deployment must provision S3/KMS and ClamAV credentials/endpoints. Bucket policy,
   versioning, lifecycle and scanner quarantine operations remain environment-owned.
3. Configure TLS/WAF/reverse proxy, trusted client-IP handling, log retention,
   monitoring and alerts outside Compose.
4. Production requires real HTTPS `PUBLIC_WEB_URL`/`CORS_ORIGINS`, SMTP delivery settings and
   independently generated secrets. Example placeholder values intentionally fail startup.
5. Set `ALLOW_ORGANIZATION_REGISTRATION=false` if tenant creation is invitation/admin controlled.

## No demo or sample business data verification

Repository-wide searches covered `seed`, `fixture`, `demo`, `sample`, `fake`, `mock`, startup
writes, migration inserts and hardcoded dashboard number patterns.

- No runtime seed command or startup business-data insertion exists.
- Explicit onboarding creates only the requested organization/admin plus technical permission and
  role metadata.
- No default users, organizations, branches, departments, teams, territories, leads, sources,
  customers, projects, units, visits, quotations, holds, bookings, payments, tickets,
  notifications or dashboard statistics are created.
- Dashboard values are aggregate SQL queries over persisted tenant records and return zero/empty
  series when no records exist.
- Test fixtures/factories are confined to `backend/tests`, temporary files and in-memory SQLite.
  Frontend mocks are confined to test files. They do not run in production or seed a database.
- No unintended business data was found, so no legitimate isolated test data was removed.

## Security status

The complete security review is in `SECURITY_AUDIT.md`. Open critical findings: 0. Open high
findings: 0. Production dependency constraints include the patched cryptography release; the npm
production audit reported zero vulnerabilities.

## Remaining tasks before release

1. Run the newly added live MySQL migration, backup/restore and Compose smoke jobs in CI or on the
   target host; this workstation cannot execute them without a Docker engine.
2. Provision production HTTPS origins, SMTP, S3/KMS, ClamAV, metrics credentials, bucket
   versioning/lifecycle, TLS edge/WAF, secrets, backups and collector/alert destinations.
3. Add browser E2E coverage for the complete Lead → Service lifecycle, including duplicate
   booking and possession-gate failures.
4. Complete Lighthouse plus manual keyboard/screen-reader tests across all business pages and add
   a cross-browser visual-regression matrix.
5. Bind Customer and Channel Partner portal identities to domain records before widening their
   deliberately restricted self-service permission allowlists.
6. Add distributed tracing and a durable general-purpose external-notification outbox worker.
7. Execute the new CI workflow and enforce it as a required branch protection check.

## Release decision

**Do not declare the deployment fully production-ready until tasks 1 and 2 pass in a live isolated
environment.** The application code and configuration are ready for that release-candidate smoke
test, and no demo/sample business data blocker remains.
