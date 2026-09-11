"""Normalized Provider Error Taxonomy and Classifiers for Phase 01.

Provides:
1. Strict ErrorCategory classification:
   retryable, non-retryable, authentication, quota, context_limit,
   provider_unavailable, policy_rejected.
2. ProviderError base exception and specialized subclasses.
3. Strict zero-secret-leakage sanitization (redacts API keys, tokens, Bearer strings).
4. Generic and provider-specific error normalizers.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    """Normalized upstream error classification as required by Phase 01 Section 6."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    AUTHENTICATION = "authentication"
    QUOTA = "quota"
    CONTEXT_LIMIT = "context_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    POLICY_REJECTED = "policy_rejected"


_SECRET_REDACTION_PATTERNS = [
    # DB connection URIs with embedded credentials (Postgres, MySQL, Redis, MongoDB, AMQP)
    re.compile(
        r"(?:postgres(?:ql)?|mysql|redis(?:s)?|mongodb(?:\+srv)?|amqp(?:s)?)://[^:\s]+:[^@\s]+@[^\s]+",
        re.IGNORECASE,
    ),
    re.compile(r"[a-zA-Z0-9+.-]+://[^:\s]+:[^@\s]+@[^\s]+", re.IGNORECASE),
    # Internal infrastructure endpoints and private IP ranges
    re.compile(
        r"(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(?::\d+)?",
        re.IGNORECASE,
    ),
    # JWT and Auth tokens
    re.compile(
        r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9._-]{10,}",
        re.IGNORECASE,
    ),
    re.compile(r"Bearer\s+[a-zA-Z0-9._-]+", re.IGNORECASE),
    re.compile(r"Basic\s+[a-zA-Z0-9+/=]{16,}", re.IGNORECASE),
    # Cloud & Provider API Keys
    re.compile(r"sk-[a-zA-Z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{20,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[a-zA-Z0-9]{36,}", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),
    # Key-value secret assignments in error strings
    re.compile(
        r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{8,}['\"]?",
        re.IGNORECASE,
    ),
    re.compile(r"x-api-key:\s*[^\s]+", re.IGNORECASE),
    re.compile(r"key=[a-zA-Z0-9_-]{10,}", re.IGNORECASE),
]


def sanitize_error_message(message: str) -> str:
    """Sanitize error messages to guarantee zero provider credentials, DB strings, or tokens leak."""
    clean = str(message)
    for pattern in _SECRET_REDACTION_PATTERNS:
        clean = pattern.sub("[REDACTED_SECRET]", clean)
    return clean


class ProviderError(Exception):
    """Base exception for all normalized LLM provider failures."""

    def __init__(
        self,
        message: str,
        provider: str,
        category: ErrorCategory,
        model: str | None = None,
        status_code: int | None = None,
        is_retryable: bool = False,
        retry_after_seconds: float | None = None,
        raw_error: Any = None,
    ) -> None:
        sanitized = sanitize_error_message(message)
        super().__init__(sanitized)
        self.message = sanitized
        self.provider = provider
        self.category = category
        self.model = model
        self.status_code = status_code
        self.is_retryable = is_retryable
        self.retry_after_seconds = retry_after_seconds
        self.raw_error = raw_error

    def __str__(self) -> str:
        cat_val = (
            self.category.value
            if hasattr(self.category, "value")
            else str(self.category)
        )
        parts = [f"[{self.provider}] {cat_val.upper()}"]
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        if self.model:
            parts.append(f"model={self.model}")
        parts.append(f": {self.message}")
        return " ".join(parts)


class ProviderAuthenticationError(ProviderError):
    """Invalid, revoked, or missing API key (HTTP 401/403). Never retryable."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 401,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.AUTHENTICATION,
            model=model,
            status_code=status_code,
            is_retryable=False,
            raw_error=raw_error,
        )


class ProviderQuotaError(ProviderError):
    """Provider account balance exhausted or hard quota exceeded. Never retryable immediately."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 429,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.QUOTA,
            model=model,
            status_code=status_code,
            is_retryable=False,
            raw_error=raw_error,
        )


class ProviderContextLimitError(ProviderError):
    """Request exceeded model context window length. Never retryable without pruning."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 400,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.CONTEXT_LIMIT,
            model=model,
            status_code=status_code,
            is_retryable=False,
            raw_error=raw_error,
        )


class ProviderUnavailableError(ProviderError):
    """Provider endpoint down, 502/503/504, connection reset, or DNS failure. Retryable with backoff."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 503,
        retry_after_seconds: float | None = None,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.PROVIDER_UNAVAILABLE,
            model=model,
            status_code=status_code,
            is_retryable=True,
            retry_after_seconds=retry_after_seconds,
            raw_error=raw_error,
        )


