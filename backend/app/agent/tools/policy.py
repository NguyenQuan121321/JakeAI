"""Policy engine for validating tool authorization and argument safety."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.tools.base import Tool, ToolRiskLevel

logger = logging.getLogger(__name__)

# Dangerous shell/command injection patterns
_DANGEROUS_PATTERNS = [
    re.compile(r";\s*rm\s+-rf", re.IGNORECASE),
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh)", re.IGNORECASE),
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh)", re.IGNORECASE),
    re.compile(r">\s*/dev/sd", re.IGNORECASE),
]


class ToolPolicyDecision:
    """Outcome of a tool execution policy check."""

    def __init__(
        self,
        allowed: bool,
        requires_approval: bool = False,
        reason: str = "Authorized",
    ) -> None:
        self.allowed = allowed
        self.requires_approval = requires_approval
        self.reason = reason


class ToolPolicyEngine:
    """Validates capabilities, tenant permissions, and argument safety before tool execution."""

    @staticmethod
    def evaluate(
        tool: Tool,
        arguments: dict[str, Any],
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> ToolPolicyDecision:
        """Evaluate authorization and safety rules for a proposed tool execution."""
        meta = tool.metadata
        roles = user_roles or []
        perms = set(user_permissions or [])

        # 1. Tenant Permission Verification
        is_admin = "admin" in roles or "tenant_admin" in roles
        if meta.permissions and not is_admin:
            missing = [p for p in meta.permissions if p not in perms]
            if missing:
                return ToolPolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason=f"Forbidden: Tenant context lacks required permissions: {missing}",
                )

        # 2. Path Traversal and Argument Injection Safeguards
        args_str = str(arguments)
        if ".." in args_str or "/etc/passwd" in args_str or "C:\\Windows\\System32" in args_str:
            return ToolPolicyDecision(
                allowed=False,
                requires_approval=False,
                reason="Policy violation: Malicious path traversal argument detected",
            )

        for pattern in _DANGEROUS_PATTERNS:
            if pattern.search(args_str):
                return ToolPolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason="Policy violation: Malicious shell execution argument detected",
                )

        # 3. Risk Level Evaluation: Dangerous tools require human approval
        if meta.risk_level == ToolRiskLevel.DANGEROUS:
            return ToolPolicyDecision(
                allowed=True,
                requires_approval=True,
                reason=f"Action '{meta.name}' is classified as DANGEROUS and requires human approval",
            )

        return ToolPolicyDecision(allowed=True, requires_approval=False, reason="Authorized")
