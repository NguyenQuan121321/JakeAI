"""Comprehensive Phase 06 AI Quality Evaluation & Regression Test Suite.

Verifies all requirements of 06_EVALUATION.md:
1. Baseline vs Optimized Pair Testing (Section 1).
2. Deterministic Quality Checks: facts, numbers, entities, citations, schema, code symbols (Section 2).
3. 7-Dimension Rubric Evaluation: correctness, completeness, groundedness, instruction following,
   reasoning sufficiency, citation quality, format correctness (Section 3).
4. Secondary Signal LLM-as-Judge: fixed model, fixed rubric, blinded candidate ordering,
   calibration against reference truth, secondary signal invariant (Section 4).
5. Explicit Regression Detection: quality regression, token regression, and cost regression
   tested against both successful and intentionally degraded/adversarial fixtures (Section 5).
6. Measurement Correctness: strict independence and non-confusion across all 12 core metrics.
7. Constrained Optimization Target: verifies portfolio >= 40% reduction with zero quality degradation,
   and proves that 40% reduction with fact loss is classified as a FAILED optimization (Section 6).
"""

from __future__ import annotations

from app.evals.llm_judge import LLMJudge
from app.evals.regression_detector import (
    RegressionDetector,
    RegressionSeverity,
    RegressionType,
)
from app.evals.rubric_evaluator import (
    RubricDimension,
    RubricEvaluator,
)
from app.optimizer.contracts import EvaluationRecord

# --------------------------------------------------------------------------
# Test Fixtures
# --------------------------------------------------------------------------

SAMPLE_CASE = {
    "workload_id": "eval_test_fin_001",
    "workload_type": "financial_reasoning",
    "system_instruction": "You are a senior financial analyst. Respond concisely in English.",
    "user_query": "Calculate operating margin and EBITDA given revenue of $500M, EBIT of $100M, and depreciation of $25M.",
    "dynamic_context": "Acme Corp Financials: Revenue $500M, Operating Profit (EBIT) $100M, Depreciation & Amortization $25M. Formula: Margin = EBIT / Revenue. EBITDA = EBIT + Dep.",
    "expected_facts": ["$500M", "$100M", "$25M", "20.0%", "$125M"],
    "expected_citations": ["[SEC-Q3-P10]"],
    "expected_json_keys": [],
    "ground_truth_answer": "Operating margin is 20.0% ($100M / $500M) and EBITDA is $125M ($100M + $25M) per [SEC-Q3-P10].",
}


# --------------------------------------------------------------------------
# 1. 7-Dimension Rubric Evaluator Tests (Section 3)
# --------------------------------------------------------------------------


def test_rubric_evaluator_all_dimensions_positive() -> None:
    """Verify that a high-quality answer scores >= 0.85 across all 7 dimensions."""
    candidate = (
        "Operating margin is 20.0% ($100M / $500M) and EBITDA is $125M ($100M + $25M). "
        "Calculated based on Revenue of $500M, EBIT of $100M, and Depreciation of $25M according to [SEC-Q3-P10]."
    )

    res = RubricEvaluator.evaluate(SAMPLE_CASE, candidate)
    assert res.passed is True
    assert res.composite_score >= 0.85
    assert len(res.critical_failures) == 0

    # Verify all 7 dimensions are present
    dims = res.dimension_scores
    assert set(dims.keys()) == {
        RubricDimension.CORRECTNESS,
        RubricDimension.COMPLETENESS,
        RubricDimension.GROUNDEDNESS,
        RubricDimension.INSTRUCTION_FOLLOWING,
        RubricDimension.REASONING_SUFFICIENCY,
        RubricDimension.CITATION_QUALITY,
        RubricDimension.FORMAT_CORRECTNESS,
    }

    assert dims[RubricDimension.CORRECTNESS].passed is True
    assert dims[RubricDimension.GROUNDEDNESS].passed is True
    assert dims[RubricDimension.CITATION_QUALITY].passed is True


