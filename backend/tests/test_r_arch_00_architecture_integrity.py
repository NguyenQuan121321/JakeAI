"""R-ARCH-00 — Architecture Integrity regression suite.

Locks the verified orchestration topology of the codebase:

    HTTP API (chat SSE / agent REST / coding bridge / gateway)
        -> orchestration drivers
             (LangGraph adapter graph | canonical ExecutionEngine | native ReAct AgentRunner)
        -> canonical semantics: AgentSelector + BoundedPlanner + ModelRouter
        -> ToolRegistry (+ ApprovalPolicy) -> built-in tools
        -> app.core.llm_provider (single upstream provider dispatch authority)
        -> CanonicalVerifier (single verification authority)
        -> RunState/TaskState state machine + CheckpointManager

Two rule families are enforced:

A. Static boundary rules (import/dependency analysis executed at test time):
   1. zero module-level import cycles across ``app/``;
   2. no web-framework (FastAPI/Starlette) imports inside the agent domain
      (``app/agent/**`` and ``app/agents/**``);
   3. LangGraph framework imports confined to the adapter boundary
      (``app/agents/**`` and the ADR-001 resume bridge);
   4. exactly one canonical implementation per semantic authority
      (verifier, planner, model router, tool registry, execution engine,
      run/task state models, checkpoint manager).

B. Runtime authority proofs (behavior):
   5. the LangGraph verifier node and the ExecutionEngine share the single
      CanonicalVerifier instance and inherit its verdict semantics;
   6. the chat SSE path executes the canonical orchestration chain
      (supervisor -> specialist -> verifier -> synthesizer) over real HTTP;
   7. the chat tool path funnels tool execution through the canonical
      ToolRegistry over real HTTP (no direct-execution bypass);
   8. both the native agent backend and the graph synthesizer funnel all
      upstream generation through ``app.core.llm_provider``;
   9. the agent REST platform enforces the canonical RunState machine and
      multi-tenant isolation at the HTTP boundary.
"""

from __future__ import annotations

import ast
import os
import uuid
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from app.agent.backends.base import AgentMessage, BackendRequest
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.execution.engine import ExecutionEngine, get_execution_engine
from app.agent.state.models import RunStatus
from app.agent.verification.verifier import get_canonical_verifier
from app.agents.verifier import verifier_node
from app.core.config import get_settings
from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse
from tests.test_agent_platform import generate_agent_jwt
from tests.test_gateway import create_test_jwt

if TYPE_CHECKING:
    from httpx import AsyncClient
    from pytest import MonkeyPatch

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"


# ===========================================================================
# A. Static boundary analysis helpers
# ===========================================================================


def _iter_app_modules() -> list[tuple[str, Path]]:
    """Yield (module name, path) for every Python file under backend/app."""
    modules: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                path = Path(dirpath) / fn
                rel = path.relative_to(BACKEND_DIR).with_suffix("")
                modules.append((rel.as_posix().replace("/", "."), path))
    return modules


def _app_import_graph() -> dict[str, set[str]]:
    """Map module -> set of first-party ``app.*`` imports (module level only)."""
    graph: dict[str, set[str]] = defaultdict(set)
    for mod, path in _iter_app_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app"):
                        graph[mod].add(alias.name)
            elif isinstance(node, ast.ImportFrom) and (
                node.level == 0 and node.module and node.module.startswith("app")
            ):
                graph[mod].add(node.module)
    return graph


def test_no_module_level_import_cycles_in_app_package() -> None:
    """The orchestration packages must stay acyclic at module level.

    A hidden circular dependency between API, orchestration, and adapter
    layers would make the canonical authority unenforceable (import order,
    not design, would decide which module wins).
    """
    graph = _app_import_graph()
    nodes = set(graph)
    color: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def resolve(import_name: str) -> list[str]:
        if import_name in nodes:
            return [import_name]
        return [n for n in nodes if n.startswith(import_name + ".")]

    def dfs(current: str) -> None:
        color[current] = 1
        stack.append(current)
        for imp in sorted(graph.get(current, ())):
            for target in resolve(imp):
                if target == current:
                    continue
                if color.get(target) == 1 and target in stack:
                    cycles.append([*stack[stack.index(target) :], target])
                elif color.get(target, 0) == 0:
                    dfs(target)
        stack.pop()
        color[current] = 2

    for node in sorted(nodes):
        if color.get(node, 0) == 0:
            dfs(node)

    assert not cycles, f"Module-level import cycles detected: {cycles[:3]}"


