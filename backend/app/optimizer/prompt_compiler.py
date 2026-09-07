"""Deterministic Two-Zone Prompt Compiler for Tier 5.

Partitions prompts into:
- Zone 1 (Static Prefix): System instructions, stable tool schemas, repository map,
  agent rules, and static policies that remain invariant across requests.
- Zone 2 (Dynamic Suffix): User request, conversation turns, active diff, retrieved RAG
  passages, and runtime tool execution results.

Enforces:
1. Strict byte determinism of Zone 1.
2. Volatile data quarantine (UUIDs, ISO timestamps, trace IDs).
3. Tenant isolation: Static prefix hash is tenant-scoped to prevent cross-tenant cache sharing.
4. Deterministic tool ordering and JSON schema serialization.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.optimizer.provider_cache_policy import (
    PromptCachePolicy,
    get_provider_cache_policy,
)
from app.optimizer.token_pruner import estimate_tokens

logger = logging.getLogger(__name__)

# Volatile patterns that MUST NOT contaminate Zone 1 (Static Prefix)
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
ISO_TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
EPHEMERAL_TOKEN_PATTERNS = [
    re.compile(r"request[-_]?id\s*[:=]\s*['\"]?[0-9a-zA-Z\-_]+['\"]?", re.IGNORECASE),
    re.compile(r"session[-_]?id\s*[:=]\s*['\"]?[0-9a-zA-Z\-_]+['\"]?", re.IGNORECASE),
    re.compile(r"trace[-_]?id\s*[:=]\s*['\"]?[0-9a-zA-Z\-_]+['\"]?", re.IGNORECASE),
    re.compile(
        r"correlation[-_]?id\s*[:=]\s*['\"]?[0-9a-zA-Z\-_]+['\"]?", re.IGNORECASE
    ),
]


class ContaminationError(ValueError):
    """Raised when Zone 1 static prefix contains volatile request data in strict mode."""

    pass


class PromptEnvelope(BaseModel):
    """Immutable compiled two-zone prompt envelope."""

    zone1_static_prefix: str = Field(
        ..., description="Zone 1: Immutable static prefix (system, tools, rules)"
    )
    zone2_dynamic_suffix: str = Field(
        ...,
        description="Zone 2: Dynamic suffix (user prompt, active diff, tool results)",
    )
    static_prefix_hash: str = Field(
        ..., description="SHA-256 hex digest of the normalized UTF-8 static prefix"
    )
    provider: str = Field(default="generic", description="Target LLM provider name")
    model: str = Field(default="default", description="Target LLM model identifier")
    cache_policy: PromptCachePolicy | None = Field(
        default=None, description="Resolved provider prompt caching policy"
    )
    tenant_id: str = Field(
        default="default",
        description="Tenant scope identifier preventing cross-tenant sharing",
    )
    static_token_count: int = Field(
        default=0, description="Calibrated token count of Zone 1"
    )
    dynamic_token_count: int = Field(
        default=0, description="Calibrated token count of Zone 2"
    )
    total_token_count: int = Field(
        default=0, description="Total combined token count of Zone 1 + Zone 2"
    )
    version: str = Field(
        default="v1.0", description="Explicit prompt/schema cache version"
    )
    is_cache_eligible: bool = Field(
        default=False,
        description="Whether static prefix meets minimum token size requirements",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Aliases for backward compatibility with CompiledPrompt
    @property
    def static_prefix(self) -> str:
        return self.zone1_static_prefix

    @property
    def dynamic_suffix(self) -> str:
        return self.zone2_dynamic_suffix

    @property
    def full_prompt(self) -> str:
        """Render complete unified prompt string."""
        if not self.zone1_static_prefix:
            return self.zone2_dynamic_suffix
        if not self.zone2_dynamic_suffix:
            return self.zone1_static_prefix
        return f"{self.zone1_static_prefix.rstrip()}\n\n{self.zone2_dynamic_suffix.lstrip()}"


class PromptCompiler:
    """Deterministic prompt compiler for Tier 5 Provider Prompt Caching."""

    def __init__(
        self,
        min_cache_tokens: int = 1024,
        strict_isolation: bool = False,
        default_version: str = "v1.0",
    ) -> None:
        self.min_cache_tokens = min_cache_tokens
        self.strict_isolation = strict_isolation
        self.default_version = default_version

    @staticmethod
    def compute_prefix_hash(
        prefix_text: str,
        version: str = "v1.0",
        tenant_id: str | None = None,
    ) -> str:
        """Compute deterministic SHA-256 fingerprint for static prefix with version and tenant scoping."""
        normalized = prefix_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        tenant_tag = (
            f"__tenant:{tenant_id}__" if tenant_id and tenant_id != "default" else ""
        )
        payload = f"{tenant_tag}__v:{version}__\n{normalized}".encode()
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def serialize_tools(tools: list[dict[str, Any]] | None) -> str:
        """Deterministically serialize tool declarations with sorted keys and stable indent."""
        if not tools:
            return ""

        sorted_tools = sorted(
            tools,
            key=lambda t: (
                t.get("name")
                or t.get("function", {}).get("name")
                or json.dumps(t, sort_keys=True)
            ),
        )
        return "### Available Tools and Function Schemas:\n" + json.dumps(
            sorted_tools, sort_keys=True, indent=2, ensure_ascii=False
        )

    def validate_isolation(self, static_text: str) -> list[str]:
        """Check static prefix for volatile request data contamination."""
        violations: list[str] = []

        if UUID_PATTERN.search(static_text):
            violations.append("Volatile UUID detected in static prefix")
        if ISO_TIMESTAMP_PATTERN.search(static_text):
            violations.append("Volatile ISO timestamp detected in static prefix")
        for pat in EPHEMERAL_TOKEN_PATTERNS:
            if pat.search(static_text):
                violations.append(f"Ephemeral identifier detected: {pat.pattern}")

        if violations and self.strict_isolation:
            raise ContaminationError(
                f"Zone 1 contamination detected: {'; '.join(violations)}"
            )

        return violations

    def compile(
        self,
        system_instruction: str = "",
        tools: list[dict[str, Any]] | None = None,
        static_context: str = "",
        user_query: str = "",
        dynamic_context: str = "",
        prompt_version: str | None = None,
        min_cache_tokens: int | None = None,
        model: str = "default",
        tenant_id: str = "default",
    ) -> PromptEnvelope:
        """Compile separate static components into Zone 1 and dynamic components into Zone 2."""
        version = prompt_version or self.default_version
        policy = get_provider_cache_policy(model)
        min_tokens = (
            min_cache_tokens
            if min_cache_tokens is not None
            else (
                policy.minimum_tokens if model != "default" else self.min_cache_tokens
            )
        )

        # Assemble Zone 1: Static Prefix
        prefix_blocks: list[str] = []
        if system_instruction.strip():
            prefix_blocks.append(system_instruction.strip())

        tools_str = self.serialize_tools(tools)
        if tools_str.strip():
            prefix_blocks.append(tools_str.strip())

        if static_context.strip():
            prefix_blocks.append(static_context.strip())

        zone1 = "\n\n".join(prefix_blocks).strip()

        # Validate isolation
        contamination_warnings = self.validate_isolation(zone1)
        if contamination_warnings:
            logger.warning(
                "Zone 1 isolation warnings detected: %s", contamination_warnings
            )

        # Assemble Zone 2: Dynamic Suffix
        suffix_blocks: list[str] = []
        if dynamic_context.strip():
            suffix_blocks.append(dynamic_context.strip())
        if user_query.strip():
            suffix_blocks.append(user_query.strip())

        zone2 = "\n\n".join(suffix_blocks).strip()

        # Metrics & Fingerprinting
        static_hash = self.compute_prefix_hash(
            zone1, version=version, tenant_id=tenant_id
        )
        static_tokens = estimate_tokens(zone1) if zone1 else 0
        dynamic_tokens = estimate_tokens(zone2) if zone2 else 0
        total_tokens = static_tokens + dynamic_tokens

        is_eligible = bool(static_tokens >= min_tokens and zone1)

        return PromptEnvelope(
            zone1_static_prefix=zone1,
            zone2_dynamic_suffix=zone2,
            static_prefix_hash=static_hash,
            provider=policy.provider_name,
            model=model,
            cache_policy=policy,
            tenant_id=tenant_id,
            static_token_count=static_tokens,
            dynamic_token_count=dynamic_tokens,
            total_token_count=total_tokens,
            version=version,
            is_cache_eligible=is_eligible,
            metadata={
                "contamination_detected": bool(contamination_warnings),
                "contamination_reasons": contamination_warnings,
                "min_cache_tokens": min_tokens,
            },
        )

    def partition_messages(
        self,
        messages: list[Any],
        prompt_version: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        static_context: str = "",
        model: str = "default",
        tenant_id: str = "default",
    ) -> PromptEnvelope:
        """Partition standard OpenAI-compatible messages into Zone 1 and Zone 2."""
        system_parts: list[str] = []
        dynamic_parts: list[str] = []

        for msg in messages:
            role = getattr(msg, "role", "") or (
                msg.get("role", "") if isinstance(msg, dict) else ""
            )
            content = getattr(msg, "content", "") or (
                msg.get("content", "") if isinstance(msg, dict) else ""
            )

            if role in ("system", "developer"):
                system_parts.append(content)
            else:
                dynamic_parts.append(f"{role.capitalize()}: {content}")

        system_instruction = "\n\n".join(system_parts)
        dynamic_context = (
            "\n\n".join(dynamic_parts[:-1]) if len(dynamic_parts) > 1 else ""
        )
        user_query = dynamic_parts[-1] if dynamic_parts else ""

        return self.compile(
            system_instruction=system_instruction,
            tools=tools,
            static_context=static_context,
            user_query=user_query,
            dynamic_context=dynamic_context,
            prompt_version=prompt_version,
            model=model,
            tenant_id=tenant_id,
        )


_prompt_compiler: PromptCompiler | None = None


def get_prompt_compiler() -> PromptCompiler:
    """Singleton getter for default PromptCompiler."""
    global _prompt_compiler
    if _prompt_compiler is None:
        _prompt_compiler = PromptCompiler()
    return _prompt_compiler
