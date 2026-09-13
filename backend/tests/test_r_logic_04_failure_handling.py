"""R-LOGIC-04 — Failure Handling canonical verification test suite.

Proves, via deliberate failure injection at the highest realistic boundary:

1. Provider error classification (401/403/429/quota/5xx/timeout) at the
   FailoverManager boundary: retry only retryable classes, bounded backoff
   with jitter, bounded total attempts, cross-provider failover.
2. Canonical ExecutionEngine: a total provider outage can never be reported
   as run success (no fabricated step output).
3. BoundedRecoveryEngine: non-retryable failures (auth, quota, policy,
   permission) terminate immediately; transient failures retry within
   bounded budgets; first-attempt edge values cannot crash the engine.
4. Gateway: total outage yields a labeled fallback without poisoning the
   exact cache, and the circuit breaker actually records failures/trips.
5. Streaming: mid-stream provider failure propagates instead of silently
   truncating; the backend stream signals an error terminal chunk.
6. RAG: total retrieval failure is classified as RETRIEVAL_FAILURE, while
   a genuinely empty index remains NO_RELEVANT_EVIDENCE.
7. Persistence: corrupt checkpoints fail closed (no fabricated success) and
   Redis write failures degrade to memory without crashing.
8. Tools: timeouts and policy denials produce failed results that recovery
   never retries into success.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.agent.runtime.models import AgentRunEvent

from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.domain.contracts import TaskSpec
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.models import Plan, PlanStep, PlanStepStatus
from app.agent.planning.planner import BoundedPlanner
from app.agent.recovery.recovery import BoundedRecoveryEngine
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunStatus
from app.agent.tools.base import Tool, ToolMetadata, ToolResult
from app.agent.tools.registry import ToolRegistry
from app.core.circuit_breaker import CircuitState
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.routing.failover import FailoverConfig, FailoverManager
from app.routing.router import RoutingDecision

# ===========================================================================
# Test doubles
# ===========================================================================


class GeneralStepPlanner(BoundedPlanner):
    """Plan with a single general (model-backed) step."""

    async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
        return Plan(
            task_id=task_spec.task_id,
            goal=task_spec.goal,
            analysis="Direct model step",
            steps=[
                PlanStep(
                    step_id="step_gen",
                    description="General reasoning step",
                    candidate_agents=["general_agent"],
                    dependencies=[],
                    status=PlanStepStatus.PENDING,
                )
            ],
        )


class TwoStepPlanner(BoundedPlanner):
    """Plan with two sequential general steps (for run-level timeout)."""

    async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
        return Plan(
            task_id=task_spec.task_id,
            goal=task_spec.goal,
            analysis="Two sequential model steps",
            steps=[
                PlanStep(
                    step_id="step_a",
                    description="First step",
                    candidate_agents=["general_agent"],
                    dependencies=[],
                    status=PlanStepStatus.PENDING,
                ),
                PlanStep(
                    step_id="step_b",
                    description="Second step",
                    candidate_agents=["general_agent"],
                    dependencies=["step_a"],
                    status=PlanStepStatus.PENDING,
                ),
            ],
        )


class ScriptedBackend(AgentBackendInterface):
    """Backend executing a script of outcomes per generate() call."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[BackendRequest] = []

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.calls.append(request)
        outcome = (
            self.outcomes.pop(0)
            if self.outcomes
            else BackendResponse(
                content="ok", model="m", provider="p", finish_reason="stop"
            )
        )
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, BackendResponse)
        return outcome

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncGenerator[BackendStreamChunk, None]:
        yield BackendStreamChunk(delta_content="ok", finish_reason="stop")


async def collect_events(
    gen: AsyncGenerator[AgentRunEvent, None],
) -> list[AgentRunEvent]:
    return [event async for event in gen]


async def run_engine_to_terminal(
    engine: ExecutionEngine, task_spec: TaskSpec
) -> tuple[str | None, list[AgentRunEvent]]:
    events = await collect_events(engine.execute_task(task_spec))
    terminal = next(
        (e for e in events if e.event_type in ("completed", "failed", "cancelled")),
        None,
    )
    return (terminal.event_type if terminal else None), events


