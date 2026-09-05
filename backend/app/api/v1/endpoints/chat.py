"""Chat and Server-Sent Events (SSE) streaming endpoints."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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
    """Asynchronously generate streaming SSE frames for client consumption."""
    start_time = time.time()

    # 1. Initial Handshake & Context Acknowledgment
    yield _format_sse_event(
        "status",
        {
            "phase": "initialized",
            "conversation_id": conversation_id,
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "timestamp": time.time(),
        },
    )
    await asyncio.sleep(0.01)

    # 2. Simulated Multi-Agent Pipeline Handshake
    yield _format_sse_event(
        "status",
        {
            "phase": "routing",
            "agent": "supervisor",
            "message": "Analyzing prompt and dispatching specialist agents...",
        },
    )
    await asyncio.sleep(0.01)

    # 3. Streamed Token Chunks
    tokens = [
        "Received ",
        "query: ",
        f"'{prompt}'. ",
        "Processing ",
        "financial ",
        "context ",
        f"for tenant '{context.tenant_id}'.",
    ]

    for token in tokens:
        yield _format_sse_event(
            "token",
            {
                "delta": token,
                "conversation_id": conversation_id,
            },
        )
        await asyncio.sleep(0.005)

    # 4. Stream Completion Frame with Mascot State
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    yield _format_sse_event(
        "done",
        {
            "conversation_id": conversation_id,
            "tenant_id": context.tenant_id,
            "elapsed_ms": elapsed_ms,
            "mascot_state": "idle",
            "citations": [],
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
    # Perimeter Rate Limiting per Tenant & IP
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
