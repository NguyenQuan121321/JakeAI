"""Built-in safe utility tools and mock dangerous tool for policy verification."""

from __future__ import annotations

import datetime
import time
from typing import Any

from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel


class CalculatorTool(Tool):
    """Safely evaluates basic arithmetic expressions."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="calculator",
            description="Evaluates simple arithmetic expressions safely.",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "e.g. 10 * 5 + 2"},
                },
                "required": ["expression"],
            },
            permissions=[],
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        _ = context
        start_ts = time.time()
        expr = arguments.get("expression", "").strip()

        # Sanitize arithmetic chars only
        allowed_chars = set("0123456789+-*/(). %")
        if not expr or not all(c in allowed_chars for c in expr):
            return ToolResult(
                success=False,
                error="Invalid characters in arithmetic expression.",
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )

        try:
            # Safe eval with empty globals/locals
            res = eval(expr, {"__builtins__": {}}, {})  # nosec B307
            return ToolResult(
                success=True,
                output={"expression": expr, "result": res},
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Evaluation failed: {exc!s}",
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )


class SystemTimeTool(Tool):
    """Returns current UTC date and timestamp."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="system_time",
            description="Returns current UTC ISO timestamp and epoch seconds.",
            input_schema={"type": "object", "properties": {}},
            permissions=[],
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        _ = (arguments, context)
        start_ts = time.time()
        now = datetime.datetime.now(datetime.UTC)
        return ToolResult(
            success=True,
            output={"iso": now.isoformat(), "timestamp": now.timestamp()},
            risk_level=ToolRiskLevel.READ_ONLY,
            execution_time_ms=(time.time() - start_ts) * 1000.0,
        )


class MockDangerousShellTool(Tool):
    """Simulated terminal tool marked DANGEROUS for server-side approval verification."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="terminal_exec",
            description="Simulated shell command execution requiring mandatory human approval.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
            },
            permissions=["agent:terminal"],
            risk_level=ToolRiskLevel.DANGEROUS,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        _ = context
        start_ts = time.time()
        cmd = arguments.get("command", "")
        # Emulate safe execution of an approved command
        return ToolResult(
            success=True,
            output={"command": cmd, "stdout": f"[simulated output for: {cmd}]", "returncode": 0},
            risk_level=ToolRiskLevel.DANGEROUS,
            execution_time_ms=(time.time() - start_ts) * 1000.0,
        )
