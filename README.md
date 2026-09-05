# JakeAI Platform

Enterprise-grade embedded AI platform (AI nhúng) that integrates with **FinnApiGo** as its upstream Identity, Authorization, and Business Core service.

---

## Architectural Overview

JakeAI is designed as an end-to-end multi-agent conversational AI service with zero CSS bleeding, sub-millisecond semantic caching, multi-tenancy enforcement, and real-time Server-Sent Events (SSE) streaming.

```
                  +-----------------------------------+
                  |         Host Application          |
                  |  (Browser / Web / Mobile App)     |
                  +-----------------+-----------------+
                                    |
                           JWT Auth | Embedded Widget SDK
                                    v
+-----------------------------------------------------------------------+
| JakeAI Gateway & Policy Enforcement (FastAPI)                         |
|   - FinnApiGo JWT verification (RS256 / JWKS)                         |
|   - Multi-tenant context injection (TenantContext)                    |
|   - Redis-backed rate limiting & semantic caching                     |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
| LangGraph Multi-Agent Orchestrator                                    |
|   - Supervisor / Router Node                                          |
|   - Financial Specialist Agent Node                                   |
|   - FinnApiGo Tool Executor Node                                      |
|   - Groundedness & Self-RAG Verifier Node                             |
|   - Markdown Synthesizer Node                                         |
+-------------------+-------------------------------+-------------------+
                    |                               |
                    v                               v
+-----------------------+               +-----------------------+
| Redis 7 (Async State) |               | Qdrant Vector Store   |
| - Exact Match Cache   |               | - Multi-Tenant RAG    |
| - Rate Limiter Buckets|               | - BM25 + Dense Hybrid |
+-----------------------+               +-----------------------+
```

---

## Monorepo Layout

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml            # Automated linting, typing, testing & OpenAPI validation
│       └── cd.yml            # Multi-stage Docker container build & GHCR publishing
├── backend/
│   ├── app/
│   │   ├── api/              # API router and versioned endpoints (v1)
│   │   ├── core/             # Configuration, logging, and security
│   │   └── main.py           # FastAPI application entrypoint & OpenAPI generator
│   ├── tests/                # Pytest async test suite
│   ├── .ruff.toml            # Strict Ruff linter and formatter configuration
│   ├── mypy.ini              # Strict static typing configuration
│   ├── Dockerfile            # Multi-stage secure production container
│   ├── pyproject.toml        # Modern Python packaging configuration
│   └── requirements.txt      # Pinned backend dependencies
├── frontend/                 # Embeddable Shadow-DOM widget SDK (Phase 7)
├── docker-compose.yml        # Local orchestration (Backend, Redis, Qdrant)
├── Makefile                  # Developer workflow automation
└── README.md
```

---

## Quick Start

### Prerequisites
- Python 3.11+ (Python 3.12 recommended)
- `uv` or `pip`
- Docker & Docker Compose

### Local Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/NguyenQuan121321/JakeAI.git
   cd JakeAI
   ```

2. **Set up Virtual Environment**:
   ```bash
   cd backend
   uv venv --python 3.12 .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -r requirements.txt
   ```

3. **Start Infrastructure Services**:
   ```bash
   docker compose up -d redis qdrant
   ```

4. **Launch Backend Service**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Access Interactive Documentation**:
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - Health Probe: [http://localhost:8000/health](http://localhost:8000/health)

---

## Quality Assurance & Testing

Run linting, formatting checks, type checking, and automated tests:

```bash
# Check linting & code formatting
ruff check backend/
ruff format --check backend/

# Run static type analysis
mypy --config-file backend/mypy.ini backend/app

# Run async test suite with coverage
pytest --cov=backend/app backend/tests/ -v
```
