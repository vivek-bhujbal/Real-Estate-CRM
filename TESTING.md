# Testing

The test suites use test-only records. Backend tests create the schema in an in-memory SQLite database before each test and drop it afterward. Uploaded test files use a temporary storage directory. Frontend factories create in-memory session objects and mocked API responses only; they never seed the application database.

## Commands

From `backend`:

```powershell
python -m pytest -q
```

From `frontend`:

```powershell
npm test
npm run test:coverage
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

## Coverage layers

- Unit and validation: security helpers, permission catalog, Pydantic invariants, permission evaluation, and state-transition guards.
- Service and workflow: lead, inventory, quotations, bookings, finance, post-sales, partners, property lifecycle, rentals, service requests, notifications, dashboards, documents, and audit services.
- API and authorization: authentication, tenant isolation, permission enforcement, delegated-role escalation prevention, read-only auditor access, validation errors, search, pagination, filters, and secure downloads.
- Transactions and concurrency: hold allocation/expiry, active inventory visibility, duplicate unit booking protection, failed-booking rollback, payment idempotency/allocation, cancellation/refund, and unit transfer.
- Frontend: login and native form validation, permission-aware routes/navigation/actions, API authentication refresh, lead creation, controlled booking creation, real empty states, and service-ticket creation.
- Browser/accessibility: Playwright runs desktop and mobile Chromium checks for login, onboarding, unauthorized redirects, branded 404 recovery, keyboard focus, authenticated navigation, empty dashboards, and automated axe-core WCAG rules. Browser data and API responses exist only inside the isolated test process.

## Critical scenario map

| Scenario | Primary backend coverage |
| --- | --- |
| Login / unauthorized access | `test_auth.py`, `test_rbac.py`, `test_api_validation_and_transactions.py` |
| Lead creation / assignment / conversion | `test_lead_management.py` |
| Site visit | `test_site_visit_management.py` |
| Quotation / discount approval | `test_quotation_management.py` |
| Unit hold / duplicate booking prevention | `test_inventory_management.py`, `test_booking_management.py` |
| Booking | `test_booking_management.py`, `test_api_validation_and_transactions.py` |
| Payment / installment / collection | `test_finance_collections.py`, `test_booking_management.py` |
| Cancellation / refund / unit transfer | `test_post_sales_workflows.py` |
| Broker commission | `test_channel_partner_management.py` |
| Possession | `test_property_lifecycle.py` |
| Service request | `test_service_request_management.py` |

The long workflow tests assert database state and audit records after API operations. They do not treat a successful HTTP response alone as sufficient proof.
