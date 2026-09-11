"""Tenant Budget & Quota Governance Engine for Phase 05 AI FinOps.

Governs multi-tenant token quotas and dollar budgets:
- Distinct from physical token optimization (governance vs compression).
- Pre-flight budget check with soft warning (80%) and hard suspension (100%).
- Supports dual token quota and USD dollar budget ceilings.
- Post-inference settlement atomic ledger updates.
- Thread-safe in-memory store with async Redis backing when available.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from app.core.config import get_settings
from app.finops.models import TenantBudget

logger = logging.getLogger(__name__)

DEFAULT_MONTHLY_TOKEN_QUOTA = 1_000_000  # 1M tokens
DEFAULT_WARNING_THRESHOLD = 0.80  # 80%


class FinOpsBudgetManager:
    """Manages and enforces tenant token quotas and USD dollar budgets."""

    def __init__(self) -> None:
        self._memory_token_limits: dict[str, int] = {}
        self._memory_dollar_limits: dict[str, float] = {}
        self._memory_warning_thresholds: dict[str, float] = {}
        self._memory_token_usage: dict[str, int] = {}
        self._memory_dollar_spent: dict[str, float] = {}
        self._memory_tokens_saved: dict[str, int] = {}
        self.redis_client: Any | None = None
        self._redis_available = True

    async def _get_redis(self) -> Any | None:
        """Lazily initialize Redis connection with fast ping check."""
        if self.redis_client is not None:
            return self.redis_client
        if not self._redis_available:
            return None
        try:
            from redis import asyncio as aioredis

            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            await client.ping()
            self.redis_client = client
            return self.redis_client
        except Exception:
            self._redis_available = False
            return None

    def _get_period_key(self) -> str:
        """Current monthly billing period: YYYY-MM."""
        return time.strftime("%Y-%m")

    async def get_token_quota(self, tenant_id: str) -> int:
        """Retrieve token quota limit for tenant."""
        redis = await self._get_redis()
        if redis is not None:
            try:
                val = await redis.get(f"finops:limit:tokens:{tenant_id}")
                if val:
                    return int(val)
            except Exception as exc:
                logger.debug("Redis read token limit failed: %s", exc)
        return self._memory_token_limits.get(tenant_id, DEFAULT_MONTHLY_TOKEN_QUOTA)

    async def get_dollar_budget(self, tenant_id: str) -> float | None:
        """Retrieve optional dollar budget ceiling for tenant in USD."""
        redis = await self._get_redis()
        if redis is not None:
            try:
                val = await redis.get(f"finops:limit:dollars:{tenant_id}")
                if val:
                    return float(val)
            except Exception as exc:
                logger.debug("Redis read dollar limit failed: %s", exc)
        return self._memory_dollar_limits.get(tenant_id)

    async def get_warning_threshold(self, tenant_id: str) -> float:
        """Retrieve soft alert warning threshold ratio (default 0.80)."""
        redis = await self._get_redis()
        if redis is not None:
            try:
                val = await redis.get(f"finops:limit:warn_pct:{tenant_id}")
                if val:
                    return float(val)
            except Exception as exc:
                logger.debug("Redis read warning threshold failed: %s", exc)
        return self._memory_warning_thresholds.get(tenant_id, DEFAULT_WARNING_THRESHOLD)

    async def get_tokens_used(self, tenant_id: str, period: str | None = None) -> int:
        """Retrieve current tokens consumed in the active billing period."""
        p = period or self._get_period_key()
        redis = await self._get_redis()
        if redis is not None:
            try:
                val = await redis.get(f"finops:usage:tokens:{tenant_id}:{p}")
                if val:
                    return int(val)
            except Exception as exc:
                logger.debug("Redis read token usage failed: %s", exc)
        return self._memory_token_usage.get(f"{tenant_id}:{p}", 0)

    async def get_dollars_spent(
        self, tenant_id: str, period: str | None = None
    ) -> float:
        """Retrieve current USD dollar expenditure in the active billing period."""
        p = period or self._get_period_key()
        redis = await self._get_redis()
        if redis is not None:
            try:
                val = await redis.get(f"finops:usage:dollars:{tenant_id}:{p}")
                if val:
                    return float(val)
            except Exception as exc:
                logger.debug("Redis read dollar spent failed: %s", exc)
        return self._memory_dollar_spent.get(f"{tenant_id}:{p}", 0.0)

    async def check_budget(
        self,
        tenant_id: str,
        estimated_tokens: int = 100,
        estimated_cost_usd: float = 0.0,
    ) -> tuple[bool, str | None]:
        """Pre-flight governance check before LLM execution.

        Returns:
            (is_allowed: bool, message: str | None)
        """
        token_limit = await self.get_token_quota(tenant_id)
        tokens_used = await self.get_tokens_used(tenant_id)
        dollar_limit = await self.get_dollar_budget(tenant_id)
        dollar_spent = await self.get_dollars_spent(tenant_id)
        warn_threshold = await self.get_warning_threshold(tenant_id)

        # 1. Hard suspension on token quota exceeded
        if tokens_used + estimated_tokens > token_limit:
            return (
                False,
                f"Monthly token quota exceeded ({tokens_used}/{token_limit} tokens). Request suspended.",
            )

        # 2. Hard suspension on dollar budget exceeded (if configured)
        if dollar_limit is not None and (
            dollar_spent + estimated_cost_usd > dollar_limit
        ):
            return (
                False,
                f"Monthly dollar budget exceeded (${dollar_spent:.4f}/${dollar_limit:.2f} USD). Request suspended.",
            )

        # 3. Soft alerts at warning threshold (e.g. 80%)
        token_ratio = (tokens_used / token_limit) if token_limit > 0 else 1.0
        dollar_ratio = (
            (dollar_spent / dollar_limit) if dollar_limit and dollar_limit > 0 else 0.0
        )

        if token_ratio >= warn_threshold or dollar_ratio >= warn_threshold:
            highest_pct = max(token_ratio, dollar_ratio) * 100.0
            return (
                True,
                f"Soft warning: {round(highest_pct, 1)}% of budget ceiling consumed.",
            )

        return True, None

    async def settle_request(
        self,
        tenant_id: str,
        billed_tokens: int,
        billed_cost_usd: float,
    ) -> tuple[int, float]:
        """Atomically settle and increment token and dollar consumption post-inference."""
        period = self._get_period_key()
        redis = await self._get_redis()

        # Update Tokens
        if redis is not None:
            with contextlib.suppress(Exception):
                await redis.incrby(
                    f"finops:usage:tokens:{tenant_id}:{period}", billed_tokens
                )
                await redis.incrbyfloat(
                    f"finops:usage:dollars:{tenant_id}:{period}", billed_cost_usd
                )

        t_key = f"{tenant_id}:{period}"
        new_tokens = self._memory_token_usage.get(t_key, 0) + billed_tokens
        new_dollars = round(
            self._memory_dollar_spent.get(t_key, 0.0) + billed_cost_usd, 6
        )

        self._memory_token_usage[t_key] = new_tokens
        self._memory_dollar_spent[t_key] = new_dollars

        return new_tokens, new_dollars

    async def record_token_usage(self, tenant_id: str, tokens: int) -> int:
        """Increment token consumption and return total tokens used."""
        new_tokens, _ = await self.settle_request(tenant_id, tokens, 0.0)
        return new_tokens

    async def record_tokens_saved(
        self, tenant_id: str, tokens_saved: int, period: str | None = None
    ) -> int:
        """Increment tokens saved atomically in Redis or memory."""
        period_key = period or self._get_period_key()
        redis = await self._get_redis()
        if redis is not None:
            with contextlib.suppress(Exception):
                key = f"finops:tokens_saved:{tenant_id}:{period_key}"
                redis_val = await redis.incrby(key, tokens_saved)
                return int(redis_val)

        mem_key = f"{tenant_id}:{period_key}"
        mem_val: int = int(self._memory_tokens_saved.get(mem_key, 0) + tokens_saved)
        self._memory_tokens_saved[mem_key] = mem_val
        return mem_val

    async def get_tokens_saved(self, tenant_id: str, period: str | None = None) -> int:
        """Get current tokens saved for the active period from Redis or memory."""
        period_key = period or self._get_period_key()
        redis = await self._get_redis()
        if redis is not None:
            with contextlib.suppress(Exception):
                key = f"finops:tokens_saved:{tenant_id}:{period_key}"
                val = await redis.get(key)
                if val:
                    return int(val)
        mem_key = f"{tenant_id}:{period_key}"
        return int(self._memory_tokens_saved.get(mem_key, 0))

    async def set_budget(
        self,
        tenant_id: str,
        token_quota: int | None = None,
        dollar_budget_usd: float | None = None,
        warning_threshold: float | None = None,
    ) -> TenantBudget:
        """Update quota or budget configuration for a tenant."""
        redis = await self._get_redis()

        if token_quota is not None:
            self._memory_token_limits[tenant_id] = token_quota
            if redis is not None:
                with contextlib.suppress(Exception):
                    await redis.set(
                        f"finops:limit:tokens:{tenant_id}", str(token_quota)
                    )

        if dollar_budget_usd is not None:
            self._memory_dollar_limits[tenant_id] = dollar_budget_usd
            if redis is not None:
                with contextlib.suppress(Exception):
                    await redis.set(
                        f"finops:limit:dollars:{tenant_id}", str(dollar_budget_usd)
                    )

        if warning_threshold is not None:
            self._memory_warning_thresholds[tenant_id] = warning_threshold
            if redis is not None:
                with contextlib.suppress(Exception):
                    await redis.set(
                        f"finops:limit:warn_pct:{tenant_id}", str(warning_threshold)
                    )

        return await self.get_budget_status(tenant_id)

    async def get_budget_status(
        self, tenant_id: str, period: str | None = None
    ) -> TenantBudget:
        """Retrieve full current budget and quota status object."""
        p = period or self._get_period_key()
        token_limit = await self.get_token_quota(tenant_id)
        tokens_used = await self.get_tokens_used(tenant_id, p)
        dollar_limit = await self.get_dollar_budget(tenant_id)
        dollar_spent = await self.get_dollars_spent(tenant_id, p)
        warn_threshold = await self.get_warning_threshold(tenant_id)

        tokens_remaining = max(0, token_limit - tokens_used)
        pct_tokens = (
            round((tokens_used / token_limit * 100.0), 2) if token_limit > 0 else 100.0
        )

        dollar_remaining = (
            max(0.0, round(dollar_limit - dollar_spent, 6))
            if dollar_limit is not None
            else None
        )
        pct_dollars = (
            round((dollar_spent / dollar_limit * 100.0), 2)
            if dollar_limit and dollar_limit > 0
            else None
        )

        is_suspended = (tokens_used >= token_limit) or (
            dollar_limit is not None and dollar_spent >= dollar_limit
        )

        warning: str | None = None
        if is_suspended:
            warning = "Budget ceiling reached or exceeded. Services suspended."
        elif (pct_tokens >= warn_threshold * 100) or (
            pct_dollars is not None and pct_dollars >= warn_threshold * 100
        ):
            warning = f"Approaching budget limit (>{int(warn_threshold * 100)}%)."

        return TenantBudget(
            tenant_id=tenant_id,
            period=p,
            token_quota=token_limit,
            tokens_used=tokens_used,
            tokens_remaining=tokens_remaining,
            percentage_tokens_used=pct_tokens,
            dollar_budget_usd=dollar_limit,
            dollar_spent_usd=dollar_spent,
            dollar_remaining_usd=dollar_remaining,
            percentage_dollars_used=pct_dollars,
            warning_threshold=warn_threshold,
            is_suspended=is_suspended,
            warning=warning,
        )


_budget_manager: FinOpsBudgetManager | None = None


def get_budget_manager() -> FinOpsBudgetManager:
    """Singleton getter for FinOpsBudgetManager."""
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = FinOpsBudgetManager()
    return _budget_manager
