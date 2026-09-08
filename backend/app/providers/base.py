"""Core LLM Provider Interface, Protocol, and Capabilities Model.

Establishes:
1. LLMProvider protocol matching Phase 01 specifications (complete, stream, capabilities).
2. Explicit ModelCapabilities schema and catalog (no string-matching guessing for capabilities).
3. Stable ProviderRequest, ProviderResponse, and StreamChunk data contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.optimizer.provider_cache_policy import (
    CacheMissReason,
    get_provider_cache_policy,
)
from app.optimizer.provider_pricing import get_model_pricing
from app.optimizer.two_zone_compiler import CompiledPrompt  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx


class ProviderCacheTelemetry(BaseModel):
    """Fine-grained telemetry returned strictly from upstream provider usage metadata."""

    is_cache_eligible: bool = Field(
        default=False,
        description="Whether static prefix met minimum token size and provider policy",
    )
    cache_hit: bool = Field(
        default=False,
        description="Rule 1: ONLY True if upstream reported > 0 cached tokens",
    )
    cached_tokens: int = Field(
        default=0,
        description="Tokens read from upstream prompt cache (Anthropic cache_read, OpenAI cached_tokens)",
    )
    uncached_input_tokens: int = Field(
        default=0,
        description="Uncached input tokens processed by upstream provider",
    )
    cache_write_tokens: int = Field(
        default=0,
        description="Tokens written to upstream prompt cache (Anthropic cache_creation)",
    )
    output_tokens: int = Field(
        default=0, description="Tokens generated in upstream completion"
    )
    prefix_hash: str | None = Field(
        default=None, description="SHA-256 fingerprint of Zone 1 static prefix"
    )
    miss_reason: str = Field(
        default=CacheMissReason.NONE.value,
        description="Attribution reason for provider cache miss",
    )
    provider: str = Field(default="unknown")
    model: str = Field(default="unknown")
    latency_ms: float = Field(default=0.0)
    estimated_baseline_cost_usd: float = Field(default=0.0)
    actual_cost_usd: float = Field(default=0.0)
    estimated_savings_usd: float = Field(default=0.0)
    savings_percentage: float = Field(default=0.0)
    turn_count: int = Field(default=1, description="Number of conversation turns in request")


class UpstreamLLMResponse(BaseModel):
    """Comprehensive upstream response with text completion and telemetry."""

    text: str
    model: str
    provider: str
    telemetry: ProviderCacheTelemetry


class ModelCapabilities(BaseModel):
    """Explicit capability metadata for an upstream model.

    As required by Phase 01 Section 3:
    provider, model, context_window, supports_streaming, supports_tools,
    supports_json, supports_prompt_cache, supports_embeddings, supports_reasoning,
    input_pricing, output_pricing, cache_pricing, cache_write_pricing.
    """

    provider: str
    model: str
    context_window: int = Field(
        default=128_000, description="Maximum context window in tokens"
    )
    supports_streaming: bool = Field(
        default=True, description="Whether model supports SSE/chunk streaming"
    )
    supports_tools: bool = Field(
        default=True, description="Whether model supports function calling / tool use"
    )
    supports_json: bool = Field(
        default=True,
        description="Whether model supports JSON mode / structured outputs",
    )
    supports_prompt_cache: bool = Field(
        default=False,
        description="Whether provider prompt caching is supported for this model",
    )
    supports_embeddings: bool = Field(
        default=False, description="Whether model can produce dense vector embeddings"
    )
    supports_reasoning: bool = Field(
        default=False,
        description="Whether model has extended thinking / chain-of-thought",
    )
    input_pricing: float = Field(
        default=0.0, description="USD rate per 1,000,000 input tokens"
    )
    output_pricing: float = Field(
        default=0.0, description="USD rate per 1,000,000 output tokens"
    )
    cache_pricing: float = Field(
        default=0.0, description="USD rate per 1,000,000 cached read tokens"
    )
    cache_write_pricing: float = Field(
        default=0.0, description="USD rate per 1,000,000 cache write tokens"
    )
    min_cache_tokens: int = Field(
        default=1024,
        description="Minimum tokens required for prompt caching eligibility",
    )


class ChatMessage(BaseModel):
    """OpenAI-compatible message format for multi-turn conversations."""

    role: str = Field(..., description="Role: system, user, assistant, tool")
    content: str = Field(default="", description="Message text content")
    name: str | None = Field(default=None, description="Optional author or tool name")


class ProviderRequest(BaseModel):
    """Unified request contract passed to LLMProvider adapters."""

    model: str = Field(..., description="Target model name")
    prompt: str = Field(..., description="User prompt or query")
    messages: list[ChatMessage] | None = Field(
        default=None, description="Structured multi-turn conversation messages"
    )
    system_instruction: str | None = Field(
        default=None, description="System instructions / prompt"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)
    compiled_prompt: CompiledPrompt | None = Field(
        default=None, description="Optional pre-compiled two-zone prompt"
    )
    tools: list[dict[str, Any]] | None = Field(
        default=None, description="Tool definitions / functions"
    )
    tenant_id: str = Field(default="default", description="Tenant identifier for BYOK")
    api_key: str | None = Field(
        default=None,
        description="Explicit decrypted key if provided; otherwise resolved by adapter",
    )
    response_format: dict[str, Any] | None = Field(
        default=None, description="Optional structured format / JSON schema"
    )
    extra_headers: dict[str, str] | None = Field(
        default=None, description="Provider-specific headers"
    )
    extra_params: dict[str, Any] | None = Field(
        default=None, description="Provider-specific payload overrides"
    )


class ProviderResponse(BaseModel):
    """Unified completion response returned by LLMProvider adapters.

    Fully compatible with existing UpstreamLLMResponse.
    """

    text: str
    model: str
    provider: str
    telemetry: ProviderCacheTelemetry = Field(
        ..., description="ProviderCacheTelemetry object"
    )
    finish_reason: str | None = Field(default="stop")
    raw_usage: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] | None = Field(default=None)


class StreamChunk(BaseModel):
    """Streaming chunk emitted during SSE or token streaming."""

    delta_text: str = Field(default="", description="Incremental text token(s)")
    model: str = Field(..., description="Model generating chunk")
    provider: str = Field(..., description="Provider name")
    finish_reason: str | None = Field(default=None)
    telemetry: Any | None = Field(
        default=None, description="Usage/telemetry emitted in final chunk"
    )
    tool_call_chunks: list[dict[str, Any]] | None = Field(default=None)


@runtime_checkable
class LLMProvider(Protocol):
    """Stable internal provider interface required by Phase 01 Section 2."""

    provider_name: str

    async def complete(
        self,
        request: ProviderRequest,
        client: httpx.AsyncClient | None = None,
    ) -> ProviderResponse:
        """Execute a non-streaming completion."""
        ...

    def stream(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion tokens asynchronously with continuous TTFT tracking."""
        ...

    def capabilities(self, model: str) -> ModelCapabilities:
        """Return explicit capabilities for the given model under this provider."""
        ...


