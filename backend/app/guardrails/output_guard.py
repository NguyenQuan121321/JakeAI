"""Output Data Leakage Prevention and Cross-Tenant Scrubber Guardrail."""

import re

LEAK_PATTERNS = [
    (
        re.compile(r"(?i)you\s+are\s+a\s+senior\s+principal\s+software\s+engineer"),
        "SYSTEM_PROMPT_LEAK",
    ),
    (
        re.compile(r"(?i)you\s+are\s+jakeai(?:'s)?(?:\s+verified\s+enterprise)?"),
        "SYSTEM_PROMPT_LEAK",
    ),
    (
        re.compile(
            r"(?i)verified\s+enterprise\s+financial\s+and\s+technical\s+knowledge\s+specialist"
        ),
        "SYSTEM_PROMPT_LEAK",
    ),
    (
        re.compile(r"(?i)universal\s+ai\s+engineering\s+and\s+financial\s+assistant"),
        "SYSTEM_PROMPT_LEAK",
    ),
    (re.compile(r"(?i)system\s+prompt\s*:"), "SYSTEM_PROMPT_LEAK"),
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{25,}"), "JWT_TOKEN_LEAK"),
    (
        re.compile(
            r"(?i)(?:api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}"
        ),
        "API_KEY_LEAK",
    ),
    (
        re.compile(
            r"(?i)\b(?:dan|developer)\s+mode\s+(?:is\s+)?(?:enabled|active|on)\b"
        ),
        "JAILBREAK_AFFIRMATION",
    ),
    (
        re.compile(r"(?i)\b(?:act|acting)\s+as\s+an?\s+unfiltered\s+ai\b"),
        "JAILBREAK_AFFIRMATION",
    ),
    (
        re.compile(
            r"(?i)\b(?:i\s+am|you\s+are)\s+(?:now\s+)?(?:unfiltered|unrestricted|jailbroken)\b"
        ),
        "JAILBREAK_AFFIRMATION",
    ),
]


def sanitize_output(
    response: str,
    tenant_id: str,
    foreign_tenant_ids: list[str] | None = None,
) -> tuple[str, bool]:
    """Inspect and scrub LLM-generated output for sensitive data leaks.

    Returns:
      (sanitized_text, leakage_detected_boolean)
    """
    leak_detected = False
    sanitized = response

    # 1. Detect and scrub prompt and credential leakage patterns
    for pat, leak_type in LEAK_PATTERNS:
        if pat.search(sanitized):
            leak_detected = True
            sanitized = pat.sub(f"[REDACTED_{leak_type}]", sanitized)

    # 2. Check for foreign tenant boundary breach
    if foreign_tenant_ids:
        for f_id in foreign_tenant_ids:
            if f_id.lower() != tenant_id.lower() and f_id.lower() in sanitized.lower():
                leak_detected = True
                # Redact foreign tenant reference
                pattern = re.compile(re.escape(f_id), re.IGNORECASE)
                sanitized = pattern.sub("[REDACTED_TENANT_DATA]", sanitized)

    return sanitized, leak_detected
