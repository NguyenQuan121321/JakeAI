# 00 — Setup & Environment

This section verifies that all local and perimeter dependencies are reachable and correctly initialized before proceeding to functional verification.

## Prerequisites
- **JakeAI Service**: FastAPI ASGI application running at `{{base_url}}` (default: `http://localhost:8000`).
- **FinnApiGo Identity Provider**: Go backend running at `{{finnapigo_base_url}}` (default: `http://localhost:8081` or `http://localhost:8080`).
  - *Note*: If FinnApiGo is offline, JakeAI provides built-in development fallback JWT keys that allow the entire verification suite to execute deterministically without an active Go server.
- **Redis (Port 6379)**: Tier 1 Exact Cache and distributed state locks.
  - *Note*: If Redis is unavailable, JakeAI activates in-memory degradation fallback (`degraded_fallback_active`).
- **Qdrant (Port 6333)**: Tier 2 Dense Vector Knowledge Store and Semantic Cache.
  - *Note*: FastEmbed and in-memory local fallbacks are supported.

## Execution Sequence
1. `01 — Health Smoke`: Unauthenticated liveness probe.
2. `02 — Configuration Check`: Readiness probe verifying API status, version, and component health.
3. `03 — Authentication Dependency Check`: Probe to FinnApiGo identity authority.
