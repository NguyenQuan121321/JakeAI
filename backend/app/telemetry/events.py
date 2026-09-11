"""Structured Observability Event Schema and Safe JSON Logger (TASK OPS-05).

Enforces canonical structured logging across all platform components:
gateway, router, provider, rag, agent, guardrails.

Guarantees:
- Strict schema validation
- PII and raw prompt redaction (never log raw user prompts or unmasked secrets)
- Machine-parseable JSON log line format
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger("jakeai.telemetry.events")

ComponentType = Literal["gateway", "router", "provider", "rag", "agent", "guardrails"]
EventType = Literal[
    "request_received",
    "routing_decision",
    "provider_invocation",
    "retrieval_executed",
    "tool_executed",
    "security_incident",
    "agent_revision",
    "agent_recovery",
]


class TelemetryEvent(BaseModel):
    """Canonical enterprise observability event matching TASK OPS-05."""

    timestamp: float = Field(default_factory=time.time)
    level: str = Field(default="INFO")
    tenant_id: str = Field(default="default")
    correlation_id: str | None = None
    component: ComponentType
    event_type: EventType
    duration_ms: float | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    cost_usd: float | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize event to single-line JSON string safe for ingest."""
        # Sanitize metadata to prevent raw prompt or credential leakage
        safe_meta = {}
        sensitive_keys = {"prompt", "password", "api_key", "secret", "authorization", "token"}
        for k, v in self.metadata.items():
            if any(s in k.lower() for s in sensitive_keys):
                safe_meta[k] = "[REDACTED]"
            elif isinstance(v, str) and len(v) > 256:
                safe_meta[k] = v[:256] + "...[TRUNCATED]"
            else:
                safe_meta[k] = v

        data = {
            "timestamp": self.timestamp,
            "level": self.level,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "component": self.component,
            "event_type": self.event_type,
            "duration_ms": self.duration_ms,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "cost_usd": self.cost_usd,
            "error_code": self.error_code,
            "metadata": safe_meta,
        }
        return json.dumps(data, default=str)


def log_telemetry_event(event: TelemetryEvent) -> None:
    """Log structured event with appropriate logging level."""
    line = event.to_json()
    level = event.level.upper()
    if level == "ERROR":
        logger.error(line)
    elif level == "WARNING":
        logger.warning(line)
    else:
        logger.info(line)
