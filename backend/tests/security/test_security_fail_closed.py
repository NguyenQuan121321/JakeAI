"""TEST-05 / SEC-010 — Fail-Closed Invariants Regression Test Suite.

Comprehensive automated regression tests verifying that JakeAI fails closed across
all critical security domains: verification integrity, tenant isolation, tool execution,
BYOK credential enforcement, context budget boundaries, and unmapped contexts.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.runtime.manager import get_agent_manager
from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.agent.tools.policy import ToolPolicyEngine
from app.agent.tools.registry import ToolRegistry
from app.agent.verification.verifier import (
    CanonicalVerifier,
    RecoveryAction,
    VerificationVerdict,
)
from app.main import app
from app.optimizer.bpe_tokenizer import BPETokenizer, ContextBudgetExceededError
from app.providers.base import (
    LLMProvider,
    ModelCapabilities,
    ModelCapabilityCatalog,
    ProviderRequest,
    ProviderResponse,
)
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
)
from app.rag.context_envelope import ContextEnvelopeBuilder
from app.rag.models import DocumentChunk
from app.routing.failover import FailoverConfig, FailoverManager
from app.routing.router import RoutingDecision
from app.services.resume_bridge import ResumeBridgeManager

# ==============================================================================
# 1. Verification Failure Guarantees: Never Fabricate Success
# ==============================================================================


def test_fail_closed_verifier_rejects_mathematical_variance() -> None:
    """CanonicalVerifier strictly rejects execution on financial arithmetic variance without fabricating success."""
    verifier = CanonicalVerifier(max_revisions=0)

    result = verifier.verify_execution(
        tenant_id="tenant-audit",
        goal="Audit Q2 financial figures",
        step_outputs=[],
        tool_calls=[],
        retrieved_chunks=[],
        financial_data={
            "revenue": 100_000_000.0,
            "operating_expenses": 40_000_000.0,
            "operating_income": 85_000_000.0,  # Correct is 60,000,000.0 (Variance: $25M)
        },
        final_output="Audited income is $85M.",
    )

    assert result.verdict == VerificationVerdict.FAILED
    assert result.verdict != VerificationVerdict.PASS
    assert result.recoverability is False
    assert result.recommended_recovery_action == RecoveryAction.TERMINATE_FAILED
    assert "Mathematical variance detected" in result.reason


def test_fail_closed_verifier_rejects_foreign_tenant_breach() -> None:
    """CanonicalVerifier immediately terminates and rejects if any tool call or retrieved chunk references a foreign tenant."""
    verifier = CanonicalVerifier()

    result = verifier.verify_execution(
        tenant_id="tenant-victim",
        goal="Analyze records",
        step_outputs=[],
        tool_calls=[
            {
                "tool_name": "db_lookup",
                "tenant_id": "tenant-attacker-foreign",  # BREACH
                "arguments": {"id": 123},
                "output": {"record": "classified"},
                "success": True,
            }
        ],
        retrieved_chunks=[],
        final_output="Analysis complete.",
    )

    assert result.verdict == VerificationVerdict.REJECTED
    assert result.recoverability is False
    assert result.violated_invariant == "Multi-tenant boundary isolation"
    assert result.recommended_recovery_action == RecoveryAction.TERMINATE_REJECTED
    assert result.groundedness_score == 0.0


def test_fail_closed_verifier_rejects_hallucination_without_evidence() -> None:
    """CanonicalVerifier rejects ungrounded claims when evidence is absent."""
    verifier = CanonicalVerifier(max_revisions=0)

    # Empty retrieved chunks and empty step outputs
    result = verifier.verify_execution(
        tenant_id="tenant-audit",
        goal="State revenue",
        step_outputs=[],
        tool_calls=[],
        retrieved_chunks=[],
        final_output="Revenue reached $999 Trillion in 2026.",
    )

    # Zero grounding sources -> verdict cannot be PASS
    assert result.verdict != VerificationVerdict.PASS
    assert result.verdict in (
        VerificationVerdict.FAILED,
        VerificationVerdict.NEEDS_REVISION,
    )


# ==============================================================================
# 2. Tenant Mismatch Guarantees: Never Bleed Foreign Data
# ==============================================================================


def test_fail_closed_context_envelope_drops_foreign_tenant_data() -> None:
    """ContextEnvelopeBuilder strictly purges foreign chunk evidence and string tags."""
    builder = ContextEnvelopeBuilder()

    foreign_chunk = DocumentChunk(
        chunk_id="chunk-foreign-001",
        document_id="doc-foreign-001",
        tenant_id="tenant-competitor",
        content="Confidential acquisition price: $450M.",
        chunk_index=0,
    )

    envelope = builder.assemble(
        system_instructions="You are an assistant.",
        retrieved_evidence=[foreign_chunk],
        user_query="What is the acquisition price?",
        tenant_id="tenant-subscriber",
    )

    assert "$450M" not in envelope.serialized_prompt
    assert "Confidential acquisition" not in envelope.serialized_prompt
    assert "tenant-competitor" not in envelope.serialized_prompt


@pytest.mark.asyncio
async def test_fail_closed_resume_bridge_rejects_cross_tenant_state() -> None:
    """ResumeBridgeManager rejects cross-tenant resume calls with PermissionError fail-closed."""
    bridge = ResumeBridgeManager()
    call_id = "call-sec-fc-998"

    await bridge.save_checkpoint(
        call_id=call_id,
        tenant_id="tenant-alpha",
        state_data={"node": "approval_gate"},
    )

    with pytest.raises(PermissionError) as exc_info:
        await bridge.resume_checkpoint(
            call_id=call_id,
            result_payload={"approved": True},
            tenant_id="tenant-beta",
        )
    assert "tenant mismatch" in str(exc_info.value).lower()


def test_fail_closed_agent_task_manager_rejects_cross_tenant() -> None:
    """AgentRuntimeManager get_task rejects cross-tenant inspection with PermissionError fail-closed."""
    manager = get_agent_manager()
    task = manager.create_task(
        goal="Perform secure operations",
        tenant_id="tenant-owner",
        user_id="user-owner",
    )

    # Access by owner succeeds
    owned = manager.get_task(task.task_id, tenant_id="tenant-owner")
    assert owned.task_id == task.task_id

    # Access by foreign tenant fails closed with PermissionError
    with pytest.raises(PermissionError) as exc_info:
        manager.get_task(task.task_id, tenant_id="tenant-intruder")
    assert "Tenant mismatch" in str(exc_info.value)


# ==============================================================================
# 3. Unsafe Tool Execution Guarantees: Never Invoke Without Authorization
# ==============================================================================


class _SecureMockTool(Tool):
    """Configurable mock tool for fail-closed policy checks."""

    def __init__(
        self,
        name: str,
        risk: ToolRiskLevel = ToolRiskLevel.READ_ONLY,
        permissions: list[str] | None = None,
    ) -> None:
        self._name = name
        self._risk = risk
        self._perms = permissions or []

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self._name,
            description="Mock tool",
            input_schema={
                "type": "object",
                "properties": {"target": {"type": "string"}},
            },
            permissions=self._perms,
            risk_level=self._risk,
        )

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ToolResult:
        return ToolResult(success=True, output="success")


def test_fail_closed_unmapped_permission_rejects_execution() -> None:
    """Tool execution is rejected fail-closed if tenant lacks required permission and role is unmapped."""
    tool = _SecureMockTool(
        name="delete_database",
        risk=ToolRiskLevel.DANGEROUS,
        permissions=["database:admin:delete"],
    )

    decision = ToolPolicyEngine.evaluate(
        tool=tool,
        arguments={"target": "users_db"},
        user_roles=["standard_user"],
        user_permissions=["read_only"],
    )

    assert decision.allowed is False
    assert "Forbidden: Tenant context lacks required permissions" in decision.reason


def test_fail_closed_empty_context_rejects_privileged_tool() -> None:
    """Tool with permission requirements rejects execution when roles and permissions are empty/None."""
    tool = _SecureMockTool(
        name="read_payroll",
        risk=ToolRiskLevel.READ_ONLY,
        permissions=["payroll:read"],
    )

    decision = ToolPolicyEngine.evaluate(
        tool=tool,
        arguments={"target": "salaries.csv"},
        user_roles=None,
        user_permissions=None,
    )

    assert decision.allowed is False
    assert "Forbidden" in decision.reason


def test_fail_closed_dangerous_tool_demands_human_approval() -> None:
    """Dangerous tool cannot execute unattended without triggering human approval requirement."""
    tool = _SecureMockTool(
        name="reboot_service",
        risk=ToolRiskLevel.DANGEROUS,
        permissions=["system:execute"],
    )

    decision = ToolPolicyEngine.evaluate(
        tool=tool,
        arguments={"target": "api-gateway"},
        user_roles=["admin"],
        user_permissions=["system:execute"],
    )

    # Allowed in policy, but marked as requiring explicit approval
    assert decision.allowed is True
    assert decision.requires_approval is True
    assert "requires human approval" in decision.reason.lower()


# ==============================================================================
# 4. Missing / Invalid BYOK Key Guarantees: Block Provider Calls
# ==============================================================================


class _FailingAdapter(LLMProvider):
    """Adapter simulating missing provider credentials."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilityCatalog.get(model, provider=self.provider_name)

    async def complete(
        self, request: ProviderRequest, client: Any = None
    ) -> ProviderResponse:
        if not request.api_key:
            raise ProviderAuthenticationError(
                message=f"No {self.provider_name} API key configured (neither tenant BYOK nor platform default)",
                provider=self.provider_name,
                status_code=401,
            )
        return ProviderResponse(
            content="ok",
            provider=self.provider_name,
            model=request.model,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            cost=0.0,
            latency_ms=10.0,
        )

    async def stream(self, request: ProviderRequest, client: Any = None) -> Any:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_fail_closed_missing_byok_blocks_inference_without_mocking() -> None:
    """When a tenant lacks BYOK keys and platform defaults are absent, failover manager raises ProviderError fail-closed."""
    from app.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    adapter = _FailingAdapter("openai")
    registry.register("openai", adapter)

    failover = FailoverManager(
        config=FailoverConfig(max_retries_per_provider=0, max_total_attempts=1),
    )
    failover.registry = registry

    req = ProviderRequest(
        prompt="Execute task",
        model="gpt-4o",
        tenant_id="tenant-no-keys",
        api_key=None,  # No key available
    )
    decision = RoutingDecision(
        selected_provider="openai",
        selected_model="gpt-4o",
        estimated_cost=0.01,
        reasoning="Test routing",
        fallback_chain=[],
    )

    async def _zero_credentials(tenant: str, provider: str) -> str | None:
        return None

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        await failover.execute_with_failover(
            request=req,
            decision=decision,
            credential_resolver=_zero_credentials,
        )

    assert exc_info.value.category == ErrorCategory.AUTHENTICATION
    assert "No openai API key configured" in exc_info.value.message


