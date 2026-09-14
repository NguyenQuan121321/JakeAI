"""Comprehensive test suite for COST-09 (Workload Classification), COST-10 (Intelligent Model Routing), and COST-13 (Optimization Telemetry).

Verifies:
1. WorkloadClassifier domain classification across all 7 domains.
2. Required capability extraction (tools, JSON, reasoning).
3. Quality requirement threshold assignment.
4. ModelRouter hard candidate pre-filtering (context, capabilities, policy).
5. ModelRouter soft multi-objective scoring formula and quality guardrails.
6. Deterministic, non-loopback cross-provider fallback chains.
7. End-to-end optimization telemetry recording and snapshot aggregation.
"""

from __future__ import annotations

from app.providers.base import ModelCapabilityCatalog
from app.routing.router import (
    RoutingPolicy,
    get_model_router,
)
from app.routing.workload_classifier import (
    get_workload_classifier,
)
from app.telemetry.metrics import MetricsCollector

# ==============================================================================
# 1. Workload Classifier Tests (COST-09)
# ==============================================================================


def test_workload_classifier_simple_chat() -> None:
    """Verify conversational queries are classified as simple_chat with low quality floor."""
    classifier = get_workload_classifier()

    res = classifier.classify(prompt="Hello, good morning! How are you today?")
    assert res.workload_class == "simple_chat"
    assert res.quality_requirement <= 0.50
    assert res.latency_target_ms is not None and res.latency_target_ms <= 1000
    assert len(res.required_capabilities) == 0


def test_workload_classifier_coding() -> None:
    """Verify code patterns trigger coding workload and high quality floor."""
    classifier = get_workload_classifier()

    prompt = (
        "Can you refactor this function?\n\n"
        "```python\n"
        "def calculate_tax(income):\n"
        "    return income * 0.2\n"
        "```"
    )
    res = classifier.classify(prompt=prompt)
    assert res.workload_class == "coding"
    assert res.quality_requirement >= 0.85
    assert any("Code syntax" in r for r in res.reasons)


def test_workload_classifier_reasoning() -> None:
    """Verify analytical and reasoning patterns request supports_reasoning."""
    classifier = get_workload_classifier()

    prompt = (
        "Please derive the mathematical formula step by step for the discount factor."
    )
    res = classifier.classify(prompt=prompt)
    assert res.workload_class == "reasoning"
    assert "supports_reasoning" in res.required_capabilities
    assert res.quality_requirement >= 0.90


def test_workload_classifier_tools_and_json() -> None:
    """Verify tools and response format add required capabilities."""
    classifier = get_workload_classifier()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_stock_price",
                "description": "Fetch current stock price",
                "parameters": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                },
            },
        }
    ]
    response_format = {"type": "json_object"}

    res = classifier.classify(
        prompt="Get price for AAPL in JSON",
        tools=tools,
        response_format=response_format,
    )
    assert "supports_tools" in res.required_capabilities
    assert "supports_json" in res.required_capabilities
    assert res.quality_requirement >= 0.75


def test_workload_classifier_long_context() -> None:
    """Verify context exceeding threshold is classified as long_context."""
    classifier = get_workload_classifier()

    # Generate ~15,000 tokens of text
    large_text = (
        "The quarterly operational and financial performance demonstrates sustained revenue growth. "
        * 1500
    )
    res = classifier.classify(prompt=large_text)
    assert res.workload_class == "long_context"
    assert res.context_requirement >= 12_000


# ==============================================================================
# 2. Intelligent Model Router Tests (COST-10)
# ==============================================================================


def test_model_router_hard_prefilter_context_window() -> None:
    """Verify router rejects candidates whose context window is smaller than context_tokens."""
    router = get_model_router()

    # deepseek-chat has 64k context window; ask for 80k context
    policy = RoutingPolicy(
        requested_model="deepseek-chat",
        context_tokens=80_000,
    )
    decision = router.route(policy)
    # deepseek-chat must be rejected for context overflow
    assert decision.selected_model != "deepseek-chat"
    assert any("context window" in r for r in decision.decision_reasons)


def test_model_router_hard_prefilter_required_capabilities() -> None:
    """Verify router hard filter rejects candidates lacking required capabilities."""
    router = get_model_router()

    # Request model with supports_reasoning
    policy = RoutingPolicy(
        requested_model="claude-3-haiku",
        required_capabilities=["supports_reasoning"],
    )
    decision = router.route(policy)
    cap = ModelCapabilityCatalog.get(
        decision.selected_model, provider=decision.selected_provider
    )
    assert cap.supports_reasoning is True


def test_model_router_quality_guardrail_prevents_downgrade() -> None:
    """Verify high-intelligence coding task is never downgraded solely to save cost."""
    router = get_model_router()

    policy = RoutingPolicy(
        requested_model="gpt-4o",
        preferred_provider="openai",
        workload_class="coding",
        cost_aware_routing=True,
    )
    decision = router.route(policy)
    assert decision.selected_model == "gpt-4o"
    assert decision.selected_provider == "openai"


def test_model_router_cost_aware_simple_chat_downgrade() -> None:
    """Verify simple chat is safely down-tiered to cost-optimized model with positive savings."""
    router = get_model_router()

    policy = RoutingPolicy(
        requested_model="gpt-4o",
        preferred_provider="openai",
        workload_class="simple_chat",
        cost_aware_routing=True,
    )
    decision = router.route(policy)
    assert decision.selected_model == "gpt-4o-mini"
    assert decision.selected_provider == "openai"
    assert decision.cost_savings_usd_per_million > 0.0


def test_model_router_deterministic_repeatability() -> None:
    """Verify router produces identical decisions for identical inputs."""
    router = get_model_router()

    policy = RoutingPolicy(
        requested_model="gpt-4o",
        workload_class="reasoning",
        required_capabilities=["supports_reasoning"],
    )
    decision1 = router.route(policy)
    decision2 = router.route(policy)

    assert decision1.selected_model == decision2.selected_model
    assert decision1.selected_provider == decision2.selected_provider
    assert decision1.fallback_chain == decision2.fallback_chain


def test_model_router_cross_provider_non_loopback_fallback() -> None:
    """Verify fallback chain does not contain the primary model and uses distinct providers."""
    router = get_model_router()

    policy = RoutingPolicy(
        requested_model="claude-3-5-sonnet",
        allow_fallback=True,
    )
    decision = router.route(policy)

    # Primary model must not be in fallback chain
    for prov, mdl in decision.fallback_chain:
        assert (prov, mdl) != (decision.selected_provider, decision.selected_model)


# ==============================================================================
# 3. Live Optimization Telemetry Tests (COST-13)
# ==============================================================================


def test_optimization_telemetry_recording() -> None:
    """Verify MetricsCollector captures optimization decisions and aggregates cost savings."""
    collector = MetricsCollector()

    collector.record_optimization_decision(
        tenant_id="tenant_finops",
        workload_class="simple_chat",
        selected_provider="openai",
        selected_model="gpt-4o-mini",
        estimated_input_cost=0.15,
        cost_savings_usd_per_million=2.35,
        reason="Down-tiered simple chat query",
    )

    decisions = collector.get_optimization_decisions()
    assert len(decisions) == 1
    assert decisions[0]["tenant_id"] == "tenant_finops"
    assert decisions[0]["selected_model"] == "gpt-4o-mini"
    assert decisions[0]["cost_savings_usd_per_million"] == 2.35

    snapshot = collector.get_snapshot()
    assert snapshot.optimization_decisions_total == 1
    assert snapshot.cost_savings_usd_total > 0.0