def make_task_spec(tenant: str = "tenant-rl04") -> TaskSpec:
    return TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id=tenant,
        user_id="user-rl04",
        goal="Failure handling verification",
    )


def make_routing_decision(
    primary: tuple[str, str], fallbacks: list[tuple[str, str]]
) -> RoutingDecision:
    return RoutingDecision(
        selected_provider=primary[0],
        selected_model=primary[1],
        fallback_chain=fallbacks,
        decision_reasons=["test"],
    )


# ===========================================================================
# 1. Provider failure classification at the FailoverManager boundary
# ===========================================================================


class FlakyAdapter:
    """Provider adapter stub failing N times before succeeding, recording attempts."""

    def __init__(
        self,
        name: str,
        failures: list[Exception],
        final_text: str = "recovered",
    ) -> None:
        self.provider_name = name
        self.failures = list(failures)
        self.final_text = final_text
        self.attempts = 0

    async def complete(self, request, client=None):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)

        from app.providers.base import ProviderCacheTelemetry, ProviderResponse

        return ProviderResponse(
            text=self.final_text,
            model=request.model,
            provider=self.provider_name,
            telemetry=ProviderCacheTelemetry(),
        )


@pytest.mark.asyncio
async def test_status_matrix_retry_vs_failover_at_failover_boundary(monkeypatch):
    """401/403/quota-429 never retry; 429/503/timeout retry on the same provider."""

    adapters: dict[str, FlakyAdapter] = {}

    class FakeRegistry:
        def get(self, name):
            return adapters.get(name)

    monkeypatch.setattr(
        "app.routing.failover.get_provider_registry", lambda: FakeRegistry()
    )

    cases = [
        # (case, failures_for_primary, expected_primary_attempts)
        (
            "auth_401",
            [ProviderAuthenticationError("bad key", "primary", status_code=401)],
            1,
        ),
        (
            "forbidden_403",
            [ProviderAuthenticationError("no access", "primary", status_code=403)],
            1,
        ),
        (
            "rate_limit_429",
            [ProviderRateLimitError("slow down", "primary", status_code=429)],
            2,
        ),
        (
            "unavailable_503",
            [ProviderUnavailableError("down", "primary", status_code=503)],
            2,
        ),
        (
            "timeout",
            [ProviderTimeoutError("read timed out", "primary")],
            2,
        ),
    ]

    for name, failures, expected_attempts in cases:
        cfg = FailoverConfig(base_delay_seconds=0.01, max_delay_seconds=0.5)
        primary = FlakyAdapter("primary", list(failures))
        secondary = FlakyAdapter("secondary", [])
        adapters.clear()
        adapters.update({"primary": primary, "secondary": secondary})
        mgr = FailoverManager(config=cfg)
        decision = make_routing_decision(("primary", "m1"), [("secondary", "m2")])
        request = _make_provider_request()
        resp = await mgr.execute_with_failover(request, decision)
        assert resp.text == "recovered"
        assert primary.attempts == expected_attempts, (
            f"{name}: primary attempts {primary.attempts} != {expected_attempts}"
        )


def _make_provider_request():
    from app.providers.base import ProviderRequest

    return ProviderRequest(
        model="m1",
        prompt="p",
        tenant_id="t1",
        api_key="k",
    )


@pytest.mark.asyncio
async def test_quota_429_is_not_retried_like_rate_limit(monkeypatch):
    """A 429 carrying a quota/billing message maps to non-retryable quota."""
    from app.providers.errors import normalize_provider_error

    err = normalize_provider_error(
        provider="openai",
        status_code=429,
        response_body={
            "error": {"message": "You exceeded your current quota, billing"}
        },
    )
    assert err.category == ErrorCategory.QUOTA
    assert err.is_retryable is False

    rate = normalize_provider_error(
        provider="openai",
        status_code=429,
        response_body={"error": {"message": "rate limit exceeded"}},
    )
    assert rate.is_retryable is True


