# StudyAgent

AI-powered tutoring system that ingests educational PDFs into a searchable knowledge base and runs agentic tutoring workflows.

## Features

- **Grounded Tutoring**: Responses grounded in ingested resource content
- **Adaptive Instruction**: Adapts explanations, examples, and pacing to the learner
- **Objective-based Learning**: Teaches via learning objectives with concept scopes
- **Multi-concept Scope**: Each turn can involve primary, support, and prerequisite concepts

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Python 3.11+, SQLAlchemy 2.0 |
| Database | PostgreSQL + pgvector |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, shadcn/ui |
| AI/ML | OpenAI-compatible LLM API, sentence-transformers embeddings |
| Optional | Neo4j, Redis, MinIO |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ (20 recommended)

### 1. Start Infrastructure

```bash
docker-compose up -d
```

### 2. Setup Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy and configure environment
cp ../.env.example ../.env
# Edit .env with your LLM API key

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --port 8000
```

### 3. Setup Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Access the Application

- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/v1/health

## Project Structure

```
tutorAI/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API endpoints
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── services/        # Business logic
│   │   ├── agents/          # AI agents
│   │   ├── utils/           # Utilities
│   │   └── db/              # Database layer
│   ├── alembic/             # Migrations
│   └── tests/               # Backend tests
├── frontend/
│   └── src/
│       ├── api/             # API client
│       ├── components/      # React components
│       ├── hooks/           # React Query hooks
│       ├── pages/           # Page components
│       ├── stores/          # Zustand stores
│       ├── types/           # TypeScript types
│       └── utils/           # Utilities
├── docker/                  # Docker configurations
├── docs/                    # Specifications
└── tickets/                 # Implementation tickets
```

## API Endpoints

### Ingestion
- `POST /api/v1/ingest/upload` - Upload resource and start ingestion
- `GET /api/v1/ingest/status/{job_id}` - Get ingestion progress

### Sessions
- `POST /api/v1/sessions/resource` - Create session bound to a resource
- `GET /api/v1/sessions/{session_id}` - Inspect session

### Tutoring
- `POST /api/v1/tutor/turn` - Execute one tutoring turn

## Documentation

See `/docs/REBUILD-*.md` for detailed specifications:
- Architecture Overview
- Data Model and Storage
- Ingestion and Knowledge Base
- Tutoring Workflows and Agents
- Multi-Concept Objectives and Planning
- Runbook (Local Dev, Deploy, Ops)
- RL Training and Environment
- Frontend and API Contract
- Testing and Evaluation

## License

MIT