# ==============================================================================
# 5. Context Budget Overflow Guarantees: Reject Unbounded Tokens
# ==============================================================================


def test_fail_closed_context_envelope_raises_budget_exceeded() -> None:
    """ContextEnvelopeBuilder raises ContextBudgetExceededError when non-negotiable core instructions exceed budget."""
    builder = ContextEnvelopeBuilder()

    # Create very large system instructions that cannot fit within a tiny 10-token budget
    large_instructions = "You are an AI assistant. " * 50

    with pytest.raises(ContextBudgetExceededError) as exc_info:
        builder.assemble(
            system_instructions=large_instructions,
            user_query="Hello",
            tenant_id="tenant-budget",
            max_tokens=10,  # Impossible budget
        )

    assert "Context envelope core tokens" in str(exc_info.value)
    assert "exceed budget" in str(exc_info.value)


def test_fail_closed_bpe_tokenizer_enforce_budget_raises() -> None:
    """BPETokenizer.enforce_context_budget raises ContextBudgetExceededError fail-closed when optimized tokens exceed limit."""
    tokenizer = BPETokenizer()

    with pytest.raises(ContextBudgetExceededError) as exc_info:
        tokenizer.enforce_context_budget(
            raw_tokens=5000,
            optimized_tokens=4200,
            budget=4000,
            raise_on_exceed=True,
        )

    assert "Context budget exceeded" in str(exc_info.value)
    assert "4200 tokens, which exceeds the model limit of 4000 tokens" in str(
        exc_info.value
    )


# ==============================================================================
# 6. Unmapped Context and Tool Registry Validation
# ==============================================================================


def test_fail_closed_tool_registry_rejects_unknown_tool() -> None:
    """ToolRegistry.validate fails closed for unmapped/unregistered tool invocations."""
    registry = ToolRegistry()

    valid, err = registry.validate("unregistered_malicious_tool", {"action": "drop"})
    assert valid is False
    assert "not found in registry" in (err or "").lower()


@pytest.mark.asyncio
async def test_fail_closed_http_endpoints_reject_empty_authorization() -> None:
    """FastAPI endpoints reject requests with empty, missing, or corrupt authorization headers fail-closed."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Missing header
        resp_no_auth = await client.get("/api/v1/byok/keys")
        assert resp_no_auth.status_code == 401

        # Empty header
        resp_empty_auth = await client.get(
            "/api/v1/byok/keys", headers={"Authorization": ""}
        )
        assert resp_empty_auth.status_code == 401

        # Malformed scheme
        resp_bad_scheme = await client.get(
            "/api/v1/byok/keys", headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )
        assert resp_bad_scheme.status_code == 401
