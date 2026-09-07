"""Safe codebase symbol and text search tool."""

from __future__ import annotations

import ast
import logging
import os
import time
from pathlib import Path
from typing import Any

from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel

logger = logging.getLogger(__name__)


class SearchSymbolsTool(Tool):
    """Searches Python functions and classes in workspace files via AST parsing."""

    def __init__(self, workspace_root: str | None = None) -> None:
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="search_symbols",
            description="Searches for function and class definitions in workspace Python files.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symbol name or substring to search for",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum matches to return",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
            permissions=["agent:search"],
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        _ = context
        start_ts = time.time()
        query = arguments.get("query", "").lower()
        max_results = int(arguments.get("max_results", 10))

        matches: list[dict[str, Any]] = []

        for root, _, files in os.walk(self.workspace_root):
            if any(p in root for p in [".venv", "__pycache__", ".git"]):
                continue
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    try:
                        rel_path = full_path.relative_to(self.workspace_root).as_posix()
                        with open(full_path, encoding="utf-8", errors="ignore") as f:  # noqa: ASYNC230
                            tree = ast.parse(f.read(), filename=rel_path)

                        for node in ast.walk(tree):
                            if (
                                isinstance(
                                    node,
                                    (
                                        ast.FunctionDef,
                                        ast.AsyncFunctionDef,
                                        ast.ClassDef,
                                    ),
                                )
                                and query in node.name.lower()
                            ):
                                matches.append(
                                    {
                                        "file": rel_path,
                                        "name": node.name,
                                        "type": "class"
                                        if isinstance(node, ast.ClassDef)
                                        else "function",
                                        "lineno": node.lineno,
                                    }
                                )
                                if len(matches) >= max_results:
                                    break
                    except (
                        SyntaxError,
                        ValueError,
                        OSError,
                        UnicodeDecodeError,
                        RecursionError,
                    ) as exc:
                        logger.debug(
                            "Skipping unparseable Python file %s: %s", full_path, exc
                        )
                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

        return ToolResult(
            success=True,
            output={"query": query, "matches": matches, "count": len(matches)},
            risk_level=ToolRiskLevel.READ_ONLY,
            execution_time_ms=(time.time() - start_ts) * 1000.0,
        )
