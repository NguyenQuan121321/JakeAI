"""Unit tests for canonical state transitions and circuit breaker states (UNIT-053).

Covers:
1. RunStatus state machine transitions and assert_run_transition.
2. Terminal state immutability (COMPLETED, FAILED, CANCELLED, REJECTED, TIMEOUT).
3. Self-transition idempotency (current == target).
4. TaskStatus lifecycle transitions in TASK_TRANSITIONS.
5. CircuitBreaker state machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED/OPEN.
6. CircuitBreaker execution paths: sync/async primary, fallback, deterministic fallback.
"""

from __future__ import annotations

import time

import pytest

from app.agent.state.models import (
    RUN_TRANSITIONS,
    TASK_TRANSITIONS,
    RunStatus,
    TaskStatus,
    assert_run_transition,
)
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
)

# ==============================================================================
# 1. Run State Transition Matrix & Invariants
# ==============================================================================


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.CREATED, RunStatus.PLANNING),
        (RunStatus.CREATED, RunStatus.READY),
        (RunStatus.CREATED, RunStatus.RUNNING),
        (RunStatus.CREATED, RunStatus.FAILED),
        (RunStatus.CREATED, RunStatus.CANCELLED),
        (RunStatus.PLANNING, RunStatus.READY),
        (RunStatus.PLANNING, RunStatus.RUNNING),
        (RunStatus.PLANNING, RunStatus.FAILED),
        (RunStatus.PLANNING, RunStatus.CANCELLED),
        (RunStatus.READY, RunStatus.RUNNING),
        (RunStatus.READY, RunStatus.EXECUTING),
        (RunStatus.READY, RunStatus.FAILED),
        (RunStatus.READY, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.EXECUTING),
        (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL),
        (RunStatus.RUNNING, RunStatus.PAUSED_APPROVAL),
        (RunStatus.RUNNING, RunStatus.VERIFYING),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.REJECTED),
        (RunStatus.RUNNING, RunStatus.TIMEOUT),
        (RunStatus.EXECUTING, RunStatus.RUNNING),
        (RunStatus.EXECUTING, RunStatus.WAITING_APPROVAL),
        (RunStatus.EXECUTING, RunStatus.PAUSED_APPROVAL),
        (RunStatus.EXECUTING, RunStatus.VERIFYING),
        (RunStatus.EXECUTING, RunStatus.COMPLETED),
        (RunStatus.EXECUTING, RunStatus.FAILED),
        (RunStatus.EXECUTING, RunStatus.CANCELLED),
        (RunStatus.EXECUTING, RunStatus.REJECTED),
        (RunStatus.EXECUTING, RunStatus.TIMEOUT),
        (RunStatus.WAITING_APPROVAL, RunStatus.RUNNING),
        (RunStatus.WAITING_APPROVAL, RunStatus.EXECUTING),
        (RunStatus.WAITING_APPROVAL, RunStatus.REJECTED),
        (RunStatus.WAITING_APPROVAL, RunStatus.CANCELLED),
        (RunStatus.WAITING_APPROVAL, RunStatus.FAILED),
        (RunStatus.PAUSED_APPROVAL, RunStatus.RUNNING),
        (RunStatus.PAUSED_APPROVAL, RunStatus.EXECUTING),
        (RunStatus.PAUSED_APPROVAL, RunStatus.REJECTED),
        (RunStatus.PAUSED_APPROVAL, RunStatus.CANCELLED),
        (RunStatus.PAUSED_APPROVAL, RunStatus.FAILED),
        (RunStatus.VERIFYING, RunStatus.COMPLETED),
        (RunStatus.VERIFYING, RunStatus.REPLANNING),
        (RunStatus.VERIFYING, RunStatus.PLANNING),
        (RunStatus.VERIFYING, RunStatus.RUNNING),
        (RunStatus.VERIFYING, RunStatus.FAILED),
        (RunStatus.VERIFYING, RunStatus.REJECTED),
        (RunStatus.VERIFYING, RunStatus.CANCELLED),
        (RunStatus.REPLANNING, RunStatus.PLANNING),
        (RunStatus.REPLANNING, RunStatus.READY),
        (RunStatus.REPLANNING, RunStatus.RUNNING),
        (RunStatus.REPLANNING, RunStatus.EXECUTING),
        (RunStatus.REPLANNING, RunStatus.FAILED),
        (RunStatus.REPLANNING, RunStatus.CANCELLED),
    ],
)
def test_valid_run_transitions_succeed(current: RunStatus, target: RunStatus) -> None:
    """Legal run transitions per RUN_TRANSITIONS must succeed without error."""
    assert_run_transition(current, target)


@pytest.mark.parametrize("status", list(RunStatus))
def test_run_self_transition_is_idempotent_noop(status: RunStatus) -> None:
    """Transitioning to the identical status is an idempotent no-op for any state."""
    # Even terminal states should not error on self-transition
    assert_run_transition(status, status)


@pytest.mark.parametrize(
    "terminal_status",
    [
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.REJECTED,
        RunStatus.TIMEOUT,
    ],
)
@pytest.mark.parametrize(
    "target_status",
    [
        RunStatus.CREATED,
        RunStatus.PLANNING,
        RunStatus.READY,
        RunStatus.RUNNING,
        RunStatus.EXECUTING,
        RunStatus.WAITING_APPROVAL,
        RunStatus.VERIFYING,
        RunStatus.REPLANNING,
    ],
)
def test_terminal_run_states_are_immutable(
    terminal_status: RunStatus, target_status: RunStatus
) -> None:
    """Terminal run states can NEVER transition to any non-terminal state."""
    assert terminal_status.is_terminal is True
    with pytest.raises(ValueError, match="cannot transition from terminal state"):
        assert_run_transition(terminal_status, target_status)