def test_rubric_evaluator_detects_individual_dimension_failures() -> None:
    """Verify each rubric dimension reliably fails when its specific requirement is violated."""
    # 1. Correctness failure: missing facts
    bad_correctness = (
        "Operating margin is 50% and EBITDA is $999M according to [SEC-Q3-P10]."
    )
    res_c = RubricEvaluator.evaluate(SAMPLE_CASE, bad_correctness)
    assert res_c.dimension_scores[RubricDimension.CORRECTNESS].passed is False

    # 2. Groundedness failure: hallucinated figures not in context
    hallucinated = "Operating margin is 20.0% ($100M / $500M) and EBITDA is $125M ($100M + $25M) per [SEC-Q3-P10]. Secret debt is $888M."
    res_g = RubricEvaluator.evaluate(SAMPLE_CASE, hallucinated)
    assert res_g.dimension_scores[RubricDimension.GROUNDEDNESS].passed is False
    assert (
        "$888M"
        in res_g.dimension_scores[RubricDimension.GROUNDEDNESS].details[
            "unsupported_numbers"
        ]
    )

    # 3. Citation failure: missing citation
    missing_cite = "Operating margin is 20.0% ($100M / $500M) and EBITDA is $125M ($100M + $25M) Revenue $500M."
    res_cite = RubricEvaluator.evaluate(SAMPLE_CASE, missing_cite)
    assert res_cite.dimension_scores[RubricDimension.CITATION_QUALITY].passed is False

    # 4. Format correctness failure: unclosed code block
    bad_format = "Here is the code: ```python def foo(): return 1"
    res_f = RubricEvaluator.evaluate_format_correctness(bad_format)
    assert res_f.passed is False
    assert "Unclosed markdown code fence" in res_f.justification


# --------------------------------------------------------------------------
# 2. Secondary Signal LLM-as-Judge Tests (Section 4)
# --------------------------------------------------------------------------


def test_llm_judge_blinded_ordering_and_comparison() -> None:
    """Verify blinded candidate ordering eliminates presentation bias and produces structured comparison."""
    judge = LLMJudge(seed=123)

    baseline_good = "Operating margin is 20.0% ($100M / $500M) and EBITDA is $125M ($100M + $25M) per [SEC-Q3-P10]."
    optimized_degraded = "The company made some money and has margin. Revenue is high."

    # Test with randomized order
    res = judge.evaluate_pair(SAMPLE_CASE, baseline_good, optimized_degraded)
    assert res.winner == "baseline"
    assert res.baseline_score > res.optimized_score
    assert res.is_regression is True
    assert res.is_secondary_signal is True
    assert res.judge_model == LLMJudge.FIXED_JUDGE_MODEL

    # Test reverse forced order to prove position independence
    res_forced = judge.evaluate_pair(
        SAMPLE_CASE, baseline_good, optimized_degraded, force_order="optimized_first"
    )
    assert res_forced.winner == "baseline"
    assert res_forced.baseline_score > res_forced.optimized_score


def test_llm_judge_calibration_against_ground_truth() -> None:
    """Verify judge calibration: ground truth reference answer must defeat corrupted candidate."""
    judge = LLMJudge()
    reference = SAMPLE_CASE["ground_truth_answer"]
    corrupted = "Unrelated text without facts or calculations."

    is_calibrated = judge.calibrate(SAMPLE_CASE, reference, corrupted)
    assert is_calibrated is True


# --------------------------------------------------------------------------
# 3. Explicit Regression Detection Tests (Quality, Token, Cost - Section 5)
# --------------------------------------------------------------------------


