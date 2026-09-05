"""Automated VietQR / PayOS Billing REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.services.billing import SubscriptionInfo, get_billing_service

router = APIRouter()


class PayOSWebhookRequest(BaseModel):
    """Payload sent by PayOS / VietQR webhook."""

    code: str = Field(default="00", description="Result code (00 = success)")
    desc: str = Field(default="success", description="Result message")
    data: dict[str, Any] = Field(
        ..., description="Transaction details (orderCode, amount, description)"
    )
    signature: str = Field(..., description="HMAC-SHA256 signature for data integrity")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_payment_webhook(
    request: PayOSWebhookRequest,
    x_webhook_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    """Process VietQR / PayOS payment webhook with HMAC-SHA256 verification and tier provisioning."""
    billing_svc = get_billing_service()
    sig_to_verify = request.signature or x_webhook_signature or ""

    # Verify signature
    valid = billing_svc.verify_signature(request.data, sig_to_verify)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid HMAC signature: payload authenticity could not be verified",
        )

    return await billing_svc.process_payment_webhook(request.model_dump())


@router.get("/subscription", response_model=SubscriptionInfo)
async def get_current_subscription(
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve active subscription tier, monthly token quota, and enabled features."""
    billing_svc = get_billing_service()
    return billing_svc.get_subscription(context.tenant_id)
