"""Input Guardrail for Prompt Injection & Jailbreak Defense (TASK OPS-12)."""

from __future__ import annotations

import base64
import binascii
import logging
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GuardrailDecision(BaseModel):
    """Decision object returned by guardrail inspection."""

    allowed: bool = Field(description="True if request passed safety check")
    violation_type: str | None = Field(
        default=None, description="Category of violation detected"
    )
    reason: str | None = Field(
        default=None, description="Human-readable explanation of rejection"
    )
    risk_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Assessed safety risk score"
    )
    layer: str | None = Field(
        default=None, description="Layer that triggered the decision"
    )


# Layer 1: Cheap deterministic regex rules
INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions"),
        "PROMPT_INJECTION",
    ),
    (re.compile(r"(?i)disregard\s+(the\s+)?system\s+prompt"), "PROMPT_INJECTION"),
    (re.compile(r"(?i)dan\s+mode"), "JAILBREAK"),
    (
        re.compile(
            r"(?i)bypass\s+(all\s+)?security\s+(filters|rules|controls|guidelines)"
        ),
        "SECURITY_BYPASS",
    ),
    (
        re.compile(
            r"(?i)(?:show|reveal|display|output|print)\s+(?:the\s+)?(?:initial\s+)?(?:system\s+)?prompt"
        ),
        "PROMPT_EXTRACTION",
    ),
    (
        re.compile(
            r"(?i)you\s+are\s+now\s+(?:unrestricted|in\s+developer\s+mode|jailbroken)"
        ),
        "JAILBREAK",
    ),
    (re.compile(r"(?i)act\s+as\s+an\s+unfiltered\s+ai"), "JAILBREAK"),
    (
        re.compile(r"(?i)<\|(?:im_start|im_end|system|user|assistant)\|>"),
        "DELIMITER_INJECTION",
    ),
    (
        re.compile(r"(?i)\[(?:SYSTEM|OVERRIDE|DEVELOPER\s+MODE)\]"),
        "DELIMITER_INJECTION",
    ),
]


class SemanticSafetyClassifier:
    """Semantic and heuristic safety classifier evaluating instruction overrides and intent vectors."""

    _OVERRIDE_VERBS = {
        "forget",
        "disregard",
        "ignore",
        "override",
        "overwrite",
        "reset",
        "clear",
        "drop",
        "cancel",
        "bypass",
        "delete",
        "abandon",
        "skip",
    }
    _OVERRIDE_TARGETS = {
        "instruction",
        "instructions",
        "prompt",
        "prompts",
        "rule",
        "rules",
        "guideline",
        "guidelines",
        "constraint",
        "constraints",
        "policy",
        "policies",
        "system",
        "guardrails",
        "safeguard",
        "safeguards",
    }
    _PERSONA_HIJACK = [
        re.compile(
            r"\b(pretend|act|behave|roleplay)\s+(as|to\s+be)\s+.*(no\s+rules|unfiltered|without\s+(any\s+)?limits|evil|jailbroken)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(developer\s+mode\s+(enabled|on)|jailbreak\s+active)\b", re.IGNORECASE
        ),
        re.compile(r"\b(do\s+anything\s+now|always\s+say\s+yes)\b", re.IGNORECASE),
    ]
    _CROSS_LINGUAL_PATTERNS = [
        # Vietnamese adversarial vectors
        re.compile(
            r"bỏ\s+qua\s+(mọi\s+)?(chỉ\s+dẫn|hướng\s+dẫn|câu\s+lệnh|quy\s+tắc)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(xuất|in|hiển\s+thị)\s+(cấu\s+hình|prompt\s+hệ\s+thống|lời\s+nhắc\s+hệ\s+thống)",
            re.IGNORECASE,
        ),
        re.compile(
            r"chế\s+độ\s+(không\s+giới\s+hạn|nhà\s+phát\s+triển)", re.IGNORECASE
        ),
    ]

    @classmethod
    def evaluate(cls, text: str) -> tuple[float, str | None]:
        """Compute semantic risk score (0.0 to 1.0) and primary risk factor."""
        text_lower = text.lower()
        score = 0.0
        reason: str | None = None

        # 1. Base64 payload inspection
        b64_matches = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", text)
        for b64 in b64_matches:
            try:
                decoded = base64.b64decode(b64).decode("utf-8", errors="ignore").lower()
                for pat, v_type in INJECTION_PATTERNS:
                    if pat.search(decoded):
                        return (
                            1.0,
                            f"OBFUSCATED_INJECTION: Base64 payload decoded to {v_type}",
                        )
            except (binascii.Error, ValueError) as exc:
                logger.debug("Candidate string is not valid base64: %s", exc)

        # 2. Instruction override vector (verb + target co-occurrence)
        words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", text_lower))
        has_override_verb = bool(words.intersection(cls._OVERRIDE_VERBS))
        has_override_target = bool(words.intersection(cls._OVERRIDE_TARGETS))
        if has_override_verb and has_override_target:
            score += 0.50
            reason = "SEMANTIC_INSTRUCTION_OVERRIDE"

        # 3. Persona / boundary hijacking heuristics
        for pat in cls._PERSONA_HIJACK:
            if pat.search(text):
                score += 0.40
                reason = reason or "SEMANTIC_PERSONA_HIJACK"
                break

        # 4. Cross-lingual adversarial vectors
        for pat in cls._CROSS_LINGUAL_PATTERNS:
            if pat.search(text):
                score += 0.70
                reason = "CROSS_LINGUAL_INJECTION"
                break

        # 5. Delimiter or prompt smuggling markers
        if re.search(
            r"(?:###\s*(?:system|override|instruction)|```system)", text_lower
        ):
            score += 0.35
            reason = reason or "DELIMITER_SMUGGLING"

        return min(1.0, score), reason


def check_input_guardrail(prompt: str) -> GuardrailDecision:
    """Analyze incoming user prompt across deterministic and semantic safety classifier layers (TASK OPS-12)."""
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return GuardrailDecision(allowed=True, risk_score=0.0)

    # Layer 1: Cheap deterministic regex rules
    for pattern, violation_type in INJECTION_PATTERNS:
        if pattern.search(clean_prompt):
            return GuardrailDecision(
                allowed=False,
                violation_type=violation_type,
                reason=f"Security violation detected: {violation_type}. Prompt rejected.",
                risk_score=1.0,
                layer="deterministic_regex",
            )

    # Layer 2: Semantic Safety Classifier
    risk_score, violation = SemanticSafetyClassifier.evaluate(clean_prompt)
    if risk_score >= 0.60:
        return GuardrailDecision(
            allowed=False,
            violation_type=violation or "HIGH_RISK_SEMANTIC_INJECTION",
            reason=f"Semantic safety violation detected ({violation}, risk={risk_score:.2f}). Prompt rejected.",
            risk_score=risk_score,
            layer="semantic_safety_classifier",
        )

    return GuardrailDecision(
        allowed=True,
        risk_score=risk_score,
        layer="pass",
    )
