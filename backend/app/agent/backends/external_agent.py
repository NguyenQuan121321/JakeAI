"""External Agent Backend Adapter for JakeAI-Agent.

Enables JakeAI-Agent to delegate tasks or subtasks to an external Agent API,
normalizing requests, streaming deltas, task statuses, and error handling.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx

from app.agent.backends.base import (
    AgentBackendInterface,
    AgentToolCall,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)

logger = logging.getLogger(__name__)


class ExternalAgentBackend(AgentBackendInterface):
    """Normalized client for interacting with an external Agent service."""

    def __init__(
        self,
        endpoint_url: str,
        auth_token: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self._auth_token = auth_token
        self.timeout_seconds = timeout_seconds

    async def generate(self, request: BackendRequest) -> BackendResponse:
        """Dispatch task execution request to external agent API."""
        start_ts = time.time()
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        payload: dict[str, Any] = {
            "messages": [msg.model_dump() for msg in request.messages],
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "tools": request.tools or [],
            "metadata": request.metadata,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{self.endpoint_url}/execute",
                    headers=headers,
                    json=payload,
                )
                latency_ms = (time.time() - start_ts) * 1000.0

                if resp.status_code != 200:
                    logger.warning(
                        "External agent API error: status=%d, body=%s",
                        resp.status_code,
                        resp.text[:200],
                    )
                    return BackendResponse(
                        content="",
                        provider="external_agent",
                        latency_ms=latency_ms,
                        finish_reason=f"external_error_{resp.status_code}",
                    )

                data = resp.json()
                raw_tools = data.get("tool_calls", [])
                parsed_tools = [
                    AgentToolCall(
                        call_id=t.get("call_id", f"call_{i}"),
                        tool_name=t.get("tool_name", "unknown"),
                        arguments=t.get("arguments", {}),
                    )
                    for i, t in enumerate(raw_tools)
                ]

                return BackendResponse(
                    content=data.get("output") or data.get("content") or "",
                    tool_calls=parsed_tools,
                    model=data.get("model", "external-agent"),
                    provider="external_agent",
                    input_tokens=data.get("input_tokens", 0),
                    output_tokens=data.get("output_tokens", 0),
                    cost_usd=data.get("cost_usd", 0.0),
                    latency_ms=latency_ms,
                    finish_reason=data.get("status", "completed"),
                )
        except Exception as exc:
            latency_ms = (time.time() - start_ts) * 1000.0
            logger.error("Failed to invoke external agent backend: %s", exc)
            return BackendResponse(
                content="",
                provider="external_agent",
                latency_ms=latency_ms,
                finish_reason="external_exception",
            )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncIterator[BackendStreamChunk]:
        """Stream execution deltas from external agent API."""
        resp = await self.generate(request)
        yield BackendStreamChunk(
            delta_content=resp.content,
            tool_call_deltas=resp.tool_calls or None,
            finish_reason=resp.finish_reason,
            is_complete=True,
        )
