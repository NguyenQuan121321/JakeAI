"""R-ARCH-01 — Canonical Authority regression suite.

Locks the single-source-of-truth proofs for every business rule that historically
had competing implementations:

1. capability/intent keyword classification exists exactly once
   (``app.agent.registry.capability_patterns``) and all three former copies
   (BoundedPlanner, AgentSelector, LangGraph supervisor) consume it;
2. run/task lifecycle status is owned solely by ``app.agent.state.models``
   (the dead duplicate ``ExecutionStateStatus``/``TerminalState`` contract pair
   was removed from ``app.agent.domain.contracts``);
3. upstream provider credential resolution exists exactly once in
   ``app.core.llm_provider`` and honors tenant BYOK before platform keys;
4. the FinnApiGo tool is the single authority for OBO token exchange and for
   the tenant account-id identity derivation (callers must not pre-derive);
5. the managed agent runtime wires exactly one backend dispatch chain
   (``JakeAIBackend`` -> ``app.core.llm_provider``).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest

from app.agent.backends.jakeai import JakeAIBackend
from app.agent.domain import contracts
from app.agent.planning.planner import BoundedPlanner
from app.agent.registry.agent_selector import get_agent_selector
from app.agent.registry.capability_patterns import (
    BANKING_PATTERN,
    FINANCIAL_PATTERN,
    RETRIEVAL_PATTERN,
)
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.runtime.models import AgentConfig
from app.agent.state.models import RunStatus, TaskStatus
from app.agent.tools.builtins.finnapigo_tools import (
    FinnApiGoBalanceTool,
    FinnApiGoTransactionsTool,
)
from app.agents.supervisor import classify_intent
from app.core.config import get_settings
from app.core.llm_provider import resolve_provider_credentials

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"

PATTERN_MODULE = "app/agent/registry/capability_patterns.py"


def _app_sources() -> dict[str, str]:
    """Return relative-path -> source text for every Python file under app/."""
    sources: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                path = Path(dirpath) / fn
                sources[path.relative_to(BACKEND_DIR).as_posix()] = path.read_text(
                    encoding="utf-8"
                )
    return sources


# ===========================================================================
# 1. Capability keyword classification — single authority
# ===========================================================================


def _modules_compiling(pattern_fragment: str) -> list[str]:
    """Modules containing a module-level re.compile with the given fragment."""
    owners: list[str] = []
    for rel, src in _app_sources().items():
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign) or (
                isinstance(node, ast.AnnAssign) and node.value is not None
            ):
                value = node.value
            else:
                continue
            if not isinstance(value, ast.Call):
                continue
            func = value.func
            is_re_compile = (
                isinstance(func, ast.Attribute)
                and func.attr == "compile"
                and isinstance(func.value, ast.Name)
                and func.value.id == "re"
            )
            if not is_re_compile:
                continue
            joined = "".join(
                c.value
                for c in value.args
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            )
            if pattern_fragment in joined:
                owners.append(rel)
    return owners


def test_capability_patterns_defined_exactly_once() -> None:
    """Financial/banking/retrieval keyword regexes must have one definition site."""
    for fragment in ("ebitda", "finnapi", "bm25"):
        owners = _modules_compiling(fragment)
        assert owners == [PATTERN_MODULE], (
            f"Capability keyword '{fragment}' compiled in {owners}; "
            f"expected only {PATTERN_MODULE} (R-ARCH-01 duplicate authority)."
        )


def test_former_duplicate_pattern_copies_removed() -> None:
    """Planner, selector and supervisor must not define local keyword copies."""
    forbidden = {
        "app/agent/planning/planner.py": [
            "_FINANCIAL_KW",
            "_BANKING_KW",
            "_RETRIEVAL_KW",
        ],
        "app/agent/registry/agent_selector.py": [
            "_FINANCIAL_PATTERNS",
            "_BANKING_PATTERNS",
            "_RETRIEVAL_PATTERNS",
        ],
        "app/agents/supervisor.py": ["FINANCIAL_PATTERNS = [", "TOOL_PATTERNS = ["],
    }
    for rel, needles in forbidden.items():
        src = (BACKEND_DIR / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in src, (
                f"{rel} re-defines capability classification '{needle}'; "
                "it must consume app.agent.registry.capability_patterns."
            )


def test_layers_classify_goals_consistently() -> None:
    """The planner, the AgentSelector and the supervisor fallback must agree.

    Signals come from the one canonical pattern module; each layer keeps its
    own mapping (selector -> agent id, planner -> plan branch, supervisor ->
    LangGraph node), so consistency is asserted at the domain level.
    """
    selector = get_agent_selector()
    planner = BoundedPlanner()

    # Financial-only goal: all three layers agree on the financial domain.
    goal = "Quarterly EBITDA and operating margin variance review"
    assert bool(FINANCIAL_PATTERN.search(goal))
    assert not bool(BANKING_PATTERN.search(goal))
    assert (
        selector.select_agent(task_spec=_spec(goal)).agent_id == "financial_specialist"
    )
    plan = planner.create_initial_plan(goal=goal, tenant_id="tenant-arch-01")
    assert set(plan.steps[0].candidate_agents or []) == {"financial_specialist"}
    assert classify_intent(goal) == "financial_specialist"

    # Banking+financial goal: the planner's banking-first branch, the selector
    # and the supervisor fallback all involve the banking/financial specialists.
    goal = "finnapi account balance and EBITDA margin analysis"
    assert bool(BANKING_PATTERN.search(goal))
    assert bool(FINANCIAL_PATTERN.search(goal))
    plan = planner.create_initial_plan(goal=goal, tenant_id="tenant-arch-01")
    assert "finnapigo_specialist" in set(plan.steps[0].candidate_agents or [])
    assert classify_intent(goal) == "finnapigo_tool"
    assert selector.select_agent(task_spec=_spec(goal)).agent_id in {
        "finnapigo_specialist",
        "financial_specialist",
    }

    # Pure banking goal: selector and supervisor fallback route to banking.
    goal = "show my finnapi account balance"
    assert bool(BANKING_PATTERN.search(goal))
    assert not bool(FINANCIAL_PATTERN.search(goal))
    assert (
        selector.select_agent(task_spec=_spec(goal)).agent_id == "finnapigo_specialist"
    )
    assert classify_intent(goal) == "finnapigo_tool"

    # Retrieval goal: the selector routes to the retrieval specialist.
    goal = "search and retrieve documents from the rag knowledge base"
    assert bool(RETRIEVAL_PATTERN.search(goal))
    assert (
        selector.select_agent(task_spec=_spec(goal)).agent_id == "retrieval_specialist"
    )

    # General goal: the supervisor fallback routes to the synthesizer.
    assert classify_intent("Tell me about your weekend plans") == "synthesizer"


def _spec(goal: str) -> Any:
    from app.agent.domain.contracts import TaskSpec

    return TaskSpec(task_id="t", tenant_id="tenant-arch-01", user_id="u", goal=goal)


# ===========================================================================
# 2. Run/task lifecycle status — single authority
# ===========================================================================


def test_no_duplicate_lifecycle_status_authority() -> None:
    """The dead ExecutionStateStatus/TerminalState duplicates stay removed."""
    assert not hasattr(contracts, "ExecutionStateStatus")
    assert not hasattr(contracts, "TerminalState")
    for rel, src in _app_sources().items():
        assert "ExecutionStateStatus" not in src, (
            f"{rel} references removed duplicate lifecycle authority"
        )
        assert "class TerminalState" not in src, (
            f"{rel} re-defines terminal-state authority"
        )


def test_canonical_status_machine_is_the_lifecycle_authority() -> None:
    """RunStatus/TaskStatus expose terminal semantics with enforced transitions."""
    assert RunStatus.COMPLETED.is_terminal and RunStatus.COMPLETED.is_success
    assert RunStatus.CREATED.is_terminal is False
    for status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        assert status.is_terminal


# ===========================================================================
# 3. Provider credential resolution — single authority
# ===========================================================================


def test_provider_credential_map_defined_once() -> None:
    """The platform-key map must exist exactly once in llm_provider."""
    src = (BACKEND_DIR / "app/core/llm_provider.py").read_text(encoding="utf-8")
    assert src.count("OPENROUTER_API_KEY") == 1


class _FakeByok:
    def __init__(self, key: str | None) -> None:
        self.key = key
        self.asked: list[tuple[str, str]] = []

    async def get_decrypted_key(self, tenant_id: str, provider: str) -> str | None:
        self.asked.append((tenant_id, provider))
        return self.key


class _FakeSettings:
    OPENAI_API_KEY = "platform-openai-key"


@pytest.mark.asyncio
async def test_credential_resolution_byok_first_then_platform() -> None:
    """BYOK tenant key wins; platform key is the fallback for every variant."""
    byok = _FakeByok("tenant-byok-key")
    resolved = await resolve_provider_credentials(
        _FakeSettings(), byok, "tenant-1", "openai"
    )
    assert resolved == "tenant-byok-key"
    assert byok.asked == [("tenant-1", "openai")]

    byok = _FakeByok(None)
    resolved = await resolve_provider_credentials(
        _FakeSettings(), byok, "tenant-1", "openai"
    )
    assert resolved == "platform-openai-key"

    byok = _FakeByok(None)
    resolved = await resolve_provider_credentials(
        _FakeSettings(), byok, "tenant-1", "unknown-provider"
    )
    assert resolved is None


# ===========================================================================
# 4. Tool identity & OBO authority — single source in the tool
# ===========================================================================


@pytest.mark.asyncio
async def test_balance_tool_is_single_obo_and_account_authority() -> None:
    """The tool honors provided OBO tokens and owns the tenant account default."""
    tool = FinnApiGoBalanceTool()

    provided = await tool.execute(
        {}, {"tenant_id": "tenant-arch-01", "obo_token": "A" * 60}
    )
    assert provided.success
    assert provided.output["authorization"].startswith("Bearer " + "A" * 15)
    assert provided.output["account_id"] == "ACC-TENANT-A-01"

    self_exchanged = await tool.execute({}, {"tenant_id": "tenant-arch-01"})
    assert self_exchanged.success
    assert self_exchanged.output["authorization"].startswith("Bearer ")
    assert self_exchanged.output["authorization"].endswith("...")
    assert self_exchanged.output["account_id"] == "ACC-TENANT-A-01"


@pytest.mark.asyncio
async def test_transactions_tool_honors_provided_obo_token() -> None:
    tool = FinnApiGoTransactionsTool()
    result = await tool.execute(
        {"limit": 5}, {"tenant_id": "tenant-arch-01", "obo_token": "B" * 60}
    )
    assert result.success
    assert result.output["authorization"].startswith("Bearer " + "B" * 15)


def test_tenant_account_identity_derived_exactly_once() -> None:
    """The ACC-<tenant>-01 derivation must exist only in the builtin tool."""
    owners = [
        rel
        for rel, src in _app_sources().items()
        if "ACC-{" in src and "test" not in rel
    ]
    assert owners == ["app/agent/tools/builtins/finnapigo_tools.py"], (
        f"Tenant account identity derivation duplicated in {owners}"
    )


# ===========================================================================
# 5. Managed runtime — single wired backend dispatch
# ===========================================================================


def test_managed_runtime_wires_single_canonical_backend() -> None:
    """Even with a non-canonical backend_type, the runtime uses JakeAIBackend."""
    manager = AgentRuntimeManager(config=AgentConfig(backend_type="direct_provider"))
    assert isinstance(manager.backend, JakeAIBackend)


def test_non_canonical_backends_documented_as_adapter_boundary() -> None:
    """Standalone backends must declare their non-canonical boundary."""
    from app.agent.backends import direct_provider, external_agent

    assert direct_provider.__doc__ and "non-canonical" in direct_provider.__doc__
    assert (
        direct_provider.__doc__ and "app.core.llm_provider" in direct_provider.__doc__
    )
    assert external_agent.__doc__ and "non-canonical" in external_agent.__doc__
    assert external_agent.__doc__ and "app.core.llm_provider" in external_agent.__doc__


def test_settings_snapshot_unchanged_by_credential_refactor() -> None:
    """Guard against accidental drift of the platform-key provider set."""
    from app.core.llm_provider import _PROVIDER_SETTINGS_KEYS

    assert set(_PROVIDER_SETTINGS_KEYS) == {
        "anthropic",
        "openai",
        "groq",
        "deepseek",
        "openrouter",
        "gemini",
    }
    assert get_settings() is not None
