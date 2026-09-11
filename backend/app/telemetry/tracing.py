"""OpenTelemetry & W3C Distributed Tracing Context Propagation (TASK OPS-07).

Implements W3C Trace Context specifications (traceparent, tracestate) using
zero-dependency Python standard library constructs to guarantee:
- Absolute isolation from copyleft or GPL-tainted packages
- High-performance, async-safe contextvars propagation
- Seamless trace context continuity across Edge -> Context -> Router -> Provider -> RAG -> Agent -> Tools
"""

from __future__ import annotations

import contextvars
import re
import secrets
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

_TRACEPARENT_RE = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)


@dataclass
class TraceContext:
    """Canonical W3C Distributed Trace Context representation."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    sampled: bool = True
    tracestate: str = ""

    def to_traceparent(self) -> str:
        """Format as W3C traceparent header: 00-{trace_id}-{span_id}-{flags}."""
        flags = "01" if self.sampled else "00"
        return f"00-{self.trace_id}-{self.span_id}-{flags}"


_current_trace_context: contextvars.ContextVar[TraceContext | None] = (
    contextvars.ContextVar("current_trace_context", default=None)
)


def get_current_trace_context() -> TraceContext | None:
    """Retrieve the current active W3C trace context."""
    return _current_trace_context.get()


def set_current_trace_context(ctx: TraceContext | None) -> contextvars.Token:
    """Set active W3C trace context."""
    return _current_trace_context.set(ctx)


def parse_traceparent(header_val: str | None) -> tuple[str, str, bool] | None:
    """Parse incoming W3C traceparent header string.

    Returns (trace_id, parent_span_id, is_sampled) or None if invalid.
    """
    if not header_val:
        return None
    val = header_val.strip().lower()
    match = _TRACEPARENT_RE.match(val)
    if not match:
        return None
    version, trace_id, parent_id, flags = match.groups()
    if version == "ff":
        return None
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None
    is_sampled = (int(flags, 16) & 0x01) == 0x01
    return trace_id, parent_id, is_sampled


def create_or_inherit_trace_context(
    traceparent_header: str | None = None,
    tracestate_header: str | None = None,
    fallback_correlation_id: str | None = None,
) -> TraceContext:
    """Instantiate W3C trace context from incoming headers or generate new root trace."""
    parsed = parse_traceparent(traceparent_header)
    new_span_id = secrets.token_hex(8)

    if parsed:
        trace_id, parent_id, sampled = parsed
        return TraceContext(
            trace_id=trace_id,
            span_id=new_span_id,
            parent_span_id=parent_id,
            sampled=sampled,
            tracestate=(tracestate_header or "").strip(),
        )

    # Derive trace_id from correlation_id if valid hex 32 chars, else generate random
    if fallback_correlation_id and re.match(
        r"^[0-9a-fA-F]{32}$", fallback_correlation_id
    ):
        trace_id = fallback_correlation_id.lower()
    else:
        trace_id = secrets.token_hex(16)

    return TraceContext(
        trace_id=trace_id,
        span_id=new_span_id,
        parent_span_id=None,
        sampled=True,
        tracestate=(tracestate_header or "").strip(),
    )


@dataclass
class Span:
    """In-flight tracing span for local profiling."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_time: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"

    def finish(self, error: Exception | None = None) -> None:
        """Mark span as finished and calculate duration."""
        self.duration_ms = (time.time() - self.start_time) * 1000.0
        if error:
            self.status = "ERROR"
            self.attributes["error"] = str(error)


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
    """Synchronous context manager creating a child span under active trace context."""
    parent_ctx = get_current_trace_context()
    if parent_ctx:
        child_span_id = secrets.token_hex(8)
        span = Span(
            name=name,
            trace_id=parent_ctx.trace_id,
            span_id=child_span_id,
            parent_span_id=parent_ctx.span_id,
            attributes=attributes or {},
        )
        child_ctx = TraceContext(
            trace_id=parent_ctx.trace_id,
            span_id=child_span_id,
            parent_span_id=parent_ctx.span_id,
            sampled=parent_ctx.sampled,
            tracestate=parent_ctx.tracestate,
        )
    else:
        root_trace_id = secrets.token_hex(16)
        root_span_id = secrets.token_hex(8)
        span = Span(
            name=name,
            trace_id=root_trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            attributes=attributes or {},
        )
        child_ctx = TraceContext(
            trace_id=root_trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            sampled=True,
            tracestate="",
        )

    set_current_trace_context(child_ctx)
    try:
        yield span
        span.finish()
    except Exception as exc:
        span.finish(error=exc)
        raise
    finally:
        set_current_trace_context(parent_ctx)


@asynccontextmanager
async def async_trace_span(
    name: str, attributes: dict[str, Any] | None = None
) -> AsyncIterator[Span]:
    """Asynchronous context manager creating a child span under active trace context."""
    with trace_span(name, attributes) as span:
        yield span