@pytest.mark.parametrize(
    ("current", "invalid_target"),
    [
        (RunStatus.CREATED, RunStatus.COMPLETED),
        (RunStatus.CREATED, RunStatus.VERIFYING),
        (RunStatus.CREATED, RunStatus.WAITING_APPROVAL),
        (RunStatus.PLANNING, RunStatus.COMPLETED),
        (RunStatus.PLANNING, RunStatus.WAITING_APPROVAL),
        (RunStatus.READY, RunStatus.COMPLETED),
        (RunStatus.READY, RunStatus.WAITING_APPROVAL),
        (RunStatus.WAITING_APPROVAL, RunStatus.COMPLETED),
        (RunStatus.WAITING_APPROVAL, RunStatus.VERIFYING),
        (RunStatus.REPLANNING, RunStatus.COMPLETED),
    ],
)
def test_disallowed_run_transitions_raise_value_error(
    current: RunStatus, invalid_target: RunStatus
) -> None:
    """Disallowed transitions that violate the directed DAG order must raise ValueError."""
    assert invalid_target not in RUN_TRANSITIONS.get(current, frozenset())
    with pytest.raises(ValueError, match="Invalid run state transition"):
        assert_run_transition(current, invalid_target)


# ==============================================================================
# 2. Task State Transition Matrix
# ==============================================================================


@pytest.mark.parametrize(
    "task_status",
    [
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.REJECTED,
        TaskStatus.TIMEOUT,
    ],
)
def test_terminal_task_status_flag(task_status: TaskStatus) -> None:
    """Terminal task statuses must have is_terminal == True."""
    assert task_status.is_terminal is True


@pytest.mark.parametrize(
    "active_task_status",
    [
        TaskStatus.PENDING,
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.PAUSED_APPROVAL,
        TaskStatus.VERIFYING,
        TaskStatus.REPLANNING,
    ],
)
def test_active_task_status_flag(active_task_status: TaskStatus) -> None:
    """Non-terminal task statuses must have is_terminal == False."""
    assert active_task_status.is_terminal is False


def test_task_transitions_graph_integrity() -> None:
    """All states in TASK_TRANSITIONS must be valid TaskStatus members."""
    for source, targets in TASK_TRANSITIONS.items():
        assert isinstance(source, TaskStatus)
        for target in targets:
            assert isinstance(target, TaskStatus)


# ==============================================================================
# 3. Circuit Breaker State Machine Tests
# ==============================================================================


def test_circuit_breaker_initial_closed_state() -> None:
    """Circuit breaker initializes in CLOSED state with 0 failures."""
    cb = CircuitBreaker(
        name="test_cb",
        failure_threshold=3,
        recovery_timeout_seconds=10.0,
        half_open_success_threshold=2,
    )
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.success_count == 0
    assert cb.is_available() is True


def test_circuit_breaker_trips_to_open_on_threshold() -> None:
    """Circuit transitions from CLOSED to OPEN after failure_threshold consecutive failures."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=3)

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 2

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 3
    assert cb.is_available() is False


def test_circuit_breaker_success_resets_closed_failures() -> None:
    """A success in CLOSED state resets consecutive failure count to 0."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2

    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_open_to_half_open_transition() -> None:
    """After recovery_timeout_seconds, is_available() triggers transition to HALF_OPEN."""
    cb = CircuitBreaker(
        name="test_cb",
        failure_threshold=1,
        recovery_timeout_seconds=0.01,
        half_open_success_threshold=2,
    )
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Manually backdate last_state_change to simulate elapsed time without sleeping
    cb.last_state_change = time.monotonic() - 0.05
    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.success_count == 0


def test_circuit_breaker_half_open_to_closed_on_success_threshold() -> None:
    """Reaching half_open_success_threshold in HALF_OPEN transitions circuit back to CLOSED."""
    cb = CircuitBreaker(
        name="test_cb",
        failure_threshold=1,
        half_open_success_threshold=2,
    )
    cb.state = CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.success_count == 1

    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.success_count == 0
    assert cb.failure_count == 0


def test_circuit_breaker_half_open_failure_immediately_reopens() -> None:
    """A single failure while in HALF_OPEN immediately trips circuit back to OPEN."""
    cb = CircuitBreaker(
        name="test_cb",
        failure_threshold=3,
        half_open_success_threshold=2,
    )
    cb.state = CircuitState.HALF_OPEN
    cb.success_count = 1

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.success_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_call_with_sync_callable() -> None:
    """call_with_fallback works seamlessly with synchronous callables."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=2)

    def sync_primary(val: int) -> int:
        return val * 10

    result = await cb.call_with_fallback(sync_primary, None, None, 5)
    assert result == 50
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_open_without_fallback_raises_exception() -> None:
    """When circuit is OPEN and no fallback is provided, CircuitBreakerOpenException is raised."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=1)
    cb.state = CircuitState.OPEN
    cb.last_state_change = time.monotonic()  # fresh OPEN state

    def sync_primary() -> str:
        return "ok"

    with pytest.raises(CircuitBreakerOpenException, match="is OPEN"):
        await cb.call_with_fallback(sync_primary, None, None)


@pytest.mark.asyncio
async def test_circuit_breaker_sync_fallback_invocation() -> None:
    """When primary throws, synchronous fallback callable is invoked and returned."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=2)

    def failing_primary() -> None:
        raise ValueError("Primary computation failed")

    def sync_fallback() -> str:
        return "fallback_result"

    result = await cb.call_with_fallback(failing_primary, sync_fallback, None)
    assert result == "fallback_result"
    assert cb.total_fallback_calls == 1
    assert cb.failure_count == 1
