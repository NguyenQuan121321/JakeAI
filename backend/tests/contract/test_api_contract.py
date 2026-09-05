"""API Schema Drift and Contract Test Suite.

Verifies backward compatibility, OpenAPI 3.1.0 specifications,
and endpoint contracts against committed openapi.json.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

OPENAPI_PATH = Path(__file__).resolve().parent.parent.parent / "openapi.json"


@pytest.fixture(scope="module")
def runtime_openapi() -> dict[str, Any]:
    """Extract runtime generated OpenAPI specification from FastAPI application."""
    return app.openapi()


@pytest.fixture(scope="module")
def committed_openapi() -> dict[str, Any]:
    """Load committed baseline OpenAPI specification from disk."""
    if not OPENAPI_PATH.exists():
        pytest.fail(f"Committed OpenAPI spec not found at: {OPENAPI_PATH}")
    with open(OPENAPI_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_openapi_schema_metadata(runtime_openapi: dict[str, Any]) -> None:
    """Validate OpenAPI document structure and info metadata."""
    assert "openapi" in runtime_openapi
    assert runtime_openapi["info"]["title"] == "JakeAI Platform"
    assert "paths" in runtime_openapi
    assert len(runtime_openapi["paths"]) > 0


def test_critical_endpoints_exist(runtime_openapi: dict[str, Any]) -> None:
    """Ensure all core architectural endpoints are registered and exposed."""
    paths = runtime_openapi["paths"]

    critical_routes: dict[str, list[str]] = {
        "/health": ["get"],
        "/api/v1/health": ["get"],
        "/api/v1/chat/stream": ["post"],
        "/api/v1/rag/ingest": ["post"],
        "/api/v1/rag/query": ["post"],
        "/api/v1/byok/keys": ["post", "get"],
        "/api/v1/gateway/chat/completions": ["post"],
        "/api/v1/billing/webhook": ["post"],
        "/api/v1/billing/subscription": ["get"],
        "/api/v1/analytics/dashboard": ["get"],
        "/api/v1/devops/audit-pr": ["post"],
    }

    for path, methods in critical_routes.items():
        assert path in paths, f"Critical route '{path}' is missing from OpenAPI schema"
        for method in methods:
            assert method in paths[path], (
                f"HTTP method '{method.upper()}' missing on '{path}'"
            )


def test_chat_sse_contract(runtime_openapi: dict[str, Any]) -> None:
    """Verify Server-Sent Events contract for /api/v1/chat/stream."""
    chat_path = runtime_openapi["paths"]["/api/v1/chat/stream"]["post"]

    # Must produce text/event-stream
    responses = chat_path.get("responses", {})
    assert "200" in responses, "Status 200 response definition missing"
    content = responses["200"].get("content", {})
    assert "text/event-stream" in content, (
        "Chat stream endpoint must specify 'text/event-stream' content type"
    )

    # Request body must support prompt and query aliases
    request_body = chat_path.get("requestBody", {})
    ref = (
        request_body.get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
    )
    assert ref is not None, "Chat stream requestBody schema ref missing"

    schema_name = ref.split("/")[-1]
    schemas = runtime_openapi.get("components", {}).get("schemas", {})
    chat_schema = schemas.get(schema_name, {})

    properties = chat_schema.get("properties", {})
    assert "prompt" in properties, "Property 'prompt' missing in ChatStreamRequest"
    assert "query" in properties, "Property 'query' missing in ChatStreamRequest"


def test_rag_ingest_contract(runtime_openapi: dict[str, Any]) -> None:
    """Verify document ingestion contract for /api/v1/rag/ingest."""
    rag_path = runtime_openapi["paths"]["/api/v1/rag/ingest"]["post"]

    ref = (
        rag_path.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
    )
    schema_name = ref.split("/")[-1]
    schemas = runtime_openapi.get("components", {}).get("schemas", {})
    ingest_schema = schemas.get(schema_name, {})

    properties = ingest_schema.get("properties", {})
    assert "content" in properties, (
        "Property 'content' missing in DocumentIngestRequest"
    )
    assert "text" in properties, (
        "Property 'text' alias missing in DocumentIngestRequest"
    )


def test_backward_compatibility_no_deleted_endpoints(
    runtime_openapi: dict[str, Any], committed_openapi: dict[str, Any]
) -> None:
    """Detect breaking changes: no previously published endpoint may be deleted."""
    runtime_paths = runtime_openapi.get("paths", {})
    committed_paths = committed_openapi.get("paths", {})

    missing_endpoints: list[str] = []
    missing_methods: list[str] = []

    for path, methods in committed_paths.items():
        if path not in runtime_paths:
            missing_endpoints.append(path)
            continue
        for method in methods:
            if method not in runtime_paths[path]:
                missing_methods.append(f"{method.upper()} {path}")

    assert not missing_endpoints, (
        f"Breaking change detected! Endpoints removed: {missing_endpoints}"
    )
    assert not missing_methods, (
        f"Breaking change detected! HTTP methods removed: {missing_methods}"
    )