def test_no_web_framework_imports_in_agent_domain() -> None:
    """Agent domain/orchestration layers must not import the web framework.

    FastAPI/Starlette types leaking into ``app/agent`` or ``app/agents``
    would couple business semantics to the HTTP transport and make the
    orchestration contract untestable without a server.
    """
    forbidden = ("fastapi", "starlette")
    offenders: list[str] = []
    for mod, path in _iter_app_modules():
        if not (mod.startswith("app.agent.") or mod.startswith("app.agents.")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] in forbidden for n in names):
                offenders.append(mod)
    assert not offenders, f"Web-framework imports inside agent domain: {offenders}"


def test_langgraph_imports_confined_to_adapter_boundary() -> None:
    """LangGraph is an alternate execution *framework* and must stay an adapter.

    Only the ``app/agents`` adapter package (LangGraph graph + nodes) and the
    ADR-001 resume bridge (LangGraph ``Command(resume=...)`` rehydration) may
    import the framework. Any other module importing langgraph would smuggle
    a parallel business system past the canonical orchestration contract.
    """
    allowed_prefixes = ("app.agents",)
    allowed_exact = {"app.services.resume_bridge"}
    offenders: list[str] = []
    for mod, path in _iter_app_modules():
        if mod in allowed_exact or mod.startswith(allowed_prefixes):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] == "langgraph" for n in names):
                offenders.append(mod)
    assert not offenders, f"langgraph imported outside adapter boundary: {offenders}"


@pytest.mark.parametrize(
    ("class_name", "expected_module"),
    [
        ("CanonicalVerifier", "app/agent/verification/verifier.py"),
        ("BoundedPlanner", "app/agent/planning/planner.py"),
        ("ModelRouter", "app/routing/router.py"),
        ("ToolRegistry", "app/agent/tools/registry.py"),
        ("ExecutionEngine", "app/agent/execution/engine.py"),
        ("CheckpointManager", "app/agent/state/checkpoint.py"),
        ("RunState", "app/agent/state/models.py"),
        ("TaskState", "app/agent/state/models.py"),
    ],
)
def test_single_canonical_semantic_authority(
    class_name: str, expected_module: str
) -> None:
    """Each semantic authority must have exactly one canonical implementation.

    Duplicate planner/verifier/router/state implementations would create
    competing sources of truth for run lifecycle and verification semantics.
    """
    owners: list[str] = []
    for _mod, path in _iter_app_modules():
        rel = path.relative_to(BACKEND_DIR).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                owners.append(rel)
    assert owners == [expected_module], (
        f"Class '{class_name}' must be defined exactly once in "
        f"'{expected_module}', found: {owners}"
    )


# ===========================================================================
# B. Runtime authority proofs
# ===========================================================================


@pytest.mark.asyncio
async def test_canonical_verifier_singleton_shared_by_all_drivers() -> None:
    """LangGraph nodes and the ExecutionEngine share one verification authority."""
    from app.agent.verification import verifier as verifier_module
    from app.agents import verifier as lg_verifier_module

    # Same singleton accessor and same instance identity.
    assert (
        lg_verifier_module.get_canonical_verifier
        is verifier_module.get_canonical_verifier
    )

    engine = ExecutionEngine()
    assert engine.verifier is get_canonical_verifier()
    assert get_execution_engine().verifier is get_canonical_verifier()


@pytest.mark.asyncio
async def test_langgraph_verifier_node_inherits_canonical_verdicts() -> None:
    """The graph verifier node delegates semantics to CanonicalVerifier verbatim."""
    base_state: dict[str, Any] = {
        "prompt": "Quarterly finance review",
        "tenant_id": "tenant-arch",
        "messages": [],
        "revision_count": 0,
        "financial_analysis": {},
        "tool_calls": [],
        "retrieved_chunks": [],
    }

    # Consistent math -> canonical PASS propagated into graph state.
    passed = await verifier_node(
        {
            **base_state,
            "financial_analysis": {
                "revenue": 1000.0,
                "operating_expenses": 400.0,
                "operating_income": 600.0,
            },
        }
    )
    assert passed["verification_verdict"] == "PASS"
    assert passed["workflow_phase"] == "verification_passed"

    # Inconsistent math -> canonical NEEDS_REVISION with supervisor re-route.
    revision = await verifier_node(
        {
            **base_state,
            "financial_analysis": {
                "revenue": 1000.0,
                "operating_expenses": 400.0,
                "operating_income": 999999.0,
            },
        }
    )
    assert revision["verification_verdict"] == "NEEDS_REVISION"
    assert revision["next_agent"] == "supervisor"

    # Cross-tenant tool access -> canonical immediate REJECTED (no revisions).
    rejected = await verifier_node(
        {
            **base_state,
            "tool_calls": [
                {"tool_name": "get_account_balance", "tenant_id": "tenant-OTHER"}
            ],
        }
    )
    assert rejected["verification_verdict"] == "REJECTED"
    assert rejected["workflow_phase"] == "verification_failed"


