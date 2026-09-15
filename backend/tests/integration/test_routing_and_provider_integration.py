"""Comprehensive Routing & Provider Integration Test Suite (INT-021).

Verifies interactions between real JakeAI routing and provider components:
1. WorkloadClassifier -> RoutingPolicy formulation -> ModelRouter.route -> RoutingDecision
2. Multi-objective scoring (Quality floor guardrail, Cost-aware weights, non-loopback fallback chains)
3. FailoverManager.execute_with_failover across real provider adapters (OpenAI, Gemini, Local)
   using in-process mock HTTP transports (zero external API calls).

Mandatory failure cases tested across routing & provider boundary:
- unavailable (Primary returns HTTP 503 -> FailoverManager falls back to secondary candidate)
- timeout (Primary raises ReadTimeout -> FailoverManager falls back to secondary candidate)
- malformed response (Primary returns invalid JSON -> wrapped in ProviderUnavailableError -> fails over)
- connection failure (Primary raises ConnectError -> wrapped in ProviderUnavailableError -> fails over)
- partial failure (Primary candidate retries capped by max_retries_per_provider before failover)
- recovery (All fallback candidates fail -> raises truthful ProviderError without fabricating response)
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.providers.base import (
    ProviderCacheTelemetry,
    ProviderRequest,
)
from app.providers.errors import (
    ErrorCategory,
    ProviderError,
)
from app.providers.gemini import GeminiAdapter
from app.providers.openai import OpenAIAdapter
from app.routing.failover import FailoverConfig, FailoverManager
from app.routing.router import (
    ModelRouter,
    RoutingDecision,
    RoutingPolicy,
)
from app.routing.workload_classifier import WorkloadClassifier


async def _mock_credential_resolver(tenant_id: str, provider_name: str) -> str:
    """Async credential resolver test double."""
    return "mock-resolver-key"


def _make_mock_openai_response(
    content: str = "Analysis completed successfully.",
    model: str = "gpt-4o-mini",
    prompt_tokens: int = 50,
    completion_tokens: int = 25,
) -> dict[str, Any]:
    """Generate canonical OpenAI chat completion payload."""
    return {
        "id": "chatcmpl-mock-123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {
                "cached_tokens": 0,
            },
        },
    }


def _make_mock_gemini_response(
    content: str = "Gemini financial analysis output.",
    model: str = "gemini-2.0-flash",
) -> dict[str, Any]:
    """Generate canonical Gemini API completion payload."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": content}],
                    "role": "model",
                },
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 45,
            "candidatesTokenCount": 30,
            "totalTokenCount": 75,
            "cachedContentTokenCount": 0,
        },
        "modelVersion": model,
    }


