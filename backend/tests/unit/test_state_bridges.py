"""Unit tests for WORK-01 state bridge converters and RunState bidirectional mapping."""

from app.agent.state.models import RunState, RunStatus
from app.agents.state import (
    AgentState,
    agent_state_to_run_state,
    run_state_to_agent_state,
)


def test_run_state_bidirectional_conversion() -> None:
    """Verify RunState.to_agent_state() and RunState.from_agent_state()."""
    run = RunState(
        run_id="run-bridge-001",
        task_id="task-bridge-001",
        tenant_id="tenant-bridge",
        user_id="user-bridge",
        status=RunStatus.RUNNING,
        roles=["analyst", "auditor"],
        permissions=["read", "execute"],
        correlation_id="corr-12345",
        prompt="Analyze Q4 balance sheet",
        messages=["Hello", "Ready to analyze"],
        context={"market": "US", "ticker": "AAPL"},
        tool_calls=[{"tool": "fetch_balance_sheet", "args": {"ticker": "AAPL"}}],
        tool_results=[{"tool": "fetch_balance_sheet", "result": "OK"}],
        revision_count=2,
        verification_verdict="PASS",
        approval_state="APPROVED",
        pending_approval_id=None,
        checkpoint_metadata={"step": 3},
        final_output="Analysis complete",
        error=None,
        termination_reason="PASS",
        tokens_consumed=450,
        cost_usd=0.009,
    )

    # 1. to_agent_state
    agent_state_dict = run.to_agent_state()
    assert agent_state_dict["prompt"] == "Analyze Q4 balance sheet"
    assert agent_state_dict["tenant_id"] == "tenant-bridge"
    assert agent_state_dict["user_id"] == "user-bridge"
    assert agent_state_dict["roles"] == ["analyst", "auditor"]
    assert agent_state_dict["permissions"] == ["read", "execute"]
    assert agent_state_dict["revision_count"] == 2
    assert agent_state_dict["verification_verdict"] == "PASS"

    # 2. from_agent_state
    reconstructed_run = RunState.from_agent_state(
        agent_state_dict,  # type: ignore[arg-type]
        task_id="task-bridge-001",
        run_id="run-bridge-001",
    )
    assert reconstructed_run.run_id == "run-bridge-001"
    assert reconstructed_run.task_id == "task-bridge-001"
    assert reconstructed_run.tenant_id == "tenant-bridge"
    assert reconstructed_run.user_id == "user-bridge"
    assert reconstructed_run.prompt == "Analyze Q4 balance sheet"
    assert reconstructed_run.revision_count == 2
    assert reconstructed_run.verification_verdict == "PASS"
    assert reconstructed_run.termination_reason == "PASS"


def test_state_bridge_helpers() -> None:
    """Verify run_state_to_agent_state and agent_state_to_run_state utility functions."""
    run = RunState(
        run_id="run-bridge-002",
        task_id="task-bridge-002",
        tenant_id="tenant-corp",
        user_id="user-002",
        prompt="Synthesize portfolio risk",
    )

    # Convert from RunState instance
    state1 = run_state_to_agent_state(run)
    assert state1["prompt"] == "Synthesize portfolio risk"
    assert state1["tenant_id"] == "tenant-corp"

    # Convert from plain dict
    raw_dict = {"prompt": "Direct dict prompt", "tenant_id": "tenant-dict"}
    state2 = run_state_to_agent_state(raw_dict)
    assert state2["prompt"] == "Direct dict prompt"

    # Convert from arbitrary object with fallback
    state3 = run_state_to_agent_state(12345)
    assert state3 == {}

    # Convert AgentState back to RunState
    agent_state: AgentState = {
        "prompt": "Evaluate earnings call",
        "tenant_id": "tenant-corp",
        "user_id": "user-002",
        "roles": ["researcher"],
        "permissions": ["read"],
        "retrieved_chunks": [],
        "financial_analysis": {},
        "verification_verdict": "PASS",
        "critique_notes": "",
        "revision_count": 1,
        "final_response": "Grounded response",
        "mascot_state": "success",
        "citations": [],
    }
    converted_run = agent_state_to_run_state(agent_state, task_id="t-1", run_id="r-1")
    assert converted_run.task_id == "t-1"
    assert converted_run.run_id == "r-1"
    assert converted_run.prompt == "Evaluate earnings call"
    assert converted_run.revision_count == 1
    assert converted_run.verification_verdict == "PASS"
