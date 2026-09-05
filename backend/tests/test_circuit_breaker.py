"""Unit tests for Circuit Breaker and Fallback Routing."""

import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
)


@pytest.mark.asyncio
async def test_circuit_breaker_normal_closed_execution() -> None:
    """Verify standard execution through primary provider when circuit is CLOSED."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=2)
    assert cb.state == CircuitState.CLOSED

    async def mock_primary(x: int) -> int:
        return x * 2

    res = await cb.call_with_fallback(mock_primary, None, None, 5)
    assert res == 10
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_trips_to_open_and_uses_fallback() -> None:
    """Verify circuit trips to OPEN after threshold failures and triggers secondary fallback."""
    cb = CircuitBreaker(
        name="test_cb", failure_threshold=2, recovery_timeout_seconds=5.0
    )

    async def failing_primary() -> str:
        raise ConnectionError("Primary model connection timed out")

    async def fallback_provider() -> str:
        return "Secondary model response"

    # First failure -> Still CLOSED
    res1 = await cb.call_with_fallback(failing_primary, fallback_provider, None)
    assert res1 == "Secondary model response"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    # Second failure -> Trips to OPEN
    res2 = await cb.call_with_fallback(failing_primary, fallback_provider, None)
    assert res2 == "Secondary model response"
    assert cb.state == CircuitState.OPEN
    assert cb.total_fallback_calls == 2

    # Third call: Circuit is OPEN, primary is bypassed, fallback runs directly
    res3 = await cb.call_with_fallback(failing_primary, fallback_provider, None)
    assert res3 == "Secondary model response"
    assert cb.total_fallback_calls == 3


@pytest.mark.asyncio
async def test_deterministic_safe_fallback_when_all_providers_fail() -> None:
    """Verify zero 500 errors by returning deterministic safe fallback."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=1)

    async def failing_primary() -> str:
        raise RuntimeError("Primary 503")

    async def failing_secondary() -> str:
        raise RuntimeError("Secondary 429")

    def deterministic_fallback() -> dict[str, str]:
        return {
            "status": "degraded",
            "message": "Service operating in safe deterministic mode.",
        }

    res = await cb.call_with_fallback(
        failing_primary, failing_secondary, deterministic_fallback
    )
    assert res["status"] == "degraded"
    assert "safe deterministic mode" in res["message"]


@pytest.mark.asyncio
async def test_circuit_breaker_recovery_to_half_open_and_closed() -> None:
    """Verify recovery from OPEN to HALF_OPEN after timeout and back to CLOSED after success."""
    cb = CircuitBreaker(
        name="test_cb",
        failure_threshold=1,
        recovery_timeout_seconds=0.01,  # Short cooldown for test
        half_open_success_threshold=2,
    )

    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Simulate waiting past recovery timeout
    import asyncio

    await asyncio.sleep(0.05)

    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN

    # First successful probe
    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN

    # Second successful probe -> Back to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_raises_when_no_fallback() -> None:
    """Verify CircuitBreakerOpenException or error raised when no fallbacks provided."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=1)

    async def failing_primary() -> None:
        raise ValueError("Critical crash")

    with pytest.raises(ValueError, match="Critical crash"):
        await cb.call_with_fallback(failing_primary, None, None)

    with pytest.raises(CircuitBreakerOpenException):
        await cb.call_with_fallback(failing_primary, None, None)
