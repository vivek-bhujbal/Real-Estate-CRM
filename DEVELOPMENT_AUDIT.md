# Development Audit

Audit date: 2026-08-20

## Audit scope

This audit covers all project-owned source code, configuration, migrations, documentation, and tests in the repository. Generated directories and artifacts (`backend/.venv`, `frontend/node_modules`, `frontend/.next`, Python caches, pytest/mypy/Ruff caches, and `tsconfig.tsbuildinfo`) were inventoried but are not treated as application source.

The repository is a Phase 1 foundation, not the complete Real Estate CRM described by the product requirements. There is no runtime `.env`, `.env.local`, business seed script, or default business dataset. The only named records are ephemeral test fixtures created in an in-memory test database.

## 1. Current architecture

### Repository layout

The repository uses a simple two-application layout rather than a package-manager workspace or formal monorepo tool:

```text
RealEstate-CRM/
├── backend/                 FastAPI application and Alembic migrations
├── frontend/                Next.js App Router application
├── docs/                    Phase design and delivery roadmap
├── docker-compose.yml       Local full-stack orchestration
├── .env.example             Compose environment contract
└── README.md                Setup and verification guide
```

No Git metadata is present in the current workspace, so repository history, branches, and tracked-versus-untracked status cannot be audited.

### Runtime topology

```text
Browser
  └── Next.js frontend :3000
        └── REST requests to FastAPI :8000/api/v1
              ├── MySQL 8.4 :3306
              ├── Redis 7.4 :6379
              └── Local/volume-backed file storage
```

The browser calls FastAPI directly using `NEXT_PUBLIC_API_URL`. Access tokens are held in React memory and sent as bearer tokens. Refresh tokens are opaque values held in an HttpOnly cookie and persisted in hashed form in MySQL.

### Frontend architecture

- Next.js App Router with a global root layout and client-side authentication provider.
- Routes: `/` redirects to `/login`; `/login`, `/onboarding`, and `/dashboard` are implemented.
- `AuthProvider` owns the in-memory access token/session and calls login, registration, refresh, and logout APIs.
- `lib/api.ts` is the single REST transport and error-normalization helper.
- `AuthFrame` and `AppShell` are the principal reusable UI components.
- The dashboard reads real organization-scoped counts from the API. It does not fabricate business statistics.
- Styling is a custom global CSS design system with responsive breakpoints and reduced-motion handling.

### Backend architecture

- FastAPI application entry point in `backend/app/main.py`.
- Versioned routers under `app/api/v1`.
- Dependency-based authentication and permission checks in `app/api/dependencies.py`.
- Configuration, security, middleware, rate limiting, and error handling under `app/core`.
- Async SQLAlchemy engine/session management under `app/db`.
- All current ORM entities and status enums are in one `app/models/entities.py` module.
- Pydantic request/response schemas are under `app/schemas`.
- Authentication business logic is separated into `app/services/auth.py`.
- A storage protocol and local filesystem implementation exist under `app/storage`.
- Repository classes, domain workflow classes, background task modules, and integration modules do not yet exist.

### Database architecture

The initial schema contains fourteen tables:

- Tenant and organization: `organizations`, `branches`, `departments`, `users`
- Authorization: `roles`, `permissions`, `user_roles`, `role_permissions`
- Security and audit: `refresh_tokens`, `audit_logs`
- Early business placeholders: `leads`, `projects`, `units`, `bookings`

Tenant-owned tables carry `organization_id`. UUIDs are stored as 36-character strings. ORM timestamps are application-generated. Statuses are stored as non-native string enums. The schema includes tenant-oriented indexes and several uniqueness constraints.

Alembic is configured for the async database URL. There is one initial revision, `20260820_0001`.

### Docker architecture

- MySQL 8.4 with `utf8mb4`, a health check, configurable host port, and a named data volume.
- Redis 7.4 Alpine with append-only persistence, a health check, and a named data volume.
- Multi-stage, non-root Python 3.12 backend image.
- Multi-stage, non-root Node 22/Next.js standalone frontend image.
- A named upload volume backs backend local storage.
- Backend startup runs `alembic upgrade head` and then Uvicorn.
- Docker build contexts exclude local dependencies, caches, environment files, tests, and uploads as appropriate.

