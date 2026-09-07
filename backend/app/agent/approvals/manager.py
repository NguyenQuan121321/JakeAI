"""Approval Manager managing persistence, status transitions, and tenant boundaries."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.agent.approvals.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Manages approval gates with strict multi-tenant boundary checks."""

    def __init__(self) -> None:
        # Mapping: approval_id -> ApprovalRequest
        self._approvals: dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        task_id: str,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        reason: str,
        risk_level: str = "dangerous",
    ) -> ApprovalRequest:
        """Create and store a pending approval request."""
        approval_id = f"appr_{uuid.uuid4().hex[:12]}"
        req = ApprovalRequest(
            approval_id=approval_id,
            task_id=task_id,
            run_id=run_id,
            tenant_id=tenant_id,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=risk_level,
            reason=reason,
            status=ApprovalStatus.PENDING,
            created_at=time.time(),
        )
        self._approvals[approval_id] = req
        logger.info(
            "Created approval request %s for tool %s (tenant %s, run %s)",
            approval_id,
            tool_name,
            tenant_id,
            run_id,
        )
        return req

    def get_request(self, approval_id: str, tenant_id: str) -> ApprovalRequest:
        """Retrieve an approval request, verifying tenant ownership."""
        req = self._approvals.get(approval_id)
        if req is None:
            raise KeyError(f"Approval request '{approval_id}' not found.")

        if req.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Approval '{approval_id}' belongs to tenant '{req.tenant_id}', "
                f"access attempted by '{tenant_id}'."
            )
        return req

    def decide(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        tenant_id: str,
        user_id: str = "anonymous",
    ) -> ApprovalRequest:
        """Record human decision on an approval gate with tenant boundary check."""
        req = self.get_request(approval_id, tenant_id)

        if req.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Approval '{approval_id}' is already finalized as '{req.status}'."
            )

        now = time.time()
        req.decided_at = now
        req.decided_by = user_id
        if decision.approved:
            req.status = ApprovalStatus.APPROVED
        else:
            req.status = ApprovalStatus.REJECTED
            req.rejection_reason = decision.reason or "Rejected by operator"

        logger.info(
            "Approval %s resolved as %s by user %s (tenant %s)",
            approval_id,
            req.status.value,
            user_id,
            tenant_id,
        )
        return req

    def list_pending(
        self, tenant_id: str, run_id: str | None = None
    ) -> list[ApprovalRequest]:
        """List pending approval requests within tenant boundary."""
        results: list[ApprovalRequest] = []
        for req in self._approvals.values():
            if (
                req.tenant_id == tenant_id
                and req.status == ApprovalStatus.PENDING
                and (run_id is None or req.run_id == run_id)
            ):
                results.append(req)
        return results

    def clear(self) -> None:
        """Reset internal store for test isolation."""
        self._approvals.clear()

    # Aliases for interface ergonomics
    get_pending_approvals = list_pending
    decide_request = decide


_approval_manager: ApprovalManager | None = None


def get_approval_manager() -> ApprovalManager:
    """Singleton accessor for ApprovalManager."""
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = ApprovalManager()
    return _approval_manager
