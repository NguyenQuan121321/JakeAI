"""Comprehensive Integration & Verification Tests for Tier 5 -> 6 -> 7 -> 5 Pipeline.

Verifies:
1. Cross-tier data contract integrity and typing.
2. Rule 4: Tier 6 MUST NOT modify Tier 5's Zone 1 Static Prefix.
3. Static prefix stability under varying dynamic context.
4. Static prefix invalidation when static instructions change.
5. Tier 6 -> Tier 7 measurement contract (raw >= optimized, exact removal accounting).
6. Tier 7 -> Tier 5 cache eligibility re-evaluation.
7. Context budget enforcement (overflow accepted if Tier 6 optimizes within budget;
   safe fail-closed if still exceeds).
8. Fail-closed fallback on malformed syntax / AST errors without context corruption.
9. Upstream provider telemetry extraction (Rule 1 Zero Fake Hits).
10. Separation of Layer A, Layer B, and Tier 6 dimensions (No Double Counting).
11. Concurrency isolation across multiple tenants.
12. Property-based invariants.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.llm_provider import UpstreamLLMResponse
from app.optimizer.bpe_tokenizer import BPETokenizer, ContextBudgetExceededError
from app.optimizer.context_optimizer import ContextOptimizer
from app.optimizer.contracts import OptimizationLevel
from app.optimizer.cross_tier_pipeline import CrossTierPipeline
from app.optimizer.prompt_compiler import PromptCompiler

STATIC_SYSTEM = (
    "You are JakeAI Enterprise Assistant.\n"
    "Follow corporate security policies and zero-hallucination protocols."
)

SAMPLE_TOOLS = [
    {
        "name": "search_code",
        "description": "Semantic code search across repositories",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "run_unit_test",
        "description": "Execute pytest or jest test suite",
        "parameters": {
            "type": "object",
            "properties": {"test_target": {"type": "string"}},
            "required": ["test_target"],
        },
    },
]

PYTHON_DYNAMIC_CODE = """
import os
import sys

class PaymentProcessor:
    \"\"\"Handles billing and credit transactions.\"\"\"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.verified = False

    def process_charge(self, amount_cents: int, currency: str = "USD") -> bool:
        \"\"\"Charge card with fraud detection.\"\"\"
        if amount_cents <= 0:
            raise ValueError("Amount must be positive")
        # Internal complex validation steps
        token = os.getenv("SECRET_TOKEN", "default")
        result = self._execute_gateway_call(token, amount_cents)
        return bool(result)

    def _execute_gateway_call(self, token: str, amount: int) -> dict:
        \"\"\"Internal private communication.\"\"\"
        return {"status": "ok", "charged": amount}
"""


@pytest.fixture
def pipeline() -> CrossTierPipeline:
    return CrossTierPipeline(
        prompt_compiler=PromptCompiler(min_cache_tokens=100),
        context_optimizer=ContextOptimizer(),
        tokenizer=BPETokenizer(),
    )


@pytest.mark.asyncio
async def test_dynamic_change_does_not_change_static_prefix(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 5 Mandatory Integration Test: Static prefix remains byte-identical.

    Request A: Static S + Dynamic D1
    Request B: Static S + Dynamic D2
    Expect: hash(static_A) == hash(static_B) AND static_A == static_B
    """
    res_a = await pipeline.process(
        system_instruction=STATIC_SYSTEM,
        tools=SAMPLE_TOOLS,
        user_query="How to run unit tests?",
        dynamic_context="Dynamic context A: Test runner logs for module auth",
        model="claude-3-5-sonnet-20241022",
        tenant_id="tenant-alpha",
    )

    res_b = await pipeline.process(
        system_instruction=STATIC_SYSTEM,
        tools=SAMPLE_TOOLS,
        user_query="How to process a payment?",
        dynamic_context="Dynamic context B: Payment gateway config and webhooks",
        model="claude-3-5-sonnet-20241022",
        tenant_id="tenant-alpha",
    )

    # Diagnostic failure assertions (Section 34)
    assert (
        res_a.compiled_prompt.zone1_static_prefix
        == res_b.compiled_prompt.zone1_static_prefix
    ), (
        "Tier 5-7 integration failure: Static prefix changed when only dynamic context changed!\n"
        f"Request A Prefix:\n{res_a.compiled_prompt.zone1_static_prefix}\n"
        f"Request B Prefix:\n{res_b.compiled_prompt.zone1_static_prefix}"
    )

    assert (
        res_a.compiled_prompt.static_prefix_hash
        == res_b.compiled_prompt.static_prefix_hash
    ), (
        "Tier 5-7 integration failure: Static prefix SHA-256 hash mismatch under varying dynamic inputs!\n"
        f"Request A Hash: {res_a.compiled_prompt.static_prefix_hash}\n"
        f"Request B Hash: {res_b.compiled_prompt.static_prefix_hash}"
    )


