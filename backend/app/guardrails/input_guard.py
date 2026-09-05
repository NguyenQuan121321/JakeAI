"""Input Guardrail for Prompt Injection & Jailbreak Defense."""

import re

from pydantic import BaseModel, Field


class GuardrailDecision(BaseModel):
    """Decision object returned by guardrail inspection."""

    allowed: bool = Field(description="True if request passed safety check")
    violation_type: str | None = Field(
        default=None, description="Category of violation detected"
    )
    reason: str | None = Field(
        default=None, description="Human-readable explanation of rejection"
    )


INJECTION_PATTERNS = [
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
]


def check_input_guardrail(prompt: str) -> GuardrailDecision:
    """Analyze incoming user prompt for injection or adversarial manipulation."""
    clean_prompt = prompt.strip()

    for pattern, violation_type in INJECTION_PATTERNS:
        if pattern.search(clean_prompt):
            return GuardrailDecision(
                allowed=False,
                violation_type=violation_type,
                reason=f"Security violation detected: {violation_type}. Prompt rejected.",
            )

    return GuardrailDecision(allowed=True)