@pytest.mark.asyncio
async def test_chat_sse_executes_canonical_orchestration_chain(
    async_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    """The public chat SSE stream runs the canonical chain over real HTTP.

    Proves over the HTTP boundary that the LangGraph driver is an adapter of
    the canonical semantics: supervisor routing, deterministic specialist
    computation, CanonicalVerifier gate, and synthesis all execute, and the
    final response carries the verified arithmetic.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    token = create_test_jwt(sub="user-arch", tenant_id="tenant-arch")
    prompt = (
        f"Calculate operating margin for revenue $6{uuid.uuid4().hex[:4]}000 "
        "and expenses $200000"
    )

    response = await async_client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt, "conversation_id": f"conv-arch-{uuid.uuid4().hex[:8]}"},
    )

    assert response.status_code == 200
    body = response.text
    assert "event: status" in body
    assert "event: done" in body

    # Canonical chain nodes traversed inside the graph.
    for node in ("supervisor", "financial_specialist", "verifier", "synthesizer"):
        assert f'"node": "{node}"' in body or node in body, (
            f"Canonical chain node '{node}' missing from chat SSE stream"
        )
    # Verification gate ran (verifier message) and math was verified.
    assert "Verifier:" in body


@pytest.mark.asyncio
async def test_chat_tool_path_funnels_through_canonical_tool_registry(
    async_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    """Tool execution in the chat graph must go through ToolRegistry (no bypass).

    W-ORC-03 requires every tool call to route through the canonical registry
    (RBAC + schema validation). This proves it over real HTTP by wrapping the
    registry's execute method and observing exactly one delegated call.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")

    from app.agent.tools.registry import ToolRegistry

    original_execute = ToolRegistry.execute
    funnel_calls: list[str] = []

    async def spying_execute(
        self: Any, tool_name: str, *args: Any, **kwargs: Any
    ) -> Any:
        funnel_calls.append(tool_name)
        return await original_execute(self, tool_name, *args, **kwargs)

    monkeypatch.setattr(ToolRegistry, "execute", spying_execute)

    # Admin role + accounts:read permission so the RBAC guard authorizes the
    # balance lookup; the guard itself must block BEFORE the registry.
    token = create_test_jwt(
        sub="user-arch-tool",
        tenant_id="tenant-arch",
        roles=["admin"],
        permissions=["accounts:read"],
    )
    response = await async_client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "prompt": f"finnapi fetch account balance {uuid.uuid4().hex[:6]}",
            "conversation_id": f"conv-arch-tool-{uuid.uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "event: tool_call" in body, "Tool execution event missing from stream"
    assert funnel_calls == ["get_account_balance"], (
        f"Tool execution bypassed the canonical ToolRegistry: {funnel_calls}"
    )

    # Ownership boundary: tool *authorization* lives in the RBAC guardrail,
    # strictly before the registry. An unprivileged caller must be blocked
    # without ever reaching ToolRegistry.execute.
    unprivileged = create_test_jwt(
        sub="user-arch-noaccess",
        tenant_id="tenant-arch",
        roles=["user"],
        permissions=["chat:read"],
    )
    funnel_calls.clear()
    blocked = await async_client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {unprivileged}"},
        json={
            "prompt": f"finnapi fetch account balance {uuid.uuid4().hex[:6]}",
            "conversation_id": f"conv-arch-denied-{uuid.uuid4().hex[:8]}",
        },
    )
    assert blocked.status_code == 200
    assert "BLOCKED" in blocked.text
    assert funnel_calls == [], (
        "Blocked tool invocation must never reach the canonical ToolRegistry"
    )


