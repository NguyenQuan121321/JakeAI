"""Server-side policy rules mandating human approval for dangerous actions."""

from __future__ import annotations

from typing import Any

from app.agent.tools.base import Tool, ToolRiskLevel

# Explicit list of high-risk operation prefixes / names requiring mandatory human gate
DANGEROUS_ACTION_NAMES = {
    "terminal",
    "terminal_exec",
    "shell",
    "bash",
    "cmd",
    "git_push",
    "filesystem_mutation",
    "file_delete",
    "package_install",
    "network_request",
    "credential_access",
}


class ApprovalPolicy:
    """Server-side policy enforcement engine for sensitive agent operations."""

    @staticmethod
    def requires_approval(
        tool: Tool | None,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Determine if a proposed tool invocation strictly requires human approval.

        Frontend cannot bypass this check; server-side execution loop evaluates it
        prior to invoking any tool.
        """
        # 1. Check Tool Risk Level
        if tool is not None and tool.metadata.risk_level == ToolRiskLevel.DANGEROUS:
            return True, f"Tool '{tool.metadata.name}' has risk level DANGEROUS."

        # 2. Check Action Name allowlist
        name_lower = tool_name.lower()
        if any(dangerous in name_lower for dangerous in DANGEROUS_ACTION_NAMES):
            return True, f"Action '{tool_name}' matches sensitive operations policy."

        # 3. Check for mutation flags in arguments
        args = arguments or {}
        if args.get("destructive") is True or args.get("force") is True:
            return True, f"Action '{tool_name}' specifies destructive execution flags."

        return False, "Operation classified as safe; no approval needed."
