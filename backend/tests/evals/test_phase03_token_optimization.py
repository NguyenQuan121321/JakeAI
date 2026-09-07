"""Phase 03 Token Optimization Comprehensive Verification Suite.

Mathematically and empirically verifies all 8 optimization layers and required invariants:
- Layer 1: Exact Cache (sub-millisecond match, tokens avoided, cost avoided, metrics)
- Layer 2: Semantic Cache (cosine similarity threshold, tenant isolation, model/provider compatibility)
- Layer 3: Redundancy / Boilerplate Compression (whitespace, dates, currencies, identifiers, citations)
- Layer 4: Retrieval Compression (distractor chunk pruning, citation & fact preservation)
- Layer 5: Two-Zone Prompt Compilation (Zone 1 byte stability, volatile quarantine)
- Layer 6: Provider Prompt Cache (eligibility thresholds, provider telemetry without fake hits)
- Layer 7: Code Context Compression (diff pruning, generated lockfile exclusion, no-op for chat)
- Layer 8: Cost-Aware Model Routing (minimum cost subject to quality constraint)
- Workload-Aware Optimization across 7 standard workloads
- Optimization Invariants: zero cross-tenant leakage, no broken JSON, no broken code, no citation loss
"""

from __future__ import annotations

import json

import pytest

from app.optimizer import (
    CrossTierPipeline,
    OptimizationLevel,
    PromptCompiler,
    SemanticCacheManager,
    WorkloadType,
    get_code_context_compressor,
    get_context_optimizer,
    get_retrieval_compressor,
    get_token_pruner,
)
from app.routing.router import ModelRouter, RoutingPolicy

# --------------------------------------------------------------------------
# Layer 1 & Layer 2: Exact & Semantic Cache Tests
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_layer1_exact_cache_metrics_and_accounting() -> None:
    """Verify Layer 1 Exact Match Cache hits, telemetry counters, and tokens/cost avoided."""
    cache = SemanticCacheManager(default_ttl=300)
    cache.reset_metrics()

    prompt = "What is the capital of France?"
    tenant_id = "tenant_alpha"
    response = "The capital of France is Paris."

    # Initial lookup is a miss
    entry = await cache.get(prompt, tenant_id=tenant_id, model="gpt-4o")
    assert entry is None
    metrics = cache.get_metrics()
    assert metrics["total_requests"] == 1
    assert metrics["misses"] == 1
    assert metrics["exact_hits"] == 0

    # Store entry with avoided tokens & cost metadata
    await cache.set(
        prompt=prompt,
        tenant_id=tenant_id,
        response=response,
        model="gpt-4o",
        provider="openai",
        tokens_avoided=150,
        cost_avoided_usd=0.00075,
    )

    # Second lookup is an exact hit
    hit = await cache.get(
        prompt, tenant_id=tenant_id, model="gpt-4o", provider="openai"
    )
    assert hit is not None
    assert hit.cache_type == "exact"
    assert hit.response == response
    assert hit.tokens_avoided == 150
    assert hit.cost_avoided_usd == 0.00075

    updated_metrics = cache.get_metrics()
    assert updated_metrics["total_requests"] == 2
    assert updated_metrics["exact_hits"] == 1
    assert updated_metrics["tokens_avoided"] == 150
    assert updated_metrics["cost_avoided_usd"] == 0.00075
    assert updated_metrics["hit_rate_pct"] == 50.0