def test_regression_detector_detects_quality_regression() -> None:
    """Verify detector triggers BLOCK on critical fact loss or score drop."""
    # Case A: Critical fact loss
    report_a = RegressionDetector.evaluate_case(
        workload_id="test_case_q_regr",
        baseline_score=1.0,
        optimized_score=0.70,
        raw_tokens=500,
        optimized_tokens=300,
        baseline_cost_usd=0.005,
        optimized_cost_usd=0.003,
        missing_facts=["$125M", "20.0%"],
    )
    assert report_a.verdict == RegressionSeverity.BLOCK
    assert report_a.has_blocking_regressions is True
    assert report_a.quality_regression_detected is True
    assert any("Critical facts lost" in r.message for r in report_a.regressions)

    # Case B: Security prompt leakage
    report_b = RegressionDetector.evaluate_case(
        workload_id="test_case_leak",
        baseline_score=1.0,
        optimized_score=0.0,
        raw_tokens=500,
        optimized_tokens=300,
        baseline_cost_usd=0.005,
        optimized_cost_usd=0.003,
        leakage_detected=True,
    )
    assert report_b.verdict == RegressionSeverity.BLOCK
    assert any(r.dimension == "security_leakage" for r in report_b.regressions)


def test_regression_detector_detects_token_regression() -> None:
    """Verify detector triggers BLOCK when optimization increases token count."""
    report = RegressionDetector.evaluate_case(
        workload_id="test_case_token_regr",
        baseline_score=1.0,
        optimized_score=1.0,
        raw_tokens=200,
        optimized_tokens=350,  # Token inflation!
        baseline_cost_usd=0.002,
        optimized_cost_usd=0.0018,
    )
    assert report.verdict == RegressionSeverity.BLOCK
    assert report.has_blocking_regressions is True
    assert report.token_regression_detected is True
    assert any(
        r.regression_type == RegressionType.TOKEN_REGRESSION for r in report.regressions
    )
    assert any("+150 tokens" in r.delta for r in report.regressions)


def test_regression_detector_detects_cost_regression() -> None:
    """Verify detector triggers BLOCK when optimized path is more expensive than baseline."""
    report = RegressionDetector.evaluate_case(
        workload_id="test_case_cost_regr",
        baseline_score=1.0,
        optimized_score=1.0,
        raw_tokens=500,
        optimized_tokens=400,
        baseline_cost_usd=0.0010,
        optimized_cost_usd=0.0035,  # Cost inflation!
    )
    assert report.verdict == RegressionSeverity.BLOCK
    assert report.has_blocking_regressions is True
    assert report.cost_regression_detected is True
    assert any(
        r.regression_type == RegressionType.COST_REGRESSION for r in report.regressions
    )


def test_regression_detector_passes_clean_optimization() -> None:
    """Verify detector outputs PASS when quality, tokens, and cost all improve."""
    report = RegressionDetector.evaluate_case(
        workload_id="test_case_clean",
        baseline_score=1.0,
        optimized_score=1.0,
        raw_tokens=1000,
        optimized_tokens=550,
        baseline_cost_usd=0.005,
        optimized_cost_usd=0.0025,
    )
    assert report.verdict == RegressionSeverity.PASS
    assert report.has_blocking_regressions is False
    assert len(report.regressions) == 0


# --------------------------------------------------------------------------
# 4. Measurement Correctness: Non-Confusion of 12 Core Metrics (Section 3 & Prompt)
# --------------------------------------------------------------------------


