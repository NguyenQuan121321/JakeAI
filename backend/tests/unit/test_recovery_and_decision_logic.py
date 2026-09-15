"""Unit tests for BoundedRecoveryEngine recovery and decision logic (UNIT-056).

Covers:
1. RecoveryLimits defaults and backward-compatible alias harmonization.
2. evaluate_step_failure: execution time limits, retry ceilings, and bounded agent switching.
3. evaluate_step_failure: non-retryable error classification (auth, quota, policy, context, tools).
4. evaluate_step_failure: rate limit model switching and transient network retries.
5. evaluate_verification_result: PASS, REJECTED, NEEDS_REVISION, time/replan exhaustion.
6. get_recovery_engine singleton.
"""

from __future__ import annotations

import pytest

from app.agent.domain.contracts import (
    PlanStep,
    RecoveryAction,
    VerificationResult,
    VerificationVerdict,
)
from app.agent.recovery.recovery import (
    BoundedRecoveryEngine,
    RecoveryLimits,
    get_recovery_engine,
)
from app.agent.registry.agent_registry import AgentMetadata, AgentRegistry

# ==============================================================================
# 1. RecoveryLimits Configuration & Aliases
# ==============================================================================


def test_recovery_limits_defaults() -> None:
    """RecoveryLimits initializes with canonical hard limits."""
    limits = RecoveryLimits()
    assert limits.MAX_STEP_RETRIES == 3
    assert limits.MAX_AGENT_SWITCHES == 2
    assert limits.MAX_REPLANS == 2
    assert limits.MAX_TOTAL_ITERATIONS == 10
    assert limits.MAX_EXECUTION_TIME_SECONDS == 60.0


def test_recovery_limits_harmonize_aliases() -> None:
    """Legacy alias dictionary keys are harmonized to canonical field names."""
    data = {
        "max_total_recovery_seconds": 45.0,
        "max_replan_cycles": 4,
        "max_step_retries": 5,
    }
    limits = RecoveryLimits.model_validate(data)
    assert limits.MAX_EXECUTION_TIME_SECONDS == 45.0
    assert limits.MAX_REPLANS == 4
    assert limits.MAX_STEP_RETRIES == 5


# ==============================================================================
# 2. evaluate_step_failure: Timeouts & Ceilings
# ==============================================================================


@pytest.fixture
def mock_registry() -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(
        AgentMetadata(
            agent_id="agent_primary",
            name="Primary Agent",
            description="Primary executor",
            capabilities=["analysis", "coding"],
            tools=["calc", "read_file"],
        )
    )
    reg.register(
        AgentMetadata(
            agent_id="agent_backup_1",
            name="Backup Agent 1",
            description="First backup",
            capabilities=["analysis", "coding"],
            tools=["calc", "read_file"],
        )
    )
    reg.register(
        AgentMetadata(
            agent_id="agent_backup_2",
            name="Backup Agent 2",
            description="Second backup",
            capabilities=["analysis", "coding"],
            tools=["calc", "read_file"],
        )
    )
    return reg


def test_step_failure_execution_time_budget_exceeded(
    mock_registry: AgentRegistry,
) -> None:
    """When elapsed_time_seconds exceeds limit, terminate run immediately."""
    engine = BoundedRecoveryEngine(
        limits=RecoveryLimits(max_execution_time_seconds=30.0),
        agent_registry=mock_registry,
    )
    step = PlanStep(
        step_id="step_1",
        description="Compute metrics",
        assigned_agent="agent_primary",
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message="Network glitch",
        current_step_retries=0,
        elapsed_time_seconds=30.1,
    )
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "exceeded limit" in decision.reason
    assert decision.attempt >= 1


def test_step_failure_retries_exhausted_triggers_agent_switch(
    mock_registry: AgentRegistry,
) -> None:
    """When step retries hit MAX_STEP_RETRIES, switch to eligible alternative agent."""
    engine = BoundedRecoveryEngine(
        limits=RecoveryLimits(max_step_retries=3, max_agent_switches=2),
        agent_registry=mock_registry,
    )
    step = PlanStep(
        step_id="step_1",
        description="Compute metrics",
        assigned_agent="agent_primary",
        required_capabilities=["analysis"],
        agent_switches=0,
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message="Agent repeatedly failed task",
        current_step_retries=3,  # >= MAX_STEP_RETRIES
        elapsed_time_seconds=10.0,
    )
    assert decision.action == RecoveryAction.SWITCH_AGENT
    assert decision.alternative_agent in ("agent_backup_1", "agent_backup_2")
    assert "transferring to alternative agent" in decision.reason


