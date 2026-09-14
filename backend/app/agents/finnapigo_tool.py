"""FinnApiGo Tool Executor agent node for upstream API integrations."""

import time
import uuid
from typing import Any

from app.agents.state import AgentState
from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.guardrails.rbac_guard import check_tool_rbac_guardrail


async def finnapigo_tool_node(state: AgentState) -> dict[str, Any]:
    """Execute authenticated upstream FinnApiGo operations with tenant scoping."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default")
    user_id = state.get("user_id", "anonymous")

    from app.agent.tools.registry import get_tool_registry

    # Determine tool name from state or semantic prompt classification. Account
    # identity is NOT pre-derived here: the FinnApiGo tool owns the canonical tenant
    # account default (R-ARCH-01 single authority).
    pre_tool_name = state.get("tool_name")
    pre_args = state.get("arguments") or state.get("tool_args")

    if pre_tool_name:
        tool_name = str(pre_tool_name)
        arguments = dict(pre_args) if isinstance(pre_args, dict) else {}
        if tool_name == "list_transactions" and "limit" not in arguments:
            arguments["limit"] = 5
    else:
        import re

        prompt_lower = prompt.lower()
        # Semantic synonyms & intent patterns
        balance_pattern = re.compile(
            r"(?i)\b(?:balances?|funds?|liquidity|capital|cash|deposits?|available|standing|solvency)\b"
        )
        tx_pattern = re.compile(
            r"(?i)\b(?:transactions?|history|payments?|disbursements?|wires?|transfers?|credits?|debits?|activity|ledger\s+entries|ledger\s+history|outflows?|inflows?)\b"
        )
        limits_pattern = re.compile(
            r"(?i)\b(?:limits?|quotas?|rate\s*limits?|tiers?|plans?|capacit(?:y|ies)|thresholds?|usage\s+caps?)\b"
        )

        if tx_pattern.search(prompt_lower):
            tool_name = "list_transactions"
            arguments = dict(pre_args) if isinstance(pre_args, dict) else {"limit": 5}
        elif balance_pattern.search(prompt_lower):
            tool_name = "get_account_balance"
            arguments = dict(pre_args) if isinstance(pre_args, dict) else {}
        elif limits_pattern.search(prompt_lower):
            tool_name = "get_tenant_limits"
            arguments = dict(pre_args) if isinstance(pre_args, dict) else {}
        else:
            # Ambiguous account queries default safely to account balance inspection
            tool_name = "get_account_balance"
            arguments = dict(pre_args) if isinstance(pre_args, dict) else {}

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
    raw_corr_id = state.get("correlation_id")
    correlation_id: str = str(raw_corr_id) if raw_corr_id else str(uuid.uuid4())
    obo_token = state.get("obo_token")
    if not obo_token:
        ctx = TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=state.get("roles", []),
            permissions=state.get("permissions", []),
            correlation_id=correlation_id,
        )
        obo_token = exchange_obo_token(ctx)

    # Execute tool via canonical ToolRegistry with schema validation and timeout
    tool_registry = get_tool_registry()
    tool_context = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "roles": state.get("roles", []),
        "permissions": state.get("permissions", []),
        "obo_token": obo_token,
        "correlation_id": correlation_id,
    }

    tool_res = await tool_registry.execute(
        tool_name=tool_name,
        arguments=arguments,
        context=tool_context,
    )

    if not tool_res.success:
        failed_entry: dict[str, Any] = {
            "tool_name": tool_name,
            "status": "ERROR",
            "reason": tool_res.error,
            "tenant_id": tenant_id,
            "caller_user_id": user_id,
        }
        return {
            "current_agent": "finnapigo_tool",
            "workflow_phase": "tool_failed",
            "tool_calls": [*state.get("tool_calls", []), failed_entry],
            "mascot_state": "alert",
            "next_agent": "verifier",
            "messages": [
                *state.get("messages", []),
                f"FinnApiGo Tool: Execution of '{tool_name}' failed: {tool_res.error}",
            ],
        }

    tool_call_entry: dict[str, Any] = {
        "tool_name": tool_name,
        "invoked_at": time.time(),
        "tenant_id": tenant_id,
        "caller_user_id": user_id,
        "delegated_actor": "jakeai-platform",
        "authorization_header": f"Bearer {obo_token[:15]}...",
        "output": tool_res.output,
        "execution_time_ms": tool_res.execution_time_ms,
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
