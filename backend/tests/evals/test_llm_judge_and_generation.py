"""Unit tests for Real LLM Judge and Actual Model Generation Evaluation (TASK OPS-09 & OPS-10)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.evals.benchmark_runner import BenchmarkRunner
from app.evals.llm_judge import JudgeComparisonResult, LLMJudge
from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse


@pytest.mark.asyncio
async def test_llm_judge_heuristic_rubric_fallback():
    judge = LLMJudge()
    case = {
        "workload_id": "wl-test",
        "user_query": "Calculate quarterly VAT",
        "ground_truth_answer": "VAT is $1,200",
        "expected_facts": ["$1,200"],
    }
    # Direct heuristic rubric evaluation
    res = judge.evaluate_pair(
        case=case,
        baseline_text="The total quarterly VAT is $1,200 based on verified sales.",
        optimized_text="The total quarterly VAT is $1,200.",
    )
    assert isinstance(res, JudgeComparisonResult)
    assert res.evaluation_method == "heuristic_rubric"
    assert res.judge_version == "1.0.0"
    assert res.baseline_score > 0.0
    assert res.optimized_score > 0.0


@pytest.mark.asyncio
async def test_llm_judge_real_model_invocation():
    judge = LLMJudge(judge_model="gemini-1.5-flash")
    case = {
        "workload_id": "wl-test-judge",
        "user_query": "Explain invoice reconciliation",
        "ground_truth_answer": "Reconciliation verifies invoice against purchase order and receipt.",
    }

    mock_llm_output = """```json
    {
      "candidate_a_scores": {
        "correctness": 5, "completeness": 5, "groundedness": 5, "instruction_following": 5,
        "reasoning_sufficiency": 5, "citation_quality": 4, "format_correctness": 5
      },
      "candidate_b_scores": {
        "correctness": 3, "completeness": 3, "groundedness": 3, "instruction_following": 4,
        "reasoning_sufficiency": 3, "citation_quality": 2, "format_correctness": 4
      },
      "winner": "candidate_a",
      "explanation": "Candidate A provides superior technical depth and accurate 3-way matching steps."
    }
    ```"""

    mock_resp = UpstreamLLMResponse(
        text=mock_llm_output,
        model="gemini-1.5-flash",
        provider="gemini",
        telemetry=ProviderCacheTelemetry(),
    )

    with patch(
        "app.core.llm_provider.call_upstream_llm_detailed", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = mock_resp

        res = await judge.async_evaluate_pair_with_llm(
            case=case,
            baseline_text="Candidate A text here",
            optimized_text="Candidate B text here",
            force_order="baseline_first",
        )

        assert res.evaluation_method == "llm_judge"
        assert res.winner == "baseline"
        assert res.baseline_score > res.optimized_score
        assert "Candidate A provides superior" in res.explanation
        assert "correctness" in res.dimension_breakdown


@pytest.mark.asyncio
async def test_benchmark_runner_actual_model_generation():
    runner = BenchmarkRunner()
    case = {
        "workload_id": "case_test_gen",
        "workload_type": "coding",
        "system_instruction": "You are a code assistant.",
        "user_query": "Write add function",
        "dynamic_context": "def add(a, b): return a + b",
        "expected_facts": ["add"],
        "expected_symbols": ["add"],
        "ground_truth_answer": "def add(a, b): return a + b",
    }

    # 1. Test execute_model_generation=False: evaluated_artifact is "compiled_prompt"
    rec_prompt, _, _ = await runner.run_case(case, execute_model_generation=False)
    assert rec_prompt.verdict_details.get("evaluated_artifact") == "compiled_prompt"

    # 2. Test execute_model_generation=True with upstream LLM mocked
    mock_resp = UpstreamLLMResponse(
        text="```python\ndef add(a, b):\n    return a + b\n```",
        model="gpt-4o",
        provider="openai",
        telemetry=ProviderCacheTelemetry(),
    )

    with patch(
        "app.core.llm_provider.call_upstream_llm_detailed", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = mock_resp

        rec_gen, q_res, _ = await runner.run_case(case, execute_model_generation=True)
        assert rec_gen.verdict_details.get("evaluated_artifact") == "model_generation"
        assert q_res.passed is True
