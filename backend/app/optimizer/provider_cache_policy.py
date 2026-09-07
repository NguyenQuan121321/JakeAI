"""Provider Cache Policies, Capability Matrix, and Adapters for Tier 5.

Establishes provider-specific caching rules, minimum token thresholds, TTLs,
and explicit breakpoint requirements across LLM providers:
- Anthropic: SUPPORTED (min 1,024 tokens, explicit breakpoint required, 5m TTL)
- OpenAI: SUPPORTED (min 1,024 tokens, automatic prefix caching, 5-10m TTL)
- DeepSeek: SUPPORTED (min 64 tokens, automatic prefix caching)
- Google Gemini: PARTIALLY_SUPPORTED (explicit context caching > 32,768 tokens)
- Groq: NOT_SUPPORTED (instant inference without KV cache persistence)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.optimizer.provider_pricing import (
    ProviderCostBreakdown,
    calculate_provider_costs,
)


class ProviderCacheStatus(StrEnum):
    """Cache support classification according to Tier 5 specifications."""

    SUPPORTED = "supported"
    SUPPORTED_AUTOMATIC = "supported_automatic"
    SUPPORTED_EXPLICIT = "supported_explicit"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"
    UNKNOWN = "unknown"


class CacheMissReason(StrEnum):
    """Fine-grained attribution for provider prompt cache misses."""

    NONE = "none"
    PREFIX_TOO_SHORT = "prefix_too_short"
    BELOW_MINIMUM_SIZE = "below_minimum_size"  # Backward-compatible alias
    PREFIX_CHANGED = "prefix_changed"
    PROVIDER_UNSUPPORTED = "provider_unsupported"
    MODEL_UNSUPPORTED = "model_unsupported"
    CACHE_EXPIRED = "cache_expired"
    TTL_EXPIRED = "ttl_expired"  # Backward-compatible alias
    INVALID_REQUEST = "invalid_request"
    EXPLICIT_CACHE_REQUIRED = "explicit_cache_required"
    PROVIDER_REPORTED_MISS = "provider_reported_miss"
    DYNAMIC_DATA_CONTAMINATION = "dynamic_data_contamination"
    TOOL_SCHEMA_CHANGED = "tool_schema_changed"
    MODEL_CHANGED = "model_changed"
    COLD_START = "cold_start"
    UNKNOWN = "unknown"


class PromptCachePolicy(BaseModel):
    """Caching policy configuration for a specific provider/model family."""

    provider_name: str
    status: ProviderCacheStatus
    enabled: bool = True
    mechanism: str = Field(
        default="automatic",
        description="Caching mechanism: explicit_breakpoint, automatic, context_cache, or none",
    )
    minimum_tokens: int = Field(
        default=1024,
        description="Minimum static prefix token count required for caching",
    )
    ttl: int = Field(
        default=300, description="Upstream ephemeral cache lifetime in seconds"
    )
    explicit_breakpoint: bool = Field(
        default=False,
        description="True if provider requires explicit cache_control markers (e.g. Anthropic)",
    )
    automatic: bool = Field(
        default=True,
        description="True if provider performs automatic prefix caching (e.g. OpenAI, DeepSeek)",
    )
    supports_cache_write_telemetry: bool = Field(
        default=False,
        description="Whether upstream returns cache write/creation token metrics",
    )
    supports_cache_read_telemetry: bool = Field(
        default=False,
        description="Whether upstream returns cache read/hit token metrics",
    )
    pricing_model: str = "standard"
    description: str = ""

    # Aliases for backward compatibility
    @property
    def min_cache_tokens(self) -> int:
        return self.minimum_tokens

    @property
    def explicit_breakpoint_required(self) -> bool:
        return self.explicit_breakpoint

    @property
    def default_ttl_seconds(self) -> int:
        return self.ttl


# Type alias for backward compatibility
ProviderCachePolicy = PromptCachePolicy


# Pre-configured provider policies
POLICIES: dict[str, PromptCachePolicy] = {
    "anthropic": PromptCachePolicy(
        provider_name="anthropic",
        status=ProviderCacheStatus.SUPPORTED,
        enabled=True,
        mechanism="explicit_breakpoint",
        minimum_tokens=1024,
        ttl=300,
        explicit_breakpoint=True,
        automatic=False,
        supports_cache_write_telemetry=True,
        supports_cache_read_telemetry=True,
        pricing_model="claude-3-5-sonnet",
        description="Anthropic Prompt Caching with explicit cache_control breakpoints and 5-minute TTL.",
    ),
    "openai": PromptCachePolicy(
        provider_name="openai",
        status=ProviderCacheStatus.SUPPORTED,
        enabled=True,
        mechanism="automatic",
        minimum_tokens=1024,
        ttl=300,
        explicit_breakpoint=False,
        automatic=True,
        supports_cache_write_telemetry=False,
        supports_cache_read_telemetry=True,
        pricing_model="gpt-4o",
        description="OpenAI Automatic Prefix Caching for prompts >= 1024 tokens.",
    ),
    "deepseek": PromptCachePolicy(
        provider_name="deepseek",
        status=ProviderCacheStatus.SUPPORTED,
        enabled=True,
        mechanism="automatic",
        minimum_tokens=64,
        ttl=300,
        explicit_breakpoint=False,
        automatic=True,
        supports_cache_write_telemetry=True,
        supports_cache_read_telemetry=True,
        pricing_model="deepseek-chat",
        description="DeepSeek automatic context caching with 64-token minimum.",
    ),
    "gemini": PromptCachePolicy(
        provider_name="gemini",
        status=ProviderCacheStatus.PARTIALLY_SUPPORTED,
        enabled=True,
        mechanism="context_cache",
        minimum_tokens=32768,
        ttl=3600,
        explicit_breakpoint=True,
        automatic=False,
        supports_cache_write_telemetry=True,
        supports_cache_read_telemetry=True,
        pricing_model="gemini-1.5-pro",
        description="Google Gemini explicit context caching supported for large corpora (>32k tokens).",
    ),
    "groq": PromptCachePolicy(
        provider_name="groq",
        status=ProviderCacheStatus.NOT_SUPPORTED,
        enabled=False,
        mechanism="none",
        minimum_tokens=0,
        ttl=0,
        explicit_breakpoint=False,
        automatic=False,
        supports_cache_write_telemetry=False,
        supports_cache_read_telemetry=False,
        pricing_model="groq-lpu",
        description="Groq LPU architecture does not offer persistent prompt KV caching.",
    ),
}


def get_provider_cache_policy(provider_or_model: str) -> PromptCachePolicy:
    """Resolve provider cache policy from provider name or model identifier."""
    val = provider_or_model.lower().strip()

    if "claude" in val or "anthropic" in val:
        return POLICIES["anthropic"]
    if any(k in val for k in ("gpt", "openai", "o1", "o3", "chatgpt")):
        return POLICIES["openai"]
    if "deepseek" in val:
        return POLICIES["deepseek"]
    if "gemini" in val or "google" in val:
        return POLICIES["gemini"]
    if "groq" in val:
        return POLICIES["groq"]

    # Fallback to unknown/unsupported
    return PromptCachePolicy(
        provider_name=val,
        status=ProviderCacheStatus.UNKNOWN,
        enabled=False,
        mechanism="none",
        minimum_tokens=1024,
        ttl=0,
        explicit_breakpoint=False,
        automatic=False,
        supports_cache_write_telemetry=False,
        supports_cache_read_telemetry=False,
        pricing_model="default",
        description=f"Unknown caching behavior for provider/model {provider_or_model}.",
    )


def evaluate_cache_eligibility(
    policy: PromptCachePolicy,
    static_token_count: int,
    previous_prefix_hash: str | None = None,
    current_prefix_hash: str | None = None,
    has_contamination: bool = False,
) -> tuple[bool, CacheMissReason]:
    """Pre-flight check to determine if a prompt is eligible for upstream provider caching.

    Returns (is_eligible, expected_miss_reason).
    """
    if policy.status == ProviderCacheStatus.NOT_SUPPORTED:
        return False, CacheMissReason.PROVIDER_UNSUPPORTED

    if has_contamination:
        return False, CacheMissReason.DYNAMIC_DATA_CONTAMINATION

    if static_token_count < policy.minimum_tokens:
        return False, CacheMissReason.BELOW_MINIMUM_SIZE

    if (
        previous_prefix_hash is not None
        and current_prefix_hash is not None
        and previous_prefix_hash != current_prefix_hash
    ):
        return True, CacheMissReason.PREFIX_CHANGED

    return True, CacheMissReason.NONE


# ==============================================================================
# SECTION 4: Provider-Specific Prompt Cache Adapter Interfaces
# ==============================================================================


class ProviderPromptCacheAdapter(ABC):
    """Abstract interface defining provider-specific prompt cache handling."""

    @abstractmethod
    def prepare_request(
        self,
        static_prefix: str,
        dynamic_suffix: str,
        model: str,
        is_eligible: bool,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Prepare provider-specific API payload including breakpoints if supported."""
        ...

    @abstractmethod
    def parse_usage(self, response_data: dict[str, Any]) -> dict[str, int]:
        """Extract cache_read, cache_write, uncached_input, and output tokens from response."""
        ...

    def calculate_cache_cost(
        self,
        model: str,
        uncached_input_tokens: int,
        cached_input_tokens: int,
        cache_write_tokens: int = 0,
        output_tokens: int = 0,
    ) -> ProviderCostBreakdown:
        """Calculate provider-specific cost and FinOps savings."""
        return calculate_provider_costs(
            model=model,
            uncached_input_tokens=uncached_input_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            output_tokens=output_tokens,
        )

    @abstractmethod
    def cache_capabilities(self) -> PromptCachePolicy:
        """Return provider-specific cache policy capabilities."""
        ...


