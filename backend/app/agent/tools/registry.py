"""Tool Registry managing discovery, schema validation, and safe execution."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.tools.base import Tool, ToolMetadata, ToolResult
from app.agent.tools.policy import ToolPolicyEngine

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry maintaining available Agent tools with policy and schema enforcement."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        name = tool.metadata.name
        self._tools[name] = tool
        logger.debug(
            "Registered agent tool: %s (risk: %s)", name, tool.metadata.risk_level
        )

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Look up tool by name."""
        return self._tools.get(name)

    def discover(
        self,
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> list[ToolMetadata]:
        """Discover tools available to the given user/tenant context."""
        results: list[ToolMetadata] = []
        for tool in self._tools.values():
            decision = ToolPolicyEngine.evaluate(
                tool=tool,
                arguments={},
                user_roles=user_roles,
                user_permissions=user_permissions,
            )
            if decision.allowed:
                results.append(tool.metadata)
        return results

    def validate(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate presence of required parameters based on input_schema."""
        tool = self.get(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' not found in registry."

        schema = tool.metadata.input_schema
        required_fields = schema.get("required", [])
        missing = [f for f in required_fields if f not in arguments]
        if missing:
            return False, f"Missing required parameters for '{tool_name}': {missing}"

        return True, None

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Validate policy and execute target tool with timing and error isolation."""
        start_ts = time.time()
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' is not registered.",
                execution_time_ms=0.0,
            )

        ctx = context or {}
        roles = ctx.get("roles", [])
        perms = ctx.get("permissions", [])

        # Evaluate policy
        decision = ToolPolicyEngine.evaluate(
            tool=tool,
            arguments=arguments,
            user_roles=roles,
            user_permissions=perms,
        )

        if not decision.allowed:
            return ToolResult(
                success=False,
                error=decision.reason,
                risk_level=tool.metadata.risk_level,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )

        # Validate arguments
        valid, err_msg = self.validate(tool_name, arguments)
        if not valid:
            return ToolResult(
                success=False,
                error=err_msg,
                risk_level=tool.metadata.risk_level,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )

        try:
            return await tool.execute(arguments=arguments, context=ctx)
        except Exception as exc:
            exec_time = (time.time() - start_ts) * 1000.0
            logger.error("Execution exception in tool '%s': %s", tool_name, exc)
            return ToolResult(
                success=False,
                error=f"Tool execution exception: {exc!s}",
                risk_level=tool.metadata.risk_level,
                execution_time_ms=exec_time,
            )


_default_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Singleton accessor for global default ToolRegistry."""
    global _default_tool_registry
    if _default_tool_registry is None:
        _default_tool_registry = ToolRegistry()
        # Register built-in tools
        from app.agent.tools.builtins.file_tools import ReadFileTool
        from app.agent.tools.builtins.mock_tools import (
            CalculatorTool,
            MockDangerousShellTool,
            SystemTimeTool,
        )
        from app.agent.tools.builtins.search_tools import SearchSymbolsTool

        _default_tool_registry.register(ReadFileTool())
        _default_tool_registry.register(SearchSymbolsTool())
        _default_tool_registry.register(CalculatorTool())
        _default_tool_registry.register(SystemTimeTool())
        _default_tool_registry.register(MockDangerousShellTool())

    return _default_tool_registry
