"""Canonical upstream provider credential resolution (single authority).

R-ARCH-03: the platform-fallback key map and the BYOK-first resolution order
were previously duplicated in ``app.core.llm_provider`` (non-streaming and
streaming dispatch, R-ARCH-01 fix) and again in
``app.routing.failover._default_resolve_credentials``. Both consumers now
import this module so a new provider can never be registered in one map and
silently miss failover-time (or dispatch-time) resolution.

Deliberately dependency-free: takes ``settings`` and the BYOK manager as
parameters so neither ``app.routing`` nor ``app.core.llm_provider`` needs to
import the other.
"""

from __future__ import annotations

from typing import Any

# Platform fallback setting per provider; tenant BYOK keys always take priority.
_PROVIDER_SETTINGS_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


async def resolve_provider_credentials(
    settings: Any, byok_mgr: Any, tenant_id: str, provider: str
) -> str | None:
    """Resolve upstream credentials: tenant BYOK key first, then platform key."""
    key: str | None = await byok_mgr.get_decrypted_key(tenant_id, provider)
    if key:
        return key
    s_key = _PROVIDER_SETTINGS_KEYS.get(provider)
    platform_key: str | None = getattr(settings, s_key, None) if s_key else None
    return platform_key