@pytest.mark.asyncio
async def test_backoff_is_bounded_exponential_with_jitter():
    """Backoff grows exponentially, includes jitter, and never exceeds the cap."""
    mgr = FailoverManager(
        config=FailoverConfig(
            base_delay_seconds=0.2,
            backoff_factor=2.0,
            max_delay_seconds=1.0,
        )
    )
    delays = [mgr._calculate_backoff(attempt=a) for a in range(6)]
    # Exponential envelope: each nominal delay (without jitter) is 2x previous.
    for attempt, delay in enumerate(delays):
        nominal = 0.2 * (2.0**attempt)
        assert nominal <= delay <= nominal * 1.1 + 1e-9 or delay == 1.0
    # All delays respect the cap.
    assert all(d <= 1.0 for d in delays)
    # Jitter: identical attempts produce different delays at least once.
    samples = {mgr._calculate_backoff(attempt=1) for _ in range(20)}
    assert len(samples) > 1


@pytest.mark.asyncio
async def test_retry_after_respected_and_capped():
    mgr = FailoverManager(
        config=FailoverConfig(base_delay_seconds=0.2, max_delay_seconds=1.0)
    )
    assert mgr._calculate_backoff(0, retry_after=0.5) == 0.5
    assert mgr._calculate_backoff(0, retry_after=50.0) == 1.0


@pytest.mark.asyncio
async def test_total_attempt_ceiling_prevents_retry_storm(monkeypatch):
    """With many fallback candidates, total attempts never exceed the ceiling."""
    adapters = {
        f"p{i}": FlakyAdapter(
            f"p{i}",
            [ProviderUnavailableError("down", f"p{i}", status_code=503)] * 10,
        )
        for i in range(5)
    }

    class FakeRegistry:
        def get(self, name):
            return adapters.get(name)

    monkeypatch.setattr(
        "app.routing.failover.get_provider_registry", lambda: FakeRegistry()
    )
    mgr = FailoverManager(
        config=FailoverConfig(
            max_retries_per_provider=2,
            max_total_attempts=4,
            base_delay_seconds=0.01,
        )
    )
    decision = make_routing_decision(("p0", "m"), [(f"p{i}", "m") for i in range(1, 5)])
    with pytest.raises(ProviderUnavailableError):
        await mgr.execute_with_failover(_make_provider_request(), decision)
    total = sum(a.attempts for a in adapters.values())
    assert total == 4


# ===========================================================================
# 2. ExecutionEngine: total provider outage must never report success
# ===========================================================================


@pytest.mark.asyncio
async def test_provider_outage_fails_run_without_fabricated_success(monkeypatch):
    """RL04-F-01: outage through the REAL JakeAIBackend fails the run terminally."""
    import app.agent.backends.jakeai as jakeai_mod

    async def outage(*args: Any, **kwargs: Any) -> None:
        return None  # what FailoverManager exhaustion produces

    monkeypatch.setattr(jakeai_mod, "call_upstream_llm_detailed", outage)

    engine = ExecutionEngine(
        backend=JakeAIBackend(),
        checkpoint_manager=CheckpointManager(),
        planner=GeneralStepPlanner(backend=JakeAIBackend()),
    )
    terminal, events = await run_engine_to_terminal(engine, make_task_spec())

    assert terminal == "failed"
    step_completed = [e for e in events if e.event_type == "step_completed"]
    assert step_completed == [], "no step may complete during a total outage"
    run_state = next(iter(engine._runs.values()))
    assert run_state.status == RunStatus.FAILED
    assert run_state.status.is_terminal
    assert "Completed step execution." not in (run_state.final_output or "")


@pytest.mark.asyncio
async def test_backend_error_finish_reason_fails_step_not_fabricates():
    """A backend response with an error finish_reason fails the step."""
    backend = ScriptedBackend(
        [BackendResponse(content="", model="m", provider="p", finish_reason="http_401")]
    )
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=CheckpointManager(),
        planner=GeneralStepPlanner(backend=backend),
    )
    terminal, events = await run_engine_to_terminal(engine, make_task_spec())
    assert terminal == "failed"
    # The error carries the finish reason so recovery can classify it.
    failed_event = next(e for e in events if e.event_type == "failed")
    assert "http_401" in json.dumps(failed_event.data)


