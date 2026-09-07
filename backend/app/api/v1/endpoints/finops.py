"""AI FinOps & Cost Truth REST API Endpoints.

Provides endpoints for:
- GET /api/v1/finops/summary: Aggregated token efficiency, actual costs, and savings breakdown
- GET /api/v1/finops/transactions: Paginated per-request accounting records with separate metrics
- GET /api/v1/finops/budget: Active tenant token quota and dollar budget health
- POST /api/v1/finops/budget: Configure token quotas, dollar budget limits, and warning thresholds
- GET /api/v1/finops/reconciliation: Authoritative provider vs local planning variance telemetry
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.finops.models import (
    FinOpsRecord,
    FinOpsSummary,
    ReconciliationReport,
    TenantBudget,
    UpdateBudgetRequest,
)
from app.finops.service import get_finops_service

router = APIRouter()


@router.get("/summary", response_model=FinOpsSummary)
async def get_finops_summary(
    period: str | None = Query(
        default=None,
        description="Billing period formatted as YYYY-MM (defaults to current month)",
    ),
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve tenant FinOps summary: baseline vs actual costs, non-double-counted savings, and quota health."""
    svc = get_finops_service()
    return await svc.get_summary(tenant_id=context.tenant_id, period=period)


@router.get("/transactions", response_model=list[FinOpsRecord])
async def list_finops_transactions(
    period: str | None = Query(
        default=None, description="Billing period filter (YYYY-MM)"
    ),
    limit: int = Query(default=50, ge=1, le=500, description="Max records to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve paginated per-request accounting records with separate token and cost metrics."""
    svc = get_finops_service()
    return svc.get_transactions(
        tenant_id=context.tenant_id,
        period=period,
        limit=limit,
        offset=offset,
    )


@router.get("/budget", response_model=TenantBudget)
async def get_tenant_budget(
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve active tenant token quota and dollar budget status."""
    svc = get_finops_service()
    return await svc.get_budget(tenant_id=context.tenant_id)


@router.post("/budget", response_model=TenantBudget, status_code=status.HTTP_200_OK)
async def configure_tenant_budget(
    request: UpdateBudgetRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Configure tenant token quota limit, monthly dollar budget ceiling, and warning threshold."""
    svc = get_finops_service()
    return await svc.set_budget(
        tenant_id=context.tenant_id,
        token_quota=request.token_quota,
        dollar_budget_usd=request.dollar_budget_usd,
        warning_threshold=request.warning_threshold,
    )


@router.get("/reconciliation", response_model=ReconciliationReport)
async def get_reconciliation_report(
    period: str | None = Query(
        default=None, description="Billing period filter (YYYY-MM)"
    ),
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve reconciliation report comparing local planning estimates against authoritative provider truth."""
    svc = get_finops_service()
    return svc.get_reconciliation_report(tenant_id=context.tenant_id, period=period)
