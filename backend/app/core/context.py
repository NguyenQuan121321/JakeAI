"""Multi-tenant context models and context variable accessors."""

import uuid
from contextvars import ContextVar, Token

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    """Execution context injected into requests upon FinnApiGo JWT verification."""

    tenant_id: str = Field(description="Unique tenant or organization identifier")
    user_id: str = Field(description="Authenticated subject user identifier")
    org_id: str | None = Field(default=None, description="Optional organization ID")
    roles: list[str] = Field(
        default_factory=list,
        description="Assigned tenant authorization roles",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth2/OIDC granted authorization scopes",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description="Granular permission strings",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Distributed request tracing correlation ID",
    )

    def has_permission(self, permission: str) -> bool:
        """Check if tenant context has a specific permission or admin role."""
        if "admin" in self.roles or "tenant_admin" in self.roles:
            return True
        return permission in self.permissions

    def has_all_permissions(self, required_permissions: list[str]) -> bool:
        """Check if tenant context has all specified permissions."""
        if "admin" in self.roles or "tenant_admin" in self.roles:
            return True
        return all(p in self.permissions for p in required_permissions)


_tenant_context_ctx: ContextVar[TenantContext | None] = ContextVar(
    "tenant_context", default=None
)


def get_current_tenant_context() -> TenantContext | None:
    """Retrieve the active tenant context for the current async task execution."""
    return _tenant_context_ctx.get()


def set_current_tenant_context(ctx: TenantContext) -> Token[TenantContext | None]:
    """Bind a tenant context to the current async task context."""
    return _tenant_context_ctx.set(ctx)
