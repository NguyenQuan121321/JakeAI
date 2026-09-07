"""Tier 5 -> Tier 6 -> Tier 7 -> Tier 5 Cross-Tier Integration Pipeline.

Executes the unified cross-tier contract:
1. Tier 5 (Initial Partitioning): Separates Zone 1 (immutable static) from Zone 2 (dynamic).
2. Tier 6 (Context Optimizer): Task-aware AST skeletonization and pruning on Zone 2 ONLY.
   - Enforces Rule 4: Zone 1 static prefix is NEVER modified.
3. Tier 7 (BPE Tokenizer & Budget): Measures exact physical reduction, enforces context budgets.
4. Tier 5 (Final Provider Compilation): Re-evaluates cache eligibility with post-optimization
   token metrics and configures provider-specific cache breakpoints.
5. LLM Call & Tier 7 Final Reconciliation: Binds authoritative provider usage telemetry
   and calculates FinOps cost savings without double-counting.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable  # noqa: TC003
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.llm_provider import UpstreamLLMResponse

from app.optimizer.bpe_tokenizer import BPETokenizer, get_bpe_tokenizer
from app.optimizer.context_optimizer import (
    ContextOptimizer,
    get_context_optimizer,
)
from app.optimizer.contracts import (
    CrossTierResult,
    OptimizationLevel,
    OptimizedContext,
    ProviderCacheMetrics,
    TokenMetrics,
)
from app.optimizer.prompt_compiler import (
    PromptCompiler,
    PromptEnvelope,
    get_prompt_compiler,
)
from app.optimizer.provider_cache_policy import (
    CacheMissReason,
    evaluate_cache_eligibility,
    get_provider_cache_policy,
)
from app.optimizer.provider_pricing import calculate_provider_costs
from app.optimizer.token_accounting import TokenAccounting

logger = logging.getLogger(__name__)


class CrossTierPipeline:
    """Production orchestrator executing Tier 5 -> Tier 6 -> Tier 7 -> Tier 5."""

    def __init__(
        self,
        prompt_compiler: PromptCompiler | None = None,
        context_optimizer: ContextOptimizer | None = None,
        tokenizer: BPETokenizer | None = None,
    ) -> None:
        self.compiler = prompt_compiler or get_prompt_compiler()
        self.optimizer = context_optimizer or get_context_optimizer()
        self.tokenizer = tokenizer or get_bpe_tokenizer()

    async def process(
        self,
        system_instruction: str = "",
        tools: list[dict[str, Any]] | None = None,
        static_context: str = "",
        user_query: str = "",
        dynamic_context: str = "",
        provider: str = "generic",
        model: str = "default",
        tenant_id: str = "default",
        version: str = "v1.0",
        context_budget: int | None = None,
        optimization_level: OptimizationLevel | None = None,
        preserve_symbols: set[str] | None = None,
        call_llm: bool = False,
        llm_caller: Callable[..., Any] | None = None,
        request_id: str = "cross-tier-test",
        workload_type: str | None = None,
    ) -> CrossTierResult:
        """Execute complete cross-tier pipeline with full observability."""
        _ = provider
        t_start = time.perf_counter()
        latencies: dict[str, float] = {}

        # -------------------------------------------------------------
        # Phase 1: Tier 5 — Initial Two-Zone Partitioning
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        initial_envelope: PromptEnvelope = self.compiler.compile(
            system_instruction=system_instruction,
            tools=tools,
            static_context=static_context,
            user_query=user_query,
            dynamic_context=dynamic_context,
            prompt_version=version,
            model=model,
            tenant_id=tenant_id,
        )
        latencies["tier5_initial_ms"] = (time.perf_counter() - t0) * 1000.0

        # Snapshot of Zone 1 to verify Rule 4 invariant (zero static mutation)
        immutable_zone1_prefix = initial_envelope.zone1_static_prefix
        immutable_zone1_hash = initial_envelope.static_prefix_hash

        # -------------------------------------------------------------
        # Phase 2: Tier 6 — Task-Aware Context Optimization & AST Skeletonizer
        # -------------------------------------------------------------
        t1 = time.perf_counter()
        # Enforce Rule 4: Tier 6 optimizes ONLY Zone 2 (dynamic suffix)
        optimized_context: OptimizedContext = self.optimizer.optimize_dynamic_context(
            dynamic_context=dynamic_context,
            user_query=user_query,
            optimization_level=optimization_level,
            preserve_symbols=preserve_symbols,
            workload_type=workload_type,
        )
        latencies["tier6_optimization_ms"] = (time.perf_counter() - t1) * 1000.0

        # Assemble effective Zone 2 (optimized dynamic context + user query)
        suffix_parts: list[str] = []
        if optimized_context.content.strip():
            suffix_parts.append(optimized_context.content.strip())
        if user_query.strip():
            suffix_parts.append(user_query.strip())
        effective_zone2 = "\n\n".join(suffix_parts).strip()

        # -------------------------------------------------------------
        # Phase 3: Tier 7 — Real BPE Tokenization & Budget Enforcement
        # -------------------------------------------------------------
        t2 = time.perf_counter()
        zone1_tokens = self.tokenizer.count_tokens(immutable_zone1_prefix, model=model)
        zone2_raw_tokens = self.tokenizer.count_tokens(
            initial_envelope.zone2_dynamic_suffix, model=model
        )
        zone2_optimized_tokens = self.tokenizer.count_tokens(
            effective_zone2, model=model
        )

        total_optimized_tokens = zone1_tokens + zone2_optimized_tokens
        total_raw_tokens = zone1_tokens + zone2_raw_tokens

        # Check Context Budget Enforcement (Section 9)
        if context_budget is not None:
            self.tokenizer.enforce_context_budget(
                raw_tokens=total_raw_tokens,
                optimized_tokens=total_optimized_tokens,
                budget=context_budget,
                raise_on_exceed=True,
            )

        tokens_removed = max(0, total_raw_tokens - total_optimized_tokens)
        reduction_ratio = (
            round(tokens_removed / total_raw_tokens, 4) if total_raw_tokens > 0 else 0.0
        )

        token_metrics = TokenMetrics(
            tokenizer=(
                f"tiktoken/{self.tokenizer.default_encoding_name}"
                if self.tokenizer.is_native_bpe
                else "calibrated-bpe-heuristic"
            ),
            tokenizer_version="0.14.0" if self.tokenizer.is_native_bpe else "1.0.0",
            input_tokens=total_optimized_tokens,
            output_tokens=None,
            removed_tokens=tokens_removed,
            estimated=not self.tokenizer.is_native_bpe,
            raw_tokens=total_raw_tokens,
            optimized_tokens=total_optimized_tokens,
            reduction_ratio=reduction_ratio,
        )
        latencies["tier7_tokenization_ms"] = (time.perf_counter() - t2) * 1000.0

        # -------------------------------------------------------------
        # Phase 4: Tier 5 — Final Prompt & Provider Cache Compilation
        # -------------------------------------------------------------
        t3 = time.perf_counter()
        # Rule 4 Verification: Ensure Zone 1 remains identical byte-for-byte
        assert initial_envelope.zone1_static_prefix == immutable_zone1_prefix, (
            "Rule 4 Violation: Zone 1 Static Prefix mutated during Tier 6 processing!"
        )
        assert initial_envelope.static_prefix_hash == immutable_zone1_hash, (
            "Rule 4 Violation: Zone 1 Static Prefix Hash mutated!"
        )

        # Re-evaluate cache eligibility with post-optimization token counts
        policy = get_provider_cache_policy(model)
        is_eligible, miss_reason = evaluate_cache_eligibility(
            policy=policy,
            static_token_count=zone1_tokens,
        )

        final_envelope = PromptEnvelope(
            zone1_static_prefix=immutable_zone1_prefix,
            zone2_dynamic_suffix=effective_zone2,
            static_prefix_hash=immutable_zone1_hash,
            provider=policy.provider_name,
            model=model,
            cache_policy=policy,
            tenant_id=tenant_id,
            static_token_count=zone1_tokens,
            dynamic_token_count=zone2_optimized_tokens,
            total_token_count=total_optimized_tokens,
            version=version,
            is_cache_eligible=is_eligible,
            metadata={
                "miss_reason": miss_reason.value,
                "optimizations": optimized_context.transformations,
            },
        )
        latencies["tier5_final_ms"] = (time.perf_counter() - t3) * 1000.0

        # -------------------------------------------------------------
        # Phase 5: LLM Execution & Tier 7 Reconciliation
        # -------------------------------------------------------------
        provider_cache_metrics = ProviderCacheMetrics(
            eligible=is_eligible,
            requested=is_eligible and policy.explicit_breakpoint,
            hit=None,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            uncached_input_tokens=total_optimized_tokens,
            miss_reason=miss_reason.value,
        )
        cost_metrics: dict[str, Any] = {}
        response_text: str | None = None

        if call_llm:
            from app.core.llm_provider import (
                ProviderCacheTelemetry,
                UpstreamLLMResponse,
                call_upstream_llm_detailed,
            )

            t4 = time.perf_counter()
            upstream_res: UpstreamLLMResponse | None = None
            if llm_caller is not None:
                # Custom mock caller for testing
                res = await llm_caller(
                    prompt=effective_zone2,
                    compiled_prompt=final_envelope,
                    model=model,
                    tenant_id=tenant_id,
                )
                if isinstance(res, UpstreamLLMResponse):
                    upstream_res = res
                else:
                    upstream_res = UpstreamLLMResponse(
                        text=str(res),
                        model=model,
                        provider=policy.provider_name,
                        telemetry=ProviderCacheTelemetry(
                            is_cache_eligible=is_eligible,
                            uncached_input_tokens=total_optimized_tokens,
                            output_tokens=50,
                            provider=policy.provider_name,
                            model=model,
                        ),
                    )
            else:
                upstream_res = await call_upstream_llm_detailed(
                    prompt=effective_zone2,
                    tenant_id=tenant_id,
                    model=model,
                    compiled_prompt=final_envelope,
                )

            latencies["llm_call_ms"] = (time.perf_counter() - t4) * 1000.0

            if upstream_res:
                response_text = upstream_res.text
                telemetry = upstream_res.telemetry
                token_metrics.output_tokens = telemetry.output_tokens

                # Rule 1 Enforcement: HIT is derived ONLY from upstream usage telemetry
                cached_tokens = telemetry.cached_tokens
                cache_hit = telemetry.cache_hit
                provider_cache_metrics.hit = cache_hit
                provider_cache_metrics.cache_read_tokens = cached_tokens
                provider_cache_metrics.cache_creation_tokens = (
                    telemetry.cache_write_tokens
                )
                provider_cache_metrics.uncached_input_tokens = (
                    telemetry.uncached_input_tokens
                )
                if cache_hit:
                    provider_cache_metrics.miss_reason = CacheMissReason.NONE.value

                # FinOps Cost Reconciliation (Section 18)
                costs = calculate_provider_costs(
                    model=model,
                    uncached_input_tokens=telemetry.uncached_input_tokens,
                    cached_input_tokens=cached_tokens,
                    cache_write_tokens=telemetry.cache_write_tokens,
                    output_tokens=telemetry.output_tokens,
                )
                cost_metrics = costs.model_dump()

                # Token Accounting Ledger (Separating Layer A, Layer B, and Tier 6)
                TokenAccounting.record_transaction(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    model=model,
                    raw_prompt_tokens=total_raw_tokens,
                    pruned_prompt_tokens=total_optimized_tokens,
                    completion_tokens=telemetry.output_tokens,
                    cache_hit=False,  # Layer A was not a hit (network call was made)
                    cache_type="none",
                    provider_cache_hit=cache_hit,
                    provider_cached_tokens=cached_tokens,
                    provider_uncached_tokens=telemetry.uncached_input_tokens,
                    provider_cache_write_tokens=telemetry.cache_write_tokens,
                    provider_miss_reason=provider_cache_metrics.miss_reason,
                    provider_cost_savings_usd=costs.savings_usd,
                    provider_actual_cost_usd=costs.actual_cost_usd,
                    provider_name=policy.provider_name,
                )

        latencies["total_pipeline_ms"] = (time.perf_counter() - t_start) * 1000.0

        all_transformations = list(optimized_context.transformations)
        if final_envelope.is_cache_eligible:
            all_transformations.append("tier5_provider_cache_breakpoint_attached")

        return CrossTierResult(
            raw_context=initial_envelope.full_prompt,
            compiled_prompt=final_envelope,
            optimized_context=optimized_context,
            token_metrics=token_metrics,
            provider_cache_metrics=provider_cache_metrics,
            cost_metrics=cost_metrics,
            fallback_used=optimized_context.fallback_used,
            fallback_reason=optimized_context.fallback_reason,
            transformations=all_transformations,
            response_content=response_text,
            latency_metrics=latencies,
        )


_cross_tier_pipeline: CrossTierPipeline | None = None


def get_cross_tier_pipeline() -> CrossTierPipeline:
    """Singleton accessor for CrossTierPipeline."""
    global _cross_tier_pipeline
    if _cross_tier_pipeline is None:
        _cross_tier_pipeline = CrossTierPipeline()
    return _cross_tier_pipeline