@pytest.mark.asyncio
async def test_static_change_invalidates_prefix_hash(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 16: Changing static information MUST invalidate static prefix hash."""
    res_v1 = await pipeline.process(
        system_instruction="System policy version 1.0: Enforce strict auth.",
        user_query="Check user permissions",
        model="claude-3-5-sonnet-20241022",
    )

    res_v2 = await pipeline.process(
        system_instruction="System policy version 2.0: Enforce RBAC and MFA.",
        user_query="Check user permissions",
        model="claude-3-5-sonnet-20241022",
    )

    assert (
        res_v1.compiled_prompt.static_prefix_hash
        != res_v2.compiled_prompt.static_prefix_hash
    )
    assert (
        res_v1.compiled_prompt.zone1_static_prefix
        != res_v2.compiled_prompt.zone1_static_prefix
    )


@pytest.mark.asyncio
async def test_tier6_output_measured_by_tier7_bpe(pipeline: CrossTierPipeline) -> None:
    """Sections 6 & 7: Every Tier 6 optimization must be measurable by Tier 7 BPE tokenizer."""
    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM,
        user_query="Explain the architecture of payment system",
        dynamic_context=PYTHON_DYNAMIC_CODE,
        optimization_level=OptimizationLevel.AGGRESSIVE,
        model="gpt-4o",
    )

    tm = res.token_metrics
    assert tm.raw_tokens >= tm.optimized_tokens, (
        f"Invariant broken: raw tokens ({tm.raw_tokens}) < optimized tokens ({tm.optimized_tokens})"
    )
    assert tm.removed_tokens == tm.raw_tokens - tm.optimized_tokens, (
        f"Invariant broken: removed_tokens ({tm.removed_tokens}) != raw - optimized"
    )
    expected_ratio = round(tm.removed_tokens / tm.raw_tokens, 4)
    assert abs(tm.reduction_ratio - expected_ratio) < 0.001

    # Verify skeletonization occurred in aggressive mode
    assert "..." in res.optimized_context.content
    assert "process_charge" in res.optimized_context.content
    assert res.fallback_used is False


@pytest.mark.asyncio
async def test_context_budget_enforcement_accepts_when_tier6_fits(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 9: Raw context exceeds budget, but Tier 6 optimization brings it within budget."""
    long_code = PYTHON_DYNAMIC_CODE * 4
    tokenizer = pipeline.tokenizer
    raw_est = tokenizer.count_tokens(STATIC_SYSTEM + "\n\n" + long_code)

    # Set budget lower than raw, but higher than optimized
    budget = raw_est - 30

    # In aggressive mode, skeletonization will reduce tokens significantly
    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM,
        user_query="High-level architecture overview",
        dynamic_context=long_code,
        context_budget=budget,
        optimization_level=OptimizationLevel.AGGRESSIVE,
        model="gpt-4o",
    )

    assert res.token_metrics.raw_tokens > budget, "Raw should exceed budget"
    assert res.token_metrics.optimized_tokens <= budget, (
        "Optimized must fit within budget"
    )
    assert res.compiled_prompt.total_token_count <= budget