@pytest.mark.asyncio
async def test_non_retryable_step_failure_terminates_without_retry():
    """RL04-F-02: an auth failure is terminal — no retry/model-switch events."""
    backend = ScriptedBackend(
        [
            RuntimeError(
                "[openai] AUTHENTICATION (HTTP 401) model=gpt-4o: Invalid API key"
            )
        ]
    )
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=CheckpointManager(),
        planner=GeneralStepPlanner(backend=backend),
    )
    terminal, events = await run_engine_to_terminal(engine, make_task_spec())

    assert terminal == "failed"
    assert len(backend.calls) == 1, (
        "non-retryable failure must not re-invoke the backend"
    )
    for banned in ("step_retrying", "model_switched", "agent_switched"):
        assert not [e for e in events if e.event_type == banned]


@pytest.mark.asyncio
async def test_transient_failure_retries_within_bounded_budget():
    """Transient 503s retry with backoff, bounded by MAX_STEP_RETRIES=3."""
    failures = [ProviderUnavailableError("down", "p", status_code=503)] * 3
    success = BackendResponse(
        content="final answer", model="m", provider="p", finish_reason="stop"
    )
    backend = ScriptedBackend([*failures, success])
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=CheckpointManager(),
        planner=GeneralStepPlanner(backend=backend),
    )
    terminal, events = await run_engine_to_terminal(engine, make_task_spec())

    # With generic provider-unavailable text the recovery engine retries the
    # step; success arrives within the bounded retry budget.
    assert terminal == "completed"
    retries = [e for e in events if e.event_type == "step_retrying"]
    assert len(retries) <= 3


@pytest.mark.asyncio
async def test_run_timeout_is_terminal_and_never_resumable(monkeypatch):
    """Run-level timeout yields terminal TIMEOUT status; resume is refused."""
    calls = {"n": 0}

    class SlowBackend(ScriptedBackend):
        async def generate(self, request):
            calls["n"] += 1
            await asyncio.sleep(0.6)
            return await super().generate(request)

    backend = SlowBackend(
        [
            BackendResponse(content="a", model="m", provider="p", finish_reason="stop"),
            BackendResponse(content="b", model="m", provider="p", finish_reason="stop"),
        ]
    )
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=CheckpointManager(),
        planner=TwoStepPlanner(backend=backend),
    )
    spec = make_task_spec()
    spec.metadata["timeout_seconds"] = 0.5
    terminal, events = await run_engine_to_terminal(engine, spec)

    assert terminal == "failed"
    failed_event = next(e for e in events if e.event_type == "failed")
    assert failed_event.data.get("status") == "timeout"
    run_state = next(iter(engine._runs.values()))
    assert run_state.status == RunStatus.TIMEOUT
    assert run_state.status.is_terminal

    # Terminal states remain terminal: resume is refused.
    resume_events = await collect_events(
        engine.resume_run(run_id=run_state.run_id, tenant_id=spec.tenant_id)
    )
    assert resume_events[0].event_type == "resume_refused"


# ===========================================================================
# 3. BoundedRecoveryEngine classification matrix
# ===========================================================================


@pytest.mark.parametrize(
    "error_message,expected_action",
    [
        (
            "[openai] AUTHENTICATION (HTTP 401) model=gpt-4o: Invalid API key",
            "terminate_failed",
        ),
        (
            "[openai] AUTHENTICATION (HTTP 403) model=gpt-4o: forbidden",
            "terminate_failed",
        ),
        (
            "[openai] QUOTA (HTTP 429): You exceeded your current quota",
            "terminate_failed",
        ),
        ("[openai] POLICY_REJECTED (HTTP 400): content violation", "terminate_failed"),
        ("[openai] CONTEXT_LIMIT (HTTP 400): prompt is too long", "terminate_failed"),
        (
            "Forbidden: Tenant context lacks required permissions: finops:write",
            "terminate_failed",
        ),
        (
            "Policy violation: Malicious path traversal argument detected",
            "terminate_failed",
        ),
        (
            "Backend model generation failed (finish_reason=http_401).",
            "terminate_failed",
        ),
        ("Rate limit 429: Provider overloaded", "switch_model"),
        ("Step execution timed out after 30.0s.", "retry"),
        ("Connection reset by peer during upstream call", "retry"),
        ("[direct:openai] exception: ConnectError", "retry"),
    ],
)
def test_recovery_classification_matrix(error_message, expected_action):
    engine = BoundedRecoveryEngine()
    step = PlanStep(
        step_id="s1",
        description="d",
        candidate_agents=["general_agent"],
        dependencies=[],
        status=PlanStepStatus.FAILED,
    )
    decision = engine.evaluate_step_failure(
        step=step,
        error_message=error_message,
        current_step_retries=0,
        elapsed_time_seconds=0.0,
    )
    assert decision.action.value == expected_action, error_message


