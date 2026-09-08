"""Regression tests for TASK-R1-04 / TOK-02, TOK-03: Full-Envelope Token Accounting.

Validates:
1. `raw_prompt_tokens` accounts for all model-visible input tokens:
   system instructions + conversation history turns + query + tools.
2. Tenant quota deductions meter the full model-visible prompt envelope.
3. Provider prompt cache savings (Layer B) are segregated from physical pruning (Layer A)
   and properly credited in TokenAccounting.
"""

from unittest.mock import patch

import pytest

from app.optimizer.token_accounting import TokenAccounting
from app.services.ai_gateway import (
    ChatMessage,
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)


@pytest.mark.asyncio
async def test_full_envelope_token_accounting() -> None:
    """Verify that multi-turn history and system instructions are counted in raw_prompt_tokens and quota."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-token-envelope-test"
    await quota_mgr.set_quota_limit(tenant_id, 1_000_000)
    await proxy.cache_mgr.invalidate(tenant_id)

    # 1,000-token system instruction (approx 4,000 chars of words)
    system_text = "system prompt instruction rule constraint " * 200  # ~1000 tokens
    # 500-token conversation history
    history_user = "user prior context conversation history data " * 50  # ~300 tokens
    history_asst = "assistant reply confirmation explanation data " * 50  # ~250 tokens
    # 50-token user query
    current_query = "What is the final status of the operation question? " * 5  # ~50 tokens

    messages = [
        ChatMessage(role="system", content=system_text),
        ChatMessage(role="user", content=history_user),
        ChatMessage(role="assistant", content=history_asst),
        ChatMessage(role="user", content=current_query),
    ]

    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=messages,
    )

    with patch.object(quota_mgr, "record_usage", wraps=quota_mgr.record_usage) as spy_usage:
        res = await proxy.chat_completions(tenant_id, req)

        # 1. Total tokens in usage must reflect the entire envelope, not just current_query
        assert res.usage["prompt_tokens"] >= 1500, (
            f"Prompt tokens was {res.usage['prompt_tokens']}, expected >= 1500"
        )

        # 2. Quota deduction must be called with prompt_tokens >= 1500
        assert spy_usage.call_count >= 1
        call_args = spy_usage.call_args[1] if spy_usage.call_args[1] else spy_usage.call_args[0]
        deducted_prompt_tokens = (
            call_args["prompt_tokens"]
            if isinstance(call_args, dict) and "prompt_tokens" in call_args
            else spy_usage.call_args[0][1]
        )
        assert deducted_prompt_tokens >= 1500, (
            f"Deducted tokens was {deducted_prompt_tokens}, expected >= 1500"
        )


def test_token_accounting_provider_cache_savings_segregation() -> None:
    """Verify TOK-03: Provider prompt cache savings are tracked when physical pruning is 0."""
    record = TokenAccounting.record_transaction(
        request_id="req-tok-03",
        tenant_id="tenant-tok-03",
        model="gpt-4o",
        raw_prompt_tokens=6000,
        pruned_prompt_tokens=6000,  # 0 physical pruning
        completion_tokens=200,
        cache_hit=False,
        provider_cache_hit=True,
        provider_cached_tokens=5000,
        provider_uncached_tokens=1000,
        provider_cost_savings_usd=0.00625,
    )

    # Assert segregation of fields
    assert record.physical_pruned_tokens == 0
    assert record.provider_cached_tokens == 5000
    assert record.tokens_saved >= 5000, (
        f"Expected tokens_saved >= 5000, got {record.tokens_saved}"
    )
    assert record.effective_billed_tokens < record.actual_billed_tokens