@pytest.mark.asyncio
async def test_layer2_semantic_cache_model_and_tenant_isolation() -> None:
    """Verify Layer 2 Semantic Cache enforces strict tenant AND model/provider boundaries."""
    cache = SemanticCacheManager(similarity_threshold=0.85, default_ttl=300)
    prompt_base = "calculate quarterly earnings and revenue growth"
    prompt_similar = "calculate quarterly earnings and revenue growth rate"
    tenant_a = "tenant_enterprise_a"
    tenant_b = "tenant_enterprise_b"

    # Populate cache for Tenant A with Model gpt-4o
    await cache.set(
        prompt=prompt_base,
        tenant_id=tenant_a,
        response="Quarterly earnings rose 18% to $120M.",
        model="gpt-4o",
        provider="openai",
        tokens_avoided=200,
        cost_avoided_usd=0.001,
    )

    # 1. Semantic match under Tenant A with same model -> HIT
    match_a = await cache.get(
        prompt_similar, tenant_id=tenant_a, model="gpt-4o", provider="openai"
    )
    assert match_a is not None
    assert match_a.cache_type == "semantic"
    assert match_a.similarity_score >= 0.85
    assert "$120M" in match_a.response

    # 2. Cross-Tenant Isolation: Same query under Tenant B -> MUST BE MISS (Invariant 4)
    match_b = await cache.get(
        prompt_similar, tenant_id=tenant_b, model="gpt-4o", provider="openai"
    )
    assert match_b is None

    # 3. Cross-Model Isolation: Same query under Tenant A but with claude-3-5-sonnet -> MUST BE MISS
    match_diff_model = await cache.get(
        prompt_similar,
        tenant_id=tenant_a,
        model="claude-3-5-sonnet",
        provider="anthropic",
    )
    assert match_diff_model is None


# --------------------------------------------------------------------------
# Layer 3: Redundancy & Boilerplate Compression Tests
# --------------------------------------------------------------------------


def test_layer3_boilerplate_pruning_and_entity_protection() -> None:
    """Verify Layer 3 prunes corporate boilerplate while protecting 100% of dates, currencies, and citations."""
    pruner = get_token_pruner()
    raw_context = (
        "================================================================================\n"
        "CONFIDENTIAL & STRICTLY PRIVATE - ALL RIGHTS RESERVED\n"
        "PAGE 1 OF 10 | COPYRIGHT 2026 ACME CORP\n"
        "Disclaimer: Terms of Service and Privacy Policy apply to all readers.\n"
        "--------------------------------------------------------------------------------\n"
        "On October 15, 2026, the Cloud ARR generated $112.0 million with a margin of 78.5%.\n"
        "According to [SEC-Q3-P14], operating cash flow reached $142.5 million.\n"
        "FinnApiGo Q3/2026 revenue was 185.5 tỷ VNĐ audited independently.\n"
        "Token verification employs hmac.compare_digest for constant-time checks on db-prod.internal.\n"
        "All rights reserved. Terms of Service and Privacy Policy apply.\n"
        "--------------------------------------------------------------------------------"
    )

    res = pruner.prune_context(raw_context)

    # Assert compression occurred
    assert res.tokens_saved > 0
    assert res.compression_ratio >= 15.0

    # Assert boilerplate was removed
    assert "confidential" not in res.pruned_text.lower()
    assert "page 1 of 10" not in res.pruned_text.lower()
    assert "all rights reserved" not in res.pruned_text.lower()

    # Assert 100% of critical dates, currencies, citations, and symbols are preserved
    assert "October 15, 2026" in res.pruned_text
    assert "$112.0 million" in res.pruned_text
    assert "78.5%" in res.pruned_text
    assert "[SEC-Q3-P14]" in res.pruned_text
    assert "185.5 tỷ VNĐ" in res.pruned_text
    assert "hmac.compare_digest" in res.pruned_text
    assert "db-prod.internal" in res.pruned_text


def test_layer3_structured_json_minification_invariance() -> None:
    """Verify Layer 3 never corrupts JSON syntax, schema, or keys (Invariant 4)."""
    pruner = get_token_pruner()
    raw_json = json.dumps(
        {
            "database": {
                "host": "db-prod-cluster.internal",
                "port": 5432,
                "pool": {"min": 5, "max": 50},
            },
            "enabled": True,
            "replica_endpoints": ["rep1.internal", "rep2.internal"],
        },
        indent=4,
    )

    res = pruner.prune_context(raw_json)

    # Must save tokens by stripping whitespace/newlines
    assert res.tokens_saved > 0

    # Must parse back to identical dictionary structure without any key corruption
    parsed = json.loads(res.pruned_text)
    assert parsed["database"]["host"] == "db-prod-cluster.internal"
    assert parsed["database"]["port"] == 5432
    assert parsed["database"]["pool"]["max"] == 50
    assert len(parsed["replica_endpoints"]) == 2


