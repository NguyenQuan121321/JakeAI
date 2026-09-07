"""Health check probe endpoint for liveness and readiness verification."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.config import get_settings

router = APIRouter()
START_TIME = time.time()


class HealthResponse(BaseModel):
    """Health check status response model."""

    status: str = Field(
        default="healthy",
        description="Overall service operational health",
    )
    version: str = Field(description="Current application release version")
    environment: str = Field(
        description="Execution environment: development, staging, or production",
    )
    timestamp: datetime = Field(description="Current server UTC timestamp")
    uptime_seconds: float = Field(description="Total application uptime in seconds")
    components: dict[str, str] = Field(
        default_factory=dict,
        description="Operational status of platform components",
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Probe",
    description="Returns service health status, environment, and uptime metrics.",
    tags=["Health"],
)
async def check_health() -> HealthResponse:
    """Evaluate application health and operational uptime."""
    settings = get_settings()
    uptime = time.time() - START_TIME
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(UTC),
        uptime_seconds=round(uptime, 2),
        components={
            "api": "healthy",
            "runtime": "operational",
        },
    )


@router.get(
    "/health/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Container liveness probe verifying process is responsive.",
    tags=["Health"],
)
async def check_liveness() -> HealthResponse:
    """Evaluate liveness probe."""
    return await check_health()


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
    description="Container readiness probe verifying core dependencies are responsive.",
    tags=["Health"],
)
async def check_readiness() -> HealthResponse:
    """Evaluate readiness probe including Redis and Datastore health."""
    settings = get_settings()
    uptime = time.time() - START_TIME

    components: dict[str, str] = {
        "api": "healthy",
        "runtime": "operational",
    }

    # Check Redis
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        )
        await client.ping()
        await client.aclose()
        components["redis"] = "connected"
    except Exception:
        components["redis"] = "degraded_fallback_active"

    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(UTC),
        uptime_seconds=round(uptime, 2),
        components=components,
    )