### Test architecture

- Seven backend tests exist.
- Tests use pytest, pytest-asyncio, HTTPX ASGI transport, and in-memory SQLite.
- Coverage includes password hashing, JWT claims/signature verification, organization onboarding, real zero-count dashboard output, non-enumerating login failure, refresh-cookie rotation, and duplicate organization rejection.
- Tests call `Base.metadata.create_all()` rather than applying Alembic migrations.
- There are no frontend unit, component, accessibility, or end-to-end tests.

## 2. Existing technologies

| Area | Technology | Current use |
|---|---|---|
| Frontend framework | Next.js 16.3.1 | App Router, static page generation, standalone production output |
| UI runtime | React / React DOM 19.2.8 | Client context, forms, authenticated shell, dashboard |
| Frontend language | TypeScript 5.9.x | Strict type checking and path aliases |
| Frontend quality | ESLint 9 + `eslint-config-next` | Core Web Vitals and TypeScript lint rules |
| Frontend styling | Custom CSS | Design tokens, responsive layouts, focus states, empty/loading/error states |
| Backend framework | FastAPI | REST routes, dependencies, OpenAPI in development/test |
| Backend language | Python 3.12 target | Async application and service code |
| Validation/config | Pydantic v2 + pydantic-settings | API schemas and environment configuration |
| ORM/database access | SQLAlchemy 2 async + asyncmy | Async MySQL persistence |
| Migrations | Alembic | One initial schema revision |
| Primary database | MySQL 8.4 | Production/development relational database target |
| Test database | SQLite via aiosqlite | Fast isolated backend tests |
| Authentication | PyJWT + pwdlib/Argon2 | Signed access JWTs, password hashing, opaque refresh tokens |
| Cache/infrastructure | Redis async client + Redis 7.4 | Fixed-window authentication rate limiting and readiness checks |
| API testing | HTTPX | In-process ASGI integration tests |
| Backend quality | Ruff + strict mypy + pytest | Linting, formatting, static analysis, automated tests |
| Containers | Docker + Docker Compose | MySQL, Redis, backend, frontend, and named volumes |
| File storage | Python protocol + local adapter | Abstraction exists; no upload API uses it yet |

Dependency management is split: the frontend has a lockfile, while the backend uses bounded version ranges in `pyproject.toml` without a lockfile.

## 3. Existing modules

### Backend modules and maturity

| Module | Status | Existing capability |
|---|---|---|
| Application/bootstrap | Functional foundation | Lifespan, CORS, middleware, errors, health endpoints, router registration |
| Configuration | Functional foundation | Environment parsing, TTL limits, CORS parsing, environment-aware docs/cookies |
| Organization onboarding | Partial vertical slice | Creates an organization, first administrator, administrator role/permissions, and audit event |
| Authentication | Functional foundation | Login, current user, access JWT, rotating refresh cookie, logout/revocation, replay-family revocation |
| RBAC | Partial | Tenant-scoped role/permission tables and backend `require_permission()` dependency |
| Organization structure | Schema only | Branch and department tables; no services or APIs |
| Dashboard | Partial | Organization-scoped counts for leads, projects, available units, and bookings |
| Audit | Schema plus one event | Organization creation audit record; no reusable audit service or viewer API |
| Lead management | Schema only | Minimal lead fields and status enum; no lifecycle/service/API |
| Project management | Schema only | Minimal project fields; no tower/block/floor hierarchy or APIs |
| Inventory | Schema only | Minimal unit fields and lifecycle enum; no transition enforcement or APIs |
| Booking | Schema only | Minimal booking fields and lifecycle enum; no transactional workflow or APIs |
| Storage | Adapter only | Safe-path local save/delete implementation; not integrated with uploads |
| Rate limiting | Partial | Redis-backed fixed window on registration/login/refresh |
| Caching/background work | Not implemented | Redis is not used for caching, queues, scheduled work, or events |

