"""Real-Time Operational Analytics Dashboard REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.services.billing import AnalyticsDashboard, get_billing_service

router = APIRouter()


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve operational telemetry: tokens saved via caching, TTFT, PRs audited, and cost metrics."""
    billing_svc = get_billing_service()
    return await billing_svc.get_dashboard_metrics(context.tenant_id)
