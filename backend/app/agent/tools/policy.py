"""Policy engine for validating tool authorization and argument safety."""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from app.agent.tools.base import Tool, ToolRiskLevel

logger = logging.getLogger(__name__)

# Dangerous shell/command injection patterns
_DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-(?:[a-zA-Z]*[rf][a-zA-Z]*)\b", re.IGNORECASE),
    re.compile(r"\bmkfs(?:\.\w+)?\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;", re.IGNORECASE),
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh|zsh|dash)", re.IGNORECASE),
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh|zsh|dash)", re.IGNORECASE),
    re.compile(r"\|\s*(?:bash|sh|zsh|dash)\b", re.IGNORECASE),
    re.compile(r">\s*/dev/(?:sd[a-z]|nvme|zero|null)", re.IGNORECASE),
    re.compile(r"\b(?:nc|netcat|ncat)\b.*-e\s+/\w+", re.IGNORECASE),
    re.compile(r"(?:bash|sh)\s+-i\s+>&", re.IGNORECASE),
    re.compile(r"/dev/tcp/\d+", re.IGNORECASE),
    re.compile(r"\bchmod\s+(?:-R\s+)?777\s+/", re.IGNORECASE),
    re.compile(
        r"\b(?:cat|head|tail|less|more)\s+/etc/(?:shadow|sudoers)\b", re.IGNORECASE
    ),
]

_SENSITIVE_PATHS = [
    re.compile(r"/etc/(?:passwd|shadow|sudoers|master\.passwd)", re.IGNORECASE),
    re.compile(r"/proc/(?:self|\d+)/(?:environ|cmdline|mem)", re.IGNORECASE),
    re.compile(r"(?:^|[\\/])\.ssh(?:[\\/]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[\\/])id_rsa(?:[\\/]|$)", re.IGNORECASE),
    re.compile(r"[a-z]:\\windows\\(?:system32|win\.ini|system\.ini)", re.IGNORECASE),
    re.compile(r"\\system32\\config\\sam", re.IGNORECASE),
]

# Canonical permission aliases unifying registry metadata with RBAC guardrails
PERMISSION_ALIASES: dict[str, set[str]] = {
    "agent:read_files": {"files:read", "read_files", "agent:read_files"},
    "files:read": {"agent:read_files", "files:read", "read_files"},
    "agent:search": {"code:read", "agent:search", "search"},
    "code:read": {"agent:search", "code:read", "search"},
    "finnapigo:read": {
        "accounts:read",
        "transactions:read",
        "tenant:read",
        "finnapigo:read",
    },
    "accounts:read": {"finnapigo:read", "accounts:read"},
    "transactions:read": {"finnapigo:read", "transactions:read"},
    "tenant:read": {"finnapigo:read", "tenant:read"},
    "system:execute": {"terminal:execute", "system:execute", "mock_dangerous_shell"},
}

ROLE_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "financial_analyst": {
        "get_account_balance",
        "list_transactions",
        "get_tenant_limits",
        "calculator",
    },
    "developer": {"read_file", "search_symbols", "calculator", "system_time"},
    "engineer": {"read_file", "search_symbols", "calculator", "system_time"},
}


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
            # Check if user roles inherently allow this tool
            role_allowed = any(
                meta.name in ROLE_TOOL_ALLOWLIST.get(r, set()) for r in roles
            )
            if not role_allowed:
                # Check direct or aliased permission matches
                effective_perms = set(perms)
                for p in perms:
                    effective_perms.update(PERMISSION_ALIASES.get(p, set()))

                missing = []
                for required in meta.permissions:
                    accepted_variants = PERMISSION_ALIASES.get(required, {required})
                    if not (accepted_variants & effective_perms):
                        missing.append(required)

                if missing:
                    return ToolPolicyDecision(
                        allowed=False,
                        requires_approval=False,
                        reason=f"Forbidden: Tenant context lacks required permissions: {missing}",
                    )

        # 2. Path Traversal and Argument Injection Safeguards
        def _extract_strings(obj: Any) -> list[str]:
            res: list[str] = []
            if isinstance(obj, str):
                res.append(obj)
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    res.extend(_extract_strings(k))
                    res.extend(_extract_strings(v))
            elif isinstance(obj, (list, tuple, set)):
                for item in obj:
                    res.extend(_extract_strings(item))
            return res

        arg_strings = _extract_strings(arguments)
        args_str = str(arguments)
        # Also include whole args_str
        all_targets = [*arg_strings, args_str]

        for raw_val in all_targets:
            # Check for null byte
            if "\x00" in raw_val or "%00" in raw_val or "\\x00" in raw_val:
                return ToolPolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason="Policy violation: Malicious null byte injection detected",
                )

            # Normalize URL encoding
            try:
                decoded_val = urllib.parse.unquote(urllib.parse.unquote(raw_val))
            except Exception:
                decoded_val = raw_val

            norm_val = decoded_val.replace("\\", "/")

            # Directory traversal
            if ".." in decoded_val or ".." in norm_val:
                return ToolPolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason="Policy violation: Malicious path traversal argument detected",
                )

            # Sensitive system file access
            for sensitive in _SENSITIVE_PATHS:
                if (
                    sensitive.search(decoded_val)
                    or sensitive.search(norm_val)
                    or sensitive.search(raw_val)
                ):
                    return ToolPolicyDecision(
                        allowed=False,
                        requires_approval=False,
                        reason="Policy violation: Unauthorized sensitive path access detected",
                    )

            # Shell command injection and dangerous commands
            for pattern in _DANGEROUS_PATTERNS:
                if (
                    pattern.search(decoded_val)
                    or pattern.search(norm_val)
                    or pattern.search(raw_val)
                ):
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

        return ToolPolicyDecision(
            allowed=True, requires_approval=False, reason="Authorized"
        )
