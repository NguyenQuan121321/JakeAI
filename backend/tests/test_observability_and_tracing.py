"""Unit tests for Structured Telemetry, Prometheus Exposition, and W3C Distributed Tracing (TASK OPS-05, OPS-06, OPS-07, OPS-17)."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_application
from app.telemetry.events import TelemetryEvent
from app.telemetry.metrics import metrics
from app.telemetry.tracing import (
    create_or_inherit_trace_context,
    get_current_trace_context,
    parse_traceparent,
    set_current_trace_context,
    trace_span,
)


def test_structured_telemetry_event_schema_and_redaction():
    event = TelemetryEvent(
        tenant_id="tenant-123",
        correlation_id="corr-abc-999",
        component="guardrails",
        event_type="security_incident",
        duration_ms=12.5,
        metadata={
            "api_key": "sk-secret-1234567890",
            "user_prompt": "Drop database immediately",
            "safe_metric": 42,
        },
    )
    raw_json = event.to_json()
    data = json.loads(raw_json)

    assert data["tenant_id"] == "tenant-123"
    assert data["correlation_id"] == "corr-abc-999"
    assert data["component"] == "guardrails"
    assert data["event_type"] == "security_incident"
    # Sensitive keys must be redacted
    assert data["metadata"]["api_key"] == "[REDACTED]"
    assert data["metadata"]["user_prompt"] == "[REDACTED]"
    assert data["metadata"]["safe_metric"] == 42


def test_w3c_traceparent_parsing():
    # Valid traceparent
    valid_tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    parsed = parse_traceparent(valid_tp)
    assert parsed is not None
    trace_id, parent_id, sampled = parsed
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert parent_id == "00f067aa0ba902b7"
    assert sampled is True

    # Invalid versions or all-zeros trace/span IDs
    assert (
        parse_traceparent("ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        is None
    )
    assert (
        parse_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01")
        is None
    )
    assert (
        parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01")
        is None
    )
    assert parse_traceparent("invalid-format") is None
    assert parse_traceparent(None) is None


def test_trace_context_span_hierarchy():
    root_tp = "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01"
    ctx = create_or_inherit_trace_context(traceparent_header=root_tp)
    assert ctx.trace_id == "abcdef1234567890abcdef1234567890"
    assert ctx.parent_span_id == "1234567890abcdef"
    assert len(ctx.span_id) == 16

    set_current_trace_context(ctx)
    try:
        with trace_span("child_operation", attributes={"tag": "db_query"}) as span:
            assert span.name == "child_operation"
            assert span.trace_id == ctx.trace_id
            assert span.parent_span_id == ctx.span_id
            active_child = get_current_trace_context()
            assert active_child is not None
            assert active_child.trace_id == ctx.trace_id
            assert active_child.parent_span_id == ctx.span_id
        assert span.duration_ms >= 0.0
        assert span.status == "OK"
    finally:
        set_current_trace_context(None)


def test_prometheus_metrics_generation():
    metrics.reset()
    # Record various operational events
    metrics.record_http_request("GET", "/health", 200, 15.2)
    metrics.record_provider_request(
        "gemini",
        "gemini-1.5-flash",
        "success",
        120.5,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.0002,
    )
    metrics.record_stream_ttft("gemini", "gemini-1.5-flash", 85.0)
    metrics.record_security_incident("prompt_injection", "tenant-test", "layer1_regex")
    metrics.record_agent_task("completed", "tenant-test")
    metrics.record_agent_run("completed", "tenant-test")
    metrics.record_agent_tool_call("calculator", "success", "tenant-test")
    metrics.record_agent_revision("tenant-test")
    metrics.record_agent_recovery("tenant-test", success=True)
    metrics.record_agent_approval_wait(1500.0, "tenant-test")

    prom_text = metrics.generate_prometheus_metrics()
    assert "# HELP jakeai_http_requests_total" in prom_text
    assert (
        'jakeai_http_requests_total{method="GET",path="/health",status="200"} 1'
        in prom_text
    )
    assert "# HELP jakeai_provider_requests_total" in prom_text
    assert (
        'jakeai_provider_requests_total{provider="gemini",model="gemini-1.5-flash",status="success"} 1'
        in prom_text
    )
    assert "# HELP jakeai_stream_ttft_ms_avg" in prom_text
    assert (
        'jakeai_stream_ttft_ms_avg{provider="gemini",model="gemini-1.5-flash"} 85.00'
        in prom_text
    )
    assert "# HELP jakeai_safety_incidents_total" in prom_text
    assert (
        'jakeai_safety_incidents_total{incident_type="prompt_injection",layer="layer1_regex",tenant_id="tenant-test"} 1'
        in prom_text
    )
    assert "# HELP jakeai_agent_tasks_total" in prom_text
    assert (
        'jakeai_agent_tasks_total{status="completed",tenant_id="tenant-test"} 1'
        in prom_text
    )
    assert "# HELP jakeai_agent_tool_calls_total" in prom_text
    assert (
        'jakeai_agent_tool_calls_total{tool="calculator",status="success",tenant_id="tenant-test"} 1'
        in prom_text
    )
    assert 'jakeai_agent_revisions_total{tenant_id="tenant-test"} 1' in prom_text
    assert 'jakeai_agent_recovery_success_total{tenant_id="tenant-test"} 1' in prom_text


@pytest.mark.asyncio
async def test_get_metrics_endpoint_and_w3c_header():
    app = create_application()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Inbound request with traceparent
        inbound_tp = "00-11112222333344445555666677778888-aaaabbbbccccdddd-01"
        resp = await client.get("/metrics", headers={"traceparent": inbound_tp})
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "jakeai_http_requests_total" in resp.text

        # Verify response header has propagated W3C traceparent
        outbound_tp = resp.headers.get("traceparent")
        assert outbound_tp is not None
        assert outbound_tp.startswith("00-11112222333344445555666677778888-")
        assert resp.headers.get("x-correlation-id") is not None
