"""Request-local exact-value redaction for arbitrary BYOK credential formats."""

from contextvars import ContextVar, Token
from typing import Any

_active_credentials: ContextVar[tuple[str, ...]] = ContextVar(
    "active_credentials", default=()
)


def begin_credentials() -> Token[tuple[str, ...]]:
    return _active_credentials.set(())


def end_credentials(token: Token[tuple[str, ...]]) -> None:
    _active_credentials.reset(token)


def protect_credential(value: str) -> str:
    if value and value not in _active_credentials.get():
        _active_credentials.set((*_active_credentials.get(), value))
    return value


def redact_credentials(value: Any) -> Any:
    if isinstance(value, dict):
        return {redact_credentials(k): redact_credentials(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_credentials(v) for v in value]
    if isinstance(value, BaseException):
        return redact_credentials(str(value))
    if isinstance(value, str):
        for secret in sorted(_active_credentials.get(), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED_SECRET]")
    return value