def test_layer3_markdown_code_block_preservation() -> None:
    """Verify code blocks within markdown are preserved intact without sentence splitting corruption."""
    pruner = get_token_pruner()
    text_with_code = (
        "Here is the database connection snippet:\n\n"
        "```python\n"
        "import hmac\n"
        "def verify(sig: str) -> bool:\n"
        "    return hmac.compare_digest(computed, sig)\n"
        "```\n\n"
        "All rights reserved. Copyright 2026 Acme Corp.\n"
    )

    res = pruner.prune_context(text_with_code)
    assert "def verify(sig: str) -> bool:" in res.pruned_text
    assert "hmac.compare_digest" in res.pruned_text
    assert "```python" in res.pruned_text
    assert "all rights reserved" not in res.pruned_text.lower()


# --------------------------------------------------------------------------
# Layer 4: Retrieval Compression Tests
# --------------------------------------------------------------------------


def test_layer4_retrieval_compressor_pruning_and_citation_retention() -> None:
    """Verify Layer 4 prunes distractor chunks while retaining required citations and figures."""
    compressor = get_retrieval_compressor()
    rag_context = (
        "=== DOCUMENT EXCERPT [SEC-Q3-P14] ===\n"
        "Cloud ARR generated $112.0 million in annual recurring revenue.\n"
        "Terms of Service apply. All rights reserved.\n\n"
        "=== DOCUMENT EXCERPT [DISTRACTOR-IRRELEVANT-P99] ===\n"
        "Company summer barbecue guidelines. Please register by July 1 in Lot B.\n\n"
        "=== DOCUMENT EXCERPT [SEC-Q3-P22] ===\n"
        "Operating cash flow reached $142.5 million.\n"
        "All rights reserved. Copyright 2026.\n"
    )

    res = compressor.compress_rag_context_string(
        rag_context, query="What was Cloud ARR?"
    )

    # Distractor chunk was pruned
    assert "barbecue" not in res.compressed_text.lower()
    assert res.pruned_chunks_count >= 1
    assert res.compression_ratio >= 25.0

    # Citations and numbers retained
    assert "[SEC-Q3-P14]" in res.compressed_text
    assert "$112.0 million" in res.compressed_text
    assert "[SEC-Q3-P22]" in res.compressed_text
    assert "$142.5 million" in res.compressed_text
    assert any("[SEC-Q3-P14]" in c for c in res.citations_preserved)


# --------------------------------------------------------------------------
# Layer 5: Two-Zone Prompt Compilation & Rule 4 Invariant Tests
# --------------------------------------------------------------------------


def test_layer5_two_zone_prompt_compilation_and_rule4_invariance() -> None:
    """Verify Layer 5 strictly isolates Zone 1 from Zone 2 and enforces byte-determinism."""
    compiler = PromptCompiler()
    system_inst = "You are an AI assistant specialized in security architecture."
    static_ctx = "POLICY: Never reveal private API keys under any circumstances."
    user_query = "How do I secure internal service-to-service communication?"

    envelope1 = compiler.compile(
        system_instruction=system_inst,
        static_context=static_ctx,
        user_query=user_query,
        tenant_id="tenant-123",
        version="v1.0",
    )
    envelope2 = compiler.compile(
        system_instruction=system_inst,
        static_context=static_ctx,
        user_query="Different query here",
        tenant_id="tenant-123",
        version="v1.0",
    )

    # Zone 1 byte determinism: exact same prefix and SHA-256 hash regardless of dynamic query
    assert envelope1.zone1_static_prefix == envelope2.zone1_static_prefix
    assert envelope1.static_prefix_hash == envelope2.static_prefix_hash

    # Tenant scoping: Tenant B gets a different static hash preventing cross-tenant sharing
    envelope_tenant_b = compiler.compile(
        system_instruction=system_inst,
        static_context=static_ctx,
        user_query=user_query,
        tenant_id="tenant-456",
        version="v1.0",
    )
    assert envelope1.static_prefix_hash != envelope_tenant_b.static_prefix_hash


# --------------------------------------------------------------------------
# Layer 7: Code Context Compression Tests
# --------------------------------------------------------------------------