@pytest.mark.asyncio
class TestRoutingPipelineIntegration:
    """Integration tests verifying end-to-end classification, routing, and provider dispatch."""

    async def test_workload_classification_to_model_routing_pipeline(self) -> None:
        """Integration 1: Classifier output drives Router policy and non-loopback fallback generation."""
        classifier = WorkloadClassifier()
        router = ModelRouter()

        prompt = "Please calculate the ebitda variance step-by-step from the balance sheet and financial statement analysis."
        classified = classifier.classify(prompt)

        assert classified.workload_class in ("financial_reasoning", "reasoning")
        assert classified.quality_requirement >= 0.85

        policy = RoutingPolicy(
            requested_model="default",
            workload_class=classified.workload_class,
            quality_requirement=classified.quality_requirement,
            required_capabilities=classified.required_capabilities,
            tenant_id="tenant-routing-1",
        )

        decision = router.route(policy)

        # 1. Primary selected candidate exists
        assert decision.selected_provider in (
            "openai",
            "gemini",
            "anthropic",
            "deepseek",
            "groq",
        )
        assert decision.selected_model is not None

        # 2. Fallback chain exists and has no loopback to primary candidate
        assert len(decision.fallback_chain) >= 1
        primary_pair = (decision.selected_provider, decision.selected_model)
        assert primary_pair not in decision.fallback_chain

    async def test_cost_aware_routing_with_budget_constraint(self) -> None:
        """Integration 2: Cost-aware routing selects cost-effective models with savings calculation."""
        router = ModelRouter()

        policy = RoutingPolicy(
            requested_model="default",
            workload_class="simple_chat",
            cost_aware_routing=True,
            tenant_id="tenant-routing-cost",
        )

        decision = router.route(policy)
        assert decision.selected_model in (
            "gpt-4o-mini",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "llama-3.1-8b-instant",
            "local-model",
            "claude-3-haiku",
        )
        assert decision.cost_savings_usd_per_million >= 0.0

    async def test_provider_adapters_contract_compliance(self) -> None:
        """Integration 3: OpenAI and Gemini adapters complete normalized requests via MockTransport."""

        # Test OpenAI Adapter
        def _openai_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=_make_mock_openai_response(content="OpenAI hello")
            )

        openai_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_openai_handler)
        )
        openai_adapter = OpenAIAdapter()
        req_openai = ProviderRequest(
            model="gpt-4o-mini",
            prompt="Hello from OpenAI test",
            tenant_id="ten-openai",
            api_key="mock-openai-key",
        )
        res_openai = await openai_adapter.complete(req_openai, client=openai_client)
        assert res_openai.text == "OpenAI hello"
        assert res_openai.provider == "openai"
        assert isinstance(res_openai.telemetry, ProviderCacheTelemetry)
        await openai_client.aclose()

        # Test Gemini Adapter
        def _gemini_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=_make_mock_gemini_response(content="Gemini hello")
            )

        gemini_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_gemini_handler)
        )
        gemini_adapter = GeminiAdapter()
        req_gemini = ProviderRequest(
            model="gemini-2.0-flash",
            prompt="Hello from Gemini test",
            tenant_id="ten-gemini",
            api_key="mock-gemini-key",
        )
        res_gemini = await gemini_adapter.complete(req_gemini, client=gemini_client)
        assert res_gemini.text == "Gemini hello"
        assert res_gemini.provider == "gemini"
        await gemini_client.aclose()

    async def test_cross_provider_failover_execution(self) -> None:
        """Integration 4: FailoverManager automatically switches to fallback candidate upon primary failure."""
        primary_called = False
        fallback_called = False

        def _failover_transport_handler(request: httpx.Request) -> httpx.Response:
            nonlocal primary_called, fallback_called
            url_str = str(request.url)
            if "openai.com" in url_str:
                primary_called = True
                return httpx.Response(
                    503, json={"error": {"message": "OpenAI overloaded"}}
                )
            if "googleapis.com" in url_str:
                fallback_called = True
                return httpx.Response(
                    200,
                    json=_make_mock_gemini_response(content="Gemini fallback response"),
                )
            return httpx.Response(404)

        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_failover_transport_handler)
        )

        config = FailoverConfig(
            max_retries_per_provider=0,  # Switch immediately on error
            max_total_attempts=3,
            base_delay_seconds=0.01,
        )
        failover_mgr = FailoverManager(config=config)

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["primary gpt-4o-mini with gemini fallback"],
        )

        provider_req = ProviderRequest(
            model="gpt-4o-mini",
            prompt="Run query across failover boundary",
            tenant_id="ten-failover",
            api_key="mock-key",
        )

        response = await failover_mgr.execute_with_failover(
            request=provider_req,
            decision=decision,
            client=mock_client,
            credential_resolver=_mock_credential_resolver,
        )

        assert primary_called is True
        assert fallback_called is True
        assert response.text == "Gemini fallback response"
        assert response.provider == "gemini"
        await mock_client.aclose()


