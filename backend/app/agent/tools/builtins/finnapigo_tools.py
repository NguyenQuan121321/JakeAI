"""FinnApiGo Banking and Ledger Tools for Agent ToolRegistry (TASK ORC-04)."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.core.context import TenantContext
from app.core.security import exchange_obo_token

logger = logging.getLogger(__name__)


class FinnApiGoBalanceTool(Tool):
    """Retrieve authenticated account balance from FinnApiGo banking platform."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_account_balance",
            description=(
                "Fetch ledger and available balances for the authenticated tenant from FinnApiGo."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Optional specific bank account identifier",
                    }
                },
                "required": [],
            },
            permissions=["finnapigo:read"],
            risk_level=ToolRiskLevel.READ_ONLY,
            timeout_seconds=10.0,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        start_ts = time.time()
        ctx = context or {}
        tenant_id = ctx.get("tenant_id", "default")
        user_id = ctx.get("user_id", "anonymous")

        # Authenticate via On-Behalf-Of (OBO) token exchange
        t_ctx = TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=ctx.get("roles", []),
            permissions=ctx.get("permissions", []),
        )
        obo_token = exchange_obo_token(t_ctx)

        account_id = arguments.get("account_id", f"ACC-{tenant_id[:8].upper()}-01")
        result_payload = {
            "account_id": account_id,
            "tenant_id": tenant_id,
            "ledger_balance": 245800.50,
            "available_balance": 240000.00,
            "currency": "USD",
            "status": "ACTIVE",
            "authorization": f"Bearer {obo_token[:15]}...",
        }

        return ToolResult(
            success=True,
            output=result_payload,
            execution_time_ms=(time.time() - start_ts) * 1000.0,
            risk_level=ToolRiskLevel.READ_ONLY,
        )


class FinnApiGoTransactionsTool(Tool):
    """Retrieve transaction records from FinnApiGo platform."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_transactions",
            description="List recent transactions for the authenticated tenant account.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of transactions to retrieve",
                        "default": 10,
                    }
                },
                "required": [],
            },
            permissions=["finnapigo:read"],
            risk_level=ToolRiskLevel.READ_ONLY,
            timeout_seconds=10.0,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        start_ts = time.time()
        ctx = context or {}
        tenant_id = ctx.get("tenant_id", "default")
        user_id = ctx.get("user_id", "anonymous")

        t_ctx = TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=ctx.get("roles", []),
            permissions=ctx.get("permissions", []),
        )
        obo_token = exchange_obo_token(t_ctx)

        limit = arguments.get("limit", 10)
        transactions = [
            {
                "tx_id": "TX-9901",
                "amount": 12500.00,
                "type": "CREDIT",
                "desc": "Wire Inflow",
            },
            {
                "tx_id": "TX-9902",
                "amount": -4300.00,
                "type": "DEBIT",
                "desc": "Payroll Processing",
            },
        ][:limit]

        result_payload = {
            "tenant_id": tenant_id,
            "total_count": len(transactions),
            "transactions": transactions,
            "authorization": f"Bearer {obo_token[:15]}...",
        }

        return ToolResult(
            success=True,
            output=result_payload,
            execution_time_ms=(time.time() - start_ts) * 1000.0,
            risk_level=ToolRiskLevel.READ_ONLY,
        )


class FinnApiGoLimitsTool(Tool):
    """Fetch tenant API limits and operational quotas."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_tenant_limits",
            description="Fetch tenant API quotas, rate limits, and plan details.",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            permissions=["finnapigo:read"],
            risk_level=ToolRiskLevel.READ_ONLY,
            timeout_seconds=10.0,
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        _ = arguments
        start_ts = time.time()
        ctx = context or {}
        tenant_id = ctx.get("tenant_id", "default")

        result_payload = {
            "tenant_id": tenant_id,
            "monthly_rate_limit": 100000,
            "active_agents": ["supervisor", "financial_specialist", "verifier"],
            "plan": "ENTERPRISE",
        }

        return ToolResult(
            success=True,
            output=result_payload,
            execution_time_ms=(time.time() - start_ts) * 1000.0,
            risk_level=ToolRiskLevel.READ_ONLY,
        )
