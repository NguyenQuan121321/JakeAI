"""Token Accounting Ledger and Telemetry for FinOps Optimization.

Implements rigorous token accounting across:
- Raw prompt tokens (unpruned baseline).
- Pruned prompt tokens (heuristic compression).
- Cache hit tokens saved (Tier 1 & Tier 2 Layer A response cache).
- Provider Prompt Caching (Tier 5 Layer B Anthropic/OpenAI KV prompt cache).
- Net token reduction percentage, dollar costs, and provider savings.
"""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.optimizer.provider_pricing import get_model_pricing


class TokenUsageRecord(BaseModel):
    """Accounting entry for a single inference request."""

    request_id: str
    tenant_id: str
    model: str
    raw_prompt_tokens: int
    pruned_prompt_tokens: int
    completion_tokens: int
    cache_hit: bool  # Layer A (JakeAI Redis exact / Qdrant semantic response cache)
    cache_type: str = "none"  # "none", "exact", "semantic"
    tokens_saved: int
    actual_billed_tokens: int
    reduction_percentage: float = Field(
        ...,
        description="Percentage of tokens saved: (tokens_saved / total_baseline) * 100",
    )
    timestamp: float = Field(default_factory=time.time)

    # Tier 5: Provider Prompt Caching (Layer B) Telemetry
    provider_cache_hit: bool = Field(
        default=False,
        description="Layer B: True strictly if upstream provider reported cached tokens > 0",
    )
    provider_cached_tokens: int = Field(
        default=0,
        description="Layer B: Input tokens served from upstream KV cache",
    )
    provider_uncached_tokens: int = Field(
        default=0,
        description="Layer B: Input tokens processed normally without cache hit",
    )
    provider_cache_write_tokens: int = Field(
        default=0,
        description="Layer B: Input tokens written to upstream cache (Anthropic cache_creation)",
    )
    provider_miss_reason: str = Field(
        default="none",
        description="Layer B: Attribution for upstream prompt cache miss",
    )
    provider_cost_savings_usd: float = Field(
        default=0.0,
        description="Layer B: Dollar amount saved from prompt cache discounts",
    )
    provider_actual_cost_usd: float = Field(
        default=0.0,
        description="Layer B: Incurred upstream cost after cache discounts",
    )
    provider_name: str = Field(default="generic")
    provider_cache_read_rate: float = Field(
        default=0.0,
        description="Rate or ratio applied to provider cached read tokens",
    )
    provider_cache_write_cost: float = Field(
        default=0.0,
        description="Upstream cost incurred for writing tokens to provider prompt cache",
    )
    effective_input_cost: float = Field(
        default=0.0,
        description="Effective total dollar cost incurred for input tokens after caching discounts and write fees",
    )
    is_estimate: bool = Field(
        default=False,
        description="True if token accounting values are local estimates rather than provider-reconciled metrics",
    )

    # Canonical Token Accounting Dimensions (TOK-02)
    raw_input_tokens: int = Field(
        default=0,
        description="Total model-visible input envelope tokens before optimization",
    )
    optimized_input_tokens: int = Field(
        default=0,
        description="Model-visible input tokens submitted to provider after optimization",
    )
    provider_cached_input_tokens: int = Field(
        default=0,
        description="Input tokens served from upstream provider KV prompt cache",
    )
    physical_tokens_pruned: int = Field(
        default=0,
        description="Physical tokens removed by local context optimization/pruning",
    )
    response_cache_avoided_tokens: int = Field(
        default=0,
        description="Tokens avoided because request was answered from response cache",
    )
    effective_billed_tokens: int = Field(
        default=0,
        description="Net tokens billed/counted against tenant quota for this request",
    )
    reconciled_with_provider: bool = Field(
        default=False,
        description="Whether usage metrics were reconciled with upstream provider telemetry",
    )

    @model_validator(mode="before")
    @classmethod
    def _sync_dimensions(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Raw input tokens synchronization
        if "raw_input_tokens" in data and "raw_prompt_tokens" not in data:
            data["raw_prompt_tokens"] = data["raw_input_tokens"]
        elif "raw_prompt_tokens" in data and "raw_input_tokens" not in data:
            data["raw_input_tokens"] = data["raw_prompt_tokens"]

        # Optimized input tokens synchronization
        if "optimized_input_tokens" in data and "pruned_prompt_tokens" not in data:
            data["pruned_prompt_tokens"] = data["optimized_input_tokens"]
        elif "pruned_prompt_tokens" in data and "optimized_input_tokens" not in data:
            data["optimized_input_tokens"] = data["pruned_prompt_tokens"]

        # Provider cached tokens synchronization
        if (
            "provider_cached_input_tokens" in data
            and "provider_cached_tokens" not in data
        ):
            data["provider_cached_tokens"] = data["provider_cached_input_tokens"]
        elif (
            "provider_cached_tokens" in data
            and "provider_cached_input_tokens" not in data
        ):
            data["provider_cached_input_tokens"] = data["provider_cached_tokens"]

        # Effective billed tokens synchronization
        if "effective_billed_tokens" in data and "actual_billed_tokens" not in data:
            data["actual_billed_tokens"] = data["effective_billed_tokens"]
        elif "actual_billed_tokens" in data and "effective_billed_tokens" not in data:
            data["effective_billed_tokens"] = data["actual_billed_tokens"]

        # Physical tokens pruned derivation
        if "physical_tokens_pruned" not in data:
            raw = data.get("raw_input_tokens", 0)
            opt = data.get("optimized_input_tokens", 0)
            data["physical_tokens_pruned"] = max(0, raw - opt)

        # Response cache avoided tokens derivation
        if "response_cache_avoided_tokens" not in data:
            if data.get("cache_hit"):
                data["response_cache_avoided_tokens"] = data.get(
                    "tokens_saved",
                    data.get("raw_input_tokens", 0) + data.get("completion_tokens", 0),
                )
            else:
                data["response_cache_avoided_tokens"] = 0

        return data


class TokenBenchmarkSummary(BaseModel):
    """Aggregated benchmark report proving empirical token savings."""

    total_requests: int
    cache_hits: int
    cache_hit_rate: float
    total_baseline_tokens: int
    total_actual_billed_tokens: int
    total_tokens_saved: int
    net_reduction_percentage: float
    context_pruning_avg_savings_pct: float
    is_claim_verified: bool = Field(
        ..., description="True if net_reduction_percentage >= 40.0%"
    )

    # Aggregated Tier 5 metrics
    provider_cache_hits: int = Field(default=0)
    provider_cache_hit_rate: float = Field(default=0.0)
    total_provider_cached_tokens: int = Field(default=0)
    total_provider_cost_savings_usd: float = Field(default=0.0)


class TokenAccounting:
    """Ledger computing and recording token optimization metrics."""

    @classmethod
    def calculate_envelope_tokens(
        cls,
        messages: list[Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        system_instruction: str | None = None,
        user_query: str | None = None,
        dynamic_context: str | None = None,
        rag_context: str | None = None,
        model: str = "default",
    ) -> int:
        """Calculate canonical model-visible input envelope tokens using BPETokenizer.

        Accounts for:
        - system instructions and developer turns
        - multi-turn conversation history
        - current user query
        - assistant turns, function/tool call schemas and payloads
        - tool execution result messages
        - tool definition schemas (functions)
        - retrieved RAG context passages
        - message framing and role delimiters
        """
        from app.optimizer.bpe_tokenizer import get_bpe_tokenizer

        tokenizer = get_bpe_tokenizer()

        def _count(text: str) -> int:
            if not text:
                return 0
            return tokenizer.count_tokens(text, model=model)

        total = 0
        counted_contents: set[int] = set()

        if messages:
            for msg in messages:
                role = getattr(msg, "role", "") or (
                    msg.get("role", "") if isinstance(msg, dict) else ""
                )
                if role:
                    total += _count(str(role))
                content = getattr(msg, "content", "") or (
                    msg.get("content", "") if isinstance(msg, dict) else ""
                )
                name = getattr(msg, "name", None) or (
                    msg.get("name") if isinstance(msg, dict) else None
                )
                tool_call_id = getattr(msg, "tool_call_id", None) or (
                    msg.get("tool_call_id") if isinstance(msg, dict) else None
                )
                tool_calls = getattr(msg, "tool_calls", None) or (
                    msg.get("tool_calls") if isinstance(msg, dict) else None
                )

                if content:
                    total += _count(str(content))
                    counted_contents.add(id(content))

                # Standard chat format framing (<|im_start|>{role}\n...<|im_end|>\n)
                total += 4

                if name:
                    total += _count(str(name)) + 1
                if tool_call_id:
                    total += _count(str(tool_call_id)) + 1
                if tool_calls:
                    total += _count(json.dumps(tool_calls, ensure_ascii=False))

        # Explicit system instruction if not already counted
        if system_instruction and id(system_instruction) not in counted_contents:
            has_sys = bool(
                messages
                and any(
                    (
                        getattr(m, "role", "")
                        or (m.get("role", "") if isinstance(m, dict) else "")
                    )
                    in ("system", "developer")
                    for m in messages
                )
            )
            if not has_sys:
                total += _count(system_instruction) + 4

        # Explicit user query if not already counted
        if user_query and id(user_query) not in counted_contents:
            has_user = bool(
                messages
                and any(
                    (
                        getattr(m, "content", "")
                        or (m.get("content", "") if isinstance(m, dict) else "")
                    )
                    == user_query
                    for m in messages
                )
            )
            if not has_user:
                total += _count(user_query) + 4

        # Explicit dynamic context if provided
        if dynamic_context and id(dynamic_context) not in counted_contents:
            total += _count(dynamic_context)

        # Explicit RAG context if provided
        if rag_context and id(rag_context) not in counted_contents:
            total += _count(rag_context)

        # Tool definition schemas passed in request
        if tools:
            total += _count(json.dumps(tools, ensure_ascii=False)) + 8

        has_input = bool(
            messages
            or system_instruction
            or user_query
            or dynamic_context
            or rag_context
            or tools
        )
        return max(1, total) if has_input else 0

    @classmethod
    def record_transaction(
        cls,
        request_id: str,
        tenant_id: str,
        model: str,
        raw_prompt_tokens: int = 0,
        pruned_prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: bool = False,
        cache_type: str = "none",
        provider_cache_hit: bool = False,
        provider_cached_tokens: int = 0,
        provider_uncached_tokens: int = 0,
        provider_cache_write_tokens: int = 0,
        provider_miss_reason: str = "none",
        provider_cost_savings_usd: float = 0.0,
        provider_actual_cost_usd: float = 0.0,
        provider_name: str = "generic",
        *,
        raw_input_tokens: int | None = None,
        optimized_input_tokens: int | None = None,
        provider_cached_input_tokens: int | None = None,
        physical_tokens_pruned: int | None = None,
        response_cache_avoided_tokens: int | None = None,
        effective_billed_tokens: int | None = None,
        provider_telemetry: Any | None = None,
        provider_cache_read_rate: float | None = None,
        provider_cache_write_cost: float | None = None,
        effective_input_cost: float | None = None,
        is_estimate: bool | None = None,
    ) -> TokenUsageRecord:
        """Calculate exact token accounting and savings for an inference call.

        Supports full TOK-02 canonical token accounting dimensions, provider discount pricing,
        and reconciliation with upstream provider telemetry.
        """
        raw_in = raw_input_tokens if raw_input_tokens is not None else raw_prompt_tokens
        opt_in = (
            optimized_input_tokens
            if optimized_input_tokens is not None
            else pruned_prompt_tokens
        )
        prov_cached = (
            provider_cached_input_tokens
            if provider_cached_input_tokens is not None
            else provider_cached_tokens
        )
        prov_uncached = provider_uncached_tokens
        prov_hit = provider_cache_hit
        prov_write = provider_cache_write_tokens
        prov_miss = provider_miss_reason
        prov_savings = provider_cost_savings_usd
        prov_cost = provider_actual_cost_usd
        prov_name = provider_name
        reconciled = False

        # Provider Usage Reconciliation (when provider reports telemetry)
        if provider_telemetry is not None:
            t_uncached = getattr(provider_telemetry, "uncached_input_tokens", 0)
            t_cached = getattr(provider_telemetry, "cached_tokens", 0)
            t_output = getattr(provider_telemetry, "output_tokens", 0)
            t_write = getattr(provider_telemetry, "cache_write_tokens", 0)
            t_hit = getattr(provider_telemetry, "cache_hit", False)
            t_miss = getattr(provider_telemetry, "miss_reason", "none")
            t_savings = getattr(provider_telemetry, "estimated_savings_usd", 0.0)
            t_cost = getattr(provider_telemetry, "actual_cost_usd", 0.0)
            t_prov = getattr(provider_telemetry, "provider", "")

            if t_uncached + t_cached > 0:
                reconciled = True
                prior_pruned = max(0, raw_in - opt_in)
                opt_in = t_uncached + t_cached
                raw_in = opt_in + prior_pruned
                prov_cached = t_cached
                prov_uncached = t_uncached
                prov_hit = t_hit
                prov_write = t_write
                prov_miss = t_miss
                prov_savings = t_savings
                prov_cost = t_cost
                if t_prov:
                    prov_name = t_prov

            if t_output > 0:
                completion_tokens = t_output

        pricing = get_model_pricing(model)
        read_ratio = (
            (pricing.cache_read_per_million / pricing.input_per_million)
            if pricing.input_per_million > 0
            else 1.0
        )
        resolved_read_rate = (
            provider_cache_read_rate
            if provider_cache_read_rate is not None
            else pricing.cache_read_per_million
        )

        # Provider cache write cost in USD
        if provider_cache_write_cost is not None:
            write_cost_usd = provider_cache_write_cost
        else:
            write_cost_usd = round(
                (prov_write * pricing.cache_write_per_million) / 1_000_000.0, 6
            )

        # Effective input cost in USD
        if effective_input_cost is not None:
            eff_in_cost_usd = effective_input_cost
        else:
            uncached_tokens_count = (
                max(0, opt_in - prov_cached) if prov_cached > 0 else opt_in
            )
            eff_in_cost_usd = round(
                (
                    (uncached_tokens_count * pricing.input_per_million)
                    + (prov_cached * pricing.cache_read_per_million)
                    + (prov_write * pricing.cache_write_per_million)
                )
                / 1_000_000.0,
                6,
            )

        is_est = (
            is_estimate if is_estimate is not None else not (reconciled or cache_hit)
        )

        baseline_total = max(1, raw_in + completion_tokens)

        if cache_hit:
            resp_avoided = (
                response_cache_avoided_tokens
                if response_cache_avoided_tokens is not None
                else baseline_total
            )
            phys_pruned = 0
            billed = 0
            saved = resp_avoided
            reduction_pct = 100.0
        else:
            resp_avoided = 0
            phys_pruned = (
                physical_tokens_pruned
                if physical_tokens_pruned is not None
                else max(0, raw_in - opt_in)
            )
            if effective_billed_tokens is not None:
                billed = effective_billed_tokens
            elif prov_cached > 0:
                # Do not treat provider cached tokens as 100% free.
                # Compute billed tokens using provider cache read discount ratio + write surcharges.
                uncached_in = max(0, opt_in - prov_cached)
                cached_equiv = round(prov_cached * read_ratio)
                write_equiv = 0
                if (
                    prov_write > 0
                    and pricing.cache_write_per_million > pricing.input_per_million
                    and pricing.input_per_million > 0
                ):
                    write_ratio = (
                        pricing.cache_write_per_million - pricing.input_per_million
                    ) / pricing.input_per_million
                    write_equiv = round(prov_write * write_ratio)
                billed = uncached_in + cached_equiv + write_equiv + completion_tokens
            else:
                billed = opt_in + completion_tokens
            saved = max(0, baseline_total - billed)
            reduction_pct = round((saved / baseline_total) * 100.0, 2)

        return TokenUsageRecord(
            request_id=request_id,
            tenant_id=tenant_id,
            model=model,
            raw_prompt_tokens=raw_in,
            pruned_prompt_tokens=opt_in,
            completion_tokens=completion_tokens,
            cache_hit=cache_hit,
            cache_type=cache_type,
            tokens_saved=saved,
            actual_billed_tokens=billed,
            reduction_percentage=reduction_pct,
            provider_cache_hit=prov_hit,
            provider_cached_tokens=prov_cached,
            provider_uncached_tokens=prov_uncached,
            provider_cache_write_tokens=prov_write,
            provider_miss_reason=prov_miss,
            provider_cost_savings_usd=prov_savings,
            provider_actual_cost_usd=prov_cost,
            provider_name=prov_name,
            provider_cache_read_rate=resolved_read_rate,
            provider_cache_write_cost=write_cost_usd,
            effective_input_cost=eff_in_cost_usd,
            is_estimate=is_est,
            raw_input_tokens=raw_in,
            optimized_input_tokens=opt_in,
            provider_cached_input_tokens=prov_cached,
            physical_tokens_pruned=phys_pruned,
            response_cache_avoided_tokens=resp_avoided,
            effective_billed_tokens=billed,
            reconciled_with_provider=reconciled,
        )

    @staticmethod
    def aggregate_benchmark(
        records: list[TokenUsageRecord],
    ) -> TokenBenchmarkSummary:
        """Compute statistical summary across an evaluation corpus."""
        if not records:
            return TokenBenchmarkSummary(
                total_requests=0,
                cache_hits=0,
                cache_hit_rate=0.0,
                total_baseline_tokens=0,
                total_actual_billed_tokens=0,
                total_tokens_saved=0,
                net_reduction_percentage=0.0,
                context_pruning_avg_savings_pct=0.0,
                is_claim_verified=False,
            )

        total_reqs = len(records)
        cache_hits = sum(1 for r in records if r.cache_hit)
        cache_hit_rate = round((cache_hits / total_reqs) * 100.0, 2)

        total_baseline = sum(r.raw_prompt_tokens + r.completion_tokens for r in records)
        total_billed = sum(r.actual_billed_tokens for r in records)
        total_saved = sum(r.tokens_saved for r in records)

        net_reduction_pct = (
            round((total_saved / total_baseline) * 100.0, 2)
            if total_baseline > 0
            else 0.0
        )

        # Context pruning stats on cache-miss requests
        miss_records = [
            r for r in records if not r.cache_hit and r.raw_prompt_tokens > 0
        ]
        if miss_records:
            prune_savings = [
                ((r.raw_prompt_tokens - r.pruned_prompt_tokens) / r.raw_prompt_tokens)
                * 100.0
                for r in miss_records
            ]
            avg_prune_savings = round(sum(prune_savings) / len(prune_savings), 2)
        else:
            avg_prune_savings = 0.0

        # Tier 5 Provider Cache aggregations
        prov_hits = sum(1 for r in records if r.provider_cache_hit)
        prov_hit_rate = round((prov_hits / total_reqs) * 100.0, 2)
        total_prov_cached = sum(r.provider_cached_tokens for r in records)
        total_prov_savings = round(sum(r.provider_cost_savings_usd for r in records), 4)

        is_verified = net_reduction_pct >= 40.0

        return TokenBenchmarkSummary(
            total_requests=total_reqs,
            cache_hits=cache_hits,
            cache_hit_rate=cache_hit_rate,
            total_baseline_tokens=total_baseline,
            total_actual_billed_tokens=total_billed,
            total_tokens_saved=total_saved,
            net_reduction_percentage=net_reduction_pct,
            context_pruning_avg_savings_pct=avg_prune_savings,
            is_claim_verified=is_verified,
            provider_cache_hits=prov_hits,
            provider_cache_hit_rate=prov_hit_rate,
            total_provider_cached_tokens=total_prov_cached,
            total_provider_cost_savings_usd=total_prov_savings,
        )
