"""BYOK HTTP policy: exact permissions, explicit signed tenant, owner/delegation."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr

from app.core.byok import get_byok_manager
from app.core.byok_storage import BYOKError
from app.core.context import TenantContext
from app.core.security import get_current_tenant


class BYOKRoute(APIRoute):
    """Do not echo input, field paths, nested values, or dependency exceptions."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422, content={"detail": "BYOK_INVALID_REQUEST"}
                )
            except BYOKError as exc:
                return JSONResponse(
                    status_code=exc.status_code, content={"detail": exc.code}
                )

        return handle


router = APIRouter(route_class=BYOKRoute)


def _permission(required: str) -> Callable[..., Coroutine[Any, Any, TenantContext]]:
    async def check(
        context: TenantContext = Depends(get_current_tenant),
    ) -> TenantContext:
        # Do not use role/wildcard-expanding TenantContext.has_permission here.
        if not context.explicit_tenant or not context.tenant_id or not context.user_id:
            raise HTTPException(403, "BYOK_IDENTITY_REQUIRED")
        if required not in context.permissions:
            raise HTTPException(403, "BYOK_PERMISSION_REQUIRED")
        from app.core.identity_state import authorize_bound_effect

        await authorize_bound_effect(context.tenant_id, required)
        return context

    return check


read_policy = _permission("byok:read")
write_policy = _permission("byok:write")


def _actor(context: TenantContext) -> dict[str, Any]:
    return {
        "actor_id": context.user_id,
        "delegated_admin": "tenant_admin" in context.roles,
    }


class BYOKStoreRequest(BaseModel):
    provider: str = Field(max_length=32)
    api_key: SecretStr = Field(min_length=8, max_length=4096)
    validate_key: bool = False


class BYOKRotateRequest(BaseModel):
    new_api_key: SecretStr = Field(min_length=8, max_length=4096)
    validate_key: bool = False


class BYOKValidateRequest(BaseModel):
    provider: str = Field(max_length=32)
    api_key: SecretStr = Field(min_length=8, max_length=4096)


class BYOKValidationResponse(BaseModel):
    provider: str
    is_valid: bool
    error: str | None = None


class BYOKKeyResponse(BaseModel):
    tenant_id: str
    provider: str
    masked_key: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    last_validated_at: str | None = None
    validation_status: str | None = None


class BYOKProviderItem(BaseModel):
    provider: str
    masked_key: str | None
    configured: bool
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None
    last_validated_at: str | None = None
    validation_status: str | None = None


class BYOKListResponse(BaseModel):
    tenant_id: str
    keys: list[BYOKProviderItem]


@router.post("/keys", response_model=BYOKKeyResponse, status_code=201)
async def store_provider_key(
    request: BYOKStoreRequest, context: TenantContext = Depends(write_policy)
) -> Any:
    return await get_byok_manager().store_key(
        context.tenant_id,
        request.provider,
        request.api_key.get_secret_value(),
        request.validate_key,
        **_actor(context),
    )


@router.get("/keys", response_model=BYOKListResponse)
async def list_provider_keys(context: TenantContext = Depends(read_policy)) -> Any:
    return {
        "tenant_id": context.tenant_id,
        "keys": await get_byok_manager().list_keys(
            context.tenant_id, **_actor(context)
        ),
    }


@router.post("/keys/validate", response_model=BYOKValidationResponse)
async def validate_candidate_key(
    request: BYOKValidateRequest, _context: TenantContext = Depends(write_policy)
) -> Any:
    norm = get_byok_manager()._provider(request.provider)
    valid, error = await get_byok_manager().validate_key(
        norm, request.api_key.get_secret_value()
    )
    if error == "BYOK_PROVIDER_UNAVAILABLE":
        raise BYOKError(error)
    return {"provider": norm, "is_valid": valid, "error": error}


@router.post("/keys/{provider}/validate", response_model=BYOKValidationResponse)
async def validate_existing_key(
    provider: str, context: TenantContext = Depends(write_policy)
) -> Any:
    valid, error = await get_byok_manager().validate_stored_key(
        context.tenant_id, provider, **_actor(context)
    )
    if error == "BYOK_PROVIDER_UNAVAILABLE":
        raise BYOKError(error)
    return {"provider": provider, "is_valid": valid, "error": error}


@router.post("/keys/{provider}/rotate", response_model=BYOKKeyResponse)
async def rotate_provider_key(
    provider: str,
    request: BYOKRotateRequest,
    context: TenantContext = Depends(write_policy),
) -> Any:
    return await get_byok_manager().rotate_key(
        context.tenant_id,
        provider,
        request.new_api_key.get_secret_value(),
        request.validate_key,
        **_actor(context),
    )


@router.post("/keys/{provider}/revoke", response_model=BYOKKeyResponse)
async def revoke_provider_key(
    provider: str, context: TenantContext = Depends(write_policy)
) -> Any:
    return await get_byok_manager().revoke_key(
        context.tenant_id, provider, **_actor(context)
    )


@router.delete("/keys/{provider}")
async def delete_provider_key(
    provider: str, context: TenantContext = Depends(write_policy)
) -> Any:
    if not await get_byok_manager().delete_key(
        context.tenant_id, provider, **_actor(context)
    ):
        raise BYOKError("BYOK_NOT_CONFIGURED", 404)
    return {"tenant_id": context.tenant_id, "provider": provider, "status": "revoked"}
