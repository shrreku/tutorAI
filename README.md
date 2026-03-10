# StudyAgent

StudyAgent is an agentic tutoring system for notebook-scoped study sessions over ingested course material. It ingests PDFs and notes into a retrieval-backed knowledge base, plans learning objectives, and runs turn-by-turn tutoring with evaluation, mastery tracking, summaries, and notebook progress.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, SQLAlchemy 2, Alembic |
| Data | PostgreSQL + pgvector, optional Redis, optional Neo4j |
| Frontend | React 18, TypeScript, Vite |
| ML | OpenAI-compatible LLMs, local sentence-transformer embeddings |

## Environment Contract

- Backend/API reads root `.env` or `backend/.env` values via `backend/app/config.py`.
- Frontend runtime uses `VITE_API_BASE_URL`.
- Frontend dev proxy uses `VITE_API_PROXY_TARGET`.
- Local Docker Compose is a development environment; production images are built from `backend/Dockerfile`, `backend/Dockerfile.worker`, and `frontend/Dockerfile`.

## Local Run Matrix

### 1. Docker Compose development

```bash
docker compose up -d --build
```

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/api/v1/health/live`
- Readiness: `http://localhost:8000/api/v1/health/ready`

### 2. Local backend without Docker

```bash
cp .env.example .env
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 3. Local frontend without Docker

```bash
cd frontend
npm ci
VITE_API_BASE_URL=/api/v1 VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

### 4. Hosted split deployment

- Frontend build-time env: `VITE_API_BASE_URL=https://api.example.com/api/v1`
- Backend env: `DATABASE_URL`, `LLM_API_KEY`, `LLM_API_BASE_URL`, `ADMIN_EXTERNAL_ID`, `ADMIN_BOOTSTRAP_EMAIL`, `ADMIN_BOOTSTRAP_PASSWORD`, `REDIS_URL` when queue mode is enabled
- Worker env: same backend storage/database/queue settings

## API Contract

Canonical notebook tutoring flow:

1. `POST /api/v1/auth/register` or `POST /api/v1/auth/login`
2. `POST /api/v1/ingest/upload`
3. `POST /api/v1/notebooks`
4. `POST /api/v1/notebooks/{notebook_id}/resources`
5. `POST /api/v1/notebooks/{notebook_id}/sessions`
6. `POST /api/v1/tutor/notebooks/{notebook_id}/turn`
7. `POST /api/v1/sessions/{session_id}/end`

Deprecated legacy routes intentionally return `410 Gone`:

- `POST /api/v1/sessions/resource`
- `POST /api/v1/tutor/turn`

## BYOK Policy

StudyAgent supports optional BYOK headers on live tutoring and notebook-session creation:

- `X-LLM-Api-Key`
- `X-LLM-Api-Base-Url`

If BYOK is omitted, the server uses `LLM_API_KEY` when configured. Uploads and queued preparation always use platform-managed credentials, not BYOK headers. Keys are never persisted, logged, or traced.

## Credits Policy

- Hosted live tutoring with BYOK bypasses platform billing.
- Hosted live tutoring without BYOK, uploads, and queued preparation consume platform credits when `CREDITS_ENABLED=true`.
- New accounts receive a signup research grant.
- Admins can run the monthly research grant refresh from the admin dashboard or `POST /api/v1/billing/admin/monthly-grant`.

## Quality Bar

Before deployment:

- backend tests must pass
- frontend lint, tests, and build must pass
- Docker images must build cleanly
- deploy smoke tests must pass `/health/live`, `/health/ready`, and the authenticated flow when smoke credentials are configured

## Documentation

- Release audit: `docs/RELEASE-READINESS-AUDIT-2026-03-08.md`
- Remediation tracker: `tickets/TICKETS-RELEASE-READINESS-REMEDIATION.md`
- Deploy webhook contract: `docs/DEPLOY-WEBHOOK-OPS.md`
- Hosting rollout plan: `docs/HOSTING-ROLL-OUT-PLAN.md`

## License

MIT