def test_recovery_first_attempt_timeout_does_not_crash():
    """RL04-F-07: first-attempt timeout (retries=0) returns a terminal decision."""
    engine = BoundedRecoveryEngine()
    step = PlanStep(
        step_id="s1",
        description="d",
        candidate_agents=["general_agent"],
        dependencies=[],
        status=PlanStepStatus.FAILED,
    )
    decision = engine.evaluate_step_failure(
        step=step,
        error_message="anything",
        current_step_retries=0,
        elapsed_time_seconds=999.0,
    )
    assert decision.action.value == "terminate_failed"


def test_recovery_first_attempt_non_retryable_does_not_crash():
    decision = BoundedRecoveryEngine().evaluate_step_failure(
        step=PlanStep(
            step_id="s1",
            description="d",
            candidate_agents=["general_agent"],
            dependencies=[],
            status=PlanStepStatus.FAILED,
        ),
        error_message="[openai] AUTHENTICATION (HTTP 401): Invalid API key",
        current_step_retries=0,
        elapsed_time_seconds=0.0,
    )
    assert decision.action.value == "terminate_failed"


def test_recovery_verification_rejection_never_replans():
    """REJECTED verdict terminates rejected — security failures never loop."""
    from app.agent.domain.contracts import VerificationResult, VerificationVerdict

    decision = BoundedRecoveryEngine().evaluate_verification_result(
        verification=VerificationResult(
            verdict=VerificationVerdict.REJECTED,
            reason="tenant breach",
        ),
        current_replans=0,
        elapsed_time_seconds=0.0,
    )
    assert decision.action.value == "terminate_rejected"


# ===========================================================================
# 4. Gateway: outage fallback, cache poisoning, circuit breaker
# ===========================================================================


@pytest.mark.asyncio
async def test_gateway_outage_fallback_not_cached_and_breaker_counts(monkeypatch):
    """RL04-F-03/F-04: fallback served on outage, not cached; breaker records."""
    import app.services.ai_gateway as gw_mod
    from app.services.ai_gateway import (
        GatewayChatRequest,
        GatewayInferenceProxy,
        QuotaManager,
    )

    async def outage(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(gw_mod, "call_upstream_llm_detailed", outage)
    monkeypatch.setattr(gw_mod, "call_upstream_llm", outage)

    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())
    request = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=[{"role": "user", "content": "outage probe"}],
    )
    resp = await proxy.chat_completions(tenant_id="tenant-rl04", request=request)
    assert resp.choices[0]["message"]["content"].startswith("[JakeAI Gateway Response")
    assert proxy.breaker.failure_count == 1

    # Provider recovers: the same request must now be served by the provider,
    # NOT by the cached outage fallback.
    class _T:
        def model_dump(self) -> dict[str, Any]:
            return {}

    class _R:
        text = "REAL PROVIDER ANSWER"
        model = "gemini-1.5-flash"
        provider = "gemini"
        telemetry = _T()

    async def recovered(*args: Any, **kwargs: Any) -> _R:
        return _R()

    monkeypatch.setattr(gw_mod, "call_upstream_llm_detailed", recovered)
    resp2 = await proxy.chat_completions(tenant_id="tenant-rl04", request=request)
    assert resp2.choices[0]["message"]["content"] == "REAL PROVIDER ANSWER"
    assert resp2.cached is False


