"""SEC-007: Dedicated Authorization & RBAC Runtime Security Regression Test Suite.

Automated verification covering:
- Insufficient permissions and route-level RBAC enforcement
- Role mismatch and unauthorized actions across user personas
- Forbidden operations and unmapped tool fail-closed
- Empty caller authorization context fail-closed
- Approval lifecycle security:
  * Cross-run approval hijacking rejection (RL02-F-06)
  * TOCTOU argument tampering defense (R-AI-03-07)
  * Finalized approval replay prevention
- Unauthorized tool execution prevention
- Privileged operations without authorization (terminal_exec / dangerous tools)
"""

from typing import Any

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalDecision
from app.agent.execution.engine import ExecutionEngine
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.tools.base import Tool, ToolMetadata
from app.agent.tools.builtins.mock_tools import MockDangerousShellTool
from app.agent.tools.policy import ToolPolicyEngine
from app.core.context import TenantContext
from app.core.security import exchange_obo_token, require_permissions
from app.guardrails.rbac_guard import check_tool_rbac_guardrail
from app.main import app

# ==============================================================================
# 1. Insufficient Permission & Route-Level RBAC Enforcement
# ==============================================================================


@pytest.mark.asyncio
async def test_authz_require_permissions_dependency_enforcement() -> None:
    """Dependency factory require_permissions blocks contexts lacking required permissions."""
    checker = require_permissions("reports:export", "audit:review")

    # Context lacking both permissions
    unprivileged_ctx = TenantContext(
        tenant_id="tenant-sec-authz",
        user_id="user-viewer",
        roles=["viewer"],
        permissions=["reports:read"],
    )
    with pytest.raises(HTTPException) as exc_info:
        await checker(context=unprivileged_ctx)
    assert exc_info.value.status_code == 403
    assert "insufficient permissions" in exc_info.value.detail.lower()
    assert "reports:export" in exc_info.value.detail

    # Context with partial permissions (lacks audit:review)
    partial_ctx = TenantContext(
        tenant_id="tenant-sec-authz",
        user_id="user-analyst",
        roles=["financial_analyst"],
        permissions=["reports:export"],
    )
    with pytest.raises(HTTPException) as exc_info:
        await checker(context=partial_ctx)
    assert exc_info.value.status_code == 403
    assert "audit:review" in exc_info.value.detail

    # Context possessing all required permissions succeeds
    privileged_ctx = TenantContext(
        tenant_id="tenant-sec-authz",
        user_id="user-auditor",
        roles=["auditor"],
        permissions=["reports:export", "audit:review"],
    )
    res = await checker(context=privileged_ctx)
    assert res.user_id == "user-auditor"

    # Admin role inherently satisfies all granular permissions
    admin_ctx = TenantContext(
        tenant_id="tenant-sec-authz",
        user_id="user-admin",
        roles=["admin"],
        permissions=[],
    )
    admin_res = await checker(context=admin_ctx)
    assert admin_res.user_id == "user-admin"


# ==============================================================================
# 2. Role Mismatch and Persona Boundaries
# ==============================================================================


def test_authz_role_mismatch_financial_analyst_vs_developer() -> None:
    """Financial analysts cannot invoke developer tools, and developers cannot invoke financial tools."""
    analyst_ctx = TenantContext(
        tenant_id="tenant-roles",
        user_id="analyst-1",
        roles=["financial_analyst"],
        permissions=["accounts:read"],
    )
    developer_ctx = TenantContext(
        tenant_id="tenant-roles",
        user_id="dev-1",
        roles=["developer"],
        permissions=["code:read", "files:read"],
    )

    # Financial analyst invoking financial tools -> ALLOWED
    assert check_tool_rbac_guardrail("get_account_balance", analyst_ctx).allowed is True
    assert check_tool_rbac_guardrail("list_transactions", analyst_ctx).allowed is True

    # Financial analyst attempting developer tools -> REJECTED
    dev_attempt = check_tool_rbac_guardrail("read_file", analyst_ctx)
    assert dev_attempt.allowed is False
    assert dev_attempt.violation_type == "RBAC_ACCESS_DENIED"

    dev_sym_attempt = check_tool_rbac_guardrail("search_symbols", analyst_ctx)
    assert dev_sym_attempt.allowed is False

    # Developer invoking developer tools -> ALLOWED
    assert check_tool_rbac_guardrail("read_file", developer_ctx).allowed is True
    assert check_tool_rbac_guardrail("search_symbols", developer_ctx).allowed is True

    # Developer attempting financial tools -> REJECTED
    fin_attempt = check_tool_rbac_guardrail("get_account_balance", developer_ctx)
    assert fin_attempt.allowed is False
    assert fin_attempt.violation_type == "RBAC_ACCESS_DENIED"


