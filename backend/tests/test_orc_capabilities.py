"""Targeted unit tests for AI Orchestration capabilities ORC-09, ORC-10, and ORC-11."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.approvals.manager import ApprovalManager
from app.agent.backends.base import (
    AgentBackendInterface,
    AgentMessage,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.memory.manager import AgentMemoryManager
from app.agent.planning.models import NextActionType
from app.agent.planning.planner import BoundedPlanner
from app.agent.runtime.loop import AgentExecutionLoop
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.runtime.models import AgentConfig
from app.agent.runtime.runner import AgentRunner
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunState, RunStatus, TaskState, TaskStatus
from app.agent.tools.registry import ToolRegistry


class MockBackend(AgentBackendInterface):
    """Mock backend capturing received request and returning programmed response."""

    def __init__(self, response_text: str = '{"action": "finish", "output": "Done"}') -> None:
        self.response_text = response_text
        self.last_request: BackendRequest | None = None
        self.default_model = "test-model"

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.last_request = request
        return BackendResponse(
            content=self.response_text,
            model=request.model or self.default_model,
            provider="mock",
            latency_ms=10.0,
        )

    async def generate_stream(self, request: BackendRequest):
        yield BackendStreamChunk(delta_content=self.response_text, is_complete=True)


@pytest.mark.asyncio
async def test_orc_09_planner_memory_recall() -> None:
    """ORC-09: Planner recalls tenant episodic memories and injects them into system prompt."""
    memory_manager = AgentMemoryManager()
    tenant_id = "tenant-test-memory"

    # Seed an episodic memory fact
    memory_manager.remember_episodic(
        tenant_id=tenant_id,
        key="portfolio_risk_profile",
        value="Conservative growth, max 15% equities",
        summary="User risk profile",
    )

    backend = MockBackend()
    planner = BoundedPlanner(backend=backend, memory_manager=memory_manager)
    plan = planner.create_initial_plan("Analyze portfolio risk profile")

    action = await planner.determine_next_action(
        goal="Analyze portfolio risk profile",
        plan=plan,
        history=[],
        available_tools=[],
        current_iteration=0,
        elapsed_time_seconds=1.0,
        tenant_id=tenant_id,
    )

    assert action.action_type == NextActionType.FINISH
    assert backend.last_request is not None
    # System prompt must contain recalled context
    system_msg = backend.last_request.messages[0].content
    assert "Relevant Context from Memory:" in system_msg
    assert "portfolio_risk_profile" in system_msg
    assert "Conservative growth" in system_msg


@pytest.mark.asyncio
async def test_orc_09_loop_remembers_episodic_on_finish() -> None:
    """ORC-09: Execution loop persists completed goal into episodic memory."""
    memory_manager = AgentMemoryManager()
    checkpoint_manager = CheckpointManager()
    tool_registry = ToolRegistry()
    approval_manager = ApprovalManager()
    backend = MockBackend(response_text='{"action": "finish", "output": "Quarterly revenue was $5.2M"}')

    planner = BoundedPlanner(backend=backend, memory_manager=memory_manager)
    loop = AgentExecutionLoop(
        planner=planner,
        tool_registry=tool_registry,
        memory_manager=memory_manager,
        checkpoint_manager=checkpoint_manager,
        approval_manager=approval_manager,
    )

    task = TaskState(task_id="task-mem-finish", tenant_id="tenant-fin", user_id="user-fin", goal="Calculate Q3 revenue")
    run = RunState(run_id="run-mem-finish", task_id="task-mem-finish", tenant_id="tenant-fin", user_id="user-fin")

    events = [event async for event in loop.execute(task=task, run=run)]

    assert run.status == RunStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED
    assert any(e.event_type == "completed" for e in events)

    # Verify episodic memory was stored
    memories = memory_manager.recall_relevant(tenant_id="tenant-fin", query_key="task_task-mem-fin")
    assert len(memories) >= 1
    assert "Quarterly revenue was $5.2M" in memories[0].value
    assert "Completed goal: Calculate Q3 revenue" in (memories[0].summary or "")


@pytest.mark.asyncio
async def test_orc_10_runner_active_task_cancellation() -> None:
    """ORC-10: Runner tracks active asyncio task and cancels it cleanly upon cancellation request."""
    memory_manager = AgentMemoryManager()
    checkpoint_manager = CheckpointManager()
    tool_registry = ToolRegistry()
    approval_manager = ApprovalManager()

    # Backend that simulates a slow in-flight operation
    class SlowBackend(AgentBackendInterface):
        async def generate(self, request: BackendRequest) -> BackendResponse:
            await asyncio.sleep(5.0)
            return BackendResponse(content="Done", model="mock", provider="mock")

        async def generate_stream(self, request: BackendRequest):
            await asyncio.sleep(5.0)
            yield BackendStreamChunk(delta_content="Done", is_complete=True)

    planner = BoundedPlanner(backend=SlowBackend(), memory_manager=memory_manager)
    runner = AgentRunner(
        planner=planner,
        tool_registry=tool_registry,
        memory_manager=memory_manager,
        checkpoint_manager=checkpoint_manager,
        approval_manager=approval_manager,
    )

    task = TaskState(task_id="task-cancel", tenant_id="tenant-canc", user_id="user-canc", goal="Slow operation")
    run = RunState(run_id="run-cancel", task_id="task-cancel", tenant_id="tenant-canc", user_id="user-canc")

    async_run_task = asyncio.create_task(runner.start_run(task, run))

    # Allow run to start and register active task
    await asyncio.sleep(0.05)
    assert run.run_id in runner._active_tasks

    # Trigger cancellation via runner
    runner.request_cancellation(run.run_id)

    # Wait for the task to be cancelled
    with pytest.raises(asyncio.CancelledError):
        await async_run_task

    assert run.status == RunStatus.CANCELLED
    assert task.status == TaskStatus.CANCELLED
    assert run.run_id not in runner._active_tasks


@pytest.mark.asyncio
async def test_orc_11_dynamic_model_selection() -> None:
    """ORC-11: Custom default_model in AgentConfig propagates dynamically to backend and planner."""
    custom_model = "claude-3-5-sonnet-20241022"
    config = AgentConfig(default_model=custom_model)
    manager = AgentRuntimeManager(config=config)

    assert manager.backend.default_model == custom_model
    assert isinstance(manager.backend, JakeAIBackend)

    # Verify BoundedPlanner passes the model to BackendRequest
    mock_backend = MockBackend()
    mock_backend.default_model = custom_model
    planner = BoundedPlanner(backend=mock_backend)
    plan = planner.create_initial_plan("Test goal")

    await planner.determine_next_action(
        goal="Test goal",
        plan=plan,
        history=[],
        available_tools=[],
        current_iteration=0,
        elapsed_time_seconds=1.0,
    )

    assert mock_backend.last_request is not None
    assert mock_backend.last_request.model == custom_model
