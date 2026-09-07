"""Resource bounds and limits for agent execution."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResourceLimits(BaseModel):
    """Resource constraints enforced on agent tool and sandbox executions."""

    timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_output_bytes: int = Field(default=1_048_576, ge=1024)  # 1 MB
    max_file_size_bytes: int = Field(default=5_242_880, ge=1024)  # 5 MB
    allow_network: bool = Field(default=False)
    allow_arbitrary_shell: bool = Field(default=False)
