"""R-ARCH-02 — Dependency Boundaries regression suite.

Locks the verified dependency direction and boundary rules of the codebase:

    HTTP API -> orchestration drivers (canonical engine | LangGraph adapter | ReAct loop)
        -> canonical domain semantics (contracts, state, planning, verification)
        -> canonical capability logic (app/agent/capabilities/**)
        -> ToolRegistry (+ policy) -> built-in tools
        -> app.core.llm_provider -> ProviderRegistry adapters -> upstream

Rule families enforced here (each maps to a required R-ARCH-02 check):

A. Static dependency-direction proofs (AST import analysis at any nesting level):
   1. the agent domain (``app/agent/**``) never imports the LangGraph adapter
      package (``app/agents/**``), the LangGraph framework, or the web framework
      — adapters depend on the domain, never the inverse;
   2. pure domain modules (contracts, lifecycle state models) import no other
      ``app.*`` module at all;
   3. provider adapters (``app/providers/**``) never import orchestration,
      routing, service, or API layers — providers execute requests, they do not
      decide business workflow;
   4. provider adapters delegate credential resolution to the canonical BYOK
      authority (``app.core.byok``) instead of keeping their own stores;
   5. the only call site of a Tool instance's ``execute`` in production code is
      inside the canonical ``ToolRegistry.execute`` (no tool bypass);
   6. deterministic specialist business semantics (financial formulas, default
      figures, EBITDA adjustment) are defined exactly once in
      ``app/agent/capabilities/financial_analysis.py`` and re-defined nowhere;
   7. the LangGraph financial specialist node is pure delegation to the
      canonical capability module (no inline formulas or magic figures);
   8. HTTP endpoint modules never reference internal storage record types
      (checkpoint records, memory entries) in their response surface.

B. Runtime boundary proofs:
   9. all three drivers (LangGraph adapter node, canonical ExecutionEngine,
      degraded planner fallback) produce arithmetic identical to the canonical
      capability module for the same inputs — single runtime authority;
   10. the public chat SSE stream (real HTTP) returns financial analysis whose
       values match the canonical capability formulas for the request figures.
"""

from __future__ import annotations

import ast
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from app.agent.backends.jakeai import JakeAIBackend
from app.agent.capabilities.financial_analysis import (
    DEFAULT_OPERATING_EXPENSES,
    DEFAULT_REVENUE,
    extract_financial_figures,
)
from app.agent.capabilities.financial_analysis import (
    ebitda as canonical_ebitda,
)
from app.agent.capabilities.financial_analysis import (
    operating_income as canonical_operating_income,
)
from app.agent.capabilities.financial_analysis import (
    operating_margin_pct as canonical_operating_margin_pct,
)
from app.agent.domain.contracts import ExecutionContext, PlanStep, TaskSpec
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.models import Plan
from app.agent.planning.planner import BoundedPlanner
from app.agent.state.models import RunState
from app.agents.financial_specialist import financial_specialist_node
from app.core.config import get_settings
from tests.fixtures.auth import create_test_jwt

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from pytest import MonkeyPatch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
APP_DIR = BACKEND_DIR / "app"


# ===========================================================================
# A. Static dependency-direction analysis helpers
# ===========================================================================


def _iter_app_modules() -> Iterator[tuple[str, Path]]:
    """Yield (module name, path) for every Python file under backend/app."""
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                path = Path(dirpath) / fn
                rel = path.relative_to(BACKEND_DIR).with_suffix("")
                parts = list(rel.parts)
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                yield ".".join(parts), path


def _app_imports(tree: ast.AST) -> set[str]:
    """Collect every ``app.*`` module import at ANY nesting level (incl. lazy)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                if node.module == "app" or node.module.startswith("app."):
                    found.add(node.module)
            elif node.level > 0:
                found.add(".")
    return found


def _external_imports(tree: ast.AST) -> set[str]:
    """Collect top-level external package names imported at any nesting level."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def _module_source(rel_path: str) -> str:
    return (BACKEND_DIR / rel_path).read_text(encoding="utf-8")


# ===========================================================================
# A. Static dependency-direction rules
# ===========================================================================