@pytest.mark.asyncio
async def test_gateway_breaker_opens_after_consecutive_outages(monkeypatch):
    """Three consecutive total outages trip the breaker; calls fast-fall back."""
    import app.services.ai_gateway as gw_mod
    from app.services.ai_gateway import (
        GatewayChatRequest,
        GatewayInferenceProxy,
        QuotaManager,
    )

    provider_calls = {"n": 0}

    async def outage(*args: Any, **kwargs: Any) -> None:
        provider_calls["n"] += 1
        return None

    monkeypatch.setattr(gw_mod, "call_upstream_llm_detailed", outage)
    monkeypatch.setattr(gw_mod, "call_upstream_llm", outage)

    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())
    request = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=[{"role": "user", "content": "breaker probe"}],
    )
    for _ in range(3):
        resp = await proxy.chat_completions(tenant_id="tenant-rl04", request=request)
        assert resp.choices[0]["message"]["content"].startswith("[JakeAI Gateway")
    assert proxy.breaker.state == CircuitState.OPEN

    # While OPEN, requests are served from the deterministic fallback without
    # touching the (dead) provider.
    before = provider_calls["n"]
    resp = await proxy.chat_completions(tenant_id="tenant-rl04", request=request)
    assert resp.choices[0]["message"]["content"].startswith("[JakeAI Gateway")
    assert provider_calls["n"] == before


@pytest.mark.asyncio
async def test_gateway_stream_outage_fallback_not_cached(monkeypatch):
    """Stream path: outage fallback is streamed but never cached."""
    import app.core.llm_provider as llm_mod
    from app.services.ai_gateway import (
        GatewayChatRequest,
        GatewayInferenceProxy,
        QuotaManager,
    )

    async def outage(*args: Any, **kwargs: Any) -> None:
        return None

    # chat_completions_stream imports call_upstream_llm locally, so patch at
    # the source module.
    monkeypatch.setattr(llm_mod, "call_upstream_llm", outage)

    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())
    request = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=[{"role": "user", "content": "stream outage probe"}],
    )
    chunks = [
        chunk
        async for chunk in proxy.chat_completions_stream(
            tenant_id="tenant-rl04", request=request
        )
    ]
    assert "[JakeAI Gateway Stream" in _sse_contents(chunks)
    assert chunks[-1] == "data: [DONE]\n\n"

    # Provider recovers: the same prompt must not be answered from cache.
    # The stream path consumes call_upstream_llm's plain-text contract.
    async def recovered_text(*args: Any, **kwargs: Any) -> str:
        return "REAL STREAM ANSWER"

    monkeypatch.setattr(llm_mod, "call_upstream_llm", recovered_text)
    chunks2 = [
        chunk
        async for chunk in proxy.chat_completions_stream(
            tenant_id="tenant-rl04", request=request
        )
    ]
    content2 = _sse_contents(chunks2)
    assert "REAL STREAM ANSWER" in content2
    assert "JakeAI Gateway Stream" not in content2


def _sse_contents(chunks: list[str]) -> str:
    """Reconstruct streamed content from OpenAI-style SSE data chunks."""
    parts: list[str] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                payload = json.loads(line[len("data: ") :])
            except json.JSONDecodeError:
                continue
            choices = payload.get("choices") or [{}]
            delta = choices[0].get("delta", {}) if choices else {}
            if delta.get("content"):
                parts.append(delta["content"])
    return "".join(parts)


# ===========================================================================
# 5. Streaming failure propagation
# ===========================================================================


@pytest.mark.asyncio
async def test_midstream_failure_propagates_not_silently_truncates(monkeypatch):
    """RL04-F-05: a mid-stream provider failure raises instead of ending quietly."""
    import app.core.llm_provider as llm_mod

    class _Chunk:
        delta_text = "partial"

    async def broken_stream(*args: Any, **kwargs: Any):
        yield _Chunk()
        raise ProviderUnavailableError("connection reset mid-stream", "gemini")

    class FakeFM:
        def stream_with_failover(
            self, request, decision, client=None, credential_resolver=None
        ):
            return broken_stream()

    monkeypatch.setattr(llm_mod, "get_failover_manager", lambda: FakeFM())

    received: list[str] = []
    with pytest.raises(ProviderUnavailableError):
        async for delta in llm_mod.call_upstream_llm_stream(prompt="p", tenant_id="t1"):
            received.append(delta)
    assert received == ["partial"]