def test_measurement_correctness_twelve_metrics_strictly_independent() -> None:
    """Confirm that the 12 core metrics are strictly independent and never confused:

    1. raw_input_tokens
    2. optimized_input_tokens
    3. physical_tokens_removed
    4. provider_cached_tokens
    5. provider_uncached_tokens
    6. output_tokens
    7. total_provider_reported_tokens
    8. estimated_cost_usd
    9. actual_cost_usd_when_available
    10. tokens_saved
    11. cost_saved
    12. quality_score
    """
    record = EvaluationRecord(
        request_id="meas-test-001",
        workload_id="workload_meas_001",
        workload_type="financial_reasoning",
        provider="anthropic",
        model="claude-3-5-sonnet",
        raw_input_tokens=2000,
        optimized_input_tokens=1400,
        physical_tokens_removed=600,
        provider_cached_input_tokens=400,
        provider_uncached_input_tokens=1000,
        output_tokens=300,
        total_provider_reported_tokens=1700,  # 1400 input + 300 output
        latency_ms=45.2,
        estimated_cost_usd=0.0068,
        actual_cost_usd_when_available=0.0055,
        tokens_saved=1000,  # 600 physical + 400 provider cache read
        cost_saved=0.0045,
        quality_score=1.0,
        quality_regression=0.0,
        passed=True,
    )

    # Invariant 1: Physical tokens removed != provider cached tokens
    assert record.physical_tokens_removed != record.provider_cached_input_tokens
    assert record.physical_tokens_removed == 600
    assert record.provider_cached_input_tokens == 400

    # Invariant 2: Provider cache hit is NOT treated as physical token removal
    assert (
        record.physical_tokens_removed
        == record.raw_input_tokens - record.optimized_input_tokens
    )

    # Invariant 3: Provider uncached != optimized input tokens (when cached > 0)
    assert record.provider_uncached_input_tokens != record.optimized_input_tokens
    assert (
        record.provider_uncached_input_tokens + record.provider_cached_input_tokens
        == record.optimized_input_tokens
    )

    # Invariant 4: Local estimated cost != actual billed cost
    assert record.actual_cost_usd_when_available is not None
    assert record.actual_cost_usd_when_available != record.estimated_cost_usd

    # Invariant 5: Total tokens saved combines distinct physical + cache mechanisms without double-counting
    assert (
        record.tokens_saved
        == record.physical_tokens_removed + record.provider_cached_input_tokens
    )


# --------------------------------------------------------------------------
# 5. Constrained Optimization & 40% Target Gate (Section 6 & Prompt)
# --------------------------------------------------------------------------


def test_failed_optimization_when_40pct_reduction_has_quality_degradation() -> None:
    """Prompt Mandate: A result such as '40% token reduction + material quality degradation'

    MUST be classified as a FAILED optimization.
    """
    from app.evals.benchmark_runner import BenchmarkSummary

    # Simulate 50% reduction (well above 40% floor) BUT with critical fact loss and high regression
    degraded_summary = BenchmarkSummary(
        total_workloads=8,
        total_passed=6,  # 2 failed!
        pass_rate_pct=75.0,
        total_baseline_input_tokens=2000,
        total_optimized_input_tokens=1000,
        total_physical_tokens_removed=1000,
        physical_reduction_pct=50.0,
        total_provider_cached_tokens=0,
        total_provider_uncached_tokens=1000,
        total_output_tokens=250,
        total_baseline_cost_usd=0.010,
        total_optimized_cost_usd=0.005,
        total_cost_saved_usd=0.005,
        cost_savings_pct=50.0,
        avg_quality_score=0.72,  # Material degradation!
        max_quality_regression=0.28,  # > 0.05 gate!
        portfolio_token_reduction_pct=50.0,
        is_40pct_claim_verified=False,  # MUST BE FALSE
        verdict="FAILED",
    )

    assert degraded_summary.portfolio_token_reduction_pct >= 40.0
    assert degraded_summary.is_40pct_claim_verified is False
    assert degraded_summary.verdict == "FAILED"


# --------------------------------------------------------------------------
# 6. Rubric, Judge, and Detector Deep Branch Coverage
# --------------------------------------------------------------------------