### Existing REST API

| Method | Path | Protection |
|---|---|---|
| `GET` | `/health/live` | Public |
| `GET` | `/health/ready` | Public |
| `POST` | `/api/v1/auth/register-organization` | Public, rate limited, configurable enable/disable |
| `POST` | `/api/v1/auth/login` | Public, rate limited |
| `POST` | `/api/v1/auth/refresh` | Refresh cookie, rate limited |
| `POST` | `/api/v1/auth/logout` | Refresh cookie if present |
| `GET` | `/api/v1/auth/me` | Bearer access token |
| `GET` | `/api/v1/dashboard/summary` | Bearer token plus `dashboard.read` permission |

No list endpoints, pagination, filtering, sorting, search, CRUD endpoints, workflow endpoints, or approval endpoints exist yet.

### Frontend modules and components

| Module | Existing capability |
|---|---|
| Root layout | Metadata, global CSS, application-wide `AuthProvider` |
| Login | Organization slug/email/password authentication and safe error display |
| Onboarding | Organization and initial administrator registration with client-side constraints |
| Authentication provider | Initial refresh, login, registration, logout, in-memory session |
| API client | JSON requests, credentials, bearer header, structured `ApiError` |
| Application shell | Responsive sidebar/top bar, workspace/user identity, disabled future navigation |
| Dashboard | Real summary counts, skeletons, empty states, setup roadmap |
| Design system | CSS variables and shared classes; no component library or token package |

## 4. Existing problems

### Data integrity and tenancy

1. **Tenant IDs are not enforced across related foreign keys.** For example, `user_roles.organization_id`, `user_id`, and `role_id` have independent foreign keys. MySQL can therefore accept a row whose user and role belong to different organizations. The same issue exists for role-permission, branch-department, user-branch/department, project-unit, and booking-unit/lead relationships. Application filters reduce exposure but do not provide database-level isolation.
2. **Business state enums have no transition services.** Lead, unit, and booking statuses can theoretically be assigned in any order once write APIs are added. Unit locking, hold expiry, booking exclusivity, and concurrent booking prevention are absent.
3. **Booking uniqueness is not enforced.** The schema has no active-booking/hold invariant that prevents two successful bookings for the same unit.
4. **The initial migration is not immutable.** It calls current `Base.metadata.create_all()` and `drop_all()` instead of recording explicit Alembic operations. Changing ORM metadata changes what the historical migration does, prevents reliable schema review, and makes its downgrade capable of dropping tables outside the original revision's scope.
5. **Tests bypass migrations and MySQL semantics.** They use SQLite plus `metadata.create_all()`, so they cannot detect Alembic drift, MySQL collation/index differences, locking behavior, or transaction semantics.

### Authentication and security

1. **The frontend has no transparent access-token refresh/retry path.** It refreshes once when the provider mounts, but an API call made after the 15-minute access token expires receives an error until the page is reloaded or the user signs in again.
2. **Direct cross-origin cookie behavior constrains deployment.** The refresh cookie uses `SameSite=Lax`. This works for same-site deployments and local development, but a frontend and API on unrelated sites will not maintain the refresh session for fetch requests. No same-origin proxy/BFF contract is documented.
3. **Rate limiting fails open.** Any Redis exception silently disables limiting. It also keys directly on `request.client.host`; there is no trusted-proxy policy, so reverse-proxy deployments need explicit client-IP handling.
4. **No explicit CSRF mechanism exists.** SameSite cookies reduce risk, but refresh/logout/onboarding deployment rules and CSRF expectations are not documented or tested.
5. **Refresh sessions have no absolute maximum lifetime.** Every valid refresh creates a new token with the full configured TTL, allowing an active family to roll indefinitely.
6. **Onboarding and session issuance use separate commits.** Organization/user/role/permission creation commits before the first refresh token is committed. A session-creation failure leaves a valid organization and administrator but returns an onboarding failure to the client.
7. **Constraint errors are overgeneralized.** Any integrity failure during onboarding is reported as an existing organization slug, which can conceal a different schema or programming defect.
8. **`FIELD_ENCRYPTION_KEY` is declared only in the root example and is unused.** Sensitive-field encryption and key rotation are not implemented.