@pytest.mark.asyncio
async def test_backend_stream_signals_error_terminal_chunk(monkeypatch):
    """JakeAIBackend.generate_stream yields an error terminal chunk on mid-stream failure."""

    async def broken_stream(*args: Any, **kwargs: Any):
        yield "partial "
        raise ProviderUnavailableError("reset", "gemini")

    async def stream_call(*args: Any, **kwargs: Any):
        async for delta in broken_stream():
            yield delta

    # JakeAIBackend imports call_upstream_llm_stream lazily inside the method;
    # patching the source module makes the lazy import pick up the broken stream.
    import app.core.llm_provider as llm_mod

    monkeypatch.setattr(llm_mod, "call_upstream_llm_stream", stream_call)

    backend = JakeAIBackend()
    req = BackendRequest(
        messages=[
            {"role": "user", "content": "stream me"},
        ],
        model="gemini-1.5-flash",
        tenant_id="t1",
    )
    chunks = [c async for c in backend.generate_stream(req)]
    assert chunks[0].delta_content == "partial "
    assert chunks[-1].finish_reason == "error"
    assert chunks[-1].is_complete is True


# ===========================================================================
# 6. RAG: retrieval failure vs empty evidence
# ===========================================================================


@pytest.mark.asyncio
async def test_rag_total_retrieval_failure_classified_as_retrieval_failure():
    """RL04-F-06: both retrieval legs failing is RETRIEVAL_FAILURE, not empty evidence."""
    from app.rag.models import AbstentionReason, RetrievalResult
    from app.rag.pipeline import RAGPipeline

    class DeadRetriever:
        async def retrieve(self, query, tenant_id, top_k=5, candidate_pool=None):
            return RetrievalResult(
                query=query,
                tenant_id=tenant_id,
                chunks=[],
                total_candidates=0,
                latency_ms=1.0,
                retrieval_mode="failed",
                degraded=True,
            )

    result = await RAGPipeline(retriever=DeadRetriever()).generate_grounded_answer(
        query="q", tenant_id="tenant-rl04"
    )
    assert result.status == "ABSTAINED"
    assert result.abstention_reason == AbstentionReason.RETRIEVAL_FAILURE


@pytest.mark.asyncio
async def test_rag_empty_index_still_no_relevant_evidence():
    """A genuinely empty (but healthy) index stays NO_RELEVANT_EVIDENCE."""
    from app.rag.models import AbstentionReason, RetrievalResult
    from app.rag.pipeline import RAGPipeline

    class EmptyRetriever:
        async def retrieve(self, query, tenant_id, top_k=5, candidate_pool=None):
            return RetrievalResult(
                query=query,
                tenant_id=tenant_id,
                chunks=[],
                total_candidates=0,
                latency_ms=1.0,
                retrieval_mode="hybrid",
                degraded=False,
            )

    result = await RAGPipeline(retriever=EmptyRetriever()).generate_grounded_answer(
        query="q", tenant_id="tenant-rl04"
    )
    assert result.status == "ABSTAINED"
    assert result.abstention_reason == AbstentionReason.NO_RELEVANT_EVIDENCE


# ===========================================================================
# 7. Persistence: corrupt checkpoints fail closed; Redis failure degrades
# ===========================================================================


class _FakeRedis:
    """Minimal async Redis double (deliberately not named Mock*)."""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store = store if store is not None else {}
        self.fail_writes = False

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        if self.fail_writes:
            raise ConnectionError("redis down")
        self.store[key] = value

    async def delete(self, *keys: str):
        for k in keys:
            self.store.pop(k, None)

    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_corrupt_checkpoint_fails_closed_no_fabricated_success():
    """A corrupt checkpoint record cannot be resumed into a fake success."""
    from app.agent.state.models import RunState

    mgr = CheckpointManager()
    run_state = RunState(
        run_id="run_corrupt",
        task_id="task_corrupt",
        tenant_id="tenant-rl04",
        user_id="user-rl04",
        status=RunStatus.EXECUTING,
        prompt="p",
    )
    cp_id = await mgr.save_checkpoint(run_state)

    # Corrupt the durable record behind the manager's back (simulates a bad
    # write or version skew), then drop the in-memory copy (process restart).
    fake = _FakeRedis()
    fake.store[f"agent:checkpoint:rec:{cp_id}"] = "{corrupt json not valid"
    fake.store["agent:checkpoint:run:run_corrupt"] = cp_id
    mgr.redis_client = fake
    mgr._checkpoints.clear()
    mgr._run_to_latest.clear()

    loaded = await mgr.load_checkpoint("run_corrupt", tenant_id="tenant-rl04")
    assert loaded is None, "corrupt records must not load as a valid checkpoint"
    with pytest.raises(KeyError):
        await mgr.resume_run_from_checkpoint("run_corrupt", tenant_id="tenant-rl04")


