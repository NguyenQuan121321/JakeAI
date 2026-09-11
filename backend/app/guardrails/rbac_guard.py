"""Role-Based Access Control (RBAC) Guardrail for Multi-Agent Tool Invocations."""

from collections.abc import Mapping
from typing import Any

from app.core.context import TenantContext
from app.guardrails.input_guard import GuardrailDecision

# Public tools explicitly permitted without granular roles or permissions
PUBLIC_TOOLS: set[str] = {
    "calculator",
    "system_time",
}

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
    "read_file": {
        "permissions": ["files:read"],
        "roles": ["admin", "tenant_admin", "developer", "engineer"],
    },
    "search_symbols": {
        "permissions": ["code:read"],
        "roles": ["admin", "tenant_admin", "developer", "engineer"],
    },
    "mock_dangerous_shell": {
        "permissions": ["system:execute"],
        "roles": ["admin"],
    },
    "finnapigo_balance": {
        "permissions": ["accounts:read"],
        "roles": ["admin", "tenant_admin", "financial_analyst"],
    },
    "finnapigo_transactions": {
        "permissions": ["transactions:read"],
        "roles": ["admin", "tenant_admin", "financial_analyst"],
    },
    "finnapigo_limits": {
        "permissions": ["tenant:read"],
        "roles": ["admin", "tenant_admin"],
    },
}


def check_tool_rbac_guardrail(
    tool_name: str,
    context: TenantContext | Mapping[str, Any],
) -> GuardrailDecision:
    """Evaluate whether the caller context possesses authorization to invoke a tool."""
    # 1. Public tools bypass role/permission mapping
    if tool_name in PUBLIC_TOOLS:
        return GuardrailDecision(allowed=True)

    # 2. Unknown/unmapped tools fail closed (DENY)
    requirements = TOOL_PERMISSIONS_MAP.get(tool_name)
    if not requirements:
        return GuardrailDecision(
            allowed=False,
            violation_type="RBAC_UNMAPPED_TOOL",
            reason=f"Unauthorized: Tool '{tool_name}' has no policy mapping and fails closed.",
        )

    if isinstance(context, Mapping):
        roles = list(context.get("roles", []))
        permissions = list(context.get("permissions", []))
    else:
        roles = context.roles
        permissions = context.permissions

    # 3. Empty authorization context fails closed (DENY)
    if not roles and not permissions:
        return GuardrailDecision(
            allowed=False,
            violation_type="RBAC_EMPTY_CONTEXT",
            reason=f"Unauthorized: Caller context has no assigned roles or permissions for tool '{tool_name}'.",
        )

    # 4. Check if user holds any authorized role
    authorized_roles = set(requirements.get("roles", []))
    if any(r in authorized_roles for r in roles):
        return GuardrailDecision(allowed=True)

    # 5. Check if user holds required granular permissions
    required_permissions = set(requirements.get("permissions", []))
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
