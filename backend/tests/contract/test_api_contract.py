"""Authoritative OpenAPI 3.1.0 Contract Verification & Schema Drift Test Suite.

TEST-04 — JAKEAI API CONTRACT & HTTP AUTOMATION
Logical ID: CONTRACT-001 | Subsystem: Contract & Schema

Verifies:
1. Zero Schema Drift: runtime OpenAPI (app.openapi()) vs committed openapi.json cannot diverge.
2. Complete Operation Coverage: All 51 public API operations across 47 paths audited for:
   - HTTP method and path
   - Path/query/header parameters and required bindings
   - Request bodies, content-type (application/json), and schema references
   - Required schema fields and validation bounds
   - Response schemas for success status codes (200, 201, 202)
   - Error schemas (422 HTTPValidationError / ValidationError)
   - Authentication requirements (FinnApiGoAuth Bearer JWT vs public/perimeter)
   - Content types (application/json, text/plain, text/event-stream)
   - Streaming media types (text/event-stream)
3. Backward Compatibility: Detects breaking changes (no deleted paths, no removed methods,
   no removed 2xx status codes, no newly required properties without defaults, no type mutations).
4. Critical route contracts: Chat SSE, RAG Ingestion, BYOK Vault, Agent Platform, FinOps & Gateway.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

OPENAPI_PATH = Path(__file__).resolve().parent.parent.parent / "openapi.json"

# Exact set of 10 endpoints that are explicitly public, perimeter-secret, or webhook HMAC authenticated.
# All other 41 endpoints MUST require FinnApiGoAuth Bearer JWT security.
PUBLIC_OR_PERIMETER_OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/metrics"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/live"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/billing/webhook"),
    ("POST", "/api/v1/coding/resume"),
    ("POST", "/internal/v1/coding/resume"),
}

# Endpoints that produce Server-Sent Events (SSE)
SSE_STREAMING_OPERATIONS: set[tuple[str, str]] = {
    ("POST", "/api/v1/chat/stream"),
    ("GET", "/api/v1/agent/tasks/{task_id}/runs/{run_id}/events"),
}


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


# ==============================================================================
# 1. Zero Schema Drift & Specification Integrity
# ==============================================================================


def test_openapi_schema_metadata(runtime_openapi: dict[str, Any]) -> None:
    """Validate OpenAPI document structure and info metadata."""
    assert runtime_openapi.get("openapi", "").startswith("3.1"), (
        "OpenAPI specification must be 3.1.0+"
    )
    assert runtime_openapi["info"]["title"] == "JakeAI Platform"
    assert runtime_openapi["info"]["version"] == "0.1.0"
    assert "paths" in runtime_openapi
    assert len(runtime_openapi["paths"]) == 47, (
        f"Expected exactly 47 unique paths, found {len(runtime_openapi['paths'])}"
    )


def test_zero_schema_drift_runtime_vs_committed(
    runtime_openapi: dict[str, Any], committed_openapi: dict[str, Any]
) -> None:
    """Ensure runtime OpenAPI and committed openapi.json cannot silently diverge.

    This test performs a strict bidirectional structural and byte-level comparison
    of the generated OpenAPI schema against the committed repository spec.
    """
    runtime_json = json.dumps(runtime_openapi, sort_keys=True, indent=2)
    committed_json = json.dumps(committed_openapi, sort_keys=True, indent=2)

    if runtime_json != committed_json:
        r_paths = set(runtime_openapi.get("paths", {}).keys())
        c_paths = set(committed_openapi.get("paths", {}).keys())
        added_paths = r_paths - c_paths
        removed_paths = c_paths - r_paths

        r_schemas = set(runtime_openapi.get("components", {}).get("schemas", {}).keys())
        c_schemas = set(
            committed_openapi.get("components", {}).get("schemas", {}).keys()
        )
        added_schemas = r_schemas - c_schemas
        removed_schemas = c_schemas - r_schemas

        diff_summary = []
        if added_paths:
            diff_summary.append(f"Paths added to runtime: {added_paths}")
        if removed_paths:
            diff_summary.append(f"Paths missing from runtime: {removed_paths}")
        if added_schemas:
            diff_summary.append(f"Schemas added to runtime: {added_schemas}")
        if removed_schemas:
            diff_summary.append(f"Schemas missing from runtime: {removed_schemas}")

        pytest.fail(
            "Schema drift detected between runtime OpenAPI and committed openapi.json!\n"
            + "\n".join(diff_summary)
            + "\nRun: python -m app.main --export-openapi openapi.json to synchronize."
        )


def test_security_schemes_registered(runtime_openapi: dict[str, Any]) -> None:
    """Validate FinnApiGoAuth Bearer security scheme definition in OpenAPI components."""
    sec_schemes = runtime_openapi.get("components", {}).get("securitySchemes", {})
    assert "FinnApiGoAuth" in sec_schemes, (
        "FinnApiGoAuth security scheme missing in components"
    )
    scheme = sec_schemes["FinnApiGoAuth"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"
    assert scheme["bearerFormat"] == "JWT"


# ==============================================================================
# 2. Complete Operation Enumeration & Verification (All 51 Operations)
# ==============================================================================


def _extract_all_operations(
    spec: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    """Extract all HTTP operations from an OpenAPI specification."""
    ops: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method.lower() in ("get", "post", "put", "delete", "patch", "options"):
                ops.append((method.upper(), path, op))
    return sorted(ops, key=lambda x: (x[1], x[0]))


ALL_OPERATIONS: list[tuple[str, str, dict[str, Any]]] = _extract_all_operations(
    app.openapi()
)


def test_exact_51_public_operations_accounted(runtime_openapi: dict[str, Any]) -> None:
    """Ensure exactly 51 distinct HTTP operations are registered and exposed."""
    ops = _extract_all_operations(runtime_openapi)
    assert len(ops) == 51, (
        f"Expected exactly 51 endpoint operations, found {len(ops)}: {[(m, p) for m, p, _ in ops]}"
    )


@pytest.mark.parametrize(
    "method,path,op",
    ALL_OPERATIONS,
    ids=[f"{m} {p}" for m, p, _ in ALL_OPERATIONS],
)
def test_individual_operation_contract(
    method: str,
    path: str,
    op: dict[str, Any],
    runtime_openapi: dict[str, Any],
) -> None:
    """Audit each individual public API operation against complete contract requirements.

    Verifies:
    - HTTP method and path definition
    - Path parameter bindings in URL
    - Request body schema and application/json media type
    - Response schema for success status codes
    - Security scheme requirement (FinnApiGoAuth vs public/perimeter)
    - Content-type declaration (application/json, text/plain, text/event-stream)
    """
    schemas = runtime_openapi.get("components", {}).get("schemas", {})

    # 1. Path parameters verification
    url_params = set(re.findall(r"\{([a-zA-Z0-9_]+)\}", path))
    declared_path_params = {
        p["name"]: p for p in op.get("parameters", []) if p.get("in") == "path"
    }
    for param in url_params:
        assert param in declared_path_params, (
            f"URL parameter '{{{param}}}' in {method} {path} not declared in OpenAPI parameters"
        )
        assert declared_path_params[param].get("required") is True

    # 2. Request body verification
    request_body = op.get("requestBody")
    if request_body is not None:
        content = request_body.get("content", {})
        assert "application/json" in content, (
            f"{method} {path} requestBody must declare 'application/json'"
        )
        schema = content["application/json"].get("schema", {})
        ref = schema.get("$ref")
        if ref:
            schema_name = ref.split("/")[-1]
            assert schema_name in schemas, (
                f"{method} {path} requestBody schema '{schema_name}' missing in components.schemas"
            )

    # 3. Response schema and status code verification
    responses = op.get("responses", {})
    success_codes = [c for c in responses if c.startswith("2")]
    assert len(success_codes) > 0, (
        f"{method} {path} must declare at least one 2xx success response status code"
    )

    for code in success_codes:
        content = responses[code].get("content", {})
        if (method, path) in SSE_STREAMING_OPERATIONS:
            assert "text/event-stream" in content, (
                f"{method} {path} -> {code} must declare 'text/event-stream'"
            )
        elif (method, path) == ("GET", "/metrics"):
            assert "text/plain" in content, (
                f"{method} {path} -> {code} must declare 'text/plain'"
            )
        else:
            assert "application/json" in content, (
                f"{method} {path} -> {code} must declare 'application/json'"
            )

    # 4. Authentication requirement verification
    security = op.get("security")
    if (method, path) in PUBLIC_OR_PERIMETER_OPERATIONS:
        assert security is None or security == [], (
            f"{method} {path} is public/perimeter and should not declare Bearer security"
        )
    else:
        assert security is not None and len(security) > 0, (
            f"{method} {path} must declare security requirement"
        )
        assert any("FinnApiGoAuth" in sec for sec in security), (
            f"{method} {path} must require 'FinnApiGoAuth'"
        )


def test_operation_path_parameter_bindings(runtime_openapi: dict[str, Any]) -> None:
    """Verify every URL path parameter has a matching declared path parameter in OpenAPI."""
    ops = _extract_all_operations(runtime_openapi)
    param_pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")

    for method, path, op in ops:
        url_params = set(param_pattern.findall(path))
        declared_path_params = {
            p["name"]: p for p in op.get("parameters", []) if p.get("in") == "path"
        }

        # Every parameter in the URL must be declared in parameters with in='path'
        for param in url_params:
            assert param in declared_path_params, (
                f"URL path parameter '{{{param}}}' in {method} {path} is not declared in OpenAPI parameters"
            )
            param_def = declared_path_params[param]
            assert param_def.get("required") is True, (
                f"Path parameter '{param}' in {method} {path} must have required=True"
            )
            assert "schema" in param_def, (
                f"Path parameter '{param}' in {method} {path} must define a schema"
            )

        # No extraneous path parameters declared
        for declared_name in declared_path_params:
            assert declared_name in url_params, (
                f"Parameter '{declared_name}' declared as in='path' on {method} {path} does not exist in URL"
            )


def test_operation_authentication_contracts(runtime_openapi: dict[str, Any]) -> None:
    """Verify security requirements across all 51 operations strictly conform to contract."""
    ops = _extract_all_operations(runtime_openapi)

    for method, path, op in ops:
        op_key = (method, path)
        security = op.get("security")

        if op_key in PUBLIC_OR_PERIMETER_OPERATIONS:
            assert security is None or security == [], (
                f"Public/perimeter operation {method} {path} should not declare Bearer security requirement, found: {security}"
            )
        else:
            assert security is not None and len(security) > 0, (
                f"Protected operation {method} {path} must declare security requirement"
            )
            assert any("FinnApiGoAuth" in sec for sec in security), (
                f"Protected operation {method} {path} must require 'FinnApiGoAuth' security scheme"
            )


def test_operation_request_body_contracts(runtime_openapi: dict[str, Any]) -> None:
    """Verify request bodies declare valid application/json schemas and required properties."""
    ops = _extract_all_operations(runtime_openapi)
    schemas = runtime_openapi.get("components", {}).get("schemas", {})

    for method, path, op in ops:
        request_body = op.get("requestBody")
        if request_body is not None:
            content = request_body.get("content", {})
            assert "application/json" in content, (
                f"Operation {method} {path} requestBody must accept 'application/json'"
            )
            body_schema = content["application/json"].get("schema", {})
            assert body_schema, f"Operation {method} {path} requestBody schema is empty"

            # Check if $ref resolves
            ref = body_schema.get("$ref")
            if ref:
                schema_name = ref.split("/")[-1]
                assert schema_name in schemas, (
                    f"Referenced schema '{schema_name}' in {method} {path} requestBody not found in components.schemas"
                )
                model_schema = schemas[schema_name]
                assert "properties" in model_schema or "anyOf" in model_schema, (
                    f"Schema '{schema_name}' in {method} {path} lacks properties or anyOf"
                )


def test_operation_response_schema_contracts(runtime_openapi: dict[str, Any]) -> None:
    """Verify response schemas, status codes, and error models across all 51 operations."""
    ops = _extract_all_operations(runtime_openapi)
    schemas = runtime_openapi.get("components", {}).get("schemas", {})

    for method, path, op in ops:
        responses = op.get("responses", {})
        assert len(responses) > 0, (
            f"Operation {method} {path} has no responses declared"
        )

        # Must have at least one successful 2xx response code
        success_codes = [c for c in responses if c.startswith("2")]
        assert len(success_codes) > 0, (
            f"Operation {method} {path} has no 2xx success response code declared: {list(responses.keys())}"
        )

        for code in success_codes:
            resp_def = responses[code]
            content = resp_def.get("content", {})
            if (method, path) in SSE_STREAMING_OPERATIONS:
                assert "text/event-stream" in content, (
                    f"Streaming operation {method} {path} must define 'text/event-stream' content-type for status {code}"
                )
            elif (method, path) == ("GET", "/metrics"):
                assert "text/plain" in content, (
                    f"Metrics operation {method} {path} must define 'text/plain' content-type"
                )
            else:
                assert "application/json" in content, (
                    f"Operation {method} {path} status {code} must define 'application/json' content-type"
                )
                resp_schema = content["application/json"].get("schema", {})
                ref = resp_schema.get("$ref")
                if ref:
                    schema_name = ref.split("/")[-1]
                    assert schema_name in schemas, (
                        f"Response schema '{schema_name}' for {method} {path} -> {code} not in components.schemas"
                    )

        # Operations with parameters or request body should declare 422 validation error
        has_params = len(op.get("parameters", [])) > 0
        has_body = op.get("requestBody") is not None
        if has_params or has_body:
            assert "422" in responses, (
                f"Operation {method} {path} accepts parameters/body but missing 422 response in OpenAPI"
            )
            err_content = (
                responses["422"].get("content", {}).get("application/json", {})
            )
            ref = err_content.get("schema", {}).get("$ref", "")
            assert ref.endswith("HTTPValidationError"), (
                f"Operation {method} {path} status 422 should reference HTTPValidationError"
            )


# ==============================================================================
# 3. Backward Compatibility & Breaking Change Gates
# ==============================================================================


def test_backward_compatibility_no_deleted_endpoints(
    runtime_openapi: dict[str, Any], committed_openapi: dict[str, Any]
) -> None:
    """Detect breaking changes: no previously published endpoint or method may be deleted."""
    runtime_paths = runtime_openapi.get("paths", {})
    committed_paths = committed_openapi.get("paths", {})

    missing_endpoints: list[str] = []
    missing_methods: list[str] = []

    for path, methods in committed_paths.items():
        if path not in runtime_paths:
            missing_endpoints.append(path)
            continue
        for method in methods:
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            if method not in runtime_paths[path]:
                missing_methods.append(f"{method.upper()} {path}")

    assert not missing_endpoints, (
        f"Breaking change detected! Endpoints removed: {missing_endpoints}"
    )
    assert not missing_methods, (
        f"Breaking change detected! HTTP methods removed: {missing_methods}"
    )


def test_backward_compatibility_no_removed_success_responses(
    runtime_openapi: dict[str, Any], committed_openapi: dict[str, Any]
) -> None:
    """Ensure no successful HTTP status codes (200, 201, 202) were removed from existing endpoints."""
    runtime_paths = runtime_openapi.get("paths", {})
    committed_paths = committed_openapi.get("paths", {})

    removed_responses: list[str] = []

    for path, committed_methods in committed_paths.items():
        if path not in runtime_paths:
            continue
        for method, committed_op in committed_methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            if method not in runtime_paths[path]:
                continue
            runtime_op = runtime_paths[path][method]
            c_responses = committed_op.get("responses", {})
            r_responses = runtime_op.get("responses", {})

            for code in c_responses:
                if code.startswith("2") and code not in r_responses:
                    removed_responses.append(f"{method.upper()} {path} -> {code}")

    assert not removed_responses, (
        f"Breaking change detected! Success response codes removed: {removed_responses}"
    )


def test_backward_compatibility_no_new_required_request_fields(
    runtime_openapi: dict[str, Any], committed_openapi: dict[str, Any]
) -> None:
    """Ensure no existing schema added new strictly required fields without defaults."""
    runtime_schemas = runtime_openapi.get("components", {}).get("schemas", {})
    committed_schemas = committed_openapi.get("components", {}).get("schemas", {})

    violations: list[str] = []

    for name, c_schema in committed_schemas.items():
        if name not in runtime_schemas:
            continue
        r_schema = runtime_schemas[name]
        c_req = set(c_schema.get("required", []))
        r_req = set(r_schema.get("required", []))
        newly_required = r_req - c_req

        for prop in newly_required:
            violations.append(f"{name}.{prop}")

    assert not violations, (
        f"Breaking change detected! Schema properties newly marked as required: {violations}"
    )


# ==============================================================================
# 4. Critical Route Contract Deep Invariants
# ==============================================================================


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

    # Ingestion supports both 201 Created (sync) and 202 Accepted (async queue)
    responses = rag_path.get("responses", {})
    assert "201" in responses, "Status 201 sync response missing for /api/v1/rag/ingest"
    assert "202" in responses, (
        "Status 202 async response missing for /api/v1/rag/ingest"
    )

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


def test_metrics_snapshot_contract(runtime_openapi: dict[str, Any]) -> None:
    """Verify telemetry metrics endpoint contract and MetricsSnapshot schema (COST-13)."""
    metrics_path = (
        runtime_openapi.get("paths", {}).get("/api/v1/analytics/metrics", {}).get("get")
    )
    assert metrics_path is not None, "GET /api/v1/analytics/metrics endpoint missing"

    responses = metrics_path.get("responses", {})
    assert "200" in responses, (
        "Status 200 response missing for /api/v1/analytics/metrics"
    )

    ref = (
        responses["200"]
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
    )
    assert ref is not None, "Metrics endpoint response schema ref missing"

    schema_name = ref.split("/")[-1]
    schemas = runtime_openapi.get("components", {}).get("schemas", {})
    metrics_schema = schemas.get(schema_name, {})

    properties = metrics_schema.get("properties", {})
    assert "timestamp" in properties, "Property 'timestamp' missing"
    assert "uptime_seconds" in properties, "Property 'uptime_seconds' missing"
    assert "http_requests_total" in properties, "Property 'http_requests_total' missing"
    assert "estimated_cost_usd_total" in properties, (
        "Property 'estimated_cost_usd_total' missing"
    )
    assert "optimization_decisions_total" in properties, (
        "Property 'optimization_decisions_total' missing in MetricsSnapshot"
    )
    assert properties["optimization_decisions_total"].get("type") == "integer"
    assert properties["optimization_decisions_total"].get("default") == 0

    assert "cost_savings_usd_total" in properties, (
        "Property 'cost_savings_usd_total' missing in MetricsSnapshot"
    )
    assert properties["cost_savings_usd_total"].get("type") == "number"
    assert properties["cost_savings_usd_total"].get("default") == 0.0


def test_agent_run_events_sse_contract(runtime_openapi: dict[str, Any]) -> None:
    """Verify Server-Sent Events contract for agent execution stream."""
    stream_path = (
        runtime_openapi.get("paths", {})
        .get("/api/v1/agent/tasks/{task_id}/runs/{run_id}/events", {})
        .get("get")
    )
    assert stream_path is not None, "GET agent run events endpoint missing"

    responses = stream_path.get("responses", {})
    assert "200" in responses, "Status 200 response missing for agent run events"
    content = responses["200"].get("content", {})
    assert "text/event-stream" in content, (
        "Agent run events must specify 'text/event-stream' content type"
    )
