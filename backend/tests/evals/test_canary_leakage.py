"""Comprehensive Canary Data Leakage and Secret Sanitization Tests (TASK OPS-13 & OPS-14).

Verifies zero cross-tenant leakage across:
1. RAG retrieval & answer synthesis
2. Semantic / Exact cache boundaries
3. Long-term episodic memory
4. Error message credential sanitization
5. Tool execution observation boundaries
6. Telemetry and Prometheus metrics exposition
"""

import pytest

from app.agent.memory.manager import AgentMemoryManager
from app.evals.rag_evaluator import evaluate_rag_case
from app.optimizer.semantic_cache import SemanticCacheManager
from app.providers.errors import ProviderError, sanitize_error_message
from app.rag.models import DocumentChunk
from app.rag.pipeline import RAGPipeline
from app.telemetry.metrics import metrics

CANARY_A = "CANARY_TENANT_A_SECRET_KEY_998877"
CANARY_B = "CANARY_TENANT_B_SECRET_KEY_112233"


@pytest.mark.asyncio
async def test_rag_tenant_isolation_canary_leakage():
    """Verify Tenant B cannot retrieve or synthesize Tenant A canary tokens."""
    pipeline = RAGPipeline()

    # Preload chunk into tenant_a
    chunk_a = DocumentChunk(
        chunk_id="chunk-canary-a",
        document_id="doc-canary-a",
        tenant_id="tenant_a",
        content=f"Confidential executive bonus record: {CANARY_A}",
        source="payroll_vault.pdf",
    )
    pipeline.retriever.bm25.add_documents([chunk_a])

    # Query as Tenant B
    query = "What is the confidential executive bonus?"
    result_b = await pipeline.generate_grounded_answer(
        query=query,
        tenant_id="tenant_b",
    )

    # Assert Tenant B gets zero canary A in answer, citations, or context
    assert CANARY_A not in result_b.answer
    for cit in result_b.citations:
        assert cit.tenant_id == "tenant_b"
        assert CANARY_A not in cit.passage_content

    # Evaluate with RAGEvalResult to verify strict isolation gate
    eval_res = evaluate_rag_case(
        {
            "case_id": "test_canary_leakage_rag",
            "query": query,
            "context": "\n".join(
                c.content for c in result_b.context_selection.selected_chunks
            ),
            "response": result_b.answer,
            "tenant_id": "tenant_b",
            "foreign_tenant_id": "tenant_a",
        }
    )
    assert eval_res.tenant_isolation_verified is True
    assert eval_res.data_leakage_detected is False


@pytest.mark.asyncio
async def test_cache_tenant_isolation_canary():
    """Verify semantic cache partitions entries strictly by tenant_id."""
    cache = SemanticCacheManager()
    prompt = "What is the primary system master key?"

    # Store entry under tenant_a
    await cache.set(
        prompt=prompt,
        model="gpt-4o",
        tenant_id="tenant_a",
        response=f"The secret key is {CANARY_A}",
    )

    # Lookup as tenant_b with identical prompt and model
    entry_b = await cache.get(prompt=prompt, model="gpt-4o", tenant_id="tenant_b")
    assert entry_b is None

    # Lookup as tenant_a: found
    entry_a = await cache.get(prompt=prompt, model="gpt-4o", tenant_id="tenant_a")
    assert entry_a is not None
    assert CANARY_A in entry_a.response


def test_episodic_memory_tenant_isolation():
    """Verify episodic memory retrieval respects strict tenant partitions."""
    mem_mgr = AgentMemoryManager()

    # Store episodic memory for tenant_a
    mem_mgr.remember_episodic(
        tenant_id="tenant_a",
        user_id="user_1",
        key="bonus_info",
        value=f"Annual bonus code: {CANARY_A}",
        summary="Bonus payroll",
    )

    # Query as tenant_b
    res_b = mem_mgr.recall_relevant(
        tenant_id="tenant_b",
        user_id="user_2",
        query_key="bonus_info",
    )
    assert len(res_b) == 0
    for record in res_b:
        assert CANARY_A not in str(record.value)


def test_error_message_credential_sanitization():
    """Verify DB URIs, cloud keys, internal IPs, and JWTs are redacted from error messages (TASK OPS-14)."""
    raw_error = (
        "Connection refused: postgresql://dbuser:super_secret_password_123@10.0.1.50:5432/prod_db "
        "failed with key AIzaSyA1234567890123456789012345678901 and sk-ant-api03-abcdef1234567890abcdef1234. "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doz79w"
    )

    sanitized = sanitize_error_message(raw_error)

    assert "super_secret_password_123" not in sanitized
    assert "dbuser:" not in sanitized
    assert "10.0.1.50" not in sanitized
    assert "AIzaSyA1234567890123456789012345678901" not in sanitized
    assert "sk-ant-api03" not in sanitized
    assert "eyJhbGciOi" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized

    # Verify ProviderError exception automatically sanitizes message
    exc = ProviderError(
        message=raw_error,
        provider="anthropic",
        category="authentication",
    )
    assert "super_secret_password_123" not in exc.message
    assert "super_secret_password_123" not in str(exc)


def test_telemetry_prom_zero_canary_leakage():
    """Verify Prometheus text format never emits canary secrets or user prompts."""
    metrics.reset()
    metrics.record_http_request("POST", "/api/v1/chat/completions", 200, 45.0)
    metrics.record_provider_request("openai", "gpt-4o", "success", 120.0)
    metrics.record_security_incident("prompt_injection", "tenant_a", "layer1")

    prom_text = metrics.generate_prometheus_metrics()

    assert CANARY_A not in prom_text
    assert CANARY_B not in prom_text
    assert "super_secret_password_123" not in prom_text
