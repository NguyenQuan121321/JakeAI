"""Regression Detection Engine for Phase 06 AI Quality Evaluation.

Implements Section 5 of 06_EVALUATION.md:
Detects and classifies regressions across 3 core pillars:
1. Quality Regression:
   - Missing critical facts (numbers, metrics, currencies)
   - Missing required citations / section anchors
   - Invalid JSON schema or broken AST code syntax
   - Security/prompt leakage
   - Quality score drop vs baseline (>0.05 = BLOCK, >0.01 = WARN)
2. Token Regression:
   - Optimized input tokens exceeding unoptimized baseline tokens
   - Negative token reduction
3. Cost Regression:
   - Optimized dollar expenditure exceeding baseline cost
   - Negative cost savings
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RegressionType(StrEnum):
    """Types of regressions detected by the evaluation engine."""

    QUALITY_REGRESSION = "quality_regression"
    TOKEN_REGRESSION = "token_regression"
    COST_REGRESSION = "cost_regression"


class RegressionSeverity(StrEnum):
    """Enforcement policy actions triggered by detected regressions."""

    BLOCK = "block"  # Hard block on PR / CI
    WARN = "warn"  # Warning / review advisory
    PASS = "pass"  # No significant regression


class DetectedRegression(BaseModel):
    """Detailed record of an individual detected regression."""

    regression_type: RegressionType
    severity: RegressionSeverity
    dimension: str
    baseline_value: float | str | int
    optimized_value: float | str | int
    delta: float | str
    message: str


class RegressionReport(BaseModel):
    """Aggregated regression report for a test case or portfolio benchmark."""

    workload_id: str
    verdict: RegressionSeverity
    has_blocking_regressions: bool
    regressions: list[DetectedRegression] = Field(default_factory=list)
    quality_regression_detected: bool = False
    token_regression_detected: bool = False
    cost_regression_detected: bool = False
    summary_message: str


class RegressionDetector:
    """Engine analyzing Baseline vs Optimized metrics to enforce Regression Policy."""

    QUALITY_BLOCK_THRESHOLD = 0.05  # > 5% drop is a BLOCK
    QUALITY_WARN_THRESHOLD = 0.01  # > 1% drop is a WARN

    @classmethod
    def detect_quality_regressions(
        cls,
        baseline_score: float,
        optimized_score: float,
        missing_facts: list[str] | None = None,
        missing_citations: list[str] | None = None,
        schema_errors: list[str] | None = None,
        leakage_detected: bool = False,
        syntax_errors: list[str] | None = None,
    ) -> list[DetectedRegression]:
        """Detect factual, structural, security, or score regressions."""
        regressions: list[DetectedRegression] = []

        # 1. Critical Fact Loss (Hard Block)
        if missing_facts:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="factual_accuracy",
                    baseline_value="all_facts_present",
                    optimized_value=f"missing_{len(missing_facts)}",
                    delta=f"-{len(missing_facts)} facts",
                    message=f"Critical facts lost during optimization: {missing_facts}",
                )
            )

        # 2. Citation Loss (Hard Block)
        if missing_citations:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="citation_integrity",
                    baseline_value="all_citations_present",
                    optimized_value=f"missing_{len(missing_citations)}",
                    delta=f"-{len(missing_citations)} citations",
                    message=f"Required citations missing in optimized output: {missing_citations}",
                )
            )

        # 3. Schema / Syntax Corruption (Hard Block)
        if schema_errors:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="schema_validity",
                    baseline_value="valid_json",
                    optimized_value="invalid_json",
                    delta="syntax_error",
                    message=f"Structured output schema corrupted: {schema_errors}",
                )
            )

        if syntax_errors:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="code_syntax",
                    baseline_value="valid_ast",
                    optimized_value="syntax_error",
                    delta="syntax_error",
                    message=f"Code syntax AST corrupted: {syntax_errors}",
                )
            )

        # 4. Security Leakage (Hard Block)
        if leakage_detected:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="security_leakage",
                    baseline_value="zero_leakage",
                    optimized_value="leakage_detected",
                    delta="security_violation",
                    message="Security vulnerability: sensitive key or system prompt leaked.",
                )
            )

        # 5. Composite Score Drop
        score_drop = round(baseline_score - optimized_score, 4)
        if score_drop >= cls.QUALITY_BLOCK_THRESHOLD:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="composite_score",
                    baseline_value=baseline_score,
                    optimized_value=optimized_score,
                    delta=f"-{score_drop:.4f}",
                    message=f"Composite quality score dropped by {score_drop:.4f} (exceeds block threshold {cls.QUALITY_BLOCK_THRESHOLD}).",
                )
            )
        elif score_drop >= cls.QUALITY_WARN_THRESHOLD:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.WARN,
                    dimension="composite_score",
                    baseline_value=baseline_score,
                    optimized_value=optimized_score,
                    delta=f"-{score_drop:.4f}",
                    message=f"Composite quality score dropped slightly by {score_drop:.4f} (review advisory).",
                )
            )

        return regressions

    @classmethod
    def detect_token_regressions(
        cls,
        raw_tokens: int,
        optimized_tokens: int,
    ) -> list[DetectedRegression]:
        """Detect token consumption increase (failed optimization)."""
        regressions: list[DetectedRegression] = []

        if optimized_tokens > raw_tokens:
            token_increase = optimized_tokens - raw_tokens
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.TOKEN_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="token_count",
                    baseline_value=raw_tokens,
                    optimized_value=optimized_tokens,
                    delta=f"+{token_increase} tokens",
                    message=f"Token regression: optimized prompt increased token count by {token_increase} tokens ({raw_tokens} -> {optimized_tokens}).",
                )
            )

        return regressions

    @classmethod
    def detect_cost_regressions(
        cls,
        baseline_cost_usd: float,
        optimized_cost_usd: float,
    ) -> list[DetectedRegression]:
        """Detect cost increase (optimization increased expenditure)."""
        regressions: list[DetectedRegression] = []

        cost_delta = round(optimized_cost_usd - baseline_cost_usd, 6)
        if cost_delta > 0.0:
            regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.COST_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="cost_usd",
                    baseline_value=baseline_cost_usd,
                    optimized_value=optimized_cost_usd,
                    delta=f"+${cost_delta:.6f} USD",
                    message=f"Cost regression: optimized path increased cost by ${cost_delta:.6f} USD (${baseline_cost_usd:.6f} -> ${optimized_cost_usd:.6f}).",
                )
            )

        return regressions

    @classmethod
    def evaluate_case(
        cls,
        workload_id: str,
        baseline_score: float,
        optimized_score: float,
        raw_tokens: int,
        optimized_tokens: int,
        baseline_cost_usd: float,
        optimized_cost_usd: float,
        missing_facts: list[str] | None = None,
        missing_citations: list[str] | None = None,
        schema_errors: list[str] | None = None,
        leakage_detected: bool = False,
        syntax_errors: list[str] | None = None,
    ) -> RegressionReport:
        """Run complete regression audit across quality, token, and cost dimensions."""
        all_regressions: list[DetectedRegression] = []

        # 1. Quality Regressions
        q_regs = cls.detect_quality_regressions(
            baseline_score=baseline_score,
            optimized_score=optimized_score,
            missing_facts=missing_facts,
            missing_citations=missing_citations,
            schema_errors=schema_errors,
            leakage_detected=leakage_detected,
            syntax_errors=syntax_errors,
        )
        all_regressions.extend(q_regs)

        # 2. Token Regressions
        t_regs = cls.detect_token_regressions(
            raw_tokens=raw_tokens,
            optimized_tokens=optimized_tokens,
        )
        all_regressions.extend(t_regs)

        # 3. Cost Regressions
        c_regs = cls.detect_cost_regressions(
            baseline_cost_usd=baseline_cost_usd,
            optimized_cost_usd=optimized_cost_usd,
        )
        all_regressions.extend(c_regs)

        has_block = any(r.severity == RegressionSeverity.BLOCK for r in all_regressions)
        has_warn = any(r.severity == RegressionSeverity.WARN for r in all_regressions)

        if has_block:
            verdict = RegressionSeverity.BLOCK
            summary = f"REJECTED: {len([r for r in all_regressions if r.severity == RegressionSeverity.BLOCK])} blocking regressions detected."
        elif has_warn:
            verdict = RegressionSeverity.WARN
            summary = f"REVIEW: {len(all_regressions)} non-blocking warnings detected."
        else:
            verdict = RegressionSeverity.PASS
            summary = "PASSED: Zero quality, token, or cost regressions detected."

        return RegressionReport(
            workload_id=workload_id,
            verdict=verdict,
            has_blocking_regressions=has_block,
            regressions=all_regressions,
            quality_regression_detected=len(q_regs) > 0,
            token_regression_detected=len(t_regs) > 0,
            cost_regression_detected=len(c_regs) > 0,
            summary_message=summary,
        )

    @classmethod
    def evaluate_live_benchmark(
        cls,
        summary: Any,
        baseline_version: str = "v1",
        baseline_override: Any | None = None,
    ) -> RegressionReport:
        """Evaluate live benchmark results against versioned baseline artifact (TASK OPS-16)."""
        from app.evals.baseline_store import get_baseline_store

        store = get_baseline_store()
        baseline = baseline_override or store.load_baseline(baseline_version)

        all_regressions: list[DetectedRegression] = []

        # 1. Quality Regression vs Baseline
        quality_drop = round(baseline.avg_quality_score - summary.avg_quality_score, 4)
        if quality_drop > baseline.max_quality_regression:
            all_regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="avg_quality_score",
                    baseline_value=baseline.avg_quality_score,
                    optimized_value=summary.avg_quality_score,
                    delta=f"-{quality_drop:.4f}",
                    message=f"Quality regression exceeds threshold ({quality_drop:.4f} > {baseline.max_quality_regression:.4f})",
                )
            )
        elif quality_drop > cls.QUALITY_WARN_THRESHOLD:
            all_regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.WARN,
                    dimension="avg_quality_score",
                    baseline_value=baseline.avg_quality_score,
                    optimized_value=summary.avg_quality_score,
                    delta=f"-{quality_drop:.4f}",
                    message=f"Minor quality drop detected vs baseline ({quality_drop:.4f})",
                )
            )

        # 2. Pass Rate Regression
        if summary.pass_rate_pct < baseline.min_pass_rate_pct:
            all_regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.QUALITY_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="pass_rate_pct",
                    baseline_value=baseline.min_pass_rate_pct,
                    optimized_value=summary.pass_rate_pct,
                    delta=f"{summary.pass_rate_pct - baseline.min_pass_rate_pct:.2f}%",
                    message=f"Benchmark pass rate below baseline threshold ({summary.pass_rate_pct:.2f}% < {baseline.min_pass_rate_pct:.2f}%)",
                )
            )

        # 3. Cost / Token Regression
        if summary.total_cost_saved_usd < 0:
            all_regressions.append(
                DetectedRegression(
                    regression_type=RegressionType.COST_REGRESSION,
                    severity=RegressionSeverity.BLOCK,
                    dimension="cost_savings_usd",
                    baseline_value=0.0,
                    optimized_value=summary.total_cost_saved_usd,
                    delta=f"${summary.total_cost_saved_usd:.6f}",
                    message="Negative cost savings detected on live benchmark",
                )
            )

        has_block = any(r.severity == RegressionSeverity.BLOCK for r in all_regressions)
        has_warn = any(r.severity == RegressionSeverity.WARN for r in all_regressions)

        if has_block:
            verdict = RegressionSeverity.BLOCK
            summary_msg = f"BLOCK: Live benchmark failed AI quality regression gate against baseline {baseline.version}."
        elif has_warn:
            verdict = RegressionSeverity.WARN
            summary_msg = f"WARN: Live benchmark triggered quality advisories against baseline {baseline.version}."
        else:
            verdict = RegressionSeverity.PASS
            summary_msg = f"PASS: Live benchmark meets all quality and regression thresholds against baseline {baseline.version}."

        return RegressionReport(
            workload_id="portfolio_benchmark",
            verdict=verdict,
            has_blocking_regressions=has_block,
            regressions=all_regressions,
            quality_regression_detected=any(
                r.regression_type == RegressionType.QUALITY_REGRESSION
                for r in all_regressions
            ),
            token_regression_detected=any(
                r.regression_type == RegressionType.TOKEN_REGRESSION
                for r in all_regressions
            ),
            cost_regression_detected=any(
                r.regression_type == RegressionType.COST_REGRESSION
                for r in all_regressions
            ),
            summary_message=summary_msg,
        )
