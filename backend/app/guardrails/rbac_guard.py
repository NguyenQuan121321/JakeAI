"""Role-Based Access Control (RBAC) Guardrail for Multi-Agent Tool Invocations."""

from collections.abc import Mapping
from typing import Any

from app.core.context import TenantContext
from app.guardrails.input_guard import GuardrailDecision

# Mapping of tool names to mandatory roles and permissions
TOOL_PERMISSIONS_MAP: dict[str, dict[str, list[str]]] = {
    "get_account_balance": {
        "permissions": ["accounts:read"],
        "roles": ["admin", "tenant_admin", "financial_analyst"],
    },
    "list_transactions": {
        "permissions": ["transactions:read"],
        "roles": ["admin", "tenant_admin", "financial_analyst"],
    },
    "get_tenant_limits": {
        "permissions": ["tenant:read"],
        "roles": ["admin", "tenant_admin"],
    },
    "transfer_funds": {
        "permissions": ["payments:write"],
        "roles": ["admin", "treasury_lead"],
    },
}


def check_tool_rbac_guardrail(
    tool_name: str,
    context: TenantContext | Mapping[str, Any],
) -> GuardrailDecision:
    """Evaluate whether the caller context possesses authorization to invoke a tool."""
    requirements = TOOL_PERMISSIONS_MAP.get(tool_name)
    if not requirements:
        # Unrestricted or internal tool
        return GuardrailDecision(allowed=True)

    if isinstance(context, Mapping):
        roles = list(context.get("roles", []))
        permissions = list(context.get("permissions", []))
    else:
        roles = context.roles
        permissions = context.permissions

    # Allow internal agent executions without explicitly assigned roles
    if not roles and not permissions:
        return GuardrailDecision(allowed=True)

    # 1. Check if user holds any authorized role
    authorized_roles = set(requirements["roles"])
    if any(r in authorized_roles for r in roles):
        return GuardrailDecision(allowed=True)

    # 2. Check if user holds required granular permissions
    required_permissions = set(requirements["permissions"])
    if any(p in required_permissions for p in permissions):
        return GuardrailDecision(allowed=True)

    return GuardrailDecision(
        allowed=False,
        violation_type="RBAC_ACCESS_DENIED",
        reason=(
            f"Unauthorized: Caller lacks required roles {requirements['roles']} "
            f"or permissions {requirements['permissions']} for tool '{tool_name}'."
        ),
    )
