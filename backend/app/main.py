"""FastAPI Application Entrypoint and OpenAPI Specification Generator."""

import argparse
import json
import logging
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.v1.api import api_router
from app.api.v1.endpoints import coding, gateway
from app.api.v1.endpoints.health import (
    HealthResponse,
    check_health,
    check_liveness,
    check_readiness,
)
from app.core.config import get_settings
from app.providers.errors import ErrorCategory, ProviderError
from app.telemetry.metrics import metrics
from app.telemetry.tracing import (
    create_or_inherit_trace_context,
    set_current_trace_context,
)

logger = logging.getLogger("jakeai.main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown resource lifecycle."""
    logger.info("JakeAI platform initializing...")
    yield
    logger.info("JakeAI platform shutting down, releasing resources...")
    from app.optimizer.semantic_cache import get_semantic_cache_manager
    from app.rag.tasks import get_task_manager
    from app.services.ai_gateway import get_quota_manager

    for manager in (
        get_quota_manager(),
        get_semantic_cache_manager(),
        get_task_manager(),
    ):
        client = getattr(manager, "redis_client", None)
        if client is not None:
            with suppress(Exception):
                await client.aclose()
            manager.redis_client = None


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request Size Limiting and Tracing Middleware
    @app.middleware("http")
    async def request_size_and_tracing_middleware(
        request: Request, call_next: Any
    ) -> Response:
        """Enforce request body ceiling, trace correlation ID, and record latency metrics."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={
                            "detail": f"Request entity too large. Maximum permitted size is {settings.MAX_REQUEST_BODY_BYTES} bytes."
                        },
                    )
            except ValueError:
                pass

        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id

        # W3C Distributed Tracing (TASK OPS-07)
        traceparent = request.headers.get("traceparent")
        tracestate = request.headers.get("tracestate")
        trace_ctx = create_or_inherit_trace_context(
            traceparent_header=traceparent,
            tracestate_header=tracestate,
            fallback_correlation_id=correlation_id,
        )
        request.state.trace_context = trace_ctx
        set_current_trace_context(trace_ctx)

        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            metrics.record_http_request(
                request.method, request.url.path, 500, duration_ms
            )
            set_current_trace_context(None)
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        response.headers["traceparent"] = trace_ctx.to_traceparent()
        if trace_ctx.tracestate:
            response.headers["tracestate"] = trace_ctx.tracestate

        set_current_trace_context(None)

        metrics.record_http_request(
            request.method, request.url.path, response.status_code, duration_ms
        )
        return response

    # Global Exception Handler for Normalized Provider Errors
    @app.exception_handler(ProviderError)
    async def provider_error_handler(
        _request: Request, exc: ProviderError
    ) -> JSONResponse:
        """Normalize upstream provider errors with strict zero credential leakage."""
        metrics.record_provider_error(exc.provider, exc.category.value)
        status_map = {
            ErrorCategory.AUTHENTICATION: status.HTTP_401_UNAUTHORIZED,
            ErrorCategory.QUOTA: status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCategory.CONTEXT_LIMIT: status.HTTP_400_BAD_REQUEST,
            ErrorCategory.POLICY_REJECTED: status.HTTP_400_BAD_REQUEST,
            ErrorCategory.PROVIDER_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCategory.RETRYABLE: status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.status_code != 408
            else status.HTTP_408_REQUEST_TIMEOUT,
            ErrorCategory.NON_RETRYABLE: status.HTTP_400_BAD_REQUEST,
        }
        http_status = status_map.get(exc.category, status.HTTP_502_BAD_GATEWAY)
        headers = {}
        if exc.retry_after_seconds:
            headers["Retry-After"] = str(int(exc.retry_after_seconds))

        return JSONResponse(
            status_code=http_status,
            content={
                "error": {
                    "message": exc.message,
                    "type": exc.category.value,
                    "provider": exc.provider,
                    "model": exc.model,
                }
            },
            headers=headers,
        )

    # Direct root probes for container orchestrators
    app.add_api_route(
        "/health",
        check_health,
        methods=["GET"],
        response_model=HealthResponse,
        status_code=status.HTTP_200_OK,
        summary="Root Health Probe",
        description="Direct container liveness and readiness probe.",
        tags=["Health"],
    )
    app.add_api_route(
        "/health/live",
        check_liveness,
        methods=["GET"],
        response_model=HealthResponse,
        status_code=status.HTTP_200_OK,
        summary="Root Liveness Probe",
        description="Direct container liveness probe.",
        tags=["Health"],
    )
    app.add_api_route(
        "/health/ready",
        check_readiness,
        methods=["GET"],
        response_model=HealthResponse,
        status_code=status.HTTP_200_OK,
        summary="Root Readiness Probe",
        description="Direct container readiness probe.",
        tags=["Health"],
    )

    @app.get(
        "/metrics",
        response_class=PlainTextResponse,
        summary="Prometheus Metrics Exposition",
        description="Scrape endpoint serving platform, provider, and agent telemetry in Prometheus text format.",
        tags=["Observability"],
    )
    async def get_prometheus_metrics() -> Response:
        return PlainTextResponse(
            content=metrics.generate_prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # Mount API v1 router
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Mount Root OpenAI-compatible AI Gateway alias (/v1/chat/completions, /v1/models)
    app.include_router(
        gateway.router, prefix="/v1", tags=["OpenAI Compatible AI Gateway"]
    )

    # Mount ADR-001 Internal Coding Resume Bridge (/internal/v1/coding/resume)
    app.include_router(
        coding.router, prefix="/internal/v1/coding", tags=["Internal Coding Bridge"]
    )

    def custom_openapi() -> dict[str, Any]:
        """Generate custom OpenAPI schema with FinnApiGo security schemes."""
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=settings.PROJECT_NAME,
            version=settings.VERSION,
            description=settings.DESCRIPTION,
            routes=app.routes,
            tags=[
                {
                    "name": "Health",
                    "description": "Service health probes and uptime diagnostics",
                },
                {
                    "name": "Chat",
                    "description": (
                        "Server-Sent Events (SSE) streaming chat endpoints "
                        "powered by LangGraph"
                    ),
                },
                {
                    "name": "RAG",
                    "description": (
                        "Document ingestion, chunking, and tenant retrieval operations"
                    ),
                },
                {
                    "name": "BYOK",
                    "description": (
                        "Bring Your Own Key (BYOK) credential management and AES-256-GCM encryption"
                    ),
                },
                {
                    "name": "DevOps Bot",
                    "description": (
                        "Automated PR review, diff pruning, and changelog generation"
                    ),
                },
                {
                    "name": "AI Gateway",
                    "description": (
                        "OpenAI-compatible inference reverse proxy with caching and token quotas"
                    ),
                },
                {
                    "name": "Billing",
                    "description": (
                        "VietQR and PayOS webhook payment processing and subscription tier management"
                    ),
                },
                {
                    "name": "Analytics",
                    "description": (
                        "Real-time operational telemetry, cost savings, and token efficiency metrics"
                    ),
                },
            ],
        )

        # Ensure components and securitySchemes exist
        components = openapi_schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})

        # Define FinnApiGo JWT Bearer authentication scheme
        security_schemes["FinnApiGoAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "FinnApiGo asymmetric RS256/HS256 JWT access token. "
                "Must contain 'sub', 'tenant_id', and authorized roles/scopes."
            ),
        }

        # Apply global security requirement scheme
        openapi_schema["security"] = [{"FinnApiGoAuth": []}]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_application()


def export_openapi_spec(output_path: str = "openapi.json") -> None:
    """Export the compiled OpenAPI schema to a static JSON file."""
    schema = app.openapi()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"OpenAPI specification successfully exported to: {target.resolve()}")


def main() -> None:
    """CLI handler for server startup and OpenAPI export."""
    parser = argparse.ArgumentParser(
        description="JakeAI Backend Application Management"
    )
    parser.add_argument(
        "--export-openapi",
        nargs="?",
        const="openapi.json",
        default=None,
        help="Export static OpenAPI schema JSON to specified path",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",  # nosec B104
        help="Server host address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )

    args = parser.parse_args()

    if args.export_openapi is not None:
        export_openapi_spec(args.export_openapi)
        sys.exit(0)

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=True)


if __name__ == "__main__":
    main()
