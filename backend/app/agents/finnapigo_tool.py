"""FinnApiGo Tool Executor agent node for upstream API integrations."""

import time
from typing import Any

from app.agents.state import AgentState
from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.guardrails.rbac_guard import check_tool_rbac_guardrail


async def finnapigo_tool_node(state: AgentState) -> dict[str, Any]:
    """Execute authenticated upstream FinnApiGo operations with tenant scoping."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default_tenant")
    user_id = state.get("user_id", "anonymous")

    # Determine simulated tool operation from prompt
    if "balance" in prompt.lower():
        tool_name = "get_account_balance"
        result_payload = {
            "account_id": f"ACC-{tenant_id[:8].upper()}-01",
            "ledger_balance": 245800.50,
            "available_balance": 240000.00,
            "currency": "USD",
            "status": "ACTIVE",
        }
    elif "transaction" in prompt.lower():
        tool_name = "list_transactions"
        result_payload = {
            "total_count": 2,
            "transactions": [
                {"tx_id": "TX-9901", "amount": 12500.00, "type": "CREDIT"},
                {"tx_id": "TX-9902", "amount": -4300.00, "type": "DEBIT"},
            ],
        }
    else:
        tool_name = "get_tenant_limits"
        result_payload = {
            "tenant_id": tenant_id,
            "monthly_rate_limit": 100000,
            "active_agents": ["supervisor", "financial_specialist", "verifier"],
            "plan": "ENTERPRISE",
        }

    # Enforce RBAC guardrail before invoking tool
    rbac_decision = check_tool_rbac_guardrail(tool_name, state)
    if not rbac_decision.allowed:
        blocked_entry: dict[str, Any] = {
            "tool_name": tool_name,
            "status": "BLOCKED",
            "reason": rbac_decision.reason,
            "tenant_id": tenant_id,
            "caller_user_id": user_id,
        }
        return {
            "current_agent": "finnapigo_tool",
            "workflow_phase": "tool_blocked",
            "tool_calls": [*state.get("tool_calls", []), blocked_entry],
            "mascot_state": "alert",
            "next_agent": "verifier",
            "messages": [
                *state.get("messages", []),
                f"FinnApiGo Tool: Execution of '{tool_name}' blocked by RBAC Guardrail.",
            ],
        }

    # Propagate On-Behalf-Of (OBO) token
    obo_token = state.get("obo_token")
    if not obo_token:
        ctx = TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=state.get("roles", []),
            permissions=state.get("permissions", []),
        )
        obo_token = exchange_obo_token(ctx)

    tool_call_entry: dict[str, Any] = {
        "tool_name": tool_name,
        "invoked_at": time.time(),
        "tenant_id": tenant_id,
        "caller_user_id": user_id,
        "delegated_actor": "jakeai-platform",
        "authorization_header": f"Bearer {obo_token[:15]}...",
        "output": result_payload,
    }

    return {
        "current_agent": "finnapigo_tool",
        "workflow_phase": "tool_execution",
        "tool_calls": [*state.get("tool_calls", []), tool_call_entry],
        "mascot_state": "thinking",
        "next_agent": "verifier",
        "messages": [
            *state.get("messages", []),
            f"FinnApiGo Tool: Executed '{tool_name}' for tenant '{tenant_id}'.",
        ],
    }
