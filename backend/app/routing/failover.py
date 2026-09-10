"""Bounded Failover and Resilient Provider Execution for Phase 01.

Implements Phase 01 Section 6:
1. Error classification: retryable vs non-retryable vs auth vs quota vs context_limit vs unavailable.
2. Retry ONLY retryable classes with exponential backoff and jitter.
3. Bounded retries and total attempt ceiling to prevent retry storms.
4. Fallback chaining across candidate providers in RoutingDecision.
5. Strict zero credential leakage in logs and telemetry.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.providers.errors import (
    ErrorCategory,
    ProviderError,
    sanitize_error_message,
)
from app.providers.registry import get_provider_registry

if TYPE_CHECKING:
    import httpx

    from app.providers.base import ProviderRequest, ProviderResponse
    from app.routing.router import RoutingDecision

logger = logging.getLogger(__name__)


class FailoverConfig(BaseModel):
    """Execution parameters governing retries and fallback bounds."""

    max_retries_per_provider: int = Field(default=2, ge=0, le=5)
    max_total_attempts: int = Field(default=3, ge=1, le=8)
    base_delay_seconds: float = Field(default=0.2, ge=0.01)
    backoff_factor: float = Field(default=1.5, ge=1.0)
    max_delay_seconds: float = Field(default=3.0, ge=0.5)
    retryable_categories: set[ErrorCategory] = Field(
        default_factory=lambda: {
            ErrorCategory.RETRYABLE,
            ErrorCategory.PROVIDER_UNAVAILABLE,
        }
    )


class FailoverManager:
    """Orchestrates bounded retry loops and cross-provider fallback execution."""

    def __init__(self, config: FailoverConfig | None = None) -> None:
        self.config = config or FailoverConfig()
        self.registry = get_provider_registry()

    def _calculate_backoff(
        self, attempt: int, retry_after: float | None = None
    ) -> float:
        """Calculate exponential backoff delay with random jitter, respecting retry_after."""
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self.config.max_delay_seconds)

        delay = self.config.base_delay_seconds * (self.config.backoff_factor**attempt)
        jitter = secrets.SystemRandom().uniform(0.0, 0.1 * delay)  # nosec B311
        return min(delay + jitter, self.config.max_delay_seconds)

    async def execute_with_failover(
        self,
        request: ProviderRequest,
        decision: RoutingDecision,
        client: httpx.AsyncClient | None = None,
    ) -> ProviderResponse:
        """Execute inference against selected provider, falling back on failure."""
        providers_to_try: list[tuple[str, str]] = [
            (decision.selected_provider, decision.selected_model),
            *decision.fallback_chain,
        ]

        last_error: ProviderError | None = None
        total_attempts = 0

        from app.telemetry.metrics import metrics

        for idx, (provider_name, model_name) in enumerate(providers_to_try):
            if idx > 0 and last_error is not None:
                metrics.record_failover(
                    from_provider=providers_to_try[idx - 1][0],
                    to_provider=provider_name,
                    reason=last_error.category.value,
                )

            if total_attempts >= self.config.max_total_attempts:
                logger.warning(
                    "Failover ceiling reached (%d attempts). Aborting fallback chain.",
                    total_attempts,
                )
                break

            adapter = self.registry.get(provider_name)
            if adapter is None:
                logger.debug(
                    "Provider adapter '%s' not registered, skipping", provider_name
                )
                continue

            current_request = request.model_copy(update={"model": model_name})

            provider_retries = 0
            while provider_retries <= self.config.max_retries_per_provider:
                total_attempts += 1
                try:
                    logger.debug(
                        "Attempting [%s] model=%s (attempt %d, total %d)",
                        provider_name,
                        model_name,
                        provider_retries + 1,
                        total_attempts,
                    )
                    return await adapter.complete(current_request, client=client)
                except ProviderError as p_err:
                    last_error = p_err
                    sanitized_msg = sanitize_error_message(p_err.message)
                    logger.warning(
                        "Provider [%s] failed with category=%s (is_retryable=%s): %s",
                        provider_name,
                        p_err.category.value,
                        p_err.is_retryable,
                        sanitized_msg,
                    )

                    # Only retry if error category is explicitly retryable
                    if (
                        p_err.is_retryable
                        and p_err.category in self.config.retryable_categories
                        and provider_retries < self.config.max_retries_per_provider
                    ):
                        delay = self._calculate_backoff(
                            provider_retries, p_err.retry_after_seconds
                        )
                        logger.info(
                            "Retrying [%s] in %.2fs (backoff attempt %d)",
                            provider_name,
                            delay,
                            provider_retries + 1,
                        )
                        await asyncio.sleep(delay)
                        provider_retries += 1
                        continue

                    # If not retryable on this provider (e.g. 401 Auth, Quota, or retries exhausted), break to next provider
                    break
                except Exception as exc:
                    sanitized_msg = sanitize_error_message(str(exc))
                    last_error = ProviderError(
                        message=sanitized_msg,
                        provider=provider_name,
                        category=ErrorCategory.NON_RETRYABLE,
                        model=model_name,
                        raw_error=exc,
                    )
                    logger.warning(
                        "Unexpected non-ProviderError from [%s]: %s",
                        provider_name,
                        sanitized_msg,
                    )
                    break

        if last_error:
            raise last_error
        raise ProviderError(
            message="All providers in fallback chain exhausted without response",
            provider="failover_manager",
            category=ErrorCategory.PROVIDER_UNAVAILABLE,
            is_retryable=False,
        )

    async def stream_with_failover(
        self,
        request: ProviderRequest,
        decision: RoutingDecision,
        client: httpx.AsyncClient | None = None,
    ) -> Any:
        """Stream chunks from selected provider adapter."""
        adapter = self.registry.get(decision.selected_provider)
        if adapter is not None and hasattr(adapter, "stream"):
            current_request = request.model_copy(update={"model": decision.selected_model})
            async for chunk in adapter.stream(current_request, client=client):
                yield chunk



_global_failover_manager: FailoverManager | None = None


def get_failover_manager() -> FailoverManager:
    global _global_failover_manager
    if _global_failover_manager is None:
        _global_failover_manager = FailoverManager()
    return _global_failover_manager
