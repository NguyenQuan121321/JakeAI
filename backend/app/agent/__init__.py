"""JakeAI-Agent Subsystem: Configurable, provider-agnostic Agent runtime.

Provides:
- Agent runtime & bounded execution loop
- Model & Agent backend abstraction (JakeAI, Direct Provider, External Agent)
- Short-term, long-term, and checkpoint memory
- Extensible Tool Registry & safe execution sandbox
- Server-side human-in-the-loop approval policy
"""

from app.agent.runtime.manager import AgentRuntimeManager, get_agent_manager
from app.agent.runtime.models import AgentConfig, AgentRunEvent
from app.agent.state.models import RunState, RunStatus, TaskState, TaskStatus
from app.agent.telemetry import agent_telemetry

__all__ = [
    "AgentConfig",
    "AgentRunEvent",
    "AgentRuntimeManager",
    "RunState",
    "RunStatus",
    "TaskState",
    "TaskStatus",
    "agent_telemetry",
    "get_agent_manager",
]