@pytest.mark.asyncio
async def test_redis_write_failure_degrades_to_memory_without_crash():
    """Checkpoint writes degrade to in-memory durability when Redis fails."""
    mgr = CheckpointManager()
    fake = _FakeRedis()
    fake.fail_writes = True
    mgr.redis_client = fake

    from app.agent.state.models import RunState

    run_state = RunState(
        run_id="run_degrade",
        task_id="task_degrade",
        tenant_id="tenant-rl04",
        user_id="user-rl04",
        status=RunStatus.EXECUTING,
        prompt="p",
    )
    cp_id = await mgr.save_checkpoint(run_state)
    assert cp_id.startswith("cp_run_degrade")
    cp = await mgr.get_checkpoint(cp_id, tenant_id="tenant-rl04")
    assert cp.run_id == "run_degrade"


# ===========================================================================
# 8. Tool failures: timeout and policy denial never become success
# ===========================================================================


class _SlowTool(Tool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="slow_probe",
            description="Sleeps beyond its timeout",
            input_schema={"type": "object", "properties": {}},
            timeout_seconds=0.1,
        )

    async def execute(self, arguments, context=None) -> ToolResult:
        await asyncio.sleep(1.0)
        return ToolResult(success=True, output={"done": True})


class _DeniedTool(Tool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="denied_probe",
            description="Requires permissions the caller lacks",
            input_schema={"type": "object", "properties": {}},
            permissions=["finops:admin"],
        )

    async def execute(self, arguments, context=None) -> ToolResult:
        return ToolResult(success=True, output={"should": "never happen"})


def _fresh_registry(tool: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(tool)
    return registry


@pytest.mark.asyncio
async def test_tool_timeout_returns_failed_result():
    registry = _fresh_registry(_SlowTool())
    res = await registry.execute(
        "slow_probe", {}, context={"roles": [], "permissions": []}
    )
    assert res.success is False
    assert "timed out" in (res.error or "")


@pytest.mark.asyncio
async def test_tool_policy_denial_never_executes():
    registry = _fresh_registry(_DeniedTool())
    res = await registry.execute(
        "denied_probe", {}, context={"roles": [], "permissions": []}
    )
    assert res.success is False
    assert "Forbidden" in (res.error or "")


@pytest.mark.asyncio
async def test_engine_permission_denied_step_terminates_without_retry():
    """A policy-denied tool step terminates the run (never retried into success)."""

    class ToolStepPlanner(BoundedPlanner):
        async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
            return Plan(
                task_id=task_spec.task_id,
                goal=task_spec.goal,
                analysis="tool step",
                steps=[
                    PlanStep(
                        step_id="step_tool",
                        description="Use denied tool",
                        candidate_agents=["general_agent"],
                        dependencies=[],
                        status=PlanStepStatus.PENDING,
                        required_tools=["denied_probe"],
                    )
                ],
            )

    registry = _fresh_registry(_DeniedTool())
    backend = ScriptedBackend([])
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=CheckpointManager(),
        planner=ToolStepPlanner(backend=backend),
        tool_registry=registry,
    )
    terminal, events = await run_engine_to_terminal(engine, make_task_spec())

    assert terminal == "failed"
    assert not [e for e in events if e.event_type == "step_retrying"]
    run_state = next(iter(engine._runs.values()))
    assert run_state.status == RunStatus.FAILED


# ===========================================================================
# 9. Malformed model output: bounded deterministic fallback
# ===========================================================================


@pytest.mark.asyncio
async def test_malformed_plan_output_falls_back_deterministically():
    """A model returning garbage instead of plan JSON falls back, bounded."""
    backend = ScriptedBackend(
        [
            BackendResponse(
                content="this is not json at all {{{",
                model="m",
                provider="p",
                finish_reason="stop",
            )
        ]
    )
    planner = BoundedPlanner(backend=backend)
    plan = await planner.plan_task(make_task_spec())
    assert plan.planner_mode == "degraded_fallback"
    assert len(plan.steps) >= 1