### API and backend structure

1. **The advertised layered architecture is only partially present.** Authentication has a service layer, but there are no repository abstractions, tenant query helpers, workflow/state-machine layer, reusable audit service, task layer, or integrations layer.
2. **All ORM entities are concentrated in one file.** This is manageable for fourteen tables but will become difficult to own and migrate across the planned domain modules.
3. **Permission lookup queries the database on every protected request.** No safe invalidation-aware permission cache exists.
4. **Error formats are not fully uniform.** `AppError` and unhandled errors share a structure, but framework validation errors retain FastAPI's default response shape.
5. **Storage is not wired into the application.** There is no upload endpoint, file metadata table, content-type/signature validation, size enforcement, malware scanning hook, or object-storage adapter.
6. **Audit logging is not systemic.** Only organization creation writes an audit record. Audit rows are not protected from application updates/deletes, and there is no query/export API.
7. **Readiness failures are swallowed without diagnostic logging.** The endpoint reports dependency availability but does not emit actionable dependency failure context to operations logs.

### Frontend behavior and maintainability

1. **The dashboard's “Active leads” value counts every lead.** Lost and disqualified records would be included because the backend count has no active-status filter.
2. **The pipeline panel has no populated state.** It renders a skeleton while loading and an empty state for zero leads, but renders no pipeline content when the lead count is greater than zero.
3. **Recent activity is always a static empty state.** An audit record already exists after onboarding, but the frontend has no audit/activity endpoint to read it.
4. **Navigation is hardcoded rather than permission-driven.** Disabled future items are safe today, but future navigation visibility must use effective permissions while backend authorization remains authoritative.
5. **Route protection is client-side only.** Backend data remains protected, but `/dashboard` is statically generated and redirects only after client hydration/session restoration. There is no Next.js middleware or server-side session boundary.
6. **The API client does not support cancellation, refresh retry, request deduplication, or typed runtime response validation.**
7. **Global CSS and `AppShell` are already monolithic.** The current size is acceptable, but continued feature work without extracting primitives, tokens, and module styles will create coupling.
8. **There are no route-level error boundaries, not-found customization, or frontend test harness.**

### Delivery and operations

1. **Docker Compose defaults the backend to development mode.** `APP_ENV` is not passed by the root example or Compose service, so API documentation remains enabled and cookies remain non-secure unless operators add the variable themselves.
2. **Migrations run in every backend container startup.** Multiple replicas can race, and application startup is coupled to schema mutation. A one-shot migration job/release step is safer.
3. **The backend dependency graph is not locked.** Bounded ranges improve compatibility but do not guarantee reproducible images.
4. **The frontend Dockerfile uses `npm install` despite having a lockfile.** `npm ci` is the reproducible build command.
5. **Redis has no authentication/TLS configuration and is exposed on a host port.** This is acceptable only for a trusted local development environment.
6. **Backend and frontend services have no Compose health checks.** Frontend depends on backend start, not backend readiness.
7. **There is no reverse proxy, TLS termination, secrets manager integration, resource limits, backup/restore procedure, log rotation, metrics, tracing, or alerting configuration.**
8. **There is no CI/CD configuration.** Lint, type checks, tests, migrations, image builds, and vulnerability scanning are manual.

## 5. Missing components

### Business capabilities

- Complete organization administration: branch/department APIs, user invitation/lifecycle, teams, project visibility, and all 15 configurable primary roles.
- Role and permission management UI/API, permission catalog lifecycle, and permission-change auditing.
- Lead sources, assignment, protection, qualification transitions, activities, loss/disqualification reasons, and customer conversion.
- Customer 360, customer documents, KYC, consent, duplicate detection, and sensitive data controls.
- Projects, towers/blocks, floors, unit attributes, inventory import, pricing, price lists, and availability search.
- Site visits, sales activities, quotations, cost sheets, negotiation, discount approval, and unit holds with expiry.
- Transactional booking, documentation, verification, approval, cancellation, refunds, and unit transfer.
- Agreements, payment plans, installments, demand letters, payments, receipts, customer ledger, collections, and overdue workflows.
- Channel partners, partner lead registration/protection, commissions, and payouts.
- Loan/financing workflow, construction updates, possession, handover, and post-sale service.
- Rental properties, tenants, leases, rental invoices, rent collection, and maintenance.
- Service requests, notifications, marketing automation, workflow/approval engine, reports, exports, and operational dashboards.

