# Security Audit

Audit date: 2026-08-22

Scope: FastAPI backend, Next.js frontend, RBAC and tenant boundaries, private file
storage/downloads, authentication/session handling, audit records, dependency manifests,
and Docker configuration.

## Outcome

- Open critical findings: **0**
- Open high findings: **0**
- Fixed high findings: **3**
- Fixed medium hardening findings: **8**

The audit was performed against the source and automated test suite. No production secrets,
private keys, access keys, or committed `.env` files were found. Example environment files
contain placeholders only.

## High findings fixed

### SEC-001: Portal role BOLA / organization-wide record access

The built-in Customer, Tenant, and Broker roles contained module-level view/create
permissions, but Customer and Channel Partner records do not yet have an authenticated portal
user binding. A portal-only user could therefore reach organization-wide booking, KYC,
document, payment, partner, or lead endpoints.

Fix:

- Effective permissions now apply a fail-closed portal allowlist at authentication and on every
  backend permission check.
- Customer access is limited to user-scoped notifications and service requests.
- Tenant access retains user-linked lease, maintenance, service-request, notification, and rental
  payment operations.
- Broker access retains lead submission and non-sensitive project/inventory discovery, but not
  organization-wide lead, partner, booking, commission, customer, or document reads.
- Booking and collections payment mutations now require grouped domain context permissions in
  addition to the payment action, preventing rental payment authority from crossing into sales.
- Regression tests verify 403 responses before entity lookup, including arbitrary identifiers.

### SEC-002: Known default JWT signing secret

The application could start in development mode with a source-known JWT signing key. A
deployment accidentally left in development mode would accept forged tokens.

Fix:

- `JWT_SECRET_KEY` is mandatory in every environment and must be at least 32 characters.
- Known example/default markers are rejected at startup.
- Credentialed CORS wildcard configuration is rejected at startup.
- Docker Compose already requires the secret through environment interpolation; no secret is
  embedded in the image or Compose source.

### SEC-003: Inconsistent protection of private downloads

Several authenticated KYC, agreement, rental, possession, handover, cancellation, transfer, and
partner document downloads lacked consistent cache and active-content controls.

Fix:

- All private file responses use forced `attachment` disposition.
- Responses include `private, no-store`, `nosniff`, sandbox CSP, same-origin resource policy,
  and download hardening headers.
- Generated quotation PDFs and audit CSV exports use the same private response policy.

## Additional hardening completed

- Refresh cookies now use `HttpOnly`, `Secure` outside development/test, a narrow auth path, and
  `SameSite=Strict`.
- Refresh/logout reject untrusted Origin/Referer values and cross-site Fetch Metadata requests.
- Untrusted request IDs are validated before being reflected in response headers or audit logs.
- API responses add Permissions Policy; HTTPS environments add HSTS.
- Frontend responses add CSP, frame denial, MIME sniffing protection, referrer policy,
  Permissions Policy, and same-origin opener policy.
- Frontend script CSP now uses per-request cryptographic nonces and `strict-dynamic`; application
  routes render at request time so Next.js can attach the nonce. Script `unsafe-inline` is gone.
- All accepted PDF/JPEG/PNG uploads share fail-closed ClamAV INSTREAM scanning outside
  development/test. Scanner failure rejects the upload instead of persisting unscanned content.
- Production settings require private S3-compatible storage with server-side AES-256 or KMS
  encryption. Runtime/IAM credentials remain outside source, and temporary downloads are deleted
  after the authenticated response.
- The patched `cryptography >=50.0.0,<51` constraint closes the advisory found in the Python
  environment. Production npm dependencies reported zero vulnerabilities.

## Controls reviewed with no high finding

- Passwords use Argon2id and are never stored as plaintext.
- JWTs validate signature algorithm, issuer, audience, type, tenant, session family, token times,
  and authentication version.
- Refresh tokens are random, stored only as hashes, rotated under a database lock, and reuse
  revokes the token family.
- Password reset tokens are hashed, expiring, one-time, and invalidate existing sessions.
- SQL access uses SQLAlchemy-bound expressions; no user-controlled raw SQL was found.
- React rendering does not use `dangerouslySetInnerHTML`, direct `innerHTML`, or `eval`.
- Organization-owned entity lookups include organization scope and cross-organization tests.
- RBAC changes prevent self-role changes, prevent granting permissions the actor does not hold,
  protect the last administrator, revoke stale access through `auth_version`, and create audit
  records.
- Uploads are size-limited while streaming, use randomized private storage keys, validate file
  extension and magic bytes, reject unsafe names, prevent path traversal, and store local files
  with owner-only permissions or private encrypted object storage.
- CORS uses explicit origins, methods, and headers.
- Authentication endpoints have Redis-backed rate limits with a bounded in-process fallback.
- Unexpected backend errors return a generic message and request ID, without stack traces.
- Sensitive mutations record actor, organization, entity, before/after values, timestamp,
  request ID, IP, user agent, and device metadata. Auditor permissions are read/export only.
- Containers run application processes as non-root users; MySQL/Redis data is isolated on named
  volumes and Redis authentication is required by Compose.

## Residual recommendations

These are not open high/critical vulnerabilities, but should be addressed before stricter
enterprise/compliance deployments:

1. Add explicit Customer and Channel Partner portal-user bindings, then implement resource-level
   policies before restoring their broader self-service permissions.
2. Add branch/project/territory ABAC if staff in one branch must be isolated from other branches
   inside the same organization. Current hard isolation boundary is the organization.
3. Add account-aware and risk-based authentication throttling in addition to IP throttling to
   reduce distributed credential-stuffing attempts.
4. Provision and monitor the implemented ClamAV and encrypted S3/KMS adapters, including bucket
   versioning/lifecycle, least-privilege policy, quarantine operations and key rotation.
5. Configure trusted-proxy handling at the deployment edge if original client IP attribution is
   required; the application deliberately does not trust arbitrary forwarded headers.
6. Execute and enforce the new dependency advisory and container-image scan workflow on every
   merge and on a schedule.
   The shared local Python environment still contains an unrelated `python-jose -> ecdsa` package
   with an advisory; neither package is declared by this project or included in its container
   dependency manifest.

## Verification

- Backend: `80 passed`
- Frontend: `7` test files, `14 passed`
- Playwright/axe-core: `10 passed` across desktop and mobile Chromium
- Ruff: passed
- mypy strict mode: passed across 101 source files
- ESLint: passed
- TypeScript typecheck: passed
- Next.js production build: passed (47 routes)
- npm production dependency audit: `0 vulnerabilities`
- Docker Compose configuration validation: passed