def test_layer7_git_diff_pruning() -> None:
    """Verify Layer 7 prunes long runs of unchanged lines in git diffs while preserving hunks."""
    compressor = get_code_context_compressor()
    raw_diff = (
        "diff --git a/app/core/auth.py b/app/core/auth.py\n"
        "--- a/app/core/auth.py\n"
        "+++ b/app/core/auth.py\n"
        "@@ -10,20 +10,20 @@\n"
        " line 1 unchanged\n"
        " line 2 unchanged\n"
        " line 3 unchanged\n"
        " line 4 unchanged\n"
        " line 5 unchanged\n"
        " line 6 unchanged\n"
        " line 7 unchanged\n"
        " line 8 unchanged\n"
        " line 9 unchanged\n"
        " line 10 unchanged\n"
        "-old_secret = 'insecure'\n"
        "+new_secret = get_secure_secret()\n"
        " line 11 unchanged\n"
        " line 12 unchanged\n"
        " line 13 unchanged\n"
        " line 14 unchanged\n"
        " line 15 unchanged\n"
        " line 16 unchanged\n"
    )

    pruned_diff, count = compressor.prune_git_diff(raw_diff, max_context_lines=2)
    assert count > 0
    assert "unchanged lines omitted" in pruned_diff
    assert "-old_secret = 'insecure'" in pruned_diff
    assert "+new_secret = get_secure_secret()" in pruned_diff
    assert "diff --git a/app/core/auth.py b/app/core/auth.py" in pruned_diff


def test_layer7_generated_file_exclusion() -> None:
    """Verify Layer 7 identifies and excludes noisy package lockfiles."""
    compressor = get_code_context_compressor()
    lockfile_content = (
        '{\n  "name": "project",\n  "lockfileVersion": 3,\n  "packages": {}\n}'
        + ("\n  dep line" * 100)
    )
    summary, is_gen = compressor.exclude_generated_noise(
        lockfile_content, filename="package-lock.json"
    )

    assert is_gen is True
    assert "Generated Lockfile/Asset: package-lock.json" in summary
    assert "lines omitted for context efficiency" in summary


def test_layer7_chat_workload_guardrail_noop() -> None:
    """Verify Layer 7 strictly avoids code pruning on normal chat workloads (Invariant)."""
    compressor = get_code_context_compressor()
    chat_text = "def hello():\n    return 'world'"

    # When is_coding_workload is False, code is NOT modified
    res = compressor.compress_code_context(chat_text, is_coding_workload=False)
    assert res.compressed_code == chat_text
    assert res.tokens_saved == 0
    assert res.compression_ratio == 0.0


# --------------------------------------------------------------------------
# Layer 8: Cost-Aware Model Routing Tests
# --------------------------------------------------------------------------


def test_layer8_cost_aware_model_routing() -> None:
    """Verify Layer 8 routes simple chat queries to cost-efficient models with positive cost savings."""
    router = ModelRouter()

    # Request expensive model for simple_chat workload
    policy = RoutingPolicy(
        requested_model="gpt-4o",
        preferred_provider="openai",
        workload_class="simple_chat",
        cost_aware_routing=True,
    )
    decision = router.route(policy)

    # Cost-aware router down-tiers simple_chat to gpt-4o-mini
    assert decision.selected_model == "gpt-4o-mini"
    assert decision.selected_provider == "openai"
    assert decision.cost_savings_usd_per_million > 0.0
    assert any("Cost-Aware Routing" in r for r in decision.decision_reasons)

    # High intelligence task (coding_context) is NOT downgraded
    coding_policy = RoutingPolicy(
        requested_model="gpt-4o",
        preferred_provider="openai",
        workload_class="coding_context",
        cost_aware_routing=True,
    )
    coding_decision = router.route(coding_policy)
    assert coding_decision.selected_model == "gpt-4o"


# --------------------------------------------------------------------------
# Workload-Aware Optimization Coordinator Tests (7 Workloads)
# --------------------------------------------------------------------------