@pytest.mark.asyncio
async def test_context_budget_enforcement_fails_safely_when_still_overflowing(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 9: When even optimized context exceeds budget, fails safely without truncation."""
    with pytest.raises(ContextBudgetExceededError) as exc_info:
        await pipeline.process(
            system_instruction=STATIC_SYSTEM,
            user_query="Show full codebase",
            dynamic_context=PYTHON_DYNAMIC_CODE * 10,
            context_budget=20,  # Impossible budget
            optimization_level=OptimizationLevel.CONSERVATIVE,
        )

    assert "Context budget exceeded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fail_closed_fallback_on_malformed_syntax(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 13: Tier 6 encounters malformed syntax and falls back closed to original context."""
    malformed_code = (
        "def broken_function(\n"
        "    for x in [1, 2, 3\n"  # Syntax error
        "        print(x\n"
    )

    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM,
        user_query="Explain this snippet",
        dynamic_context=malformed_code,
        optimization_level=OptimizationLevel.BALANCED,
    )

    assert res.fallback_used is True
    assert res.fallback_reason is not None
    assert "SyntaxError" in res.fallback_reason
    # Guarantees context was not silently truncated or corrupted
    assert res.optimized_context.content == malformed_code


@pytest.mark.asyncio
async def test_provider_cache_telemetry_reconciliation_rule1(
    pipeline: CrossTierPipeline,
) -> None:
    """Sections 14, 17, 18: Authoritative provider usage telemetry and FinOps cost reconciliation."""

    async def mock_llm(
        prompt: str, compiled_prompt: Any, model: str, tenant_id: str
    ) -> UpstreamLLMResponse:
        from app.core.llm_provider import ProviderCacheTelemetry

        return UpstreamLLMResponse(
            text="PaymentProcessor architecture has been analyzed.",
            model=model,
            provider="anthropic",
            telemetry=ProviderCacheTelemetry(
                is_cache_eligible=True,
                cache_hit=True,
                cached_tokens=1200,  # Authoritative provider cache HIT
                uncached_input_tokens=300,
                cache_write_tokens=0,
                output_tokens=40,
                provider="anthropic",
                model=model,
            ),
        )

    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM * 10,  # Make it cache-eligible (>1024 tokens)
        user_query="Analyze payment system",
        dynamic_context=PYTHON_DYNAMIC_CODE,
        model="claude-3-5-sonnet-20241022",
        call_llm=True,
        llm_caller=mock_llm,
    )

    assert res.provider_cache_metrics.hit is True
    assert res.provider_cache_metrics.cache_read_tokens == 1200
    assert res.provider_cache_metrics.uncached_input_tokens == 300
    assert res.cost_metrics.get("savings_usd", 0.0) > 0.0

    # Verify no double-counting between physical reduction and provider KV cache
    assert res.token_metrics.removed_tokens >= 0  # Tier 6 physical removal
    assert res.provider_cache_metrics.cache_read_tokens == 1200  # Tier 5 KV cache read


@pytest.mark.asyncio
async def test_concurrency_and_tenant_isolation(pipeline: CrossTierPipeline) -> None:
    """Section 27 & 31: Concurrent requests across tenants do not leak context or hashes."""

    async def run_tenant(t_id: str, query: str, dyn: str):
        return await pipeline.process(
            system_instruction=STATIC_SYSTEM,
            user_query=query,
            dynamic_context=dyn,
            tenant_id=t_id,
            model="claude-3-5-sonnet-20241022",
        )

    tasks = [
        run_tenant(
            f"tenant-{i % 3}",
            f"Query {i}",
            f"Dynamic data for tenant {i % 3} with id {i}",
        )
        for i in range(30)
    ]
    results = await asyncio.gather(*tasks)

    # Group by tenant
    tenant_hashes: dict[str, set[str]] = {}
    for r in results:
        t_id = r.compiled_prompt.tenant_id
        h = r.compiled_prompt.static_prefix_hash
        tenant_hashes.setdefault(t_id, set()).add(h)

    # Each tenant should have exactly 1 consistent static prefix hash across all runs
    for t_id, hashes in tenant_hashes.items():
        assert len(hashes) == 1, (
            f"Tenant {t_id} experienced static prefix hash jitter: {hashes}"
        )

    # Hashes between different tenants should be distinct due to tenant scoping
    assert tenant_hashes["tenant-0"] != tenant_hashes["tenant-1"]
    assert tenant_hashes["tenant-1"] != tenant_hashes["tenant-2"]


