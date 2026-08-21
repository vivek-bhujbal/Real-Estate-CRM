# Phase 1 design record

## Entities

`Organization` owns all tenant business data. `Branch` and `Department` are tenant-scoped organizational units. `User` belongs to one organization. `Role` and `Permission` are tenant-configurable and joined to users through explicit association tables. `RefreshToken` persists only a token hash and supports rotation/revocation. `AuditLog` stores immutable before/after JSON snapshots with actor and request metadata.

The dashboard reads counts from tenant-owned tables. Phase 1 creates future-facing `Lead`, `Project`, `Unit`, and `Booking` tables only to establish tenant-safe summary queries and core constraints; their full workflows and write APIs are deferred to later vertical slices.

## Permissions

The authorization catalog defines eight actions (`view`, `create`, `update`, `delete`, `approve`, `assign`, `export`, and `manage`) for every supported module. Permission codes use the stable `module.action` form. `manage` implies the other actions only inside the same module; it is not a cross-module bypass.

During organization onboarding, all 15 product role templates and the tenant permission catalog are created as technical authorization metadata in the same transaction. Only the user-requested initial administrator is assigned a role. No users, leads, customers, projects, transactions, or other demo/business records are seeded. Built-in role names cannot be changed or deleted. Their permissions remain configurable except for the protected Organization Administrator role. Custom roles are supported.

Role creation, editing, and assignment are tenant-scoped, audited, and protected by separate backend permissions. A delegated administrator cannot grant a permission they do not personally hold. A user cannot change their own assignments, and authorization changes increment the target user's authentication version.

## Endpoints

- `POST /api/v1/auth/register-organization` atomically onboards a tenant and its first administrator.
- `POST /api/v1/auth/login`, `/refresh`, and `/logout` manage an access/rotating-refresh session.
- `GET /api/v1/auth/me` returns the current user and effective permissions.
- `GET /api/v1/dashboard/summary` returns real organization-scoped counts.
- `GET /api/v1/rbac/permissions`, `/roles`, and `/users` return the tenant access catalog.
- `POST/PATCH/DELETE /api/v1/rbac/roles` manage authorized custom or configurable roles.
- `PUT /api/v1/rbac/users/{user_id}/roles` atomically replaces a user's assignments.
- `GET /health/live` and `/health/ready` expose process and dependency health.

## Workflows, validation, and edge cases

Organization onboarding is atomic. Slugs/emails are normalized, passwords require length and mixed character classes, and uniqueness is enforced in MySQL. Concurrent registration is resolved by constraints. Login does not reveal whether an organization or account exists. Disabled organizations/users are rejected.

Refresh tokens are opaque random values; only SHA-256 hashes are stored. Every use rotates the token, and replay revokes the token family. Access-token claims never replace a current database user lookup.

Every tenant table contains `organization_id`; tenant scope comes from the authenticated user, never a frontend header. Empty organizations receive zero counts and explicit UI empty states.

