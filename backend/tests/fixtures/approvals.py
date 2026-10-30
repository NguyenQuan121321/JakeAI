"""Pre-decided RAM records for isolated orchestration state-machine tests.

This fixture is never installed in HTTP/security tests. It proves no user
authorization, durable consume, worker race, or actual approval acceptance.
The real ApprovalManager.decide remains disabled until that boundary exists.
"""

import time

from app.agent.approvals.models import ApprovalStatus


def component_decision(manager, approval_id, decision, tenant_id, user_id="fixture"):
    record = manager.get_request(approval_id, tenant_id)
    if record.status != ApprovalStatus.PENDING:
        raise ValueError("Component record is already finalized")
    record.decided_at = time.time()
    record.decided_by = user_id
    record.status = (
        ApprovalStatus.APPROVED if decision.approved else ApprovalStatus.REJECTED
    )
    if not decision.approved:
        record.rejection_reason = decision.reason or "Rejected by component fixture"
    return record


def pending_http_record(tenant, subject):
    """Seed a pending resource for denial/cancel tests, without granting approval."""
    from app.agent.runtime.manager import get_agent_manager
    from app.agent.state.models import RunStatus

    manager = get_agent_manager()
    task = manager.create_task(
        goal="synthetic pending action", tenant_id=tenant, user_id=subject
    )
    run = manager.create_run(task.task_id, tenant_id=tenant, user_id=subject)
    run.transition_to(RunStatus.RUNNING)
    run.transition_to(RunStatus.PAUSED_APPROVAL)
    record = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id=tenant,
        tool_name="terminal_exec",
        tool_args={"command": "synthetic"},
        reason="test",
    )
    return manager, task, run, record
