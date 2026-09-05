"""Enterprise Guardrails Layer for JakeAI Platform."""

from typing import Any

from app.core.context import TenantContext
from app.guardrails.input_guard import GuardrailDecision, check_input_guardrail
from app.guardrails.output_guard import sanitize_output
from app.guardrails.pii_guard import mask_pii
from app.guardrails.rbac_guard import check_tool_rbac_guardrail


class GuardrailsEngine:
    """Unified guardrails orchestrator providing perimeter and post-generation shields."""

    @staticmethod
    def inspect_input(prompt: str) -> GuardrailDecision:
        """Evaluate input prompt for prompt injection or jailbreak attempts."""
        return check_input_guardrail(prompt)

    @staticmethod
    def inspect_tool_execution(
        tool_name: str,
        context: TenantContext | dict[str, Any],
    ) -> GuardrailDecision:
        """Enforce RBAC policy before agent tool execution."""
        return check_tool_rbac_guardrail(tool_name, context)

    @staticmethod
    def redact_pii(text: str) -> tuple[str, int]:
        """Redact sensitive PII from incoming queries or retrieved context."""
        return mask_pii(text)

    @staticmethod
    def inspect_and_sanitize_output(
        response: str,
        tenant_id: str,
        foreign_tenant_ids: list[str] | None = None,
    ) -> tuple[str, bool]:
        """Scrub output response for secrets, prompts, or foreign tenant data."""
        return sanitize_output(response, tenant_id, foreign_tenant_ids)


__all__ = [
    "GuardrailDecision",
    "GuardrailsEngine",
    "check_input_guardrail",
    "check_tool_rbac_guardrail",
    "mask_pii",
    "sanitize_output",
]