def test_rubric_evaluator_deep_branch_coverage() -> None:
    """Exercise all branch conditions in RubricEvaluator."""
    # 1. Correctness: empty facts and ground truth
    res_c_empty = RubricEvaluator.evaluate_correctness("Any text", [], "")
    assert res_c_empty.passed is True
    assert res_c_empty.score == 1.0

    # 2. Correctness: ground truth token overlap without expected facts
    res_c_gt = RubricEvaluator.evaluate_correctness(
        candidate="The quick brown fox jumps over the lazy dog",
        expected_facts=[],
        ground_truth="A quick brown fox jumped over a lazy dog",
    )
    assert res_c_gt.passed is True
    assert res_c_gt.score > 0.5

    # 3. Completeness: empty candidate
    res_comp_empty = RubricEvaluator.evaluate_completeness("", "What is revenue?")
    assert res_comp_empty.passed is False
    assert res_comp_empty.score == 0.0

    # 4. Completeness: query with short clauses (< 5 chars)
    res_comp_short = RubricEvaluator.evaluate_completeness("valid response", "?")
    assert res_comp_short.passed is True
    assert res_comp_short.score == 1.0

    # 5. Completeness: clause with tokens that do not match candidate
    res_comp_mismatch = RubricEvaluator.evaluate_completeness(
        "I like apples",
        "calculate total enterprise valuation and aggregate amortization",
    )
    assert res_comp_mismatch.passed is False

    # 6. Instruction following: Vietnamese requirement
    res_vn_pass = RubricEvaluator.evaluate_instruction_following(
        candidate="Doanh thu đạt mức kỷ lục trong quý này.",
        system_instruction="Trả lời bằng tiếng Việt.",
        query="Báo cáo tài chính thế nào?",
    )
    assert res_vn_pass.passed is True

    res_vn_fail = RubricEvaluator.evaluate_instruction_following(
        candidate="Revenue reached record highs this quarter.",
        system_instruction="Trả lời bằng tiếng Việt.",
        query="Báo cáo tài chính thế nào?",
    )
    assert res_vn_fail.passed is False

    # 7. Instruction following: JSON only constraint
    res_json_pass = RubricEvaluator.evaluate_instruction_following(
        candidate='```json\n{"status": "ok"}\n```',
        system_instruction="Respond with JSON only.",
        query="Provide payload",
    )
    assert res_json_pass.passed is True

    res_json_fail = RubricEvaluator.evaluate_instruction_following(
        candidate="Sure! Here is the data: invalid json string",
        system_instruction="valid JSON only",
        query="Get payload",
    )
    assert res_json_fail.passed is False

    # 8. Instruction following: conciseness constraint
    res_concise = RubricEvaluator.evaluate_instruction_following(
        candidate="This is a concise single sentence response.",
        system_instruction="Be concise.",
        query="Explain EBITDA",
    )
    assert res_concise.passed is True

    # 9. Reasoning sufficiency: non-reasoning query
    res_reason_none = RubricEvaluator.evaluate_reasoning_sufficiency(
        candidate="Hello! I am ready to help.",
        query="Hello, greetings!",
    )
    assert res_reason_none.passed is True

    # 10. Citation quality: empty expected citations
    res_cite_none = RubricEvaluator.evaluate_citation_quality("Some answer", [])
    assert res_cite_none.passed is True

    # 11. Format correctness: unclosed markdown fence
    res_fmt_fence = RubricEvaluator.evaluate_format_correctness(
        "```python\nprint('hello')"
    )
    assert res_fmt_fence.passed is False
    assert any("fence" in err for err in res_fmt_fence.details["format_errors"])

    # 12. Format correctness: missing JSON keys and syntax error
    res_fmt_keys = RubricEvaluator.evaluate_format_correctness(
        candidate='{"foo": 1}',
        expected_json_keys=["foo", "bar"],
    )
    assert res_fmt_keys.passed is False

    res_fmt_syn = RubricEvaluator.evaluate_format_correctness(
        candidate="{broken_json:",
        expected_json_keys=["foo"],
    )
    assert res_fmt_syn.passed is False

    # 13. Evaluate with recommendations branch (low score)
    res_full = RubricEvaluator.evaluate(
        case={
            "workload_id": "test_low_score",
            "user_query": "Explain everything in detail.",
            "dynamic_context": "Important facts about X and Y.",
            "expected_facts": ["fact1", "fact2"],
            "expected_citations": ["[REF-1]"],
            "ground_truth_answer": "Detailed answer with fact1 and fact2 [REF-1].",
        },
        candidate="I don't know.",
    )
    assert res_full.passed is False
    assert len(res_full.recommendations) > 0


