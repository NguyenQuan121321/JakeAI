"""Unit and integration tests for service health probes and OpenAPI schema."""

import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.main import export_openapi_spec


@pytest.mark.asyncio
async def test_root_health_endpoint(async_client: AsyncClient) -> None:
    """Verify root health probe returns 200 OK and expected diagnostic schema."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == get_settings().VERSION
    assert data["environment"] == get_settings().ENVIRONMENT
    assert "timestamp" in data
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_v1_health_endpoint(async_client: AsyncClient) -> None:
    """Verify versioned API v1 health probe returns 200 OK."""
    response = await async_client.get(f"{get_settings().API_V1_STR}/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == get_settings().VERSION


@pytest.mark.asyncio
async def test_openapi_schema_generation(async_client: AsyncClient) -> None:
    """Verify OpenAPI specification complies with OpenAPI 3.0 and FinnApiGoAuth."""
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == get_settings().PROJECT_NAME
    assert schema["info"]["version"] == get_settings().VERSION

    # Validate FinnApiGo security scheme
    components = schema.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    assert "FinnApiGoAuth" in security_schemes
    assert security_schemes["FinnApiGoAuth"]["type"] == "http"
    assert security_schemes["FinnApiGoAuth"]["scheme"] == "bearer"
    assert security_schemes["FinnApiGoAuth"]["bearerFormat"] == "JWT"

    # Validate security requirements
    assert {"FinnApiGoAuth": []} in schema.get("security", [])


@pytest.mark.asyncio
async def test_swagger_and_redoc_documentation_pages(
    async_client: AsyncClient,
) -> None:
    """Verify Swagger UI and ReDoc HTML documentation endpoints load successfully."""
    docs_response = await async_client.get("/docs")
    assert docs_response.status_code == 200
    assert "swagger-ui" in docs_response.text.lower()

    redoc_response = await async_client.get("/redoc")
    assert redoc_response.status_code == 200
    assert "redoc" in redoc_response.text.lower()


def test_export_openapi_cli() -> None:
    """Verify static export of OpenAPI specification to file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "test_openapi.json"
        export_openapi_spec(str(output_file))
        assert output_file.exists()
        assert output_file.stat().st_size > 0
