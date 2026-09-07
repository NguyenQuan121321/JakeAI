"""JakeAI Provider Subsystem.

Clean provider abstraction layer providing unified inference contracts,
explicit model capabilities, normalized errors, and isolated provider adapters.
"""

from app.providers.anthropic import AnthropicAdapter
from app.providers.base import (
    LLMProvider,
    ModelCapabilities,
    ModelCapabilityCatalog,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
    get_model_capabilities,
)
from app.providers.deepseek import DeepSeekAdapter
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
    ProviderContextLimitError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderPolicyError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    normalize_provider_error,
    sanitize_error_message,
)
from app.providers.gemini import GeminiAdapter
from app.providers.groq import GroqAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter
from app.providers.registry import ProviderRegistry, get_provider_registry

__all__ = [
    "AnthropicAdapter",
    "DeepSeekAdapter",
    "ErrorCategory",
    "GeminiAdapter",
    "GroqAdapter",
    "LLMProvider",
    "ModelCapabilities",
    "ModelCapabilityCatalog",
    "OpenAIAdapter",
    "OpenRouterAdapter",
    "ProviderAuthenticationError",
    "ProviderContextLimitError",
    "ProviderError",
    "ProviderInvalidRequestError",
    "ProviderPolicyError",
    "ProviderQuotaError",
    "ProviderRateLimitError",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "StreamChunk",
    "get_model_capabilities",
    "get_provider_registry",
    "normalize_provider_error",
    "sanitize_error_message",
]
