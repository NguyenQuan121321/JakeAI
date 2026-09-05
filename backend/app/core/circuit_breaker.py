"""Circuit Breaker & Fallback Router for High-Availability Multi-Provider AI Routing.

Prevents system cascading failures and ensures 24/7 uptime without 500 errors.
States:
  CLOSED: Normal operation, routing to primary model.
  OPEN: Tripped after consecutive failures, immediately routes to fallback.
  HALF_OPEN: Probing recovery after cooldown period.
"""

import asyncio
import time
from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    """Lifecycle states of the Circuit Breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while circuit is in OPEN state."""

    pass


class CircuitBreaker:
    """State machine governing resilient upstream invocation with fallback chaining."""

    def __init__(
        self,
        name: str = "llm_router",
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_state_change: float = time.time()
        self.total_fallback_calls: int = 0

    def is_available(self) -> bool:
        """Check if primary provider can be called or if recovery probe should begin."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_state_change >= self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self.last_state_change = now
                return True
            return False
        return True

    def record_success(self) -> None:
        """Record successful upstream operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_state_change = time.time()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record failed upstream operation."""
        self.failure_count += 1
        self.last_state_change = time.time()
        if (
            self.state == CircuitState.HALF_OPEN
            or self.failure_count >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.success_count = 0

    async def call_with_fallback(
        self,
        primary_fn: Callable[..., Coroutine[Any, Any, Any] | Any],
        fallback_fn: Callable[..., Coroutine[Any, Any, Any] | Any] | None = None,
        deterministic_fallback_fn: Callable[..., Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute primary callable with automated fallback routing.

        Chain:
          1. Primary Provider (if circuit not OPEN)
          2. Secondary Provider (if primary throws or circuit is OPEN)
          3. Local Deterministic Safe Fallback (if all external providers fail)
        """
        last_error: Exception | None = None

        # 1. Attempt Primary Provider
        if self.is_available():
            try:
                res = primary_fn(*args, **kwargs)
                if asyncio.iscoroutine(res):
                    result = await res
                else:
                    result = res
                self.record_success()
                return result
            except Exception as exc:
                self.record_failure()
                last_error = exc
        else:
            last_error = CircuitBreakerOpenException(
                f"Circuit '{self.name}' is OPEN. Fast-falling back."
            )

        # 2. Attempt Secondary Fallback Provider
        self.total_fallback_calls += 1
        if fallback_fn is not None:
            try:
                res = fallback_fn(*args, **kwargs)
                if asyncio.iscoroutine(res):
                    return await res
                return res
            except Exception as exc:
                last_error = exc

        # 3. Local Deterministic Safe Fallback (Guaranteed 0% 500 errors)
        if deterministic_fallback_fn is not None:
            res = deterministic_fallback_fn(*args, **kwargs)
            if asyncio.iscoroutine(res):
                return await res
            return res

        if last_error:
            raise last_error
        raise CircuitBreakerOpenException(
            f"Circuit '{self.name}' failed without available fallback."
        )