def test_authz_viewer_cannot_execute_any_sensitive_tools() -> None:
    """Readonly viewer persona is strictly blocked from all sensitive and mutation tools."""
    viewer_ctx = TenantContext(
        tenant_id="tenant-viewer",
        user_id="viewer-99",
        roles=["viewer"],
        permissions=[],
    )

    for tool in [
        "get_account_balance",
        "list_transactions",
        "get_tenant_limits",
        "transfer_funds",
        "read_file",
        "search_symbols",
        "terminal_exec",
        "mock_dangerous_shell",
    ]:
        decision = check_tool_rbac_guardrail(tool, viewer_ctx)
        assert decision.allowed is False, f"Viewer unexpectedly allowed for {tool}"
        assert decision.violation_type == "RBAC_ACCESS_DENIED"


# ==============================================================================
# 3. Fail-Closed Boundaries: Unmapped Tools and Empty Contexts
# ==============================================================================


def test_authz_unmapped_tools_fail_closed() -> None:
    """Tools with no registered RBAC mapping fail closed with RBAC_UNMAPPED_TOOL."""
    admin_ctx = TenantContext(
        tenant_id="tenant-admin",
        user_id="admin-0",
        roles=["admin"],
    )
    for unmapped_tool in [
        "drop_database",
        "arbitrary_eval",
        "spawn_subshell",
        "unknown_custom_plugin",
    ]:
        decision = check_tool_rbac_guardrail(unmapped_tool, admin_ctx)
        assert decision.allowed is False
        assert decision.violation_type == "RBAC_UNMAPPED_TOOL"
        assert "no policy mapping" in decision.reason.lower()


def test_authz_empty_context_fails_closed() -> None:
    """Empty authorization context (no roles, no permissions) fails closed with RBAC_EMPTY_CONTEXT."""
    empty_ctx = TenantContext(
        tenant_id="tenant-anon",
        user_id="anon-user",
        roles=[],
        permissions=[],
    )
    decision = check_tool_rbac_guardrail("get_account_balance", empty_ctx)
    assert decision.allowed is False
    assert decision.violation_type == "RBAC_EMPTY_CONTEXT"
    assert "has no assigned roles or permissions" in decision.reason.lower()


# ==============================================================================
# 4. Tool Policy Engine Permission Aliases & Allowlist Enforcement
# ==============================================================================


def test_authz_tool_policy_engine_aliased_permissions() -> None:
    """ToolPolicyEngine resolves canonical permission aliases (e.g. accounts:read -> finnapigo:read)."""
    tool_meta = ToolMetadata(
        name="get_account_balance",
        description="Retrieve account balance",
        input_schema={"type": "object", "properties": {}},
        permissions=["accounts:read"],
    )

    class DummyTool(Tool):
        metadata = tool_meta

        async def execute(self, **kwargs: Any) -> Any:
            return {"balance": 1000}

    tool = DummyTool()

    # User with direct permission
    res_direct = ToolPolicyEngine.evaluate(
        tool=tool,
        arguments={},
        user_permissions=["accounts:read"],
    )
    assert res_direct.allowed is True

    # User with umbrella alias permission
    res_alias = ToolPolicyEngine.evaluate(
        tool=tool,
        arguments={},
        user_permissions=["finnapigo:read"],
    )
    assert res_alias.allowed is True

    # User with unrelated permission -> REJECTED
    res_unrelated = ToolPolicyEngine.evaluate(
        tool=tool,
        arguments={},
        user_permissions=["files:read"],
    )
    assert res_unrelated.allowed is False
    assert "Forbidden" in res_unrelated.reason


