"""Tests for COST-06 and COST-07: Prompt Compression on Live Paths & Duplicate Compressor Consolidation.

Verifies:
1. ContextSelector is the single canonical authority for RAG chunk and string compression.
2. RetrievalCompressor deprecation warning and transparent delegation to ContextSelector.
3. ContextOptimizer quality guardrails (empty fallback, citation loss detection).
4. Live chat streaming endpoint integrates context optimization into live token accounting.
5. JakeAIBackend adapter optimizes dynamic conversation prompts before upstream invocation.
"""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.backends.base import AgentMessage, BackendRequest
from app.agent.backends.jakeai import JakeAIBackend
from app.api.v1.endpoints.chat import generate_chat_stream
from app.core.context import TenantContext
from app.optimizer.context_optimizer import ContextOptimizer, WorkloadType
from app.optimizer.retrieval_compressor import (
    RetrievalCompressionResult,
    get_retrieval_compressor,
)
from app.rag.context_selector import ContextSelector
from app.rag.models import DocumentChunk


def test_context_selector_compress_document_chunks() -> None:
    """Verify ContextSelector.compress_document_chunks filters and packs candidate chunks."""
    selector = ContextSelector()
    chunks = [
        DocumentChunk(
            chunk_id="chk-1",
            content="Q3 Enterprise Revenue grew 34% to $145.2M. [SEC-Q3-P10] All rights reserved.",
            score=0.95,
            tenant_id="tenant-test",
        ),
        DocumentChunk(
            chunk_id="chk-2",
            content="Summer picnic reminder: BBQ starts at 12pm. All rights reserved.",
            score=0.10,
            tenant_id="tenant-test",
        ),
    ]

    res = selector.compress_document_chunks(
        chunks=chunks,
        query="What was Enterprise Revenue?",
        min_relative_score=0.40,
    )

    assert isinstance(res, RetrievalCompressionResult)
    assert "$145.2M" in res.compressed_text
    assert "[SEC-Q3-P10]" in res.compressed_text
    assert "BBQ" not in res.compressed_text
    assert res.pruned_chunks_count == 1
    assert res.retained_chunks_count == 1
    assert res.tokens_saved > 0
    assert "[SEC-Q3-P10]" in res.citations_preserved


def test_context_selector_compress_rag_context_string() -> None:
    """Verify ContextSelector.compress_rag_context_string prunes labeled distractors."""
    selector = ContextSelector()
    rag_text = (
        "=== DOCUMENT EXCERPT [SEC-2026-Q1] ===\n"
        "Net income was $84.5 million, up 12% YoY.\n"
        "Terms and conditions apply. All rights reserved.\n\n"
        "=== DOCUMENT EXCERPT [DISTRACTOR-IRRELEVANT] ===\n"
        "Employee parking regulations for Lot 4. Do not park in red zones.\n"
    )

    res = selector.compress_rag_context_string(rag_text, query="net income")
    assert "$84.5 million" in res.compressed_text
    assert "[SEC-2026-Q1]" in res.compressed_text
    assert "parking regulations" not in res.compressed_text
    assert res.pruned_chunks_count >= 1
    assert res.tokens_saved > 0
    assert "[SEC-2026-Q1]" in res.citations_preserved


def test_retrieval_compressor_deprecation_and_delegation() -> None:
    """Verify RetrievalCompressor emits DeprecationWarning and delegates to ContextSelector."""
    compressor = get_retrieval_compressor()
    rag_text = (
        "=== DOCUMENT EXCERPT [SEC-Q2-P5] ===\n"
        "Cloud ARR surpassed $200.0M.\n"
        "All rights reserved. Confidential.\n"
    )

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        res = compressor.compress_rag_context_string(rag_text)
        assert len(recorded) >= 1
        assert issubclass(recorded[0].category, DeprecationWarning)
        assert "RetrievalCompressor is deprecated" in str(recorded[0].message)

    assert "$200.0M" in res.compressed_text
    assert "[SEC-Q2-P5]" in res.compressed_text


