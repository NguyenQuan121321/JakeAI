"""Tool abstractions, metadata definitions, and result schemas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolRiskLevel(StrEnum):
    """Categorization of operational risk associated with tool execution."""

    READ_ONLY = "read_only"  # Zero mutation, safe inspection (e.g. read file, search)
    SAFE_WRITE = (
        "safe_write"  # Controlled scratchpad mutation (e.g. write scratch file)
    )
    DANGEROUS = "dangerous"  # High-impact operations requiring human approval (e.g. terminal, git push)


class ToolMetadata(BaseModel):
    """Comprehensive tool specification."""

    name: str = Field(..., description="Unique tool invocation name")
    description: str = Field(
        ..., description="Human and model-readable description of tool capability"
    )
    input_schema: dict[str, Any] = Field(
        ..., description="JSON Schema defining expected arguments"
    )
    permissions: list[str] = Field(
        default_factory=list, description="Required tenant permissions/capabilities"
    )
    risk_level: ToolRiskLevel = Field(default=ToolRiskLevel.READ_ONLY)


class ToolResult(BaseModel):
    """Normalized outcome returned from a tool execution."""

    success: bool
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY


class Tool(ABC):
    """Abstract base class for all Agent tools."""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Tool registration metadata."""
        ...

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Execute the tool action with validated arguments and execution context."""
        ...