def test_step_failure_agent_switches_exhausted_terminates(
    mock_registry: AgentRegistry,
) -> None:
    """When both step retries and agent switches are exhausted, terminate run."""
    engine = BoundedRecoveryEngine(
        limits=RecoveryLimits(max_step_retries=3, max_agent_switches=2),
        agent_registry=mock_registry,
    )
    step = PlanStep(
        step_id="step_1",
        description="Compute metrics",
        assigned_agent="agent_primary",
        required_capabilities=["analysis"],
        agent_switches=2,  # >= MAX_AGENT_SWITCHES
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message="Persistent failure across multiple agents",
        current_step_retries=3,
        elapsed_time_seconds=10.0,
    )
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "exceeded max retries" in decision.reason
    assert "max agent switches" in decision.reason


def test_step_failure_no_alternative_agent_available(
    mock_registry: AgentRegistry,
) -> None:
    """When retries exhausted but no alternative agent matches capabilities, terminate."""
    engine = BoundedRecoveryEngine(
        limits=RecoveryLimits(max_step_retries=2),
        agent_registry=mock_registry,
    )
    step = PlanStep(
        step_id="step_1",
        description="Quantum calculation",
        assigned_agent="agent_primary",
        required_capabilities=["quantum_computing"],  # No registered agent has this
        agent_switches=0,
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message="No matching agent",
        current_step_retries=2,
        elapsed_time_seconds=5.0,
    )
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "exceeded max retries" in decision.reason


# ==============================================================================
# 3. evaluate_step_failure: Error Taxonomy Classification
# ==============================================================================


@pytest.mark.parametrize(
    "error_keyword",
    [
        "authentication failed",
        "HTTP 401 Unauthorized",
        "HTTP 403 Forbidden",
        "permission denied by policy",
        "access denied",
        "missing_credentials for provider",
        "invalid API key supplied",
        "quota exceeded for tenant",
        "billing limit reached",
        "insufficient credit balance",
        "policy rejection: unsafe prompt",
        "guardrail blocked invocation",
        "context length exceeded (130k > 128k)",
        "maximum context tokens reached",
        "approval gate required for operation",
        "requires human approval before execution",
        "unknown tool 'database_nuke'",
        "tool not found in registry",
    ],
)
def test_step_failure_non_retryable_errors_terminate_immediately(
    error_keyword: str,
    mock_registry: AgentRegistry,
) -> None:
    """Non-retryable error markers immediately terminate without consuming retry budget."""
    engine = BoundedRecoveryEngine(agent_registry=mock_registry)
    step = PlanStep(
        step_id="step_1",
        description="Sensitive operation",
        assigned_agent="agent_primary",
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message=f"Error encountered: {error_keyword}",
        current_step_retries=0,
        elapsed_time_seconds=5.0,
    )
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "Non-retryable failure" in decision.reason


@pytest.mark.parametrize(
    "rate_limit_msg",
    [
        "HTTP 429 Too Many Requests",
        "Rate limit exceeded for gpt-4o",
        "Provider is overloaded, please back off",
    ],
)
def test_step_failure_rate_limit_triggers_model_switch(
    rate_limit_msg: str,
    mock_registry: AgentRegistry,
) -> None:
    """Rate limit or congestion errors trigger SWITCH_MODEL."""
    engine = BoundedRecoveryEngine(agent_registry=mock_registry)
    step = PlanStep(
        step_id="step_1",
        description="Query LLM",
        assigned_agent="agent_primary",
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message=rate_limit_msg,
        current_step_retries=0,
        elapsed_time_seconds=5.0,
    )
    assert decision.action == RecoveryAction.SWITCH_MODEL
    assert "switching to alternative provider/model" in decision.reason
    assert decision.attempt == 1