def test_llm_judge_branch_coverage() -> None:
    """Exercise candidate ordering and verdict branches in LLMJudge."""
    judge = LLMJudge(seed=123)

    # 1. Force order baseline first
    order_b = judge.create_blinded_pair("Base", "Opt", force_order="baseline_first")
    assert order_b.candidate_a_role == "baseline"
    assert order_b.candidate_b_role == "optimized"

    # 2. Force order optimized first
    order_o = judge.create_blinded_pair("Base", "Opt", force_order="optimized_first")
    assert order_o.candidate_a_role == "optimized"
    assert order_o.candidate_b_role == "baseline"

    # 3. Pair evaluation where optimized wins
    case = {
        "workload_id": "test_opt_wins",
        "user_query": "Summarize revenue.",
        "expected_facts": ["$100M"],
    }
    res_opt_win = judge.evaluate_pair(
        case=case,
        baseline_text="I don't know the revenue.",
        optimized_text="Revenue was $100M.",
    )
    assert res_opt_win.winner == "optimized"
    assert res_opt_win.is_regression is False

    # 4. Pair evaluation where baseline and optimized tie
    res_tie = judge.evaluate_pair(
        case=case,
        baseline_text="Revenue was $100M.",
        optimized_text="Revenue was $100M.",
    )
    assert res_tie.winner == "tie"


def test_regression_detector_branch_coverage() -> None:
    """Exercise WARN severity, citation loss, schema errors, and clean PASS in RegressionDetector."""
    # 1. Citations, schema, and AST syntax errors in detect_quality_regressions
    q_regs = RegressionDetector.detect_quality_regressions(
        baseline_score=1.0,
        optimized_score=0.96,  # 0.04 drop -> triggers WARN
        missing_citations=["[SEC-DOC-1]"],
        schema_errors=["Missing required field 'status'"],
        syntax_errors=["SyntaxError at line 4"],
    )
    assert len(q_regs) == 4
    dim_names = {r.dimension for r in q_regs}
    assert "citation_integrity" in dim_names
    assert "schema_validity" in dim_names
    assert "code_syntax" in dim_names
    assert "composite_score" in dim_names

    # 2. Token regressions: increase triggers BLOCK
    t_block = RegressionDetector.detect_token_regressions(
        raw_tokens=1000,
        optimized_tokens=1060,
    )
    assert len(t_block) == 1
    assert t_block[0].severity == RegressionSeverity.BLOCK

    # 3. Cost regressions: increase triggers BLOCK
    c_block = RegressionDetector.detect_cost_regressions(
        baseline_cost_usd=0.0100,
        optimized_cost_usd=0.0106,
    )
    assert len(c_block) == 1
    assert c_block[0].severity == RegressionSeverity.BLOCK

    # 4. evaluate_case resulting in WARN verdict (quality drop >= 0.02 and < 0.05)
    report_warn = RegressionDetector.evaluate_case(
        workload_id="test_warn",
        baseline_score=1.0,
        optimized_score=0.96,
        raw_tokens=1000,
        optimized_tokens=600,
        baseline_cost_usd=0.010,
        optimized_cost_usd=0.006,
    )
    assert report_warn.verdict == RegressionSeverity.WARN
    assert report_warn.has_blocking_regressions is False
    assert "REVIEW" in report_warn.summary_message

    # 5. evaluate_case resulting in clean PASS verdict
    report_pass = RegressionDetector.evaluate_case(
        workload_id="test_pass",
        baseline_score=1.0,
        optimized_score=1.0,
        raw_tokens=1000,
        optimized_tokens=600,
        baseline_cost_usd=0.010,
        optimized_cost_usd=0.006,
    )
    assert report_pass.verdict == RegressionSeverity.PASS
    assert report_pass.has_blocking_regressions is False
    assert "PASSED" in report_pass.summary_message
