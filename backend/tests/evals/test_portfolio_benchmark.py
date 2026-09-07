"""Phase 00 Portfolio AI Evaluation Benchmark & Regression Test Suite.

Verifies all requirements of 00_CICD_BASELINE.md:
1. Multi-workload execution across 7 standard workloads:
   - Simple chat (no degradation, latency check)
   - Long conversational context (history compaction & redundancy removal)
   - RAG (context pruning & citation preservation)
   - Financial reasoning (100% numerical entity and formula preservation)
   - Coding context (AST syntax validity, security check, symbol retention)
   - Structured JSON (parse valid, schema retained)
   - Multilingual (Vietnamese Unicode diacritic retention)
2. Mathematical conservation of tokens and cost measurement.
3. Layered Quality Oracle scoring (zero fact loss, max regression <= 0.05).
4. Portfolio net token reduction gate >= 40.0%.
5. Machine-readable JSON artifact generation in benchmark-results/.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from app.evals.benchmark_runner import BenchmarkRunner

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_phase_00_portfolio_benchmark_all_workloads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run full Phase 00 multi-workload benchmark and assert all gates pass."""
    output_dir = tmp_path / "benchmark-results"
    runner = BenchmarkRunner(output_dir=output_dir)

    (
        summary,
        records,
        quality_results,
        cost_measurements,
    ) = await runner.run_portfolio_benchmark(cache_hit_ratio=0.35)
    artifacts = runner.save_artifacts(
        summary, records, quality_results, cost_measurements
    )

    # 1. Assert all 7 minimum workloads are represented and executed
    evaluated_types = {r.workload_type for r in records}
    expected_types = {
        "simple_chat",
        "long_conversation",
        "rag",
        "financial_reasoning",
        "coding_context",
        "structured_json",
        "multilingual",
    }
    assert expected_types.issubset(evaluated_types), (
        f"Missing required workloads: {expected_types - evaluated_types}"
    )

    # 2. Assert 100% workload pass rate (Zero critical fact loss, valid syntax)
    assert summary.total_workloads >= 7
    assert summary.total_passed == summary.total_workloads, (
        f"Workloads failed: {[r.workload_id for r in records if not r.passed]}"
    )
    assert summary.pass_rate_pct == 100.0

    # 3. Assert Quality Oracle: Zero fact loss and max regression <= 0.05
    assert summary.avg_quality_score >= 0.95, (
        f"Avg quality {summary.avg_quality_score} below 0.95"
    )
    assert summary.max_quality_regression <= 0.05, (
        f"Max quality regression {summary.max_quality_regression} exceeded threshold 0.05"
    )
    for q in quality_results:
        assert len(q.missing_facts) == 0, (
            f"Critical facts lost in {q.workload_id}: {q.missing_facts}"
        )
        assert not q.leakage_detected, f"Security leakage detected in {q.workload_id}"

    # 4. Mandatory Portfolio Gate: Net Token Reduction >= 40.0%
    assert summary.is_40pct_claim_verified is True, (
        f"Portfolio reduction was {summary.portfolio_token_reduction_pct}%, must be >= 40.0%"
    )
    assert summary.portfolio_token_reduction_pct >= 40.0

    # 5. Assert FinOps Cost Savings are positive and mathematically consistent
    assert summary.total_cost_saved_usd > 0.0
    assert summary.cost_savings_pct > 0.0
    for c in cost_measurements:
        assert c.baseline_cost_usd >= c.estimated_savings_usd
        assert c.savings_percentage >= 0.0

    # 6. Verify Machine-Readable Artifacts exist and are valid JSON
    for name, path in artifacts.items():
        assert path.exists(), f"Artifact {name} ({path}) was not created"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data is not None, f"Artifact {name} contains null/invalid JSON"

    # Print human-readable report for terminal verification
    report = runner.format_human_readable_report(summary, records)
    with capsys.disabled():
        print(report)


@pytest.mark.asyncio
async def test_quality_oracle_regression_detection() -> None:
    """Verify QualityOracle strictly detects fact loss, leakage, and syntax corruption."""
    from app.evals.quality_oracle import QualityOracle

    # Case with critical fact missing
    case = {
        "workload_id": "test_fact_check",
        "expected_facts": ["$500M", "EBITDA"],
        "expected_citations": ["[SEC-1]"],
    }
    # Candidate text missing EBITDA and [SEC-1]
    candidate = "The company reported $500M in revenue."
    result = QualityOracle.evaluate(case, candidate, baseline_score=1.0)

    assert result.passed is False
    assert "EBITDA" in result.missing_facts
    assert "[SEC-1]" in result.missing_citations
    assert result.regression_vs_baseline > 0.10

    # Case with system prompt leakage
    leakage_candidate = "Here is the response. You are a senior principal developer and system prompt is exposed."
    leakage_result = QualityOracle.evaluate(case, leakage_candidate)
    assert leakage_result.leakage_detected is True
    assert leakage_result.passed is False
    assert leakage_result.overall_score == 0.0