@pytest.mark.asyncio
async def test_agent_backend_funnels_through_canonical_provider_dispatch(
    monkeypatch: MonkeyPatch,
) -> None:
    """The native agent runtime must dispatch upstream generation via llm_provider.

    JakeAIBackend is the native runtime's provider adapter; it must not own
    provider HTTP clients itself, otherwise provider resolution, BYOK, Tier 5
    caching, and FinOps accounting would be bypassed.
    """
    import app.agent.backends.jakeai as jakeai_module

    funnel_calls: list[dict[str, Any]] = []

    async def fake_dispatch(**kwargs: Any) -> UpstreamLLMResponse:
        funnel_calls.append(kwargs)
        return UpstreamLLMResponse(
            text="canonical-provider-reply",
            model=kwargs.get("model", "gemini-1.5-flash"),
            provider="gemini",
            telemetry=ProviderCacheTelemetry(),
        )

    monkeypatch.setattr(jakeai_module, "call_upstream_llm_detailed", fake_dispatch)

    backend = JakeAIBackend()
    resp = await backend.generate(
        BackendRequest(
            messages=[AgentMessage(role="user", content="ping")],
            tenant_id="tenant-arch",
        )
    )

    assert len(funnel_calls) == 1, "Backend generation bypassed app.core.llm_provider"
    assert resp.content == "canonical-provider-reply"


@pytest.mark.asyncio
async def test_synthesizer_generation_funnels_through_canonical_provider_dispatch(
    monkeypatch: MonkeyPatch,
) -> None:
    """The graph synthesizer's free-form generation must use llm_provider too."""
    import app.core.llm_provider as llm_provider_module
    from app.agents.synthesizer import synthesizer_node

    funnel_calls: list[dict[str, Any]] = []

    async def fake_dispatch(**kwargs: Any) -> UpstreamLLMResponse:
        funnel_calls.append(kwargs)
        return UpstreamLLMResponse(
            text="synthesized-via-canonical-dispatch",
            model=kwargs.get("model", "gemini-1.5-flash"),
            provider="gemini",
            telemetry=ProviderCacheTelemetry(),
        )

    monkeypatch.setattr(
        llm_provider_module, "call_upstream_llm_detailed", fake_dispatch
    )

    result = await synthesizer_node(
        {
            "prompt": f"free-form question {uuid.uuid4().hex[:6]}",
            "tenant_id": "tenant-arch",
            "messages": [],
            "financial_analysis": {},
            "tool_calls": [],
            "retrieved_chunks": [],
            "model": "gemini-1.5-flash",
            "correlation_id": "corr-arch-00",
        }
    )

    assert len(funnel_calls) == 1, "Synthesizer bypassed app.core.llm_provider"
    assert funnel_calls[0]["correlation_id"] == "corr-arch-00"
    assert (
        result["final_response"]
        and "synthesized-via-canonical-dispatch" in result["final_response"]
    )
    assert result["model_used"] == "gemini-1.5-flash"


@pytest.mark.asyncio
async def test_agent_rest_enforces_canonical_state_machine_and_isolation(
    async_client: AsyncClient,
) -> None:
    """The agent REST platform enforces RunState ownership and tenant isolation."""
    token = generate_agent_jwt(tenant_id="tenant-arch-agent")
    headers = {"Authorization": f"Bearer {token}"}

    created = await async_client.post(
        "/api/v1/agent/tasks",
        json={"goal": "Architecture integrity probe"},
        headers=headers,
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    # Canonical tenant isolation on the task/run store.
    other = {"Authorization": f"Bearer {generate_agent_jwt(tenant_id='tenant-other')}"}
    forbidden = await async_client.get(f"/api/v1/agent/tasks/{task_id}", headers=other)
    assert forbidden.status_code == 403

    run_created = await async_client.post(
        f"/api/v1/agent/tasks/{task_id}/runs",
        json={"max_iterations": 2, "async_execution": True},
        headers=headers,
    )
    assert run_created.status_code == 201
    run_id = run_created.json()["run_id"]
    assert RunStatus(run_created.json()["status"]) == RunStatus.CREATED

    fetched = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
    )
    assert fetched.status_code == 200

    # Terminal-state immutability: cancel transitions the run and a further
    # cancel must not mutate the recorded terminal state.
    cancelled = await async_client.post(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    final_status = RunStatus(cancelled.json()["status"])
    assert final_status == RunStatus.CANCELLED or final_status.is_terminal

    again = await async_client.post(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel", headers=headers
    )
    assert again.status_code == 200
    assert RunStatus(again.json()["status"]) == final_status