### Platform capabilities

- Repositories/specifications or another consistent tenant-safe data-access pattern.
- Explicit state machines and transactional domain services.
- Pagination, filtering, sorting, search, bulk operations, idempotency keys, and optimistic/concurrency controls.
- Background worker and scheduler architecture using Redis or a dedicated broker.
- Notification providers and durable outbox/event delivery.
- File metadata, upload validation, retention, object storage, and malware-scanning integration points.
- Sensitive-field encryption, key management, masking, data retention, deletion, and export policies.
- A reusable immutable audit service and auditor-facing query/export module.
- Structured logging, metrics, traces, error monitoring, and operational dashboards.
- Automated MySQL integration tests, migration tests, tenant-isolation tests, concurrency tests, and security tests.
- Frontend unit/component/accessibility tests and end-to-end tests covering authentication and major workflows.
- CI/CD, dependency/security scanning, database backup/restore, deployment manifests, and runbooks.

## 6. Recommended implementation order

1. **Stabilize the foundation before expanding scope.** Replace the metadata-driven initial migration with explicit revision operations (or establish a reviewed baseline if already deployed), add migration verification, enforce cross-tenant relationship integrity, define a single UTC timestamp policy, and add MySQL integration tests.
2. **Finish authentication/session hardening.** Add automatic access-token refresh with single-flight retry, define same-site deployment/proxy behavior, decide CSRF policy, add absolute refresh-family expiry, improve integrity-error classification, and make production settings explicit.
3. **Build the tenant-safe data-access and audit patterns.** Introduce organization-scoped repositories/query helpers, reusable permission checks, immutable audit writing, standardized validation errors, pagination contracts, and transaction/idempotency helpers. Every later module should use these patterns.
4. **Deliver organization administration end to end.** Implement branches, departments, user invitation/activation, teams, role/permission management, all 15 configurable role templates, project/user visibility, audit viewer, APIs, UI, and tests.
5. **Deliver lead-to-customer as the first business vertical.** Implement sources, assignment, activities, explicit lead transitions, duplicate handling, conversion, Customer 360, permissions, audits, API filters, responsive pages, and end-to-end tests.
6. **Deliver project and inventory management.** Add project hierarchy, unit metadata, pricing/price lists, imports, search, availability, and database-enforced unit transition rules.
7. **Deliver sales execution and holds.** Add site visits, quotations, cost sheets, configurable discount approvals, negotiations, and expiring holds with background processing.
8. **Deliver transactional booking and KYC.** Add documents, KYC, booking state machine, row locking/idempotency, verification/approval, cancellation, transfer, and agreement generation. Prove concurrent attempts cannot book one unit twice.
9. **Deliver revenue and collections.** Add payment plans, installments, demands, payments, verification, receipts, immutable double-entry-style customer ledger behavior, overdue handling, refunds, and reconciliation.
10. **Add partner, possession, service, and rental verticals.** Build each as an independently authorized, audited, tested slice rather than adding schema-only modules.
11. **Add automation and reporting after transactional sources are stable.** Implement durable notifications/outbox, configurable workflows/approvals, marketing automation, reports, exports, and real dashboards derived only from persisted data.
12. **Harden operations continuously.** Add CI/CD, reproducible backend locks and `npm ci`, one-shot migrations, container health checks, secrets management, backups, observability, security scanning, capacity testing, and disaster-recovery exercises.

At every step, migrations should create schema and required technical metadata only. Business records must originate from authenticated user actions or approved imports; no demo, sample, or default business data should be introduced.

