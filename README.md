# Real Estate CRM & Revenue Management Platform

Production-oriented multi-tenant CRM built as small, verified vertical slices. The repository contains a Next.js frontend, FastAPI API, MySQL persistence, Redis infrastructure, Alembic migrations, and Docker Compose orchestration.

## Current scope: Phase 1 foundation

- Organization onboarding with an initial administrator (a user-initiated transaction, never seed data)
- Issuer/audience-bound JWT access tokens, rotating refresh families, Argon2id password hashing,
  immediate session revocation, and one-time password recovery
- Organization-scoped users, branches, departments, roles, and permissions
- Backend-enforced tenant boundaries and permission dependencies
- Structured errors, request IDs, audit-log schema, health endpoints, and storage abstraction
- API-backed dashboard summary that returns real zero counts for an empty organization
- Responsive authenticated application shell and onboarding/login experiences

No business seed data, demo users, or fabricated statistics are created. Later phases are described in [docs/roadmap.md](docs/roadmap.md).

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