# ==============================================================================
# 5. Approval Gate Security & Anti-Misuse Invariants
# ==============================================================================


@pytest.mark.asyncio
async def test_authz_cross_run_approval_hijacking_rejected() -> None:
    """Attempting to decide an approval with mismatched run ID is rejected with 409 Conflict (RL02-F-06)."""
    runtime_mgr = AgentRuntimeManager()

    # Create task and two distinct runs
    task = runtime_mgr.create_task(
        goal="Run approval security test",
        tenant_id="tenant-approval-sec",
        user_id="user-1",
    )
    run_a = runtime_mgr.create_run(
        task_id=task.task_id,
        tenant_id="tenant-approval-sec",
        user_id="user-1",
    )
    run_b = runtime_mgr.create_run(
        task_id=task.task_id,
        tenant_id="tenant-approval-sec",
        user_id="user-1",
    )

    # Create an approval request for Run A
    app_req_a = runtime_mgr.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run_a.run_id,
        tenant_id="tenant-approval-sec",
        tool_name="terminal_exec",
        tool_args={"command": "uptime"},
        reason="Human gate required",
    )
    assert app_req_a.status.value == "pending"

    # Adversary attempts to finalize Run A's approval using Run B's identity
    with pytest.raises(ValueError) as exc_info:
        await runtime_mgr.decide_approval(
            approval_id=app_req_a.approval_id,
            decision=ApprovalDecision(approved=True),
            tenant_id="tenant-approval-sec",
            user_id="admin-user",
            task_id=task.task_id,
            run_id=run_b.run_id,  # Mismatched run ID
        )
    assert "not to run" in str(exc_info.value).lower()

    # Verify the approval gate was NOT mutated and remains PENDING for Run A
    refreshed = runtime_mgr.approval_manager.get_request(
        app_req_a.approval_id, tenant_id="tenant-approval-sec"
    )
    assert refreshed is not None
    assert refreshed.status.value == "pending"


def test_authz_finalized_approval_replay_rejected() -> None:
    """Attempting to re-decide an already approved or rejected approval request fails."""
    app_mgr = ApprovalManager()
    req = app_mgr.create_request(
        task_id="t-1",
        run_id="r-1",
        tenant_id="tenant-replay",
        tool_name="terminal_exec",
        tool_args={"command": "uptime"},
        reason="Security test",
    )
    # First decision succeeds
    decided = app_mgr.decide(
        req.approval_id,
        decision=ApprovalDecision(approved=True),
        tenant_id="tenant-replay",
        user_id="admin",
    )
    assert decided.status.value == "approved"

    # Replaying decision fails
    with pytest.raises(ValueError) as exc_info:
        app_mgr.decide(
            req.approval_id,
            decision=ApprovalDecision(approved=False),
            tenant_id="tenant-replay",
            user_id="admin",
        )
    assert "already finalized" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_authz_toctou_argument_tampering_defense() -> None:
    """Modifying tool arguments between approval grant and step execution triggers TOCTOU abort (R-AI-03-07)."""
    from app.agent.approvals import get_approval_manager
    from app.agent.domain.contracts import (
        ExecutionContext,
        PlanStep,
        StepStatus,
        TaskSpec,
    )
    from app.agent.state.models import RunState, RunStatus

    engine = ExecutionEngine()
    appr_mgr = get_approval_manager()

    step = PlanStep(
        step_id="step_toctou_authz",
        description="Execute benign command",
        required_tools=["terminal_exec"],
        tool_name="terminal_exec",
        tool_args={"command": "uptime"},
    )
    task_spec = TaskSpec(
        task_id="task_toctou_sec",
        tenant_id="tenant-toctou-sec",
        goal="Safe maintenance",
        roles=["admin"],
        permissions=["system:execute"],
    )
    run_state = RunState(
        run_id="run_toctou_sec",
        task_id=task_spec.task_id,
        tenant_id=task_spec.tenant_id,
        user_id="admin-user",
        status=RunStatus.RUNNING,
    )
    context = ExecutionContext(
        tenant_id=task_spec.tenant_id,
        user_id=task_spec.user_id,
        roles=task_spec.roles,
        permissions=task_spec.permissions,
    )

    # 1. Trigger approval for 'uptime'
    step_paused, _, _ = await engine._execute_single_step(
        step=step,
        task_spec=task_spec,
        context=context,
        run_state=run_state,
        accumulated_outputs={},
        _elapsed_seconds=0.0,
    )
    approval_id = step_paused.pending_approval_id
    assert approval_id is not None

    # 2. Approve 'uptime'
    appr_mgr.decide(
        approval_id=approval_id,
        decision=ApprovalDecision(approved=True),
        tenant_id=task_spec.tenant_id,
        user_id="admin-operator",
    )

    # 3. Tamper with arguments before re-execution
    step_paused.tool_args = {"command": "cat /etc/passwd"}

    # 4. Engine must detect tampering and fail the step
    run_state.status = RunStatus.RUNNING
    _, res_tampered, _ = await engine._execute_single_step(
        step=step_paused,
        task_spec=task_spec,
        context=context,
        run_state=run_state,
        accumulated_outputs={},
        _elapsed_seconds=0.0,
    )
    assert res_tampered.status == StepStatus.FAILED
    assert "tampered arguments" in (res_tampered.error or "")


