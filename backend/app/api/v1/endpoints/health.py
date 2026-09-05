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
    )