class AnthropicPromptCacheAdapter(ProviderPromptCacheAdapter):
    """Anthropic adapter injecting explicit cache_control breakpoints."""

    def cache_capabilities(self) -> PromptCachePolicy:
        return POLICIES["anthropic"]

    def prepare_request(
        self,
        static_prefix: str,
        dynamic_suffix: str,
        model: str,
        is_eligible: bool,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        anthropic_model = (
            model if "claude" in model.lower() else "claude-3-5-sonnet-20241022"
        )
        system_blocks: list[dict[str, Any]] = []

        if is_eligible and static_prefix.strip():
            system_blocks.append(
                {
                    "type": "text",
                    "text": static_prefix.strip(),
                    "cache_control": {"type": "ephemeral"},
                }
            )
        elif static_prefix.strip():
            system_blocks.append({"type": "text", "text": static_prefix.strip()})

        payload: dict[str, Any] = {
            "model": anthropic_model,
            "system": system_blocks,
            "messages": [{"role": "user", "content": dynamic_suffix}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def parse_usage(self, response_data: dict[str, Any]) -> dict[str, int]:
        usage = response_data.get("usage", {})
        return {
            "cached_input_tokens": usage.get("cache_read_input_tokens", 0),
            "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
            "uncached_input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }


class OpenAIPromptCacheAdapter(ProviderPromptCacheAdapter):
    """OpenAI adapter leveraging automatic prefix caching."""

    def cache_capabilities(self) -> PromptCachePolicy:
        return POLICIES["openai"]

    def prepare_request(
        self,
        static_prefix: str,
        dynamic_suffix: str,
        model: str,
        is_eligible: bool,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        _ = is_eligible
        openai_model = (
            model
            if any(k in model.lower() for k in ("gpt", "o1", "o3"))
            else "gpt-4o-mini"
        )
        messages: list[dict[str, str]] = []
        if static_prefix.strip():
            messages.append({"role": "system", "content": static_prefix.strip()})
        messages.append({"role": "user", "content": dynamic_suffix})

        payload: dict[str, Any] = {
            "model": openai_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def parse_usage(self, response_data: dict[str, Any]) -> dict[str, int]:
        usage = response_data.get("usage", {})
        total_prompt = usage.get("prompt_tokens", 0)
        prompt_details = usage.get("prompt_tokens_details", {})
        cached = prompt_details.get("cached_tokens", 0)
        return {
            "cached_input_tokens": cached,
            "cache_write_tokens": 0,
            "uncached_input_tokens": max(0, total_prompt - cached),
            "output_tokens": usage.get("completion_tokens", 0),
        }


class GeminiPromptCacheAdapter(ProviderPromptCacheAdapter):
    """Gemini adapter for Google generative language API."""

    def cache_capabilities(self) -> PromptCachePolicy:
        return POLICIES["gemini"]

    def prepare_request(
        self,
        static_prefix: str,
        dynamic_suffix: str,
        model: str,
        is_eligible: bool,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        _ = (model, is_eligible, tools)
        return {
            "contents": [{"parts": [{"text": dynamic_suffix}]}],
            "systemInstruction": {"parts": [{"text": static_prefix}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

    def parse_usage(self, response_data: dict[str, Any]) -> dict[str, int]:
        usage_meta = response_data.get("usageMetadata", {})
        prompt_count = usage_meta.get("promptTokenCount", 0)
        cached_count = usage_meta.get("cachedContentTokenCount", 0)
        return {
            "cached_input_tokens": cached_count,
            "cache_write_tokens": 0,
            "uncached_input_tokens": max(0, prompt_count - cached_count),
            "output_tokens": usage_meta.get("candidatesTokenCount", 0),
        }


class DeepSeekPromptCacheAdapter(ProviderPromptCacheAdapter):
    """DeepSeek adapter for automatic context caching."""

    def cache_capabilities(self) -> PromptCachePolicy:
        return POLICIES["deepseek"]

    def prepare_request(
        self,
        static_prefix: str,
        dynamic_suffix: str,
        model: str,
        is_eligible: bool,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        _ = (is_eligible, tools)
        messages: list[dict[str, str]] = []
        if static_prefix.strip():
            messages.append({"role": "system", "content": static_prefix.strip()})
        messages.append({"role": "user", "content": dynamic_suffix})
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    def parse_usage(self, response_data: dict[str, Any]) -> dict[str, int]:
        usage = response_data.get("usage", {})
        prompt_details = usage.get("prompt_tokens_details", {})
        cached = prompt_details.get("cached_tokens", 0)
        total_prompt = usage.get("prompt_tokens", 0)
        return {
            "cached_input_tokens": cached,
            "cache_write_tokens": 0,
            "uncached_input_tokens": max(0, total_prompt - cached),
            "output_tokens": usage.get("completion_tokens", 0),
        }


class GroqPromptCacheAdapter(ProviderPromptCacheAdapter):
    """Groq adapter indicating unsupported prompt KV caching."""

    def cache_capabilities(self) -> PromptCachePolicy:
        return POLICIES["groq"]

    def prepare_request(
        self,
        static_prefix: str,
        dynamic_suffix: str,
        model: str,
        is_eligible: bool,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        _ = (is_eligible, tools)
        messages: list[dict[str, str]] = []
        if static_prefix.strip():
            messages.append({"role": "system", "content": static_prefix.strip()})
        messages.append({"role": "user", "content": dynamic_suffix})
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    def parse_usage(self, response_data: dict[str, Any]) -> dict[str, int]:
        usage = response_data.get("usage", {})
        return {
            "cached_input_tokens": 0,
            "cache_write_tokens": 0,
            "uncached_input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }


def get_provider_adapter(provider_or_model: str) -> ProviderPromptCacheAdapter:
    """Resolve provider prompt cache adapter from model name or provider identifier."""
    val = provider_or_model.lower().strip()
    if "claude" in val or "anthropic" in val:
        return AnthropicPromptCacheAdapter()
    if any(k in val for k in ("gpt", "openai", "o1", "o3", "chatgpt")):
        return OpenAIPromptCacheAdapter()
    if "deepseek" in val:
        return DeepSeekPromptCacheAdapter()
    if "gemini" in val or "google" in val:
        return GeminiPromptCacheAdapter()
    if "groq" in val:
        return GroqPromptCacheAdapter()
    return OpenAIPromptCacheAdapter()
