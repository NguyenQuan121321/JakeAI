"""Safe local file inspection tool."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel


class ReadFileTool(Tool):
    """Safely reads file contents within a specified or sandboxed workspace."""

    def __init__(self, workspace_root: str | None = None) -> None:
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read_file",
            description="Reads text content from a specified workspace file.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path to read"},
                    "max_bytes": {"type": "integer", "description": "Max bytes to read", "default": 10000},
                },
                "required": ["path"],
            },
            permissions=["agent:read_files"],
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        _ = context
        start_ts = time.time()
        raw_path = arguments.get("path", "")
        max_bytes = int(arguments.get("max_bytes", 10000))

        # Enforce path containment
        target = (self.workspace_root / raw_path).resolve()
        try:
            target.relative_to(self.workspace_root)
        except ValueError:
            return ToolResult(
                success=False,
                error=f"Access denied: Path '{raw_path}' escapes workspace boundary.",
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )

        if not target.exists() or not target.is_file():
            return ToolResult(
                success=False,
                error=f"File '{raw_path}' not found or is not a regular file.",
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )

        try:
            with open(target, encoding="utf-8", errors="replace") as f:  # noqa: ASYNC230
                content = f.read(max_bytes)
            return ToolResult(
                success=True,
                output={"path": raw_path, "content": content, "bytes_read": len(content)},
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Failed to read file: {exc!s}",
                risk_level=ToolRiskLevel.READ_ONLY,
                execution_time_ms=(time.time() - start_ts) * 1000.0,
            )
