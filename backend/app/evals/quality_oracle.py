"""Layered Quality Oracle and Evaluation Evaluator for Phase 00.

Implements Section 5 of 00_CICD_BASELINE.md:
1. Deterministic structural checks
2. Expected-fact checks (numerical figures, currencies, metrics)
3. Citation checks (document IDs, section anchors)
4. Schema-validity checks (JSON parsing, required keys)
5. Code symbol preservation (AST parsing, function/class signatures)
6. Multilingual preservation (Vietnamese diacritics, Unicode)
7. Security & tenant boundary checks (zero prompt/secret leakage)
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from pydantic import BaseModel, Field

# Security & Data Leakage Patterns (Invariant & Baseline requirement)
LEAKAGE_PATTERNS = [
    re.compile(r"(?i)system\s+prompt"),
    re.compile(r"(?i)you\s+are\s+a\s+senior\s+principal"),
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
    re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}"),
    re.compile(r"(?i)finnapigo_jwt"),
]


class QualityScoreResult(BaseModel):
    """Layered evaluation outcome for a single test case."""

    workload_id: str = Field(..., description="Unique case identifier")
    overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized overall quality score"
    )
    structural_score: float = Field(
        ..., ge=0.0, le=1.0, description="Structural check score"
    )
    fact_score: float = Field(
        ..., ge=0.0, le=1.0, description="Factual and numerical retention score"
    )
    citation_score: float = Field(
        ..., ge=0.0, le=1.0, description="Citation and reference retention score"
    )
    schema_score: float = Field(
        ..., ge=0.0, le=1.0, description="Schema and JSON validity score"
    )
    code_symbol_score: float = Field(
        ..., ge=0.0, le=1.0, description="Code syntax and symbol retention score"
    )
    multilingual_score: float = Field(
        ..., ge=0.0, le=1.0, description="Multilingual/Unicode preservation score"
    )
    missing_facts: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)
    schema_errors: list[str] = Field(default_factory=list)
    leakage_detected: bool = False
    passed: bool = True
    regression_vs_baseline: float = 0.0
    diagnostic_details: dict[str, Any] = Field(default_factory=dict)


class QualityOracle:
    """Deterministic, layered evaluation oracle for multi-workload intelligence assessment."""

    @staticmethod
    def _check_leakage(text: str) -> bool:
        """Verify candidate text does not leak secrets or system prompts."""
        return any(pattern.search(text) for pattern in LEAKAGE_PATTERNS)

    @staticmethod
    def _evaluate_structural(text: str) -> tuple[float, list[str]]:
        """Layer 1: Structural sanity checks (non-empty, sane bounds)."""
        errors = []
        stripped = text.strip()
        if not stripped:
            return 0.0, ["Candidate text is completely empty"]

        # Check for unclosed code fences or braces
        if stripped.count("```") % 2 != 0:
            errors.append("Unclosed markdown code block")

        score = 1.0 if not errors else 0.5
        return score, errors

    @staticmethod
    def _evaluate_facts(
        text: str, expected_facts: list[str]
    ) -> tuple[float, list[str]]:
        """Layer 2: Expected facts and numerical preservation."""
        if not expected_facts:
            return 1.0, []

        text_lower = text.lower()
        missing = []
        for fact in expected_facts:
            fact_clean = fact.strip().lower()
            if fact_clean not in text_lower:
                missing.append(fact)

        score = (len(expected_facts) - len(missing)) / len(expected_facts)
        return round(max(0.0, min(1.0, score)), 4), missing

    @staticmethod
    def _evaluate_citations(
        text: str, expected_citations: list[str]
    ) -> tuple[float, list[str]]:
        """Layer 3: Citation verification."""
        if not expected_citations:
            return 1.0, []

        missing = []
        for cite in expected_citations:
            if cite not in text:
                missing.append(cite)

        score = (len(expected_citations) - len(missing)) / len(expected_citations)
        return round(max(0.0, min(1.0, score)), 4), missing

    @staticmethod
    def _evaluate_schema(
        text: str, expected_keys: list[str]
    ) -> tuple[float, list[str]]:
        """Layer 4: Schema validity and JSON parsing."""
        if not expected_keys:
            return 1.0, []

        errors = []
        # Attempt to find JSON object or parse directly
        parsed: Any = None
        try:
            parsed = json.loads(text)
        except Exception:
            # Try to extract JSON from markdown code block
            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except Exception as ex:
                    errors.append(f"Extracted JSON failed to parse: {ex}")
            else:
                errors.append("No valid JSON structure found in candidate text")

        if errors or parsed is None:
            return 0.0, errors

        # Check expected keys in parsed dictionary or string representation
        dict_text = json.dumps(parsed).lower()
        missing_keys = [k for k in expected_keys if k.lower() not in dict_text]
        if missing_keys:
            errors.append(f"Missing expected schema keys: {missing_keys}")

        score = (len(expected_keys) - len(missing_keys)) / len(expected_keys)
        return round(max(0.0, min(1.0, score)), 4), errors

    @staticmethod
    def _evaluate_code_symbols(
        text: str, expected_symbols: list[str]
    ) -> tuple[float, list[str]]:
        """Layer 5: Code AST validation and symbol preservation."""
        if not expected_symbols:
            return 1.0, []

        # Check symbol string containment
        missing = [s for s in expected_symbols if s not in text]
        symbol_retention = (len(expected_symbols) - len(missing)) / len(
            expected_symbols
        )

        # Check Python syntax if python code block or code constructs exist
        ast_valid = True
        if "```python" in text:
            blocks = re.findall(r"```python\s*([\s\S]*?)\s*```", text)
            if blocks:
                code_body = "\n".join(blocks)
                try:
                    ast.parse(code_body)
                except SyntaxError:
                    ast_valid = False
        else:
            # Look for code section starting with import / class / def
            match = re.search(r"\n?(?:import |from |class |def )[\s\S]*", text)
            if match:
                code_body = match.group(0).strip()
                try:
                    ast.parse(code_body)
                except SyntaxError:
                    ast_valid = False

        if not ast_valid and len(missing) > 0:
            score = max(0.0, symbol_retention * 0.8)
        else:
            score = symbol_retention

        return round(max(0.0, min(1.0, score)), 4), missing

    @staticmethod
    def _evaluate_multilingual(
        text: str, expected_tokens: list[str]
    ) -> tuple[float, list[str]]:
        """Layer 6: Multilingual and Unicode diacritic preservation."""
        if not expected_tokens:
            return 1.0, []

        text_lower = text.lower()
        missing = [tok for tok in expected_tokens if tok.lower() not in text_lower]

        score = (len(expected_tokens) - len(missing)) / len(expected_tokens)
        return round(max(0.0, min(1.0, score)), 4), missing

    @classmethod
    def evaluate(
        cls,
        case: dict[str, Any],
        candidate_text: str,
        baseline_score: float = 1.0,
        quality_floor: float = 0.85,
    ) -> QualityScoreResult:
        """Run all evaluation layers and produce a composite quality verdict."""
        workload_id = case.get("workload_id", "unknown")
        expected_facts = case.get("expected_facts", [])
        expected_citations = case.get("expected_citations", [])
        expected_symbols = case.get("expected_code_symbols", [])
        expected_keys = case.get("expected_json_keys", [])
        expected_multilingual = case.get("expected_multilingual_tokens", [])

        # Leakage
        leakage = cls._check_leakage(candidate_text)

        # Layers
        struct_score, struct_errs = cls._evaluate_structural(candidate_text)
        fact_score, missing_facts = cls._evaluate_facts(candidate_text, expected_facts)
        cite_score, missing_cites = cls._evaluate_citations(
            candidate_text, expected_citations
        )
        schema_score, schema_errs = cls._evaluate_schema(candidate_text, expected_keys)
        code_score, missing_symbols = cls._evaluate_code_symbols(
            candidate_text, expected_symbols
        )
        multi_score, missing_multi = cls._evaluate_multilingual(
            candidate_text, expected_multilingual
        )

        # Layer weighting:
        # If a layer is active (has expected items), it contributes to the overall score.
        active_weights: list[tuple[float, float]] = [(struct_score, 0.15)]
        if expected_facts:
            active_weights.append((fact_score, 0.35))
        if expected_citations:
            active_weights.append((cite_score, 0.20))
        if expected_keys:
            active_weights.append((schema_score, 0.20))
        if expected_symbols:
            active_weights.append((code_score, 0.25))
        if expected_multilingual:
            active_weights.append((multi_score, 0.20))

        total_weight = sum(w for _, w in active_weights)
        if total_weight > 0:
            overall = sum(s * w for s, w in active_weights) / total_weight
        else:
            overall = struct_score

        if leakage:
            overall = 0.0

        overall = round(max(0.0, min(1.0, overall)), 4)
        regression = max(0.0, round(baseline_score - overall, 4))
        passed = (
            overall >= quality_floor
            and not leakage
            and len(missing_facts) == 0  # Zero critical fact loss
        )

        return QualityScoreResult(
            workload_id=workload_id,
            overall_score=overall,
            structural_score=struct_score,
            fact_score=fact_score,
            citation_score=cite_score,
            schema_score=schema_score,
            code_symbol_score=code_score,
            multilingual_score=multi_score,
            missing_facts=missing_facts,
            missing_citations=missing_cites,
            missing_symbols=missing_symbols,
            schema_errors=schema_errs,
            leakage_detected=leakage,
            passed=passed,
            regression_vs_baseline=regression,
            diagnostic_details={
                "structural_errors": struct_errs,
                "missing_multilingual_tokens": missing_multi,
                "leakage_detected": leakage,
            },
        )
