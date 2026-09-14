"""Shared Server-Sent Event formatting helpers (single authority).

R-ARCH-03: the W3C SSE frame builder was duplicated between
``app.agent.runtime.models.AgentStreamEvent.to_sse`` and the chat endpoint's
``_format_sse_event``, and the streaming response header set was duplicated
between the chat and gateway endpoints.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.context import TenantContext


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a structured payload into one W3C Server-Sent Event frame."""
    json_data = json.dumps(data)
    return f"event: {event}\ndata: {json_data}\n\n"


def streaming_sse_headers(context: TenantContext) -> dict[str, str]:
    """Standard response headers for tenant-scoped SSE streaming endpoints."""
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Tenant-ID": context.tenant_id,
        "X-Correlation-ID": context.correlation_id,
    }
