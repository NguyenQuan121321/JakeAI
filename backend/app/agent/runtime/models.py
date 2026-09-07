"""Runtime configuration models and streaming event contracts."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration defining an Agent instance and its operational constraints."""

    agent_id: str = Field(default="default-agent")
    name: str = Field(default="JakeAI General Agent")
    description: str = Field(
        default="Autonomous agent with bounded planning and tool execution"
    )
    system_instructions: str | None = None
    default_model: str = Field(default="gemini-1.5-flash")
    backend_type: str = Field(
        default="jakeai", description="jakeai | direct_provider | external_agent"
    )
    max_iterations: int = Field(default=10, ge=1, le=50)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    allowed_tools: list[str] = Field(
        default_factory=list, description="Empty = all authorized tools"
    )
    require_human_approval_for_dangerous: bool = Field(default=True)


class AgentRunEvent(BaseModel):
    """Normalized event frame emitted during Agent run streaming."""

    event_type: str = Field(
        ...,
        description="step | tool_call | observation | approval_required | completed | failed | cancelled",
    )
    task_id: str
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as W3C standard Server-Sent Event frame."""
        payload = json.dumps(self.model_dump())
        return f"event: {self.event_type}\ndata: {payload}\n\n"