class ModelCapabilityCatalog:
    """Explicit catalog of known model capabilities across all supported providers."""

    _CATALOG: dict[str, ModelCapabilities] = {
        # Anthropic
        "claude-3-5-sonnet": ModelCapabilities(
            provider="anthropic",
            model="claude-3-5-sonnet",
            context_window=200_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=3.00,
            output_pricing=15.00,
            cache_pricing=0.30,
            cache_write_pricing=3.75,
            min_cache_tokens=1024,
        ),
        "claude-3-haiku": ModelCapabilities(
            provider="anthropic",
            model="claude-3-haiku",
            context_window=200_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.25,
            output_pricing=1.25,
            cache_pricing=0.025,
            cache_write_pricing=0.30,
            min_cache_tokens=1024,
        ),
        "claude-3-opus": ModelCapabilities(
            provider="anthropic",
            model="claude-3-opus",
            context_window=200_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=15.00,
            output_pricing=75.00,
            cache_pricing=1.50,
            cache_write_pricing=18.75,
            min_cache_tokens=1024,
        ),
        # OpenAI
        "gpt-4o": ModelCapabilities(
            provider="openai",
            model="gpt-4o",
            context_window=128_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=2.50,
            output_pricing=10.00,
            cache_pricing=1.25,
            cache_write_pricing=2.50,
            min_cache_tokens=1024,
        ),
        "gpt-4o-mini": ModelCapabilities(
            provider="openai",
            model="gpt-4o-mini",
            context_window=128_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.15,
            output_pricing=0.60,
            cache_pricing=0.075,
            cache_write_pricing=0.15,
            min_cache_tokens=1024,
        ),
        "o1": ModelCapabilities(
            provider="openai",
            model="o1",
            context_window=200_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=True,
            input_pricing=15.00,
            output_pricing=60.00,
            cache_pricing=7.50,
            cache_write_pricing=15.00,
            min_cache_tokens=1024,
        ),
        "o3-mini": ModelCapabilities(
            provider="openai",
            model="o3-mini",
            context_window=200_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=True,
            input_pricing=1.10,
            output_pricing=4.40,
            cache_pricing=0.55,
            cache_write_pricing=1.10,
            min_cache_tokens=1024,
        ),
        # Google Gemini
        "gemini-1.5-flash": ModelCapabilities(
            provider="gemini",
            model="gemini-1.5-flash",
            context_window=1_048_576,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.075,
            output_pricing=0.30,
            cache_pricing=0.01875,
            cache_write_pricing=0.075,
            min_cache_tokens=32768,
        ),
        "gemini-1.5-pro": ModelCapabilities(
            provider="gemini",
            model="gemini-1.5-pro",
            context_window=2_097_152,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=3.50,
            output_pricing=10.50,
            cache_pricing=0.875,
            cache_write_pricing=3.50,
            min_cache_tokens=32768,
        ),
        "gemini-2.0-flash": ModelCapabilities(
            provider="gemini",
            model="gemini-2.0-flash",
            context_window=1_048_576,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.10,
            output_pricing=0.40,
            cache_pricing=0.025,
            cache_write_pricing=0.10,
            min_cache_tokens=32768,
        ),
        # Groq
        "llama-3.3-70b-versatile": ModelCapabilities(
            provider="groq",
            model="llama-3.3-70b-versatile",
            context_window=128_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=False,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.59,
            output_pricing=0.79,
            cache_pricing=0.59,
            cache_write_pricing=0.59,
            min_cache_tokens=0,
        ),
        "llama-3.1-8b-instant": ModelCapabilities(
            provider="groq",
            model="llama-3.1-8b-instant",
            context_window=128_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=False,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.05,
            output_pricing=0.08,
            cache_pricing=0.05,
            cache_write_pricing=0.05,
            min_cache_tokens=0,
        ),
        # DeepSeek
        "deepseek-chat": ModelCapabilities(
            provider="deepseek",
            model="deepseek-chat",
            context_window=64_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=0.14,
            output_pricing=0.28,
            cache_pricing=0.014,
            cache_write_pricing=0.14,
            min_cache_tokens=64,
        ),
        "deepseek-reasoner": ModelCapabilities(
            provider="deepseek",
            model="deepseek-reasoner",
            context_window=64_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=True,
            supports_embeddings=False,
            supports_reasoning=True,
            input_pricing=0.55,
            output_pricing=2.19,
            cache_pricing=0.14,
            cache_write_pricing=0.55,
            min_cache_tokens=64,
        ),
        # OpenRouter
        "openrouter/auto": ModelCapabilities(
            provider="openrouter",
            model="openrouter/auto",
            context_window=128_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=False,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=2.00,
            output_pricing=8.00,
            cache_pricing=2.00,
            cache_write_pricing=2.00,
            min_cache_tokens=0,
        ),
    }

    @classmethod
    def get(cls, model: str, provider: str | None = None) -> ModelCapabilities:
        """Resolve explicit ModelCapabilities, falling back to base pricing/policy."""
        m_lower = model.lower().strip()

        # 1. Exact match first
        if m_lower in cls._CATALOG:
            cap = cls._CATALOG[m_lower]
            if not provider or cap.provider == provider:
                return cap

        # 2. Longer keys first to prevent 'gpt-4o' masking 'gpt-4o-mini'
        for k in sorted(cls._CATALOG.keys(), key=len, reverse=True):
            if k in m_lower or m_lower in k:
                cap = cls._CATALOG[k]
                if provider and cap.provider != provider:
                    continue
                return cap

        # Fallback to pricing catalog & cache policy synthesis
        pricing = get_model_pricing(model)
        policy = get_provider_cache_policy(model)
        prov = provider or pricing.provider

        return ModelCapabilities(
            provider=prov,
            model=model,
            context_window=128_000,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=policy.enabled,
            supports_embeddings=False,
            supports_reasoning="o1" in m_lower
            or "o3" in m_lower
            or "reasoner" in m_lower,
            input_pricing=pricing.input_per_million,
            output_pricing=pricing.output_per_million,
            cache_pricing=pricing.cache_read_per_million,
            cache_write_pricing=pricing.cache_write_per_million,
            min_cache_tokens=policy.min_cache_tokens,
        )

    @classmethod
    def list_all(cls) -> list[ModelCapabilities]:
        """Return all cataloged model capabilities."""
        return list(cls._CATALOG.values())


def get_model_capabilities(
    model: str, provider: str | None = None
) -> ModelCapabilities:
    """Helper to retrieve explicit ModelCapabilities for a model."""
    return ModelCapabilityCatalog.get(model, provider=provider)