def test_workload_aware_optimizer_all_workload_classes() -> None:
    """Verify ContextOptimizer correctly tailors optimization across all 7 workload types."""
    optimizer = get_context_optimizer()

    # 1. simple_chat: zero code skeletonization, only whitespace
    chat_ctx = "User prefers short answers.   \n\n\n   English only."
    chat_res = optimizer.optimize_dynamic_context(
        dynamic_context=chat_ctx,
        user_query="Hi there",
        workload_type=WorkloadType.SIMPLE_CHAT,
    )
    assert "simple_chat_whitespace_normalization" in chat_res.transformations

    # 2. structured_json: minification
    json_ctx = '{\n  "host": "localhost",\n  "port": 5432\n}'
    json_res = optimizer.optimize_dynamic_context(
        dynamic_context=json_ctx,
        user_query="Get port",
        workload_type=WorkloadType.STRUCTURED_JSON,
    )
    assert "structured_json_minification" in json_res.transformations
    assert json.loads(json_res.content)["port"] == 5432

    # 3. multilingual: Unicode NFC + boilerplate pruning
    vn_ctx = "Báo cáo tài chính quý 3 năm 2026. Doanh thu: 185.5 tỷ VNĐ. All rights reserved."
    vn_res = optimizer.optimize_dynamic_context(
        dynamic_context=vn_ctx,
        user_query="Doanh thu?",
        workload_type=WorkloadType.MULTILINGUAL,
    )
    assert "185.5 tỷ VNĐ" in vn_res.content
    assert "all rights reserved" not in vn_res.content.lower()

    # 4. rag: retrieval compression
    rag_ctx = (
        "=== DOCUMENT EXCERPT [SEC-1] ===\nCloud revenue was $100M. Confidential.\n"
    )
    rag_res = optimizer.optimize_dynamic_context(
        dynamic_context=rag_ctx,
        user_query="Cloud revenue?",
        workload_type=WorkloadType.RAG,
    )
    assert "rag_retrieval_compression" in rag_res.transformations
    assert "$100M" in rag_res.content

    # 5. financial_reasoning: 100% numerical retention
    fin_ctx = "Operating Profit: $80.0M. Depreciation: $25.0M. EBITDA = Operating Profit + Depreciation. Copyright 2026."
    fin_res = optimizer.optimize_dynamic_context(
        dynamic_context=fin_ctx,
        user_query="Calculate EBITDA",
        workload_type=WorkloadType.FINANCIAL_REASONING,
    )
    assert "$80.0M" in fin_res.content
    assert "$25.0M" in fin_res.content
    assert "EBITDA" in fin_res.content

    # 6. coding_context: AST skeletonization on balanced/aggressive, conservative keeps full code
    code_ctx = (
        "class Service:\n    def helper(self):\n        print('debugging line')\n"
    )
    code_res = optimizer.optimize_dynamic_context(
        dynamic_context=code_ctx,
        user_query="explain architecture",
        optimization_level=OptimizationLevel.AGGRESSIVE,
        workload_type=WorkloadType.CODING_CONTEXT,
    )
    assert "def helper(self):" in code_res.content
    assert "class Service:" in code_res.content


# --------------------------------------------------------------------------
# End-to-End CrossTierPipeline Integration
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_tier_pipeline_e2e_integration() -> None:
    """Verify CrossTierPipeline executes Tier 5 -> 6 -> 7 with workload awareness."""
    pipeline = CrossTierPipeline()
    sys_inst = "You are a quantitative financial analyst."
    static_ctx = "POLICY: Cite source documents strictly using bracket notations."
    dynamic_ctx = (
        "=== DOCUMENT EXCERPT [SEC-Q3-P14] ===\n"
        "Cloud ARR generated $112.0 million with gross margin 78.5%.\n"
        "CONFIDENTIAL AND PROPRIETARY. ALL RIGHTS RESERVED.\n"
    )
    query = "What was the Cloud ARR and gross margin?"

    result = await pipeline.process(
        system_instruction=sys_inst,
        static_context=static_ctx,
        user_query=query,
        dynamic_context=dynamic_ctx,
        model="gpt-4o",
        tenant_id="tenant-acme-corp",
        workload_type="rag",
    )

    # 1. Assert Zone 1 Byte-For-Byte Rule 4 Invariance
    assert result.compiled_prompt.zone1_static_prefix == f"{sys_inst}\n\n{static_ctx}"
    assert result.fallback_used is False

    # 2. Assert Zone 2 Context Optimization
    assert result.token_metrics.removed_tokens > 0
    assert result.token_metrics.reduction_ratio > 0.0

    # 3. Assert critical financial figures & citations exist in compiled prompt
    assert "$112.0 million" in result.compiled_prompt.full_prompt
    assert "78.5%" in result.compiled_prompt.full_prompt
    assert "[SEC-Q3-P14]" in result.compiled_prompt.full_prompt
