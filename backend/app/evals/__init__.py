"""AI Evaluation Package for JakeAI Phase 06."""

from app.evals.llm_judge import BlindedOrder, JudgeComparisonResult, LLMJudge
from app.evals.quality_oracle import QualityOracle, QualityScoreResult
from app.evals.rag_evaluator import RAGEvalResult, evaluate_rag_case
from app.evals.regression_detector import (
    DetectedRegression,
    RegressionDetector,
    RegressionReport,
    RegressionSeverity,
    RegressionType,
)
from app.evals.rubric_evaluator import (
    DimensionScore,
    RubricDimension,
    RubricEvaluationResult,
    RubricEvaluator,
)

__all__ = [
    "BlindedOrder",
    "DetectedRegression",
    "DimensionScore",
    "JudgeComparisonResult",
    "LLMJudge",
    "QualityOracle",
    "QualityScoreResult",
    "RAGEvalResult",
    "RegressionDetector",
    "RegressionReport",
    "RegressionSeverity",
    "RegressionType",
    "RubricDimension",
    "RubricEvaluationResult",
    "RubricEvaluator",
    "evaluate_rag_case",
]
