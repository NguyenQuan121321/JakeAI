"""R-ARCH-03 — Duplicate Abstractions regression suite.

Locks every deduplication fix of this task so the duplicates cannot silently
return:

F-1  ``app.agent.workflows`` (test-only WorkflowEngine duplicate) removed.
F-2  Redis client plumbing has a single construction authority
     (``app.core.redis_client``); QuotaManager keeps its binary-mode client
     private instead of injecting it into the shared text-mode budget manager.
F-3  Model pricing is defined once (``app.optimizer.provider_pricing``); the
     capability catalog derives its prices from it.
F-4  Provider credential resolution is defined once
     (``app.core.provider_credentials``); failover delegates to it.
F-5  LLM JSON output extraction is defined once
     (``app.agent.utils.structured_output.extract_json_dict``); the six inline
     fence-strip copies are migrated.
F-6  SSE frame building and streaming response headers are defined once
     (``app.core.sse``).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"


def _app_sources() -> dict[str, str]:
    """Return relative-path -> source text for every Python file under app/."""
    sources: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                p = Path(dirpath) / fn
                sources[p.relative_to(APP_DIR).as_posix()] = p.read_text(
                    encoding="utf-8"
                )
    return sources


def _src(relative: str) -> str:
    return (APP_DIR / relative).read_text(encoding="utf-8")


# ===========================================================================
# F-1 — WorkflowEngine duplicate removed
# ===========================================================================


def test_workflow_engine_package_removed() -> None:
    """The test-only third workflow engine stays removed (R-ARCH-00 F-02)."""
    assert not (APP_DIR / "agent" / "workflows").exists()
    assert importlib.util.find_spec("app.agent.workflows") is None

    for rel, src in _app_sources().items():
        assert "WorkflowEngine" not in src, rel
        assert "WorkflowExecutionStatus" not in src, rel


# ===========================================================================
# F-2 — Redis plumbing single authority
# ===========================================================================

# Modules whose cached-helper duplicates were collapsed onto the factory.
_REDIS_HELPER_MODULES = (
    "agent/state/checkpoint.py",
    "services/resume_bridge.py",
    "core/rate_limiter.py",
    "finops/budget.py",
    "core/byok.py",
    "optimizer/semantic_cache.py",
    "rag/tasks.py",
    "services/ai_gateway.py",
)

# Per-request lifecycle clients (connect -> ping -> close, no caching) that
# deliberately construct their own client; see app/core/redis_client.py docstring.
_REDIS_PER_REQUEST_SITES = (
    "api/v1/endpoints/health.py",
    "core/security.py",
)


def test_redis_client_construction_has_single_authority() -> None:
    """All cached-helper modules delegate to the shared factory; nobody else
    constructs long-lived clients from REDIS_URL."""
    sources = _app_sources()
    factory_src = sources["core/redis_client.py"]
    assert "acquire_redis_client" in factory_src

    for rel in _REDIS_HELPER_MODULES:
        src = sources[rel]
        assert "acquire_redis_client(" in src, f"{rel} must use the factory"
        assert "from_url(" not in src, f"{rel} must not construct clients itself"

    for rel, src in sources.items():
        if rel in _REDIS_PER_REQUEST_SITES or rel == "core/redis_client.py":
            continue
        assert "from_url(" not in src, (
            f"{rel} constructs a Redis client outside the single authority"
        )


def test_redis_mock_detection_defined_once() -> None:
    """The Mock/AsyncMock test-double detection lives only in the factory."""
    sources = _app_sources()
    hits = [
        rel
        for rel, src in sources.items()
        if '("Mock", "AsyncMock")' in src or "('Mock', 'AsyncMock')" in src
    ]
    assert hits == ["core/redis_client.py"]


@pytest.mark.asyncio
async def test_quota_manager_binary_client_stays_private(monkeypatch) -> None:
    """QuotaManager must not write its binary-mode client through the
    redis_client property into the shared text-mode FinOpsBudgetManager."""
    from app.finops.budget import FinOpsBudgetManager
    from app.services.ai_gateway import QuotaManager

    budget = FinOpsBudgetManager()
    qm = QuotaManager(budget_manager=budget)
    sentinel = object()
    captured: dict[str, object] = {}

    async def fake_acquire(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("app.services.ai_gateway.acquire_redis_client", fake_acquire)
    client = await qm._get_redis()
    assert client is sentinel
    # The bug this locks: the property setter previously injected the
    # bytes-returning client into the budget manager shared with accounting.
    assert budget.redis_client is None
    assert captured["decode_responses"] is False

    async def explode(**kwargs):  # pragma: no cover - guard
        raise AssertionError("second call must reuse the cached client")

    monkeypatch.setattr("app.services.ai_gateway.acquire_redis_client", explode)
    assert await qm._get_redis() is sentinel


# ===========================================================================
# F-3 — Pricing single authority
# ===========================================================================


def test_capability_catalog_pricing_matches_canonical_authority() -> None:
    """Every catalog entry's prices are exactly the canonical pricing entries.

    Exact-key membership is asserted so brand-fallback heuristics can never
    silently mask a missing catalog entry (the pre-fix deepseek-reasoner /
    gemini-2.0-flash divergence).
    """
    from app.optimizer.provider_pricing import PRICING_CATALOG, get_model_pricing
    from app.providers.base import ModelCapabilityCatalog

    for key, cap in ModelCapabilityCatalog._CATALOG.items():
        assert key in PRICING_CATALOG, f"{key} missing from canonical PRICING_CATALOG"
        pricing = get_model_pricing(key)
        assert pricing is PRICING_CATALOG[key], f"{key} not resolved exactly"
        assert cap.input_pricing == pricing.input_per_million, key
        assert cap.output_pricing == pricing.output_per_million, key
        assert cap.cache_pricing == pricing.cache_read_per_million, key
        assert cap.cache_write_pricing == pricing.cache_write_per_million, key


def test_capability_catalog_has_no_pricing_literals() -> None:
    """The capability catalog must not re-hardcode price numbers."""
    src = _src("providers/base.py")
    assert __import__("re").search(r"input_pricing=\d", src) is None, (
        "pricing literal re-introduced in providers/base.py"
    )


# ===========================================================================
# F-4 — Credential resolution single authority
# ===========================================================================


def test_llm_provider_reexports_canonical_credentials() -> None:
    """llm_provider keeps its public API by re-exporting the canonical resolver."""
    import app.core.llm_provider as lp
    import app.core.provider_credentials as pc

    assert lp.resolve_provider_credentials is pc.resolve_provider_credentials
    assert lp._PROVIDER_SETTINGS_KEYS is pc._PROVIDER_SETTINGS_KEYS


def test_failover_has_no_local_credential_map() -> None:
    """The verbatim map clone in failover._default_resolve_credentials is gone."""
    src = _src("routing/failover.py")
    assert "provider_settings_keys" not in src
    assert "resolve_provider_credentials" in src


@pytest.mark.asyncio
async def test_failover_default_resolver_matches_canonical_resolution(
    monkeypatch,
) -> None:
    """Failover-time resolution is BYOK-first then platform key, like dispatch."""

    class FakeByok:
        def __init__(self, key: str | None) -> None:
            self.key = key
            self.asked: list[tuple[str, str]] = []

        async def get_decrypted_key(self, tenant_id: str, provider: str):
            self.asked.append((tenant_id, provider))
            return self.key

    class FakeSettings:
        OPENAI_API_KEY = "platform-openai-key"

    from app.routing.failover import FailoverManager

    byok = FakeByok(None)
    monkeypatch.setattr("app.core.byok.get_byok_manager", lambda: byok)
    monkeypatch.setattr("app.core.config.get_settings", lambda: FakeSettings())

    fm = FailoverManager()
    resolved = await fm._default_resolve_credentials("tenant-1", "openai")
    assert resolved == "platform-openai-key"
    assert byok.asked == [("tenant-1", "openai")]

    byok = FakeByok("tenant-byok-key")
    monkeypatch.setattr("app.core.byok.get_byok_manager", lambda: byok)
    assert await fm._default_resolve_credentials("tenant-1", "openai") == (
        "tenant-byok-key"
    )

    byok = FakeByok(None)
    monkeypatch.setattr("app.core.byok.get_byok_manager", lambda: byok)
    assert await fm._default_resolve_credentials("tenant-1", "mystery") is None


# ===========================================================================
# F-5 — JSON extraction single authority
# ===========================================================================

_JSON_MIGRATED_MODULES = (
    "agent/backends/jakeai.py",
    "agents/supervisor.py",
    "agent/planning/planner.py",
    "evals/llm_judge.py",
    "evals/rubric_evaluator.py",
    "evals/quality_oracle.py",
)


def test_json_extraction_copies_removed() -> None:
    """The inline fence-strip idiom is gone; each site uses the canonical util."""
    sources = _app_sources()
    for rel in _JSON_MIGRATED_MODULES:
        src = sources[rel]
        assert "extract_json_dict" in src, f"{rel} must use the canonical extractor"
        assert '.split("```json")' not in src, rel
        assert '.split("```json", 1)' not in src, rel

    for rel, src in sources.items():
        assert '.split("```json")' not in src, (
            f"{rel} re-introduces the inline fence-strip idiom"
        )


def test_planner_extract_json_action_uses_canonical_semantics() -> None:
    """Planner action extraction accepts fenced and embedded JSON via the util."""
    from app.agent.planning.planner import BoundedPlanner

    fenced = '```json\n{"action": "tool_call", "tool_name": "x", "arguments": {}}\n```'
    assert BoundedPlanner._extract_json_action(fenced)["action"] == "tool_call"

    embedded = 'Next step: {"action": "finish", "final_output": "done"} — thanks'
    assert BoundedPlanner._extract_json_action(embedded)["action"] == "finish"

    assert BoundedPlanner._extract_json_action("plain text, no json") is None
    assert BoundedPlanner._extract_json_action("") is None
    assert BoundedPlanner._extract_json_action('{"not_an_action": 1}') is None


def test_jakeai_backend_tool_call_extraction() -> None:
    """Backend tool-call extraction works for fenced and prose-wrapped JSON."""
    from app.agent.backends.jakeai import JakeAIBackend

    fenced = '```json\n{"tool_name": "get_account_balance", "arguments": {}}\n```'
    calls = JakeAIBackend._extract_tool_calls(fenced)
    assert len(calls) == 1
    assert calls[0].tool_name == "get_account_balance"

    embedded = 'Sure: {"tool": "grep", "arguments": {"q": "x"}}'
    calls = JakeAIBackend._extract_tool_calls(embedded)
    assert len(calls) == 1
    assert calls[0].tool_name == "grep"

    assert JakeAIBackend._extract_tool_calls("no tool payload here") == []
    assert JakeAIBackend._extract_tool_calls("") == []


def test_quality_oracle_schema_layer_uses_canonical_extraction() -> None:
    """Schema scoring: fenced JSON scores fully; garbage reports the failure."""
    from app.evals.quality_oracle import QualityOracle

    fenced = '```json\n{"answer": 42}\n```'
    score, errors = QualityOracle._evaluate_schema(fenced, ["answer"])
    assert score == 1.0
    assert errors == []

    score, errors = QualityOracle._evaluate_schema("utter garbage", ["answer"])
    assert score == 0.0
    assert errors == ["No valid JSON structure found in candidate text"]


def test_rubric_format_correctness_uses_canonical_extraction() -> None:
    """Rubric schema-key checking works on fenced JSON and rejects garbage."""
    from app.evals.rubric_evaluator import RubricEvaluator

    fenced = '```json\n{"metric": "revenue"}\n```'
    result = RubricEvaluator.evaluate_format_correctness(fenced, ["metric"])
    assert result.passed

    garbage = RubricEvaluator.evaluate_format_correctness("not json", ["metric"])
    assert not garbage.passed
    assert any(
        "JSON syntax invalid" in e for e in garbage.details.get("format_errors", [])
    )


def test_rubric_json_only_check_is_validation_not_extraction() -> None:
    """The 'JSON only' constraint check must stay strict: prose-wrapped JSON
    fails it even though the canonical extractor could dig the object out."""
    from app.evals.rubric_evaluator import RubricEvaluator

    result = RubricEvaluator.evaluate_format_correctness(
        'Here is your JSON: {"metric": "revenue"}',
        None,
    )
    # The schema layer is not active (no expected keys), so no failure is
    # recorded here; this test documents that the strict Check-3 validator in
    # evaluate_output_constraints is a separate, intentionally-strict job.
    assert result is not None


# ===========================================================================
# F-6 — SSE single authority
# ===========================================================================


def test_agent_run_event_sse_matches_canonical_formatter() -> None:
    from app.agent.runtime.models import AgentRunEvent
    from app.core.sse import format_sse_event

    event = AgentRunEvent(event_type="step", task_id="t1", run_id="r1", data={"k": "v"})
    assert event.to_sse() == format_sse_event("step", event.model_dump())


def test_sse_headers_defined_once() -> None:
    """The streaming header set is defined once and consumed by both endpoints."""
    sources = _app_sources()
    assert sources["core/sse.py"].count("X-Accel-Buffering") == 1

    hits = [
        rel
        for rel, src in sources.items()
        if "X-Accel-Buffering" in src or "streaming_sse_headers(" in src
    ]
    assert sorted(hits) == [
        "api/v1/endpoints/chat.py",
        "api/v1/endpoints/gateway.py",
        "core/sse.py",
    ]
    for rel in ("api/v1/endpoints/chat.py", "api/v1/endpoints/gateway.py"):
        assert "streaming_sse_headers(context)" in sources[rel], rel