@pytest.mark.parametrize(
    "transient_msg",
    [
        "Connection reset by peer",
        "Read timeout after 30s",
        "HTTPConnectionPool: connection timed out",
    ],
)
def test_step_failure_transient_network_triggers_retry(
    transient_msg: str,
    mock_registry: AgentRegistry,
) -> None:
    """Transient network errors trigger RETRY with backoff."""
    engine = BoundedRecoveryEngine(agent_registry=mock_registry)
    step = PlanStep(
        step_id="step_1",
        description="Fetch API data",
        assigned_agent="agent_primary",
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message=transient_msg,
        current_step_retries=1,
        elapsed_time_seconds=10.0,
    )
    assert decision.action == RecoveryAction.RETRY
    assert "Transient network failure" in decision.reason
    assert decision.attempt == 2


def test_step_failure_general_tool_error_retries(
    mock_registry: AgentRegistry,
) -> None:
    """General execution failure retries step when retries remain."""
    engine = BoundedRecoveryEngine(agent_registry=mock_registry)
    step = PlanStep(
        step_id="step_1",
        description="Parse JSON",
        assigned_agent="agent_primary",
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message="JSONDecodeError: Expecting value: line 1 column 1",
        current_step_retries=0,
        elapsed_time_seconds=2.0,
    )
    assert decision.action == RecoveryAction.RETRY
    assert "Initiating retry attempt 1" in decision.reason
    assert decision.attempt == 1


# ==============================================================================
# 4. evaluate_verification_result
# ==============================================================================


def test_verification_pass_action_none() -> None:
    """Verification verdict PASS produces action NONE."""
    engine = BoundedRecoveryEngine()
    verif = VerificationResult(
        verdict=VerificationVerdict.PASS,
        reason="All assertions satisfied",
    )
    decision = engine.evaluate_verification_result(
        verification=verif, current_replans=0, elapsed_time_seconds=10.0
    )
    assert decision.action == RecoveryAction.NONE
    assert "successfully" in decision.reason


def test_verification_rejected_action_terminate_rejected() -> None:
    """Verification verdict REJECTED produces action TERMINATE_REJECTED."""
    engine = BoundedRecoveryEngine()
    verif = VerificationResult(
        verdict=VerificationVerdict.REJECTED,
        reason="Cross-tenant leakage detected",
    )
    decision = engine.evaluate_verification_result(
        verification=verif, current_replans=0, elapsed_time_seconds=10.0
    )
    assert decision.action == RecoveryAction.TERMINATE_REJECTED
    assert "Hard security rejection" in decision.reason


def test_verification_time_budget_exceeded() -> None:
    """Verification exceeding MAX_EXECUTION_TIME_SECONDS terminates run."""
    engine = BoundedRecoveryEngine(
        limits=RecoveryLimits(max_execution_time_seconds=30.0)
    )
    verif = VerificationResult(
        verdict=VerificationVerdict.NEEDS_REVISION,
        reason="Code format mismatch",
    )
    decision = engine.evaluate_verification_result(
        verification=verif, current_replans=0, elapsed_time_seconds=30.5
    )
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "Execution budget exceeded" in decision.reason


def test_verification_replan_budget_exhausted() -> None:
    """When current_replans >= MAX_REPLANS, NEEDS_REVISION terminates run."""
    engine = BoundedRecoveryEngine(limits=RecoveryLimits(max_replans=2))
    verif = VerificationResult(
        verdict=VerificationVerdict.NEEDS_REVISION,
        reason="Output incomplete",
    )
    decision = engine.evaluate_verification_result(
        verification=verif, current_replans=2, elapsed_time_seconds=15.0
    )
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "maximum replans (2) exhausted" in decision.reason


def test_verification_needs_revision_triggers_replan() -> None:
    """When replan budget remains, NEEDS_REVISION triggers REPLAN with attempt + 1."""
    engine = BoundedRecoveryEngine(limits=RecoveryLimits(max_replans=3))
    verif = VerificationResult(
        verdict=VerificationVerdict.NEEDS_REVISION,
        reason="Calculation precision issue",
    )
    decision = engine.evaluate_verification_result(
        verification=verif, current_replans=1, elapsed_time_seconds=15.0
    )
    assert decision.action == RecoveryAction.REPLAN
    assert decision.attempt == 2
    assert "Verifier requested revision" in decision.reason


def test_get_recovery_engine_singleton() -> None:
    """get_recovery_engine returns stable singleton instance."""
    e1 = get_recovery_engine()
    e2 = get_recovery_engine()
    assert e1 is e2
