"""Unit tests for canonical structured output parsing utility (WORK-01-CI-FIX-05)."""

import inspect
from collections.abc import AsyncGenerator

import pytest

from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.domain.contracts import TaskSpec
from app.agent.planning.planner import BoundedPlanner
from app.agent.registry.agent_registry import AgentMetadata, AgentRegistry
from app.agent.registry.agent_selector import AgentSelector
from app.agent.utils import structured_output
from app.agent.utils.structured_output import extract_json_dict


class MockTestBackend(AgentBackendInterface):
    """Deterministic mock backend for parser integration tests."""

    def __init__(self, response_text: str) -> None:
        super().__init__()
        self.response_text = response_text

    async def generate(self, request: BackendRequest) -> BackendResponse:
        return BackendResponse(content=self.response_text)

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncGenerator[BackendStreamChunk, None]:
        yield BackendStreamChunk(delta_content=self.response_text, is_complete=True)


def test_case_1_raw_json_object() -> None:
    """1. Raw JSON object is extracted directly."""
    raw = '{"action": "plan", "steps": ["step1", "step2"], "status": "ok"}'
    result = extract_json_dict(raw)
    assert result == {"action": "plan", "steps": ["step1", "step2"], "status": "ok"}


def test_case_2_fenced_json_block() -> None:
    """2. ```json fenced block is parsed correctly."""
    text = 'Here is the response:\n```json\n{"selected_agent_id": "financial_specialist", "confidence": 0.95}\n```\nDone.'
    result = extract_json_dict(text)
    assert result == {"selected_agent_id": "financial_specialist", "confidence": 0.95}


def test_case_3_generic_fenced_block() -> None:
    """3. Generic ``` fenced block is parsed correctly."""
    text = 'Plan below:\n```\n{"task_id": "task_123", "goal": "calculate"}\n```'
    result = extract_json_dict(text)
    assert result == {"task_id": "task_123", "goal": "calculate"}


def test_case_4_embedded_json_object() -> None:
    """4. Embedded JSON object in prose is discovered and parsed."""
    text = 'The agent decided: {"action": "execute", "target": "balance"}. This completes the step.'
    result = extract_json_dict(text)
    assert result == {"action": "execute", "target": "balance"}


def test_case_5_empty_text() -> None:
    """5. Empty text returns None."""
    assert extract_json_dict("") is None


def test_case_6_whitespace_only_text() -> None:
    """6. Whitespace-only text returns None."""
    assert extract_json_dict("   \n\t  \r  ") is None


def test_case_7_malformed_json() -> None:
    """7. Malformed JSON returns None."""
    assert extract_json_dict('{"action": "plan", "unclosed') is None
    assert extract_json_dict('{"action": invalid_no_quotes}') is None


def test_case_8_valid_json_array() -> None:
    """8. Valid JSON array returns None (must be an object dictionary)."""
    assert extract_json_dict('[{"action": "plan"}]') is None
    assert extract_json_dict('["item1", "item2"]') is None


def test_case_9_valid_json_primitives() -> None:
    """9. Valid JSON primitives return None."""
    assert extract_json_dict('"just a string"') is None
    assert extract_json_dict("12345") is None
    assert extract_json_dict("true") is None
    assert extract_json_dict("false") is None
    assert extract_json_dict("null") is None


def test_case_10_missing_closing_fence() -> None:
    """10. Missing closing fence returns None."""
    assert extract_json_dict('```json\n{"action": "finish"}') is None
    assert extract_json_dict('```\n{"action": "finish"}') is None


def test_case_11_multiple_blocks() -> None:
    """11. Multiple blocks extracts the first valid JSON block without trailing confusion."""
    text = (
        'First block:\n```json\n{"block": 1}\n```\n'
        'Second block:\n```json\n{"block": 2}\n```'
    )
    result = extract_json_dict(text)
    assert result == {"block": 1}


def test_case_12_braces_inside_surrounding_prose() -> None:
    """12. Braces inside surrounding prose do not break object extraction."""
    text = 'Note: parameter {env} is active. Actual result: {"selected_agent": "synthesizer"} completed.'
    result = extract_json_dict(text)
    assert result == {"selected_agent": "synthesizer"}


def test_case_13_malformed_embedded_object() -> None:
    """13. Malformed embedded object returns None."""
    text = "Here is bad syntax: {key without quotes: value} sorry!"
    assert extract_json_dict(text) is None


