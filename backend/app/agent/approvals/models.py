"""Models for human-in-the-loop approval workflow."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ApprovalStatus(StrEnum):
    """Status of a dangerous action approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(BaseModel):
    """Payload submitted by authorized human user to resolve an approval gate."""

    approved: bool = Field(..., description="Whether the dangerous action is approved to proceed")
    reason: str | None = Field(default=None, description="Optional explanation or rejection rationale")


class ApprovalRequest(BaseModel):
    """Server-persisted approval gate record."""

    approval_id: str = Field(..., description="Unique approval identifier")
    task_id: str = Field(..., description="Target task identifier")
    run_id: str = Field(..., description="Target execution run identifier")
    tenant_id: str = Field(..., description="Tenant boundary identifier")
    tool_name: str = Field(..., description="Dangerous tool pending execution")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Proposed tool arguments")
    risk_level: str = Field(default="dangerous", description="Tool risk classification")
    reason: str = Field(..., description="Explanation of why approval is required")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    created_at: float = Field(default_factory=time.time)
    decided_at: float | None = None
    decided_by: str | None = None
    rejection_reason: str | None = None
