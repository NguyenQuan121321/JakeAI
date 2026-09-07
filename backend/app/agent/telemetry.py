"""Agent Platform Telemetry and Metrics Tracker with zero secret leakage."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentMetricsSnapshot(BaseModel):
    """Point-in-time metrics summary for the Agent subsystem."""

    tasks_created: int = 0
    runs_started: int = 0
    runs_completed: int = 0
    runs_failed: int = 0
    runs_cancelled: int = 0
    approvals_requested: int = 0
    approvals_approved: int = 0
    approvals_rejected: int = 0
    steps_executed: int = 0
    tool_calls_total: int = 0
    tokens_consumed: int = 0
    total_cost_usd: float = 0.0
    tool_calls_by_tool: dict[str, int] = Field(default_factory=dict)
    runs_by_backend: dict[str, int] = Field(default_factory=dict)


class AgentTelemetry:
    """Thread-safe telemetry collector for agent tasks, runs, and tool usage."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks_created = 0
        self._runs_started = 0
        self._runs_completed = 0
        self._runs_failed = 0
        self._runs_cancelled = 0
        self._approvals_requested = 0
        self._approvals_approved = 0
        self._approvals_rejected = 0
        self._steps_executed = 0
        self._tool_calls_total = 0
        self._tokens_consumed = 0
        self._total_cost_usd = 0.0
        self._tool_counts: dict[str, int] = defaultdict(int)
        self._backend_counts: dict[str, int] = defaultdict(int)

    def record_task_created(self, _tenant_id: str) -> None:
        with self._lock:
            self._tasks_created += 1

    def record_run_started(self, _tenant_id: str, backend_type: str = "jakeai") -> None:
        with self._lock:
            self._runs_started += 1
            self._backend_counts[backend_type] += 1

    def record_run_completed(
        self,
        tenant_id: str,
        duration_ms: float,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        _ = (tenant_id, duration_ms)
        with self._lock:
            self._runs_completed += 1
            self._tokens_consumed += tokens
            self._total_cost_usd += cost_usd

    def record_run_failed(self, _tenant_id: str, _reason: str | None = None) -> None:
        with self._lock:
            self._runs_failed += 1

    def record_run_cancelled(self, _tenant_id: str) -> None:
        with self._lock:
            self._runs_cancelled += 1

    def record_step_executed(self, _tenant_id: str) -> None:
        with self._lock:
            self._steps_executed += 1

    def record_tool_call(self, tool_name: str, _tenant_id: str) -> None:
        with self._lock:
            self._tool_calls_total += 1
            self._tool_counts[tool_name] += 1

    def record_approval_requested(self, _tool_name: str, _tenant_id: str) -> None:
        with self._lock:
            self._approvals_requested += 1

    def record_approval_decision(self, approved: bool, _tenant_id: str) -> None:
        with self._lock:
            if approved:
                self._approvals_approved += 1
            else:
                self._approvals_rejected += 1

    def get_snapshot(self) -> AgentMetricsSnapshot:
        with self._lock:
            return AgentMetricsSnapshot(
                tasks_created=self._tasks_created,
                runs_started=self._runs_started,
                runs_completed=self._runs_completed,
                runs_failed=self._runs_failed,
                runs_cancelled=self._runs_cancelled,
                approvals_requested=self._approvals_requested,
                approvals_approved=self._approvals_approved,
                approvals_rejected=self._approvals_rejected,
                steps_executed=self._steps_executed,
                tool_calls_total=self._tool_calls_total,
                tokens_consumed=self._tokens_consumed,
                total_cost_usd=round(self._total_cost_usd, 6),
                tool_calls_by_tool=dict(self._tool_counts),
                runs_by_backend=dict(self._backend_counts),
            )

    def clear(self) -> None:
        with self._lock:
            self._tasks_created = 0
            self._runs_started = 0
            self._runs_completed = 0
            self._runs_failed = 0
            self._runs_cancelled = 0
            self._approvals_requested = 0
            self._approvals_approved = 0
            self._approvals_rejected = 0
            self._steps_executed = 0
            self._tool_calls_total = 0
            self._tokens_consumed = 0
            self._total_cost_usd = 0.0
            self._tool_counts.clear()
            self._backend_counts.clear()


agent_telemetry = AgentTelemetry()