def test_agent_domain_never_depends_on_langgraph_adapter_or_frameworks() -> None:
    """Rule 1: ``app/agent/**`` must not import ``app/agents/**`` or frameworks.

    Dependency direction: the LangGraph adapter package depends on the
    canonical agent domain; the domain must never depend on the adapter, the
    LangGraph framework, or the web framework (checked at every nesting level,
    including lazy function-body imports).
    """
    violations: list[str] = []
    for mod_name, path in _iter_app_modules():
        if not (mod_name == "app.agent" or mod_name.startswith("app.agent.")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        adapter_imports = {i for i in _app_imports(tree) if i.startswith("app.agents")}
        external = _external_imports(tree) & {"langgraph", "fastapi", "starlette"}
        if adapter_imports or external:
            violations.append(f"{mod_name}: {sorted(adapter_imports | external)}")
    assert not violations, f"Domain -> adapter/framework dependency found: {violations}"


def test_pure_domain_modules_import_no_foreign_app_modules() -> None:
    """Rule 2: contracts and lifecycle state models are dependency-free.

    ``app/agent/domain/contracts.py`` and ``app/agent/state/models.py`` define
    the canonical contracts every layer speaks; they must import no ``app.*``
    module outside their own subpackage so nothing can be transitively coupled
    through them.
    """
    violations: list[str] = []
    for mod_name, path in _iter_app_modules():
        if mod_name not in (
            "app.agent.domain",
            "app.agent.domain.contracts",
            "app.agent.state.models",
        ):
            continue
        imports = _app_imports(ast.parse(path.read_text(encoding="utf-8")))
        own_subpackage = "app.agent.domain"
        leaks = {i for i in imports if i != "." and not i.startswith(own_subpackage)}
        if leaks:
            violations.append(f"{mod_name}: {sorted(leaks)}")
    assert not violations, f"Pure domain modules import app modules: {violations}"


def test_providers_never_import_orchestration_or_api_layers() -> None:
    """Rule 3: provider adapters execute requests; they never own workflow.

    ``app/providers/**`` must not import the orchestration domain
    (``app.agent*``/``app.agents``), routing policy, services, API endpoints,
    guardrails, or finops — providers receive fully-resolved requests from
    ``app.core.llm_provider``/``FailoverManager``.
    """
    forbidden_prefixes = (
        "app.agent",
        "app.agents",
        "app.routing",
        "app.services",
        "app.api",
        "app.guardrails",
        "app.finops",
    )
    violations: list[str] = []
    for mod_name, path in _iter_app_modules():
        if not mod_name.startswith("app.providers"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = {i for i in _app_imports(tree) if i.startswith(forbidden_prefixes)}
        if bad:
            violations.append(f"{mod_name}: {sorted(bad)}")
    assert not violations, f"Providers import business layers: {violations}"


def test_provider_adapters_delegate_credentials_to_canonical_byok() -> None:
    """Rule 4: credential resolution is delegated to the canonical BYOK vault.

    Every networked provider adapter must resolve keys via ``app.core.byok``;
    no adapter may keep its own credential store.
    """
    adapters = [
        "anthropic.py",
        "deepseek.py",
        "gemini.py",
        "groq.py",
        "openai.py",
        "openrouter.py",
    ]
    violations: list[str] = []
    for adapter in adapters:
        tree = ast.parse(_module_source(f"app/providers/{adapter}"))
        if "app.core.byok" not in _app_imports(tree):
            violations.append(adapter)
    assert not violations, f"Adapter bypassing canonical BYOK authority: {violations}"


def test_tool_instance_execute_has_single_production_call_site() -> None:
    """Rule 5: the only production call site of ``Tool.execute`` is the registry.

    Tools must not be executed outside the canonical ``ToolRegistry.execute``
    funnel (policy + schema validation + timeout).
    """
    call_sites: list[str] = []
    for mod_name, path in _iter_app_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            if node.func.attr != "execute":
                continue
            recv = node.func.value
            ident = (
                recv.id
                if isinstance(recv, ast.Name)
                else recv.attr
                if isinstance(recv, ast.Attribute)
                else ""
            )
            if "registry" in ident or ident in {"loop", "runner", "self"}:
                continue
            if mod_name == "app.agent.tools.registry":
                continue  # the canonical funnel itself
            call_sites.append(f"{mod_name}:{node.lineno} ({ident}.execute)")
    assert not call_sites, f"Tool.execute called outside ToolRegistry: {call_sites}"


def test_financial_capability_formulas_defined_exactly_once() -> None:
    """Rule 6: financial business semantics live in exactly one module.

    The default figures and the EBITDA adjustment factor may appear only in
    ``app/agent/capabilities/financial_analysis.py``.
    """
    magic_markers = ("1500000", "950000", "1.12")
    violations: list[str] = []
    for mod_name, path in _iter_app_modules():
        if mod_name == "app.agent.capabilities.financial_analysis":
            continue
        source = path.read_text(encoding="utf-8")
        for marker in magic_markers:
            if marker in source:
                violations.append(f"{mod_name}: literal '{marker}'")
    assert not violations, (
        f"Financial semantics re-defined outside authority: {violations}"
    )


def test_langgraph_financial_node_is_pure_delegation() -> None:
    """Rule 7: the adapter's financial node holds no business semantics.

    The node must import the canonical capability module and must not contain
    inline business arithmetic on the extracted figures.
    """
    source = _module_source("app/agents/financial_specialist.py")
    tree = ast.parse(source)
    assert "app.agent.capabilities.financial_analysis" in _app_imports(tree), (
        "Adapter financial node must delegate to the canonical capability module"
    )
    for marker in ("1500000", "950000", "1.12"):
        assert marker not in source, (
            f"Adapter node re-defines business semantics: literal '{marker}' found"
        )
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            pytest.fail(
                f"Adapter node contains inline business arithmetic at line {node.lineno}"
            )


def test_endpoints_never_expose_internal_storage_records() -> None:
    """Rule 8: public API DTOs must not expose internal persistence records.

    Endpoint modules must not reference internal storage record types
    (``CheckpointRecord``, ``MemoryEntry``); the HTTP surface speaks the
    canonical state/contract models only.
    """
    internal_types = ("CheckpointRecord", "MemoryEntry")
    violations: list[str] = []
    for mod_name, path in _iter_app_modules():
        if not mod_name.startswith("app.api"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {
            n.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id in internal_types
        } | {
            n.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr in internal_types
        }
        if names:
            violations.append(f"{mod_name}: {sorted(names)}")
    assert not violations, f"Endpoints expose internal storage records: {violations}"


# ===========================================================================
# B. Runtime boundary proofs
# ===========================================================================


@pytest.mark.asyncio
async def test_all_drivers_match_canonical_capability_arithmetic() -> None:
    """Rule 9: adapter node and degraded planner fallback share one arithmetic.

    Drives the LangGraph adapter node with explicit figures and the degraded
    planner fallback with its canonical defaults, and asserts both outputs
    equal the canonical capability formulas (single runtime authority).
    """
    # 1. LangGraph adapter node parity.
    revenue, expenses = 2_400_000.0, 1_150_000.25
    state: dict[str, Any] = {
        "prompt": f"Revenue is ${revenue:,.2f} and expenses are ${expenses:,.2f}.",
        "tenant_id": "tenant-arch-02",
        "user_id": "user-arch-02",
    }
    result = await financial_specialist_node(state)  # type: ignore[arg-type]
    analysis = result["financial_analysis"]
    expected_income = canonical_operating_income(revenue, expenses)
    assert analysis["revenue"] == revenue
    assert analysis["operating_expenses"] == expenses
    assert analysis["operating_income"] == pytest.approx(expected_income)
    assert analysis["operating_margin_pct"] == canonical_operating_margin_pct(
        expected_income, revenue
    )
    assert analysis["ebitda"] == pytest.approx(canonical_ebitda(expected_income))

    # 2. Degraded planner fallback parity (canonical default figures).
    planner = BoundedPlanner(backend=JakeAIBackend())
    plan = Plan(task_id="task-arch-02", goal="Calculate operating margin")
    action = await planner.determine_next_action(
        goal="Calculate operating margin and EBITDA",
        plan=plan,
        history=[],
        available_tools=[],  # no calculator -> deterministic synthesis branch
        current_iteration=0,
        elapsed_time_seconds=0.0,
        tenant_id="tenant-arch-02",
    )
    assert action.action_type.value == "finish"
    default_income = canonical_operating_income(
        DEFAULT_REVENUE, DEFAULT_OPERATING_EXPENSES
    )
    final = action.final_output or ""
    assert f"${default_income:,.2f}" in final
    assert (
        f"{canonical_operating_margin_pct(default_income, DEFAULT_REVENUE)}%" in final
    )
    assert f"${canonical_ebitda(default_income):,.2f}" in final
    assert f"${DEFAULT_REVENUE:,.2f}" in final


@pytest.mark.asyncio
async def test_engine_financial_step_matches_canonical_capability() -> None:
    """Rule 9 (engine): the canonical DAG engine's financial step output equals
    the canonical capability values for the default figures."""
    engine = ExecutionEngine()
    step = PlanStep(step_id="s1", description="financial analysis")
    task_spec = TaskSpec(
        task_id="task-arch-02", tenant_id="tenant-arch-02", goal="financial analysis"
    )
    context = ExecutionContext(tenant_id="tenant-arch-02")
    run_state = RunState(
        run_id="run-arch-02",
        task_id="task-arch-02",
        tenant_id="tenant-arch-02",
        user_id="user-arch-02",
    )
    _, res, _ = await engine._execute_single_step(
        step=step,
        task_spec=task_spec,
        context=context,
        run_state=run_state,
        accumulated_outputs={},  # no banking outputs -> canonical default figures
        _elapsed_seconds=0.0,
    )
    default_income = canonical_operating_income(
        DEFAULT_REVENUE, DEFAULT_OPERATING_EXPENSES
    )
    output = res.output
    assert output["revenue"] == DEFAULT_REVENUE
    assert output["operating_expenses"] == DEFAULT_OPERATING_EXPENSES
    assert output["operating_income"] == round(default_income, 2)
    assert output["operating_margin_pct"] == canonical_operating_margin_pct(
        round(default_income, 2), DEFAULT_REVENUE
    )
    assert output["ebitda"] == round(canonical_ebitda(round(default_income, 2)), 2)


@pytest.mark.asyncio
async def test_chat_http_financial_output_matches_canonical_capability(
    async_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    """Rule 10: the public HTTP chat stream returns canonical arithmetic.

    Posts a financial prompt with unique figures to the real SSE endpoint and
    verifies the streamed specialist message equals the canonical capability
    formulas — proving the adapter delegates (no alternate semantics at the
    HTTP boundary).
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    token = create_test_jwt(sub="user-arch-02", tenant_id="tenant-arch-02")
    revenue = float(f"7{uuid.uuid4().int % 100000:05d}00") + 0.5
    expenses = 810_000.75
    prompt = (
        f"Calculate operating margin for revenue ${revenue:,.2f} "
        f"and expenses ${expenses:,.2f}"
    )

    response = await async_client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "prompt": prompt,
            "conversation_id": f"conv-arch-02-{uuid.uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "event: done" in body

    figures = extract_financial_figures(prompt)
    assert figures[0] == pytest.approx(revenue)
    expected_income = canonical_operating_income(figures[0], figures[1])
    expected_margin = canonical_operating_margin_pct(expected_income, figures[0])
    # The canonical (not an alternate) margin percentage must appear in the
    # specialist's streamed status message.
    assert f"({expected_margin}%)" in body or f"{expected_margin}% Margin" in body, (
        f"HTTP report margin does not match canonical capability "
        f"(expected {expected_margin}% for figures {figures})"
    )


def test_registry_discovers_builtin_tools_through_policy() -> None:
    """Rule 5 (runtime): built-ins are reachable only via the registry funnel.

    The singleton registry registers every built-in; policy-gated discovery
    proves authorization runs through the registry rather than direct
    instantiation.
    """
    from app.agent.tools.registry import get_tool_registry

    registry = get_tool_registry()
    discoverable = {m.name for m in registry.discover(user_roles=["admin"])}
    assert "get_account_balance" in discoverable
    assert "read_file" in discoverable
    assert registry.get("get_account_balance") is not None