# ==============================================================================
# 6. Privileged Operations Without Authorization
# ==============================================================================


def test_authz_privileged_shell_requires_admin_and_system_execute() -> None:
    """Privileged tools (terminal_exec / mock_dangerous_shell) fail closed without admin role or system:execute."""
    shell_tool = MockDangerousShellTool()

    # 1. Non-admin with unrelated permissions -> REJECTED
    non_admin_ctx = TenantContext(
        tenant_id="tenant-priv",
        user_id="user-power",
        roles=["developer"],
        permissions=["code:read", "files:read"],
    )
    decision = check_tool_rbac_guardrail("terminal_exec", non_admin_ctx)
    assert decision.allowed is False
    assert decision.violation_type == "RBAC_ACCESS_DENIED"

    # 2. Admin role -> ALLOWED by RBAC guardrail
    admin_ctx = TenantContext(
        tenant_id="tenant-priv",
        user_id="user-admin",
        roles=["admin"],
        permissions=["system:execute"],
    )
    admin_decision = check_tool_rbac_guardrail("terminal_exec", admin_ctx)
    assert admin_decision.allowed is True

    # 3. Policy engine flags dangerous tool as requiring human approval even for admin
    policy_decision = ToolPolicyEngine.evaluate(
        tool=shell_tool,
        arguments={"command": "uptime"},
        user_roles=admin_ctx.roles,
        user_permissions=admin_ctx.permissions,
    )
    assert policy_decision.allowed is True
    assert policy_decision.requires_approval is True
    assert "DANGEROUS" in policy_decision.reason


@pytest.mark.asyncio
async def test_authz_http_boundary_approval_cross_run_conflict() -> None:
    """HTTP boundary rejects cross-run approval decision with HTTP 409 Conflict."""
    from app.agent.runtime.manager import get_agent_manager

    runtime_mgr = get_agent_manager()

    task = runtime_mgr.create_task(
        goal="HTTP approval conflict test",
        tenant_id="tenant-http-authz",
        user_id="user-1",
    )
    run_1 = runtime_mgr.create_run(
        task_id=task.task_id,
        tenant_id="tenant-http-authz",
        user_id="user-1",
    )
    run_2 = runtime_mgr.create_run(
        task_id=task.task_id,
        tenant_id="tenant-http-authz",
        user_id="user-1",
    )

    app_req = runtime_mgr.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run_1.run_id,
        tenant_id="tenant-http-authz",
        tool_name="terminal_exec",
        tool_args={"command": "uptime"},
        reason="Security test gate",
    )

    token = exchange_obo_token(
        TenantContext(
            tenant_id="tenant-http-authz",
            user_id="user-1",
            roles=["admin"],
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Post Run 1's approval ID against Run 2's URL
        resp = await client.post(
            f"/api/v1/agent/tasks/{task.task_id}/runs/{run_2.run_id}/approvals/{app_req.approval_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"approved": True, "reason": "Authorized by test"},
        )
        assert resp.status_code == 409
        assert "not to run" in resp.json()["detail"].lower()
