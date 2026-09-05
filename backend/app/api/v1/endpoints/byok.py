"""BYOK (Bring Your Own Key) REST endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.byok import SUPPORTED_PROVIDERS, get_byok_manager
from app.core.context import TenantContext
from app.core.security import get_current_tenant

router = APIRouter()


class BYOKStoreRequest(BaseModel):
    """Request payload to register or update an LLM provider API key."""

    provider: str = Field(
        ..., description="LLM provider: openai, gemini, anthropic, or openrouter"
    )
    api_key: str = Field(
        ..., min_length=8, description="Raw provider API key to encrypt"
    )


class BYOKKeyResponse(BaseModel):
    """Response returning masked key information."""

    tenant_id: str
    provider: str
    masked_key: str
    status: str


class BYOKProviderItem(BaseModel):
    """Provider key status item."""

    provider: str
    masked_key: str | None
    configured: bool


class BYOKListResponse(BaseModel):
    """List of configured provider keys for a tenant."""

    tenant_id: str
    keys: list[BYOKProviderItem]


@router.post(
    "/keys", response_model=BYOKKeyResponse, status_code=status.HTTP_201_CREATED
)
async def store_provider_key(
    request: BYOKStoreRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Store and encrypt a tenant-supplied LLM provider key."""
    norm_provider = request.provider.lower().strip()
    if norm_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{request.provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}",
        )

    byok = get_byok_manager()
    result = await byok.store_key(
        tenant_id=context.tenant_id,
        provider=norm_provider,
        api_key=request.api_key.strip(),
    )
    return result


@router.get("/keys", response_model=BYOKListResponse)
async def list_provider_keys(
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """List all supported providers and their configuration status with masked previews."""
    byok = get_byok_manager()
    keys = await byok.list_keys(context.tenant_id)
    return {
        "tenant_id": context.tenant_id,
        "keys": keys,
    }


@router.delete("/keys/{provider}", status_code=status.HTTP_200_OK)
async def delete_provider_key(
    provider: str,
    context: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Revoke and delete an encrypted provider key."""
    norm_provider = provider.lower().strip()
    byok = get_byok_manager()
    deleted = await byok.delete_key(context.tenant_id, norm_provider)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No key found for provider '{provider}' under this tenant",
        )
    return {
        "tenant_id": context.tenant_id,
        "provider": norm_provider,
        "status": "revoked",
    }
