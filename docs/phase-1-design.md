# Phase 1 design record

## Entities

`Organization` owns all tenant business data. `Branch` and `Department` are tenant-scoped organizational units. `User` belongs to one organization. `Role` and `Permission` are tenant-configurable and joined to users through explicit association tables. `RefreshToken` persists only a token hash and supports rotation/revocation. `AuditLog` stores immutable before/after JSON snapshots with actor and request metadata.

The dashboard reads counts from tenant-owned tables. Phase 1 creates future-facing `Lead`, `Project`, `Unit`, and `Booking` tables only to establish tenant-safe summary queries and core constraints; their full workflows and write APIs are deferred to later vertical slices.

## Permissions

Phase 1 defines stable permission codes: `dashboard.read`, `organization.read`, `organization.manage`, `users.read`, `users.manage`, `roles.read`, `roles.manage`, and `audit.read`. During organization onboarding, the administrator role and its explicit permissions are created inside the same transaction. This is user-requested tenant setup, not startup seed data. The remaining primary roles are not fabricated; administrators will create them when role management is delivered.

## Endpoints

- `POST /api/v1/auth/register-organization` atomically onboards a tenant and its first administrator.
- `POST /api/v1/auth/login`, `/refresh`, and `/logout` manage an access/rotating-refresh session.
- `GET /api/v1/auth/me` returns the current user and effective permissions.
- `GET /api/v1/dashboard/summary` returns real organization-scoped counts.
- `GET /health/live` and `/health/ready` expose process and dependency health.

## Workflows, validation, and edge cases

Organization onboarding is atomic. Slugs/emails are normalized, passwords require length and mixed character classes, and uniqueness is enforced in MySQL. Concurrent registration is resolved by constraints. Login does not reveal whether an organization or account exists. Disabled organizations/users are rejected.

Refresh tokens are opaque random values; only SHA-256 hashes are stored. Every use rotates the token, and replay revokes the token family. Access-token claims never replace a current database user lookup.

Every tenant table contains `organization_id`; tenant scope comes from the authenticated user, never a frontend header. Empty organizations receive zero counts and explicit UI empty states.

