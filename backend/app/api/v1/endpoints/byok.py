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
        ...,
        description="LLM provider: openai, gemini, anthropic, groq, deepseek, or openrouter",
    )
    api_key: str = Field(
        ..., min_length=8, description="Raw provider API key to encrypt"
    )
    validate_key: bool = Field(
        default=False,
        description="Whether to perform live probe validation before storing",
    )


class BYOKRotateRequest(BaseModel):
    """Request payload to rotate an existing provider API key."""

    new_api_key: str = Field(
        ..., min_length=8, description="New raw provider API key to encrypt"
    )
    validate_key: bool = Field(
        default=False,
        description="Whether to perform live probe validation before rotating",
    )


class BYOKValidateRequest(BaseModel):
    """Request payload to validate a candidate provider API key."""

    provider: str = Field(..., description="Target LLM provider")
    api_key: str = Field(..., min_length=8, description="Raw API key to validate")


class BYOKValidationResponse(BaseModel):
    """Response returning provider key validation verdict."""

    provider: str
    is_valid: bool
    error: str | None = None


class BYOKKeyResponse(BaseModel):
    """Response returning masked key information and lifecycle status."""

    tenant_id: str
    provider: str
    masked_key: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    last_validated_at: str | None = None
    validation_status: str | None = None


class BYOKProviderItem(BaseModel):
    """Provider key status item."""

    provider: str
    masked_key: str | None
    configured: bool
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None
    last_validated_at: str | None = None
    validation_status: str | None = None


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
    try:
        result = await byok.store_key(
            tenant_id=context.tenant_id,
            provider=norm_provider,
            api_key=request.api_key.strip(),
            validate=request.validate_key,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


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


@router.post("/keys/validate", response_model=BYOKValidationResponse)
async def validate_candidate_key(
    request: BYOKValidateRequest,
    _context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Validate candidate LLM provider key via minimal quota-safe probe."""
    norm_provider = request.provider.lower().strip()
    if norm_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{request.provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}",
        )
    byok = get_byok_manager()
    is_valid, err = await byok.validate_key(norm_provider, request.api_key.strip())
    return {
        "provider": norm_provider,
        "is_valid": is_valid,
        "error": err,
    }


@router.post("/keys/{provider}/validate", response_model=BYOKValidationResponse)
async def validate_existing_key(
    provider: str,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Validate an existing stored key for this tenant without burning generation quota."""
    norm_provider = provider.lower().strip()
    if norm_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}",
        )
    byok = get_byok_manager()
    try:
        is_valid, err = await byok.validate_stored_key(context.tenant_id, norm_provider)
        return {
            "provider": norm_provider,
            "is_valid": is_valid,
            "error": err,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/keys/{provider}/rotate",
    response_model=BYOKKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def rotate_provider_key(
    provider: str,
    request: BYOKRotateRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Rotate an existing provider key for this tenant."""
    norm_provider = provider.lower().strip()
    if norm_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}",
        )
    byok = get_byok_manager()
    try:
        result = await byok.rotate_key(
            tenant_id=context.tenant_id,
            provider=norm_provider,
            new_api_key=request.new_api_key.strip(),
            validate=request.validate_key,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/keys/{provider}/revoke",
    response_model=BYOKKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_provider_key(
    provider: str,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Revoke an existing provider key, preventing runtime inference without wiping metadata."""
    norm_provider = provider.lower().strip()
    if norm_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}",
        )
    byok = get_byok_manager()
    try:
        result = await byok.revoke_key(context.tenant_id, norm_provider)
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


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
