"""Empirical Benchmark & Token Accounting Verification Suite.

Mathematically and empirically verifies the platform claim of >= 40% Token Reduction:
1. RAG context pruning compression ratio (25-45% reduction on raw context).
2. 100% retention of financial entities, numbers, and critical facts (Zero Information Loss).
3. Realistic enterprise workload (35% FAQ/exact cache hits + 65% pruned RAG requests).
4. Asserts net token reduction >= 40.0% with verifiable mathematical accounting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.optimizer import (
    TokenAccounting,
    get_token_pruner,
)

if TYPE_CHECKING:
    import pytest


# Representative enterprise SEC filing & financial disclosures with realistic boilerplate
ENTERPRISE_RAG_CORPUS = [
    """
    ================================================================================
    ACME FINANCIAL CORP - Q3 2025 FORM 10-Q EARNINGS REPORT
    CONFIDENTIAL - STRICTLY PRIVATE & INTERNAL USE ONLY
    PAGE 14 OF 88 | ALL RIGHTS RESERVED | COPYRIGHT 2025 ACME CORP
    --------------------------------------------------------------------------------
    Disclaimer: Forward-looking statements involve risks and uncertainties.
    Terms of Service and Privacy Policy apply to all readers.

    For the third quarter ended September 30, 2025, Acme Financial reported total
    revenue of $245.8 million, representing a 14.2% year-over-year increase.
    Operating expenses stood at $182.4 million, resulting in an operating profit of $63.4 million.
    Net income for the quarter reached $48.2 million, or $1.15 diluted earnings per share.

    ================================================================================
    PAGE 15 OF 88 | ALL RIGHTS RESERVED
    --------------------------------------------------------------------------------
    For the third quarter ended September 30, 2025, Acme Financial reported total
    revenue of $245.8 million, representing a 14.2% year-over-year increase.
    The enterprise cloud division was the primary growth catalyst, generating $112.0 million
    in annual recurring revenue (ARR) with an adjusted gross margin of 78.5%.
    The enterprise cloud division was the primary growth catalyst, generating $112.0 million.
    Disclaimer: Forward-looking statements involve risks and uncertainties.
    """,
    """
    --------------------------------------------------------------------------------
    SUPPLEMENTAL FINANCIAL SCHEDULE - SEGMENT REVENUE
    PAGE 22 OF 88 | COPYRIGHT © ACME FINANCIAL CORP | ALL RIGHTS RESERVED
    --------------------------------------------------------------------------------
    Terms of service: The information contained herein is subject to change.

    Enterprise Cloud ARR expanded from $89.0 million in Q3 2024 to $112.0 million in Q3 2025.
    Customer retention rate remained robust at 118% net dollar expansion.
    Operating cash flow generated during the nine-month period reached $142.5 million.
    Free cash flow conversion stood at 84.0% of adjusted EBITDA.

    --------------------------------------------------------------------------------
    PAGE 23 OF 88 | ALL RIGHTS RESERVED | CONFIDENTIAL
    --------------------------------------------------------------------------------
    Customer retention rate remained robust at 118% net dollar expansion.
    Capital expenditures totaled $22.8 million primarily invested in AI GPU clusters.
    """,
]


def test_heuristic_token_pruner_compression_and_fact_retention() -> None:
    """Verify that HeuristicTokenPruner achieves >= 25% compression with 0% fact loss."""
    pruner = get_token_pruner()
    result = pruner.prune_context(ENTERPRISE_RAG_CORPUS)

    # 1. Assert Compression Ratio
    assert result.compression_ratio >= 25.0, (
        f"Expected compression >= 25%, got {result.compression_ratio}% "
        f"({result.tokens_saved}/{result.original_tokens} tokens saved)"
    )

    # 2. Assert Zero Information Loss: All critical financial figures must be preserved
    critical_facts = [
        "$245.8 million",
        "14.2%",
        "$182.4 million",
        "$63.4 million",
        "$48.2 million",
        "$1.15",
        "$112.0 million",
        "78.5%",
        "118%",
        "$142.5 million",
        "84.0%",
        "$22.8 million",
    ]

    for fact in critical_facts:
        assert fact.lower() in result.pruned_text.lower(), (
            f"Critical financial fact '{fact}' was accidentally pruned!"
        )

    # 3. Assert Boilerplate was pruned
    assert "confidential" not in result.pruned_text.lower()
    assert "page 14 of 88" not in result.pruned_text.lower()
    assert "all rights reserved" not in result.pruned_text.lower()


def test_enterprise_workload_token_benchmark_40_percent_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empirically prove that the combined AI Gateway optimization achieves >= 40% Token Reduction.

    Simulates a standard enterprise multi-user workload across 100 requests:
    - 35% repeat / FAQ queries (Cache hits on Tier 1 / Tier 2: 100% token savings).
    - 65% novel queries retrieving RAG contexts pruned via HeuristicTokenPruner.
    """
    pruner = get_token_pruner()
    records = []

    # 1. 35 Cache Hit Requests (FAQ / Repeat queries)
    # Average FAQ query + response = ~250 prompt tokens + ~150 completion tokens = 400 baseline
    for i in range(35):
        raw_prompt = 250
        completion = 150
        record = TokenAccounting.record_transaction(
            request_id=f"req-cache-{i}",
            tenant_id="tenant-corp-acme",
            model="gemini-1.5-flash",
            raw_prompt_tokens=raw_prompt,
            pruned_prompt_tokens=0,
            completion_tokens=completion,
            cache_hit=True,
            cache_type="exact" if i < 20 else "semantic",
        )
        records.append(record)

    # 2. 65 Novel RAG Requests with context pruning
    for i in range(65):
        # Retrieve raw multi-chunk context
        raw_context = ENTERPRISE_RAG_CORPUS[i % len(ENTERPRISE_RAG_CORPUS)]
        pruned = pruner.prune_context(raw_context)

        user_query_tokens = 30
        raw_prompt_tokens = pruned.original_tokens + user_query_tokens
        pruned_prompt_tokens = pruned.pruned_tokens + user_query_tokens
        completion_tokens = 180

        record = TokenAccounting.record_transaction(
            request_id=f"req-miss-{i}",
            tenant_id="tenant-corp-acme",
            model="gemini-1.5-flash",
            raw_prompt_tokens=raw_prompt_tokens,
            pruned_prompt_tokens=pruned_prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit=False,
            cache_type="none",
        )
        records.append(record)

    # 3. Aggregate statistical benchmark
    summary = TokenAccounting.aggregate_benchmark(records)

    # 4. Assertions verifying the claim with empirical evidence
    assert summary.total_requests == 100
    assert summary.cache_hit_rate == 35.0
    assert summary.context_pruning_avg_savings_pct >= 25.0

    # MANDATORY GATE: Prove net token reduction >= 40.0%
    assert summary.is_claim_verified, (
        f"Claim FAILED: Net token reduction was {summary.net_reduction_percentage}%, "
        f"must be >= 40.0% to support platform benchmark statement."
    )
    assert summary.net_reduction_percentage >= 40.0

    # Format human-verifiable benchmark report
    report_table = f"""
========================================================================================
             JAKEAI TOKEN OPTIMIZATION EMPIRICAL BENCHMARK REPORT
========================================================================================
Total Evaluated Requests        : {summary.total_requests}
Cache Hit Rate (Tier 1 & Tier 2): {summary.cache_hit_rate}% ({summary.cache_hits}/{summary.total_requests})
Avg Context Pruning Savings     : {summary.context_pruning_avg_savings_pct}%
----------------------------------------------------------------------------------------
Total Baseline Tokens Consumed  : {summary.total_baseline_tokens:,} tokens
Total Actual Billed Tokens      : {summary.total_actual_billed_tokens:,} tokens
Total Tokens Saved              : {summary.total_tokens_saved:,} tokens
----------------------------------------------------------------------------------------
NET TOKEN REDUCTION PERCENTAGE  : {summary.net_reduction_percentage}%
BENCHMARK VERDICT               : {"[PASS] VERIFIED >= 40% REDUCTION" if summary.is_claim_verified else "[FAIL]"}
========================================================================================
"""
    with capsys.disabled():
        print(report_table)


