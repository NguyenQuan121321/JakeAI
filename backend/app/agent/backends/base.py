"""Core Agent Backend Abstraction and Protocol.

Defines the normalized interface through which the Agent runtime communicates
with model backends (JakeAI Provider Platform, Direct Provider, External Agent).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    """Normalized message format used within the Agent subsystem."""

    role: str = Field(..., description="Role: system, user, assistant, tool")
    content: str = Field(default="", description="Message content")
    name: str | None = Field(
        default=None, description="Optional name/identifier for tool messages"
    )
    tool_call_id: str | None = Field(
        default=None, description="Associated tool call identifier"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentToolCall(BaseModel):
    """Normalized representation of a tool call request from a model."""

    call_id: str = Field(..., description="Unique tool call invocation ID")
    tool_name: str = Field(..., description="Target tool name")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Parsed tool input arguments"
    )


class BackendRequest(BaseModel):
    """Normalized inference request dispatched from the Agent runtime to a backend."""

    messages: list[AgentMessage] = Field(
        ..., min_length=1, description="Conversation history"
    )
    tools: list[dict[str, Any]] | None = Field(
        default=None, description="Optional tool schemas presented to the model"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)
    tenant_id: str = Field(default="default", description="Tenant context identifier")
    user_id: str = Field(
        default="anonymous", description="Authenticated user identifier"
    )
    model: str | None = Field(
        default=None, description="Optional specific model target"
    )
    system_instruction: str | None = Field(
        default=None, description="Optional system instruction override"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackendResponse(BaseModel):
    """Normalized completion response returned by a backend."""

    content: str = Field(default="", description="Generated assistant message text")
    tool_calls: list[AgentToolCall] = Field(
        default_factory=list, description="Tool calls requested by the model"
    )
    model: str = Field(default="unknown", description="Model used for generation")
    provider: str = Field(
        default="unknown", description="Upstream provider or backend identifier"
    )
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    finish_reason: str = Field(
        default="stop", description="Generation completion reason"
    )


class BackendStreamChunk(BaseModel):
    """Normalized streaming delta emitted during real-time generation."""

    delta_content: str = Field(default="")
    tool_call_deltas: list[AgentToolCall] | None = None
    finish_reason: str | None = None
    is_complete: bool = False


class AgentBackendInterface(ABC):
    """Abstract interface defining the contract for all Agent model backends."""

    @abstractmethod
    async def generate(self, request: BackendRequest) -> BackendResponse:
        """Execute a complete inference call against the underlying backend."""
        ...

    @abstractmethod
    def generate_stream(
        self, request: BackendRequest
    ) -> AsyncIterator[BackendStreamChunk]:
        """Execute a streaming inference call emitting normalized delta chunks."""
        ...