def test_context_optimizer_quality_guardrails_empty_fallback() -> None:
    """Verify ContextOptimizer safely falls back to raw context if reduced to empty."""
    optimizer = ContextOptimizer()
    raw_text = "Important system notes."

    # Simulate empty reduction
    with patch.object(optimizer.pruner, "prune_context") as mock_prune:
        mock_prune.return_value.pruned_text = "   "
        mock_prune.return_value.tokens_saved = 10
        opt = optimizer.optimize_dynamic_context(
            dynamic_context=raw_text,
            user_query="test",
            workload_type=WorkloadType.GENERAL,
        )
        assert opt.fallback_used is True
        assert opt.content == raw_text
        assert "empty_optimized_content" in str(opt.fallback_reason)


def test_context_optimizer_quality_guardrails_citation_loss() -> None:
    """Verify ContextOptimizer safely falls back to raw context if a citation is dropped."""
    optimizer = ContextOptimizer()
    raw_text = "Evidence from [SEC-CRITICAL-P10] indicates $50M profit."

    with patch.object(optimizer.pruner, "prune_context") as mock_prune:
        # Simulate pruner dropping the citation
        mock_prune.return_value.pruned_text = "Evidence indicates $50M profit."
        mock_prune.return_value.tokens_saved = 5
        opt = optimizer.optimize_dynamic_context(
            dynamic_context=raw_text,
            user_query="test",
            workload_type=WorkloadType.GENERAL,
        )
        assert opt.fallback_used is True
        assert opt.content == raw_text
        assert "citation_loss" in str(opt.fallback_reason)


@pytest.mark.asyncio
async def test_live_chat_stream_compression_accounting() -> None:
    """Verify live chat streaming path optimizes dynamic context and passes reduced tokens to TokenAccounting."""
    context = TenantContext(
        tenant_id="tenant-opt-test",
        user_id="user-1",
        roles=["analyst"],
        permissions=["read", "write"],
    )

    repetitive_rag = (
        "=== DOCUMENT EXCERPT [SEC-Q4-P1] ===\n"
        "Operating margin reached 28.5% with total net cash of $500.0M.\n"
        "Please review full disclaimer. All rights reserved. Forward looking statements apply.\n\n"
        "=== DOCUMENT EXCERPT [DISTRACTOR-IRRELEVANT-9] ===\n"
        "Company picnic is postponed until further notice. Please do not reply.\n"
    )

    events: list[str] = []
    with patch(
        "app.optimizer.token_accounting.TokenAccounting.record_transaction"
    ) as mock_record:
        from app.optimizer.token_accounting import TokenUsageRecord

        mock_record.return_value = TokenUsageRecord(
            request_id="test",
            tenant_id="tenant-opt-test",
            model="default",
            raw_input_tokens=150,
            optimized_input_tokens=80,
            completion_tokens=20,
            actual_billed_tokens=100,
            tokens_saved=70,
            reduction_percentage=41.18,
            cache_hit=False,
            cache_type="none",
        )

        async for chunk in generate_chat_stream(
            prompt="Summarize operating margin",
            context=context,
            conversation_id="conv-opt-123",
            parameters={"rag_context": repetitive_rag},
        ):
            events.append(chunk)

        assert mock_record.called
        call_kwargs = mock_record.call_args.kwargs
        assert call_kwargs["raw_input_tokens"] > call_kwargs["optimized_input_tokens"]
        assert call_kwargs["tenant_id"] == "tenant-opt-test"

    telemetry_events = [e for e in events if "event: telemetry" in e]
    assert len(telemetry_events) == 1
    assert "tokens_saved" in telemetry_events[0]


@pytest.mark.asyncio
async def test_jakeai_backend_compression_integration() -> None:
    """Verify JakeAIBackend optimizes combined prompt before invoking upstream LLM."""
    backend = JakeAIBackend(default_model="gemini-1.5-flash")
    req = BackendRequest(
        messages=[
            AgentMessage(
                role="user",
                content="Here is my code context:\n```python\nimport os\ndef a():\n    pass\n```\nAll rights reserved. Copyright 2026.",
            ),
            AgentMessage(
                role="assistant", content="Acknowledged. All rights reserved."
            ),
            AgentMessage(role="user", content="How does function a work?"),
        ],
        tenant_id="tenant-test",
    )

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = {
            "content": "Function a is a stub.",
            "model": "gemini-1.5-flash",
            "provider": "google",
            "prompt_tokens": 50,
            "completion_tokens": 10,
        }

        resp = await backend.generate(req)
        assert resp.content == "Function a is a stub."
        assert mock_call.called
        call_prompt = mock_call.call_args.kwargs["prompt"]
        assert "all rights reserved" not in call_prompt.lower()