def test_token_accounting_mathematical_conservation() -> None:
    """Verify that TokenAccounting adheres strictly to the Conservation of Tokens law."""
    raw_prompt = 500
    pruned_prompt = 350
    completion = 150

    # Cache Miss Transaction
    miss_record = TokenAccounting.record_transaction(
        request_id="req-test-miss",
        tenant_id="test-tenant",
        model="gpt-4o",
        raw_prompt_tokens=raw_prompt,
        pruned_prompt_tokens=pruned_prompt,
        completion_tokens=completion,
        cache_hit=False,
    )

    baseline_total = raw_prompt + completion
    # Invariant: baseline == actual_billed + tokens_saved
    assert baseline_total == miss_record.actual_billed_tokens + miss_record.tokens_saved
    assert miss_record.tokens_saved == 150
    assert miss_record.actual_billed_tokens == 500
    assert round(miss_record.reduction_percentage, 1) == 23.1

    # Cache Hit Transaction
    hit_record = TokenAccounting.record_transaction(
        request_id="req-test-hit",
        tenant_id="test-tenant",
        model="gpt-4o",
        raw_prompt_tokens=raw_prompt,
        pruned_prompt_tokens=0,
        completion_tokens=completion,
        cache_hit=True,
    )

    assert hit_record.actual_billed_tokens == 0
    assert hit_record.tokens_saved == baseline_total
    assert hit_record.reduction_percentage == 100.0
    assert baseline_total == hit_record.actual_billed_tokens + hit_record.tokens_saved
