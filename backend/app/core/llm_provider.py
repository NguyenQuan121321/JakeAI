"""Centralized Upstream LLM Dispatcher.

Handles upstream provider invocations (Google Gemini, OpenAI) with tenant-scoped
BYOK key prioritization, platform fallback keys, circuit breaker compatibility,
and graceful degradation.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.byok import get_byok_manager
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def call_upstream_llm(
    prompt: str,
    tenant_id: str = "default",
    model: str = "gemini-1.5-flash",
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str | None:
    """Call upstream LLM provider prioritizing decrypted tenant BYOK keys.

    Falls back to platform keys, or returns None if no upstream provider is configured
    or reachable.
    """
    settings = get_settings()
    byok_mgr = get_byok_manager()

    default_system = (
        system_instruction
        or "You are JakeAI, an enterprise financial and operational AI companion. "
        "Respond helpfully, concisely, and professionally in the same language as the user's prompt."
    )

    model_lower = model.lower()
    is_gemini = "gemini" in model_lower or not (
        "gpt" in model_lower or "claude" in model_lower
    )

    # 1. Google Gemini Provider
    if is_gemini:
        gemini_key = (
            await byok_mgr.get_decrypted_key(tenant_id, "gemini")
            or settings.GEMINI_API_KEY
        )
        if gemini_key:
            try:
                import httpx

                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model if 'gemini' in model_lower else 'gemini-1.5-flash'}:generateContent?key={gemini_key}"
                )
                payload: dict[str, Any] = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "systemInstruction": {"parts": [{"text": default_system}]},
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return str(parts[0].get("text", "")).strip()
            except Exception as exc:
                logger.debug("Gemini API call failed (%s), trying fallbacks", exc)

    # 2. OpenAI Provider
    openai_key = (
        await byok_mgr.get_decrypted_key(tenant_id, "openai") or settings.OPENAI_API_KEY
    )
    if openai_key:
        try:
            import httpx

            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {openai_key}"}
            openai_model = (
                model
                if ("gpt" in model_lower or "o3" in model_lower)
                else "gpt-4o-mini"
            )
            payload = {
                "model": openai_model,
                "messages": [
                    {"role": "system", "content": default_system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        return str(
                            choices[0].get("message", {}).get("content", "")
                        ).strip()
        except Exception as exc:
            logger.debug("OpenAI API call failed (%s), falling back to template", exc)

    return None
