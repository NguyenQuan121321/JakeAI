"""Personally Identifiable Information (PII) Detection and Masking Guardrail."""

import re

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"
)
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b")
SSN_TAX_ID_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{2}-\d{7}\b")


def mask_pii(text: str) -> tuple[str, int]:
    """Mask sensitive PII entities from text and return masked text and redaction count."""
    redactions = 0

    # 1. Mask Credit Cards
    text, n = CREDIT_CARD_PATTERN.subn("[REDACTED_CARD]", text)
    redactions += n

    # 2. Mask SSN / Tax IDs
    text, n = SSN_TAX_ID_PATTERN.subn("[REDACTED_ID]", text)
    redactions += n

    # 3. Mask Emails
    text, n = EMAIL_PATTERN.subn("[REDACTED_EMAIL]", text)
    redactions += n

    # 4. Mask Phone Numbers
    text, n = PHONE_PATTERN.subn("[REDACTED_PHONE]", text)
    redactions += n

    return text, redactions
