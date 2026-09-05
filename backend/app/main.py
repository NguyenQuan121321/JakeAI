"""FastAPI Application Entrypoint and OpenAPI Specification Generator."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.v1.api import api_router
from app.api.v1.endpoints.health import HealthResponse, check_health
from app.core.config import get_settings


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
    )

    # Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Direct root probe for container orchestrators
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

    # Mount API v1 router
    app.include_router(api_router, prefix=settings.API_V1_STR)

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
                    "name": "Gateway",
                    "description": (
                        "FinnApiGo perimeter security, policy enforcement and SSE"
                    ),
                },
                {
                    "name": "Multi-Agent",
                    "description": (
                        "LangGraph multi-agent financial reasoning and orchestration"
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
        default="0.0.0.0",
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