class ProviderRateLimitError(ProviderError):
    """Temporary rate limit / concurrency saturation (HTTP 429). Retryable with backoff."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 429,
        retry_after_seconds: float | None = None,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.RETRYABLE,
            model=model,
            status_code=status_code,
            is_retryable=True,
            retry_after_seconds=retry_after_seconds,
            raw_error=raw_error,
        )


class ProviderPolicyError(ProviderError):
    """Content blocked by provider safety guardrails or compliance policy. Never retryable."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 400,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.POLICY_REJECTED,
            model=model,
            status_code=status_code,
            is_retryable=False,
            raw_error=raw_error,
        )


class ProviderTimeoutError(ProviderError):
    """HTTP client read/connect timeout. Retryable."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.RETRYABLE,
            model=model,
            status_code=408,
            is_retryable=True,
            raw_error=raw_error,
        )


class ProviderInvalidRequestError(ProviderError):
    """Bad request syntax, invalid parameters, or malformed schema (HTTP 400). Non-retryable."""

    def __init__(
        self,
        message: str,
        provider: str,
        model: str | None = None,
        status_code: int | None = 400,
        raw_error: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            provider=provider,
            category=ErrorCategory.NON_RETRYABLE,
            model=model,
            status_code=status_code,
            is_retryable=False,
            raw_error=raw_error,
        )


def normalize_provider_error(
    provider: str,
    status_code: int | None,
    response_body: Any = None,
    exc: Exception | None = None,
    model: str | None = None,
    retry_after: float | None = None,
) -> ProviderError:
    """Normalize raw HTTP response status or exception into typed ProviderError."""
    # Extract message from dict if available
    body_msg = ""
    if isinstance(response_body, dict):
        err = response_body.get("error", {})
        if isinstance(err, dict):
            body_msg = str(err.get("message") or err.get("detail") or "")
        elif isinstance(err, str):
            body_msg = err
        else:
            body_msg = str(response_body.get("detail") or response_body)
    elif response_body is not None:
        body_msg = str(response_body)

    exc_msg = str(exc) if exc is not None else ""
    raw_msg = (
        body_msg or exc_msg or f"Provider error with status {status_code}"
    ).strip()
    msg_lower = raw_msg.lower()

    # Context length exceeded checks
    if any(
        k in msg_lower
        for k in (
            "context length",
            "maximum context",
            "token limit",
            "too many tokens",
            "prompt is too long",
        )
    ):
        return ProviderContextLimitError(
            raw_msg,
            provider,
            model=model,
            status_code=status_code,
            raw_error=response_body or exc,
        )

    # Policy / safety violation checks
    if any(
        k in msg_lower
        for k in (
            "safety",
            "blocked",
            "policy",
            "content violation",
            "harm_category",
            "moderation",
        )
    ):
        return ProviderPolicyError(
            raw_msg,
            provider,
            model=model,
            status_code=status_code,
            raw_error=response_body or exc,
        )

    # Status-code based normalization
    if status_code in (401, 403):
        return ProviderAuthenticationError(
            raw_msg,
            provider,
            model=model,
            status_code=status_code,
            raw_error=response_body or exc,
        )

    if status_code == 429:
        if any(
            k in msg_lower
            for k in (
                "quota",
                "insufficient_quota",
                "credit",
                "billing",
                "exceeded your current quota",
            )
        ):
            return ProviderQuotaError(
                raw_msg,
                provider,
                model=model,
                status_code=429,
                raw_error=response_body or exc,
            )
        return ProviderRateLimitError(
            raw_msg,
            provider,
            model=model,
            status_code=429,
            retry_after_seconds=retry_after,
            raw_error=response_body or exc,
        )

    if status_code == 402:
        return ProviderQuotaError(
            raw_msg,
            provider,
            model=model,
            status_code=402,
            raw_error=response_body or exc,
        )

    if status_code in (502, 503, 504, 529):
        return ProviderUnavailableError(
            raw_msg,
            provider,
            model=model,
            status_code=status_code,
            retry_after_seconds=retry_after,
            raw_error=response_body or exc,
        )

    if status_code == 408 or "timeout" in msg_lower:
        return ProviderTimeoutError(
            raw_msg, provider, model=model, raw_error=response_body or exc
        )

    if status_code == 400:
        return ProviderInvalidRequestError(
            raw_msg,
            provider,
            model=model,
            status_code=status_code,
            raw_error=response_body or exc,
        )

    # General network / connection exceptions
    if exc is not None and any(
        k in type(exc).__name__.lower()
        for k in ("connect", "network", "dns", "transport")
    ):
        return ProviderUnavailableError(
            raw_msg, provider, model=model, status_code=None, raw_error=exc
        )

    return ProviderError(
        message=raw_msg,
        provider=provider,
        category=ErrorCategory.NON_RETRYABLE,
        model=model,
        status_code=status_code,
        is_retryable=False,
        raw_error=response_body or exc,
    )
