"""Chat and Server-Sent Events (SSE) streaming endpoints with LangGraph integration."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents import stream_multi_agent_workflow
from app.core.context import TenantContext
from app.core.rate_limiter import enforce_rate_limit
from app.core.security import get_current_tenant

router = APIRouter()


class ChatStreamRequest(BaseModel):
    """Payload model for chat streaming requests."""

    prompt: str = Field(min_length=1, description="User question or financial prompt")
    conversation_id: str | None = Field(
        default=None,
        description="Optional conversation thread ID",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional model execution parameters",
    )


def _format_sse_event(event: str, data: dict[str, Any]) -> str:
    """Format structured payload into W3C Server-Sent Event frame."""
    json_data = json.dumps(data)
    return f"event: {event}\ndata: {json_data}\n\n"


async def generate_chat_stream(
    prompt: str,
    context: TenantContext,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Stream real-time LangGraph multi-agent events via SSE."""
    start_time = time.time()

    # 1. Initial Handshake & Context Acknowledgment
    yield _format_sse_event(
        "status",
        {
            "phase": "initialized",
            "conversation_id": conversation_id,
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "mascot_state": "thinking",
            "timestamp": time.time(),
        },
    )
    await asyncio.sleep(0.01)

    final_response: str = ""
    citations: list[dict[str, Any]] = []
    final_mascot_state: str = "idle"

    # 2. Real-time LangGraph Event Stream
    async for event in stream_multi_agent_workflow(prompt, context, conversation_id):
        node = event.get("node")
        phase = event.get("workflow_phase", "executing")
        mascot = event.get("mascot_state", "thinking")
        msg = event.get("message", "")

        yield _format_sse_event(
            "status",
            {
                "node": node,
                "phase": phase,
                "mascot_state": mascot,
                "message": msg,
            },
        )
        await asyncio.sleep(0.005)

        # Emit tool telemetry if tools were executed
        if event.get("tool_calls"):
            yield _format_sse_event(
                "tool_call",
                {
                    "node": node,
                    "tool_calls": event.get("tool_calls"),
                },
            )

        if event.get("final_response"):
            final_response = event["final_response"]
            citations = event.get("citations", [])
            final_mascot_state = mascot

    # 3. Stream Generated Markdown Tokens
    if final_response:
        # Stream word tokens for smooth client UI animation
        words = final_response.split(" ")
        for i, word in enumerate(words):
            delta = word if i == 0 else f" {word}"
            yield _format_sse_event(
                "token",
                {
                    "delta": delta,
                    "conversation_id": conversation_id,
                },
            )
            await asyncio.sleep(0.002)

    # 4. Stream Completion Frame with Mascot State
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    yield _format_sse_event(
        "done",
        {
            "conversation_id": conversation_id,
            "tenant_id": context.tenant_id,
            "elapsed_ms": elapsed_ms,
            "mascot_state": final_mascot_state,
            "citations": citations,
        },
    )


@router.post(
    "/stream",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Real-time Chat SSE Stream",
    description="Stream real-time multi-agent responses via Server-Sent Events (SSE).",
    tags=["Chat"],
)
async def chat_stream_endpoint(
    payload: ChatStreamRequest,
    request: Request,
    context: TenantContext = Depends(get_current_tenant),
) -> StreamingResponse:
    """Enforce security & rate limits, then initiate real-time SSE stream."""
    await enforce_rate_limit(request, context.tenant_id)

    conv_id = payload.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"

    return StreamingResponse(
        generate_chat_stream(
            prompt=payload.prompt,
            context=context,
            conversation_id=conv_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Tenant-ID": context.tenant_id,
            "X-Correlation-ID": context.correlation_id,
        },
    )