def test_case_14_regression_no_broad_exceptions() -> None:
    """14. Prove that canonical parser contains no silent 'except Exception:' or 'except BaseException:'."""
    source = inspect.getsource(structured_output)
    assert "except Exception" not in source
    assert "except BaseException" not in source
    assert "# noqa: B110" not in source
    assert "# nosec" not in source


@pytest.mark.asyncio
async def test_planner_integration_valid_structured_output() -> None:
    """Task 11: BoundedPlanner with canonical parser extracts valid DAG plan."""
    valid_json = (
        "```json\n"
        "{\n"
        '  "steps": [\n'
        "    {\n"
        '      "step_id": "step_1",\n'
        '      "description": "Calculate operating margin",\n'
        '      "dependencies": []\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )
    backend = MockTestBackend(response_text=valid_json)
    planner = BoundedPlanner(backend=backend)
    spec = TaskSpec(
        task_id="t1",
        tenant_id="tenant_test",
        user_id="u1",
        goal="Calculate operating margin",
    )
    plan = await planner.plan_task(spec)
    assert plan.planner_mode == "structured"
    assert len(plan.steps) == 1
    assert plan.steps[0].step_id == "step_1"


@pytest.mark.asyncio
async def test_planner_integration_none_fallback_deterministic() -> None:
    """Task 11: BoundedPlanner with parser returning None gracefully falls back to deterministic DAG."""
    malformed_output = "I am a language model and I cannot generate JSON today."
    backend = MockTestBackend(response_text=malformed_output)
    planner = BoundedPlanner(backend=backend)
    spec = TaskSpec(
        task_id="t2",
        tenant_id="tenant_test",
        user_id="u1",
        goal="Calculate operating margin",
    )
    plan = await planner.plan_task(spec)
    # Parser returned None, so planner triggered deterministic DAG fallback
    assert plan.planner_mode in ("deterministic_fallback", "degraded_fallback")
    assert len(plan.steps) >= 1


@pytest.mark.asyncio
async def test_agent_selector_integration_valid_selection() -> None:
    """Task 11: AgentSelector with canonical parser selects agent from structured model output."""
    selection_json = (
        "```json\n"
        "{\n"
        '  "selected_agent_id": "financial_specialist",\n'
        '  "reasoning": "Direct match for financial ratio computation.",\n'
        '  "confidence": 0.98\n'
        "}\n"
        "```"
    )
    backend = MockTestBackend(response_text=selection_json)
    registry = AgentRegistry()
    registry.register(
        AgentMetadata(
            agent_id="financial_specialist",
            name="Financial Specialist",
            description="Specialized in financial analytics",
            capabilities=["financial_analysis"],
        )
    )
    registry.register(
        AgentMetadata(
            agent_id="general_agent",
            name="General Agent",
            description="General purpose assistant",
            capabilities=["general_reasoning"],
        )
    )
    selector = AgentSelector(registry=registry, backend=backend)
    spec = TaskSpec(
        task_id="t3",
        tenant_id="tenant_test",
        user_id="u1",
        goal="Calculate financial margin",
    )
    selection = await selector.select_agent_async(spec)
    assert selection.selection_mode == "model"
    assert selection.agent_id == "financial_specialist"
    assert selection.confidence == 0.98


@pytest.mark.asyncio
async def test_agent_selector_integration_none_fallback_deterministic() -> None:
    """Task 11: AgentSelector with parser returning None falls back to deterministic selection."""
    malformed_output = "I cannot decide which agent to choose."
    backend = MockTestBackend(response_text=malformed_output)
    registry = AgentRegistry()
    registry.register(
        AgentMetadata(
            agent_id="financial_specialist",
            name="Financial Specialist",
            description="Specialized in financial analytics",
            capabilities=["financial_analysis"],
        )
    )
    registry.register(
        AgentMetadata(
            agent_id="general_agent",
            name="General Agent",
            description="General purpose assistant",
            capabilities=["general_reasoning"],
        )
    )
    selector = AgentSelector(registry=registry, backend=backend)
    spec = TaskSpec(
        task_id="t4",
        tenant_id="tenant_test",
        user_id="u1",
        goal="Calculate financial margin",
    )
    selection = await selector.select_agent_async(spec)
    # Parser returned None, so selector fell back to deterministic ranking
    assert selection.selection_mode == "deterministic_fallback"
    assert selection.agent_id == "financial_specialist"
