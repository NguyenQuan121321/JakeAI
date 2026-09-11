"""Provider Registry for managing and resolving LLMProvider adapters."""

from __future__ import annotations

import logging

from app.providers.anthropic import AnthropicAdapter
from app.providers.base import LLMProvider, ModelCapabilities, ModelCapabilityCatalog
from app.providers.deepseek import DeepSeekAdapter
from app.providers.gemini import GeminiAdapter
from app.providers.groq import GroqAdapter
from app.providers.local import LocalModelAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Central registry for LLMProvider adapters."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("anthropic", AnthropicAdapter())
        self.register("openai", OpenAIAdapter())
        self.register("gemini", GeminiAdapter())
        self.register("groq", GroqAdapter())
        self.register("deepseek", DeepSeekAdapter())
        self.register("openrouter", OpenRouterAdapter())
        self.register("local", LocalModelAdapter())

    def register(self, name: str, adapter: LLMProvider) -> None:
        self._providers[name.lower().strip()] = adapter

    def get(self, name: str) -> LLMProvider | None:
        return self._providers.get(name.lower().strip())

    def resolve_provider_name_for_model(self, model: str) -> str:
        m = model.lower().strip()
        if "local" in m or "ollama" in m or "vllm" in m:
            return "local"
        if "openrouter" in m or "/" in m:
            return "openrouter"
        if "claude" in m or "anthropic" in m:
            return "anthropic"
        if any(k in m for k in ("gpt", "o1", "o3", "openai")):
            return "openai"
        if "gemini" in m or "google" in m:
            return "gemini"
        if "groq" in m or "llama" in m:
            return "groq"
        if "deepseek" in m:
            return "deepseek"
        return "gemini"

    def resolve_for_model(
        self, model: str, preferred_provider: str | None = None
    ) -> LLMProvider:
        if preferred_provider:
            p = self.get(preferred_provider)
            if p:
                return p

        prov_name = self.resolve_provider_name_for_model(model)
        adapter = self.get(prov_name)
        if adapter:
            return adapter

        # Fallback to OpenAI or Gemini
        return (
            self._providers.get("openai")
            or self._providers.get("gemini")
            or next(iter(self._providers.values()))
        )

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    def list_capabilities(self) -> list[ModelCapabilities]:
        return ModelCapabilityCatalog.list_all()


_global_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ProviderRegistry()
    return _global_registry
