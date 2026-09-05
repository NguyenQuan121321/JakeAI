"""FinnApiGo Tool Executor agent node for upstream API integrations."""

import time
from typing import Any

from app.agents.state import AgentState


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

    tool_call_entry = {
        "tool_name": tool_name,
        "invoked_at": time.time(),
        "tenant_id": tenant_id,
        "caller_user_id": user_id,
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
