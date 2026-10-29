"""Hosted J02 only: replace external model adapters, retain actual Jake routes/services.

No identity, policy, store, cache, budget, or middleware implementation is replaced.
The isolated Docker network has no Internet route.
"""
import os

if os.environ.get("J02_SYNTHETIC_PROVIDER") != "1":
    raise RuntimeError("Synthetic fixture requires the isolated J02 job")

from app.main import app
from app.providers.base import ModelCapabilityCatalog, ProviderCacheTelemetry, ProviderResponse
from app.providers.registry import get_provider_registry


class SyntheticProvider:
    provider_name = "openai"

    async def complete(self, request, client=None):
        return ProviderResponse(text="synthetic " * 20000, model=request.model,
            provider="openai", telemetry=ProviderCacheTelemetry())

    async def stream(self, request, client=None):
        yield await self.complete(request, client)

    def capabilities(self, model):
        return ModelCapabilityCatalog.get(model)


get_provider_registry().register("openai", SyntheticProvider())