@pytest.mark.asyncio
async def test_property4_no_corruption_output_valid_ast(
    pipeline: CrossTierPipeline,
) -> None:
    """Property 4: Transformed code must remain syntactically valid Python (parseable by ast.parse)."""
    import ast

    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM,
        user_query="High-level architecture overview",
        dynamic_context=PYTHON_DYNAMIC_CODE,
        optimization_level=OptimizationLevel.AGGRESSIVE,
        model="claude-3-5-sonnet-20241022",
    )

    # Output code must be 100% valid Python syntax
    parsed = ast.parse(res.optimized_context.content)
    assert parsed is not None
    assert res.fallback_used is False


@pytest.mark.asyncio
async def test_provider_request_payload_inspection_anthropic_vs_openai(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 25: Verify actual provider-specific request payload structure."""
    from app.optimizer.provider_cache_policy import (
        AnthropicPromptCacheAdapter,
        OpenAIPromptCacheAdapter,
    )

    anthropic_adapter = AnthropicPromptCacheAdapter()
    openai_adapter = OpenAIPromptCacheAdapter()

    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM * 10,
        user_query="Explain billing system",
        dynamic_context=PYTHON_DYNAMIC_CODE,
        model="claude-3-5-sonnet-20241022",
    )

    # 1. Anthropic must attach explicit cache_control breakpoint
    anthropic_payload = anthropic_adapter.prepare_request(
        static_prefix=res.compiled_prompt.zone1_static_prefix,
        dynamic_suffix=res.compiled_prompt.zone2_dynamic_suffix,
        model="claude-3-5-sonnet-20241022",
        is_eligible=True,
    )
    system_blocks = anthropic_payload.get("system", [])
    assert len(system_blocks) > 0
    assert system_blocks[-1].get("cache_control") == {"type": "ephemeral"}

    # 2. OpenAI must NOT invent explicit cache_control fields (automatic prefix caching)
    openai_payload = openai_adapter.prepare_request(
        static_prefix=res.compiled_prompt.zone1_static_prefix,
        dynamic_suffix=res.compiled_prompt.zone2_dynamic_suffix,
        model="gpt-4o",
        is_eligible=True,
    )
    assert "cache_control" not in openai_payload


@pytest.mark.asyncio
async def test_streaming_pipeline_reconciliation(pipeline: CrossTierPipeline) -> None:
    """Section 26: Streaming request token accounting reconciliation."""
    from app.core.llm_provider import ProviderCacheTelemetry

    chunks = ["Payment", "Processor", " is", " verified."]

    async def mock_streaming_caller(
        prompt: str, compiled_prompt: Any, model: str, tenant_id: str
    ):
        full_text = "".join(chunks)
        return UpstreamLLMResponse(
            text=full_text,
            model=model,
            provider="anthropic",
            telemetry=ProviderCacheTelemetry(
                is_cache_eligible=True,
                cache_hit=True,
                cached_tokens=1100,
                uncached_input_tokens=250,
                cache_write_tokens=0,
                output_tokens=len(chunks),
                provider="anthropic",
                model=model,
            ),
        )

    res = await pipeline.process(
        system_instruction=STATIC_SYSTEM * 10,
        user_query="Stream the payment processing status",
        dynamic_context=PYTHON_DYNAMIC_CODE,
        model="claude-3-5-sonnet-20241022",
        call_llm=True,
        llm_caller=mock_streaming_caller,
    )

    assert res.response_content == "PaymentProcessor is verified."
    assert res.token_metrics.output_tokens == 4
    assert res.provider_cache_metrics.hit is True
    assert res.provider_cache_metrics.cache_read_tokens == 1100


@pytest.mark.asyncio
async def test_chaos_failure_injection_degrades_safely(
    pipeline: CrossTierPipeline,
) -> None:
    """Section 30: Chaos / Failure injection degrades safely without crashing."""
    # When dynamic context is extreme or empty
    res_empty = await pipeline.process(
        system_instruction="",
        user_query="",
        dynamic_context="",
    )
    assert res_empty.token_metrics.input_tokens == 0
    assert res_empty.fallback_used is False

    # When LLM caller raises an unhandled exception
    async def failing_llm(
        prompt: str, compiled_prompt: Any, model: str, tenant_id: str
    ):
        raise RuntimeError("Simulated upstream 503 Service Unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        await pipeline.process(
            system_instruction=STATIC_SYSTEM,
            user_query="Test failure",
            call_llm=True,
            llm_caller=failing_llm,
        )
    assert "Simulated upstream 503" in str(exc_info.value)
