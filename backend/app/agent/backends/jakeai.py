"""JakeAI Provider Platform Backend Adapter for JakeAI-Agent.

Connects the Agent runtime to the JakeAI Provider Platform via stable
internal interface (call_upstream_llm_detailed), benefiting from BYOK,
model routing, Tier 5 prompt caching, context optimization, and FinOps.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from app.agent.backends.base import (
    AgentBackendInterface,
    AgentToolCall,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.core.llm_provider import call_upstream_llm_detailed

logger = logging.getLogger(__name__)


class JakeAIBackend(AgentBackendInterface):
    """Backend implementation routing through the JakeAI Provider Platform."""

    def __init__(self, default_model: str = "gemini-1.5-flash") -> None:
        self.default_model = default_model

    async def generate(self, request: BackendRequest) -> BackendResponse:
        """Execute completion via JakeAI Provider Platform."""
        start_ts = time.time()
        model_target = request.model or self.default_model

        # Extract system instruction and build combined prompt from messages
        system_content = request.system_instruction or ""
        conversation_history: list[str] = []

        for msg in request.messages:
            if msg.role == "system":
                if not system_content:
                    system_content = msg.content
                else:
                    system_content += f"\n{msg.content}"
            elif msg.role == "user":
                conversation_history.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                conversation_history.append(f"Assistant: {msg.content}")
            elif msg.role == "tool":
                conversation_history.append(
                    f"Tool[{msg.name or 'tool'}]: {msg.content}"
                )

        combined_prompt = "\n".join(conversation_history) if conversation_history else "Hello"

        # Dispatch via JakeAI Provider Platform
        upstream_resp = await call_upstream_llm_detailed(
            prompt=combined_prompt,
            tenant_id=request.tenant_id,
            model=model_target,
            system_instruction=system_content if system_content else None,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
        )

        latency_ms = (time.time() - start_ts) * 1000.0

        if upstream_resp is None:
            return BackendResponse(
                content="",
                model=model_target,
                provider="jakeai",
                latency_ms=latency_ms,
                finish_reason="error",
            )

        telemetry = upstream_resp.telemetry
        content_text = upstream_resp.text or ""

        # Parse any structured tool calls from content if presented in JSON blocks
        parsed_tool_calls = self._extract_tool_calls(content_text)

        return BackendResponse(
            content=content_text,
            tool_calls=parsed_tool_calls,
            model=upstream_resp.model,
            provider=f"jakeai:{upstream_resp.provider}",
            input_tokens=telemetry.uncached_input_tokens + telemetry.cached_tokens,
            output_tokens=telemetry.output_tokens,
            cached_tokens=telemetry.cached_tokens,
            cost_usd=telemetry.actual_cost_usd,
            latency_ms=latency_ms,
            finish_reason="tool_calls" if parsed_tool_calls else "stop",
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncIterator[BackendStreamChunk]:
        """Stream generation from JakeAI Provider Platform."""
        # For stream contract normalization, call generate and yield chunk
        full_resp = await self.generate(request)
        if full_resp.content:
            yield BackendStreamChunk(
                delta_content=full_resp.content,
                tool_call_deltas=full_resp.tool_calls or None,
                finish_reason=full_resp.finish_reason,
                is_complete=True,
            )
        else:
            yield BackendStreamChunk(
                delta_content="",
                finish_reason=full_resp.finish_reason,
                is_complete=True,
            )

    @staticmethod
    def _extract_tool_calls(text: str) -> list[AgentToolCall]:
        """Extract tool calls if the model output structured JSON tool requests."""
        tool_calls: list[AgentToolCall] = []
        if not text:
            return tool_calls

        # Check for ```json ... ``` or explicit tool_call blocks
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict) and "tool" in data and "arguments" in data:
                    tool_calls.append(
                        AgentToolCall(
                            call_id=f"call_{int(time.time() * 1000)}",
                            tool_name=str(data["tool"]),
                            arguments=data.get("arguments") or {},
                        )
                    )
            except Exception:
                pass
        return tool_calls