@pytest.mark.asyncio
class TestRoutingAndProviderMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable(self) -> None:
        """Failure Case 1: Primary provider 503 triggers failover to healthy secondary."""

        def _transport(request: httpx.Request) -> httpx.Response:
            if "openai.com" in str(request.url):
                return httpx.Response(
                    503, json={"error": {"message": "Service Unavailable"}}
                )
            return httpx.Response(
                200, json=_make_mock_gemini_response("Recovered via Gemini")
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(_transport))
        failover_mgr = FailoverManager(
            config=FailoverConfig(max_retries_per_provider=0, base_delay_seconds=0.01)
        )

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["failover test"],
        )

        resp = await failover_mgr.execute_with_failover(
            request=ProviderRequest(model="gpt-4o-mini", prompt="Test", api_key="k"),
            decision=decision,
            client=client,
            credential_resolver=_mock_credential_resolver,
        )
        assert resp.text == "Recovered via Gemini"
        await client.aclose()

    async def test_failure_case_2_timeout(self) -> None:
        """Failure Case 2: Primary provider timeout triggers failover to secondary."""

        def _transport(request: httpx.Request) -> httpx.Response:
            if "openai.com" in str(request.url):
                raise httpx.ReadTimeout("Read timed out after 30s")
            return httpx.Response(
                200, json=_make_mock_gemini_response("Recovered after timeout")
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(_transport))
        failover_mgr = FailoverManager(
            config=FailoverConfig(max_retries_per_provider=0, base_delay_seconds=0.01)
        )

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["timeout failover test"],
        )

        resp = await failover_mgr.execute_with_failover(
            request=ProviderRequest(model="gpt-4o-mini", prompt="Test", api_key="k"),
            decision=decision,
            client=client,
            credential_resolver=_mock_credential_resolver,
        )
        assert resp.text == "Recovered after timeout"
        await client.aclose()

    async def test_failure_case_3_malformed_response(self) -> None:
        """Failure Case 3: Primary returns invalid JSON -> ProviderError -> failover succeeds."""

        def _transport(request: httpx.Request) -> httpx.Response:
            if "openai.com" in str(request.url):
                return httpx.Response(200, text="Not valid JSON at all")
            return httpx.Response(
                200,
                json=_make_mock_gemini_response("Recovered from malformed response"),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(_transport))
        failover_mgr = FailoverManager(
            config=FailoverConfig(max_retries_per_provider=0, base_delay_seconds=0.01)
        )

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["malformed failover test"],
        )

        resp = await failover_mgr.execute_with_failover(
            request=ProviderRequest(model="gpt-4o-mini", prompt="Test", api_key="k"),
            decision=decision,
            client=client,
            credential_resolver=_mock_credential_resolver,
        )
        assert resp.text == "Recovered from malformed response"
        await client.aclose()

    async def test_failure_case_4_connection_failure(self) -> None:
        """Failure Case 4: Primary raises ConnectError -> ProviderUnavailableError -> failover succeeds."""

        def _transport(request: httpx.Request) -> httpx.Response:
            if "openai.com" in str(request.url):
                raise httpx.ConnectError("Connection refused by upstream gateway")
            return httpx.Response(
                200,
                json=_make_mock_gemini_response("Recovered from connection failure"),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(_transport))
        failover_mgr = FailoverManager(
            config=FailoverConfig(max_retries_per_provider=0, base_delay_seconds=0.01)
        )

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["connection failure failover test"],
        )

        resp = await failover_mgr.execute_with_failover(
            request=ProviderRequest(model="gpt-4o-mini", prompt="Test", api_key="k"),
            decision=decision,
            client=client,
            credential_resolver=_mock_credential_resolver,
        )
        assert resp.text == "Recovered from connection failure"
        await client.aclose()

    async def test_failure_case_5_partial_failure_bounded_attempts(self) -> None:
        """Failure Case 5: Primary retries are bounded by max_retries_per_provider before failover."""
        primary_attempts = 0

        def _transport(request: httpx.Request) -> httpx.Response:
            nonlocal primary_attempts
            if "openai.com" in str(request.url):
                primary_attempts += 1
                return httpx.Response(
                    503, json={"error": {"message": "503 overloaded"}}
                )
            return httpx.Response(
                200, json=_make_mock_gemini_response("Recovered after primary retries")
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(_transport))
        failover_mgr = FailoverManager(
            config=FailoverConfig(
                max_retries_per_provider=2,
                max_total_attempts=5,
                base_delay_seconds=0.01,
            )
        )

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["partial failure bounded attempts"],
        )

        resp = await failover_mgr.execute_with_failover(
            request=ProviderRequest(model="gpt-4o-mini", prompt="Test", api_key="k"),
            decision=decision,
            client=client,
            credential_resolver=_mock_credential_resolver,
        )
        # Primary was tried 1 initial + 2 retries = 3 attempts before failover
        assert primary_attempts == 3
        assert resp.text == "Recovered after primary retries"
        await client.aclose()

    async def test_failure_case_6_recovery_exhausted_candidates(self) -> None:
        """Failure Case 6: Total failure when all candidates fail raises truthful ProviderError."""

        def _transport(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                503, json={"error": {"message": "All providers completely down"}}
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(_transport))
        failover_mgr = FailoverManager(
            config=FailoverConfig(
                max_retries_per_provider=0,
                max_total_attempts=2,
                base_delay_seconds=0.01,
            )
        )

        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o-mini",
            fallback_chain=[("gemini", "gemini-2.0-flash")],
            policy_applied="test",
            decision_reasons=["all candidates fail test"],
        )

        with pytest.raises(ProviderError) as exc_info:
            await failover_mgr.execute_with_failover(
                request=ProviderRequest(
                    model="gpt-4o-mini", prompt="Test", api_key="k"
                ),
                decision=decision,
                client=client,
                credential_resolver=_mock_credential_resolver,
            )

        assert exc_info.value.category in (
            ErrorCategory.PROVIDER_UNAVAILABLE,
            ErrorCategory.RETRYABLE,
        )
        assert exc_info.value.status_code == 503
        await client.aclose()
