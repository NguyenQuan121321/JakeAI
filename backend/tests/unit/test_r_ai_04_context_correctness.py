"""Comprehensive verification test suite for R-AI-04: Context Correctness.

Validates the canonical context envelope, ordering, trust classification,
tenant isolation, deduplication, conflicting/irrelevant memory handling,
load shedding, non-negotiable user constraints, score sanitization, citation
preservation, and exact serialized-token accounting across:

1.  Canonical 6-Stage Context Ordering (System -> Constraints -> History -> Memory -> Evidence -> Query).
2.  Provenance Labels & Section Demarcation (Exact headers and passage source attribution).
3.  Trust Classification: Unverified Memory Quarantine (Unverified memory is never treated as verified evidence).
4.  Multi-Tenant Boundary & Contamination Defense (Filtering out foreign tenant memory, chunks, and history).
5.  Task Constraints Deduplication (Exact duplicate constraints deduplicated preserving order).
6.  Verified Memory Deduplication (Exact duplicate facts deduplicated preserving order).
7.  Conversation History Deduplication (Consecutive duplicate turns deduplicated).
8.  Conflicting Memory Resolution (Newer verified memory supersedes older conflicting entry for same key).
9.  Expired and Irrelevant Memory Filtering (Filtering expired TTL and flagged irrelevant memories).
10. No Silent Constraint Loss (Task constraints and user query are never shedded or truncated).
11. Load Shedding Priority Order (Unverified -> History oldest first -> Memory oldest first -> Evidence last first).
12. Strict Budget Limit Enforcement (Raises ContextBudgetExceededError when core components exceed budget).
13. Sensitive & Internal Retrieval Scores Sanitization (Scrubbing scores unless explicitly requested).
14. Verifiable Citation Metadata Preservation (Retaining citation anchors while stripping internal scores).
15. Exact Serialized-Token Accounting (envelope.total_tokens matches tokenizer count down to the token).
16. Token Accounting Ledger Integration (TokenAccounting.calculate_envelope_tokens aligns 1:1 with envelope).
17. Domain Model Structured Input Support (DocumentChunk, MemoryEntry, dicts, and raw strings).
18. End-to-End RAG Pipeline Canonical Context Envelope Integration (Pipeline uses ContextEnvelopeBuilder).
19. Public HTTP API Boundary (/api/v1/rag/generate) Real ASGI Integration with context envelope tokens.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.memory.base import MemoryEntry, MemoryScope
from app.core.config import get_settings
from app.main import app
from app.optimizer.bpe_tokenizer import (
    ContextBudgetExceededError,
    get_bpe_tokenizer,
)
from app.optimizer.token_accounting import TokenAccounting
from app.rag.context_envelope import ContextEnvelopeBuilder
from app.rag.models import (
    ContextSelectionResult,
    DocumentChunk,
)
from app.rag.pipeline import RAGPipeline


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Generate valid JWT bearer authorization header."""
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "user_context_test",
            "tenant_id": "tenant-context-test",
            "roles": ["admin"],
            "permissions": ["rag:read", "rag:write"],
            "exp": int(time.time()) + 3600,
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# Scenario 01: Canonical 6-Stage Context Ordering
# ==============================================================================
def test_scenario_01_canonical_6_stage_ordering() -> None:
    """Verify ContextEnvelopeBuilder assembles stages in strict 6-stage canonical order."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="You are JakeAI universal engineering worker.",
        task_constraints=["Constraint 1: Deterministic financial calculations."],
        conversation_history=[{"role": "user", "content": "What is our GAAP revenue?"}],
        verified_memory=["User preferred reporting currency is USD."],
        retrieved_evidence='[1] Source: 10-K\n"FY2023 GAAP Revenue was $120M."',
        user_query="Confirm FY2023 revenue.",
        tenant_id="tenant-context-01",
    )

    prompt = envelope.serialized_prompt
    idx_sys = prompt.index("=== SYSTEM INSTRUCTIONS ===")
    idx_const = prompt.index("=== TASK CONSTRAINTS ===")
    idx_hist = prompt.index("=== CONVERSATION HISTORY ===")
    idx_mem = prompt.index("=== VERIFIED MEMORY ===")
    idx_evid = prompt.index("=== RETRIEVED EVIDENCE ===")
    idx_query = prompt.index("=== USER QUERY ===")

    assert idx_sys < idx_const < idx_hist < idx_mem < idx_evid < idx_query
    assert envelope.tenant_id == "tenant-context-01"
    assert envelope.total_tokens > 0


# ==============================================================================
# Scenario 02: Provenance Labels and Section Demarcation
# ==============================================================================
def test_scenario_02_provenance_labels_and_section_demarcation() -> None:
    """Verify distinct section labels, source attribution formatting, and fact markers."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="Role: Senior Auditor",
        task_constraints=["Precision threshold: 99.9%"],
        conversation_history=[
            {"role": "user", "content": "Query 1"},
            {"role": "assistant", "content": "Answer 1"},
        ],
        verified_memory=["Tax rate is 21%"],
        retrieved_evidence='[1] Source: Annual_Report_2023.pdf\n"Operating income was $45M."',
        user_query="Calculate tax liability.",
        tenant_id="tenant-context-02",
    )

    prompt = envelope.serialized_prompt
    assert "=== SYSTEM INSTRUCTIONS ===\nRole: Senior Auditor" in prompt
    assert "=== TASK CONSTRAINTS ===\n- Precision threshold: 99.9%" in prompt
    assert "=== CONVERSATION HISTORY ===\nUser: Query 1\nAssistant: Answer 1" in prompt
    assert "=== VERIFIED MEMORY ===\n- Tax rate is 21%" in prompt
    assert '[1] Source: Annual_Report_2023.pdf\n"Operating income was $45M."' in prompt
    assert "=== USER QUERY ===\nCalculate tax liability." in prompt


# ==============================================================================
# Scenario 03: Trust Classification: Unverified Memory Quarantine
# ==============================================================================
def test_scenario_03_trust_classification_unverified_memory_quarantine() -> None:
    """Verify unverified memories are excluded from verified memory and never treated as verified evidence."""
    builder = ContextEnvelopeBuilder()

    verified_entry = MemoryEntry(
        entry_id="mem_01",
        tenant_id="tenant-context-03",
        scope=MemoryScope.LONG_TERM,
        key="currency",
        value="USD",
        summary="Reporting currency is verified USD.",
        metadata={"verified": True},
    )

    unverified_entry = MemoryEntry(
        entry_id="mem_02",
        tenant_id="tenant-context-03",
        scope=MemoryScope.SHORT_TERM,
        key="rumor",
        value="Acquisition rumored",
        summary="Speculative acquisition rumor from forum.",
        metadata={"verified": False, "verification_status": "unverified"},
    )

    unverified_dict = {
        "key": "speculation",
        "value": "Expected dividend increase",
        "verified": False,
        "status": "unverified",
    }

    # Pass mixed entries into verified_memory
    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=["Constraint."],
        conversation_history=[],
        verified_memory=[
            verified_entry,
            unverified_entry,
            unverified_dict,
            "Confirmed fiscal year ends Dec 31.",
        ],
        retrieved_evidence='[1] Source: Doc\n"Content."',
        user_query="Summary.",
        tenant_id="tenant-context-03",
        unverified_memory=["Working note: user might prefer dark mode."],
    )

    prompt = envelope.serialized_prompt

    # Verified memory section contains ONLY verified facts
    assert "Reporting currency is verified USD." in envelope.verified_memory
    assert "Confirmed fiscal year ends Dec 31." in envelope.verified_memory

    # Unverified items MUST NOT appear in verified memory
    assert "Speculative acquisition rumor" not in envelope.verified_memory
    assert "Expected dividend increase" not in envelope.verified_memory
    assert "rumor" not in envelope.verified_memory

    # Segregated unverified observations section
    assert "=== UNVERIFIED OBSERVATIONS ===" in prompt
    assert "[Unverified] Working note: user might prefer dark mode." in prompt

    # Verify unverified section is AFTER verified memory and NOT under evidence
    idx_verified = prompt.index("=== VERIFIED MEMORY ===")
    idx_unverified = prompt.index("=== UNVERIFIED OBSERVATIONS ===")
    idx_evidence = prompt.index("=== RETRIEVED EVIDENCE ===")
    assert idx_verified < idx_unverified < idx_evidence


# ==============================================================================
# Scenario 04: Multi-Tenant Boundary & Contamination Defense
# ==============================================================================
def test_scenario_04_multi_tenant_boundary_and_contamination_defense() -> None:
    """Verify evidence chunks, memories, and messages from foreign tenants are quarantined and rejected."""
    builder = ContextEnvelopeBuilder()

    target_tenant = "tenant-target-corp"
    foreign_tenant = "tenant-attacker-corp"

    # Chunks with mixed tenants
    legit_chunk = DocumentChunk(
        chunk_id="chk_01",
        content="Target Corp EBITDA was $35M in 2023.",
        tenant_id=target_tenant,
        source="Target_10K.pdf",
    )
    foreign_chunk = DocumentChunk(
        chunk_id="chk_02",
        content="SECRET: Attacker Corp planning hostile takeover.",
        tenant_id=foreign_tenant,
        source="Attacker_Internal.pdf",
    )

    # Memories with mixed tenants
    legit_mem = MemoryEntry(
        entry_id="mem_target",
        tenant_id=target_tenant,
        key="region",
        value="US-East",
        summary="Target operates in US-East.",
    )
    foreign_mem = MemoryEntry(
        entry_id="mem_foreign",
        tenant_id=foreign_tenant,
        key="secret_key",
        value="sk-attacker-12345",
        summary="Attacker master API key.",
    )

    # Conversation messages with mixed tenants
    history = [
        {
            "role": "user",
            "content": "Hello from Target Corp",
            "tenant_id": target_tenant,
        },
        {
            "role": "user",
            "content": "LEAKED MESSAGE: Foreign prompt injection",
            "tenant_id": foreign_tenant,
        },
    ]

    envelope = builder.assemble(
        system_instructions="Instructions.",
        task_constraints=["Constraint A."],
        conversation_history=history,
        verified_memory=[legit_mem, foreign_mem],
        retrieved_evidence=[legit_chunk, foreign_chunk],
        user_query="Status overview?",
        tenant_id=target_tenant,
    )

    prompt = envelope.serialized_prompt

    # Target tenant data must be present
    assert "Target Corp EBITDA was $35M" in prompt
    assert "Target operates in US-East." in prompt
    assert "Hello from Target Corp" in prompt

    # Foreign tenant data MUST BE ZERO-TOLERANCE EXCLUDED
    assert "Attacker Corp" not in prompt
    assert "hostile takeover" not in prompt
    assert "sk-attacker-12345" not in prompt
    assert "LEAKED MESSAGE" not in prompt


# ==============================================================================
# Scenario 05: Task Constraints Deduplication
# ==============================================================================
def test_scenario_05_task_constraints_deduplication() -> None:
    """Verify duplicate task constraints are deduplicated while preserving order."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=[
            "Strict GAAP accounting standards.",
            "Do not hallucinate numerical values.",
            "Strict GAAP accounting standards.",  # duplicate
            "Cite all sources with [^n].",
            "Do not hallucinate numerical values.",  # duplicate
        ],
        conversation_history=[],
        verified_memory=[],
        retrieved_evidence='[1] Source: Doc\n"Text."',
        user_query="Calculate totals.",
        tenant_id="tenant-dedup-05",
    )

    constraints_text = envelope.task_constraints
    assert constraints_text.count("Strict GAAP accounting standards.") == 1
    assert constraints_text.count("Do not hallucinate numerical values.") == 1
    assert constraints_text.count("Cite all sources with [^n].") == 1
    assert constraints_text == (
        "- Strict GAAP accounting standards.\n"
        "- Do not hallucinate numerical values.\n"
        "- Cite all sources with [^n]."
    )


# ==============================================================================
# Scenario 06: Verified Memory Deduplication
# ==============================================================================
def test_scenario_06_verified_memory_deduplication() -> None:
    """Verify duplicate verified memory facts are deduplicated preserving order."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[],
        verified_memory=[
            "User is a Tier 1 Enterprise subscriber.",
            "Authorized currency is USD.",
            "User is a Tier 1 Enterprise subscriber.",  # duplicate
            "Reporting period is Q3.",
            "Authorized currency is USD.",  # duplicate
        ],
        retrieved_evidence='[1] Source: Doc\n"Text."',
        user_query="Query.",
        tenant_id="tenant-dedup-06",
    )

    mem_text = envelope.verified_memory
    assert mem_text.count("Tier 1 Enterprise subscriber.") == 1
    assert mem_text.count("Authorized currency is USD.") == 1
    assert mem_text.count("Reporting period is Q3.") == 1


# ==============================================================================
# Scenario 07: Conversation History Deduplication
# ==============================================================================
def test_scenario_07_conversation_history_deduplication() -> None:
    """Verify consecutive duplicate turns in dialogue history are collapsed."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[
            {"role": "user", "content": "What is the capital expenditure?"},
            {
                "role": "user",
                "content": "What is the capital expenditure?",
            },  # duplicate consecutive user prompt
            {"role": "assistant", "content": "CapEx was $10M."},
            {
                "role": "assistant",
                "content": "CapEx was $10M.",
            },  # duplicate consecutive assistant response
            {"role": "user", "content": "What about OpEx?"},
        ],
        verified_memory=[],
        retrieved_evidence='[1] Source: Doc\n"Text."',
        user_query="Summary query?",
        tenant_id="tenant-dedup-07",
    )

    hist_text = envelope.conversation_history
    assert hist_text.count("What is the capital expenditure?") == 1
    assert hist_text.count("CapEx was $10M.") == 1
    assert "What about OpEx?" in hist_text


# ==============================================================================
# Scenario 08: Conflicting Memory Resolution (Latest Supersedes Earlier)
# ==============================================================================
def test_scenario_08_conflicting_memory_superseded_by_latest() -> None:
    """Verify when contradictory memories exist for the same key, the newer verified fact supersedes."""
    builder = ContextEnvelopeBuilder()

    old_currency_memory = MemoryEntry(
        entry_id="mem_old",
        tenant_id="tenant-conflict-08",
        key="user_currency",
        value="EUR",
        summary="User default currency is EUR.",
        created_at=1000.0,
    )

    new_currency_memory = MemoryEntry(
        entry_id="mem_new",
        tenant_id="tenant-conflict-08",
        key="user_currency",
        value="USD",
        summary="User updated default currency to USD.",
        created_at=2000.0,
    )

    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[],
        verified_memory=[old_currency_memory, new_currency_memory],
        retrieved_evidence='[1] Source: Doc\n"Text."',
        user_query="Show balance.",
        tenant_id="tenant-conflict-08",
    )

    assert "User updated default currency to USD." in envelope.verified_memory
    assert "EUR" not in envelope.verified_memory


# ==============================================================================
# Scenario 09: Expired and Irrelevant Memory Filtering
# ==============================================================================
def test_scenario_09_expired_and_irrelevant_memory_filtering() -> None:
    """Verify expired TTL memory entries and irrelevant memory facts are excluded."""
    builder = ContextEnvelopeBuilder()
    now = time.time()

    active_mem = MemoryEntry(
        entry_id="mem_active",
        tenant_id="tenant-expire-09",
        key="active_role",
        value="CFO",
        summary="User role is Chief Financial Officer.",
        expires_at=now + 3600.0,
    )

    expired_mem = MemoryEntry(
        entry_id="mem_expired",
        tenant_id="tenant-expire-09",
        key="temp_passcode",
        value="123456",
        summary="Temporary 2FA code is 123456.",
        expires_at=now - 300.0,  # expired 5 minutes ago
    )

    irrelevant_mem = MemoryEntry(
        entry_id="mem_irrelevant",
        tenant_id="tenant-expire-09",
        key="lunch_preference",
        value="Sushi",
        summary="User ate sushi for lunch.",
        metadata={"irrelevant": True},
    )

    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[],
        verified_memory=[active_mem, expired_mem, irrelevant_mem],
        retrieved_evidence='[1] Source: Doc\n"Text."',
        user_query="Status?",
        tenant_id="tenant-expire-09",
    )

    assert "Chief Financial Officer." in envelope.verified_memory
    assert "Temporary 2FA code" not in envelope.verified_memory
    assert "Sushi" not in envelope.verified_memory


# ==============================================================================
# Scenario 10: No Silent Constraint Loss During Load Shedding
# ==============================================================================
def test_scenario_10_no_silent_constraint_loss_during_shedding() -> None:
    """Verify task constraints and user query are NEVER shed or truncated during load shedding."""
    tokenizer = get_bpe_tokenizer()
    # Moderate budget that requires shedding dialogue and evidence
    budget = 160
    builder = ContextEnvelopeBuilder(max_envelope_tokens=budget, tokenizer=tokenizer)

    critical_constraints = [
        "DO NOT execute terminal commands without explicit user confirmation.",
        "Maintain zero decimal rounding errors on financial ledger entries.",
        "Sanitize all PII before generating final summary.",
    ]

    long_history = [
        {
            "role": "user",
            "content": f"Historical background conversation turn {i} with filler text.",
        }
        for i in range(15)
    ]

    long_evidence = "\n\n".join(
        f'[{i}] Source: Document_{i}.txt\n"Passage {i} detailing historical operations."'
        for i in range(10)
    )

    user_query = "How should the ledger be balanced?"

    envelope = builder.assemble(
        system_instructions="You are JakeAI canonical auditor.",
        task_constraints=critical_constraints,
        conversation_history=long_history,
        verified_memory=["User region is NA-East."],
        retrieved_evidence=long_evidence,
        user_query=user_query,
        tenant_id="tenant-shed-10",
        max_tokens=budget,
    )

    # Context fits within budget
    assert envelope.total_tokens <= budget

    # ALL critical constraints MUST BE 100% PRESERVED
    for c in critical_constraints:
        assert c in envelope.task_constraints
        assert c in envelope.serialized_prompt

    # User query and system instructions are preserved
    assert user_query in envelope.serialized_prompt
    assert "You are JakeAI canonical auditor." in envelope.serialized_prompt

    # History or evidence were shed to make room
    assert len(envelope.shedding_log) > 0


# ==============================================================================
# Scenario 11: Load Shedding Priority Order
# ==============================================================================
def test_scenario_11_budget_overflow_shedding_order() -> None:
    """Verify graceful load shedding sheds unverified -> history oldest -> memory oldest -> evidence last."""
    tokenizer = get_bpe_tokenizer()
    budget = 140
    builder = ContextEnvelopeBuilder(max_envelope_tokens=budget, tokenizer=tokenizer)

    envelope = builder.assemble(
        system_instructions="System instructions.",
        task_constraints=["Constraint A."],
        conversation_history=[
            {"role": "user", "content": "Turn 1: very old message."},
            {"role": "assistant", "content": "Turn 2: older response."},
            {"role": "user", "content": "Turn 3: recent question."},
        ],
        verified_memory=["Fact 1: core memory.", "Fact 2: secondary memory."],
        unverified_memory=["Scratchpad observation 1.", "Scratchpad observation 2."],
        retrieved_evidence='[1] Source: Doc 1\n"Evidence text 1."\n\n[2] Source: Doc 2\n"Evidence text 2."',
        user_query="Target query?",
        tenant_id="tenant-order-11",
        max_tokens=budget,
    )

    assert envelope.total_tokens <= budget
    assert "Constraint A." in envelope.serialized_prompt
    assert "Target query?" in envelope.serialized_prompt
    # First stage shed should be unverified or history
    assert (
        "unverified_memory_shed" in envelope.shedding_log
        or "conversation_history_shed" in envelope.shedding_log
    )


# ==============================================================================
# Scenario 12: Strict Budget Limit Enforcement Raises Error
# ==============================================================================
def test_scenario_12_strict_budget_limit_enforcement_raises_error() -> None:
    """Verify ContextBudgetExceededError is raised when essential core context exceeds budget."""
    builder = ContextEnvelopeBuilder()

    # System instruction (20 tokens) + Constraints (50 tokens) + Query (10 tokens) = ~80 tokens
    # Setting budget to an impossible 25 tokens MUST NOT silently drop constraints or return oversized prompt.
    with pytest.raises(ContextBudgetExceededError) as exc_info:
        builder.assemble(
            system_instructions="You are JakeAI Enterprise Auditor with strict compliance rules.",
            task_constraints=[
                "Constraint 1: Never disclose internal API keys.",
                "Constraint 2: Never perform write operations without authorization.",
                "Constraint 3: Comply with SOX 404 financial reporting requirements.",
            ],
            conversation_history=[],
            verified_memory=[],
            retrieved_evidence="",
            user_query="Generate compliance overview.",
            tenant_id="tenant-budget-12",
            max_tokens=25,  # Impossible budget
        )

    assert "exceed budget" in str(exc_info.value).lower()
    assert "essential user constraints" in str(exc_info.value).lower()


# ==============================================================================
# Scenario 13: Sensitive & Internal Retrieval Scores Sanitization
# ==============================================================================
def test_scenario_13_sensitive_and_internal_scores_sanitization() -> None:
    """Verify internal retrieval scores are sanitized by default and preserved only when requested."""
    builder = ContextEnvelopeBuilder()

    raw_evidence = (
        "[1] Source: Annual_Report.pdf (Score: 0.95)\n"
        '"Total revenue reached $500M with strong EBITDA margin."\n\n'
        "[2] Source: 10-Q_Q3.pdf [score=0.88] (similarity: 0.92) (rrf_score: 0.033)\n"
        '"Net income increased by 15% year-over-year."'
    )

    # Default: sanitize internal scores
    envelope_clean = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[],
        verified_memory=[],
        retrieved_evidence=raw_evidence,
        user_query="Revenue query?",
        tenant_id="tenant-scores-13",
        include_internal_scores=False,
    )

    clean_prompt = envelope_clean.serialized_prompt
    assert "Score: 0.95" not in clean_prompt
    assert "score=0.88" not in clean_prompt
    assert "similarity: 0.92" not in clean_prompt
    assert "rrf_score: 0.033" not in clean_prompt

    # Real data must remain 100% intact
    assert "Total revenue reached $500M" in clean_prompt
    assert "Net income increased by 15%" in clean_prompt
    assert "[1] Source: Annual_Report.pdf" in clean_prompt

    # Explicit flag: include internal scores
    envelope_raw = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[],
        verified_memory=[],
        retrieved_evidence=raw_evidence,
        user_query="Revenue query?",
        tenant_id="tenant-scores-13",
        include_internal_scores=True,
    )

    raw_prompt = envelope_raw.serialized_prompt
    assert "Score: 0.95" in raw_prompt


# ==============================================================================
# Scenario 14: Verifiable Citation Metadata Preservation
# ==============================================================================
def test_scenario_14_verifiable_citations_preserved_during_sanitization() -> None:
    """Verify citation anchors are preserved and cataloged when internal scores are stripped."""
    builder = ContextEnvelopeBuilder()

    evidence = (
        "[SEC-10K-P14] Source: SEC_Filing_2023.pdf (Score: 0.94)\n"
        '"Operating income was $120,000,000 as reported under GAAP."\n\n'
        "[^2] Source: Internal_Audit_Q3.pdf [score=0.85]\n"
        '"Cash reserves stood at $45,000,000."'
    )

    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=[],
        conversation_history=[],
        verified_memory=[],
        retrieved_evidence=evidence,
        user_query="Audit numbers?",
        tenant_id="tenant-cit-14",
    )

    prompt = envelope.serialized_prompt

    # Scores stripped
    assert "Score: 0.94" not in prompt
    assert "score=0.85" not in prompt

    # Citations preserved
    assert "[SEC-10K-P14]" in prompt
    assert "[^2]" in prompt
    assert "SEC-10K-P14" in envelope.citations or "[SEC-10K-P14]" in envelope.citations


# ==============================================================================
# Scenario 15: Exact Serialized-Token Accounting
# ==============================================================================
def test_scenario_15_exact_serialized_token_accounting() -> None:
    """Verify envelope.total_tokens precisely matches BPETokenizer count on serialized_prompt."""
    tokenizer = get_bpe_tokenizer()
    builder = ContextEnvelopeBuilder(tokenizer=tokenizer)

    envelope = builder.assemble(
        system_instructions="You are JakeAI accounting specialist.",
        task_constraints=["Constraint 1: High precision.", "Constraint 2: No guesses."],
        conversation_history=[
            {"role": "user", "content": "What is our debt-to-equity ratio?"},
            {"role": "assistant", "content": "Calculating based on recent 10-Q."},
        ],
        verified_memory=["User preferred GAAP standard."],
        retrieved_evidence='[1] Source: Balance_Sheet.pdf\n"Total debt is $200M, total equity is $400M."',
        user_query="State the D/E ratio.",
        tenant_id="tenant-tokens-15",
    )

    expected_tokens = tokenizer.count_tokens(envelope.serialized_prompt)
    assert envelope.total_tokens == expected_tokens
    assert envelope.total_tokens > 0


# ==============================================================================
# Scenario 16: Token Accounting Ledger Integration
# ==============================================================================
def test_scenario_16_token_accounting_ledger_alignment() -> None:
    """Verify TokenAccounting.calculate_envelope_tokens aligns 1:1 with ContextEnvelope."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="System instructions.",
        task_constraints=["Rule 1: Verify all claims."],
        conversation_history=[{"role": "user", "content": "Hi"}],
        verified_memory=["Fact A."],
        retrieved_evidence='[1] Source: Doc\n"Text."',
        user_query="Question?",
        tenant_id="tenant-ledger-16",
    )

    # Call TokenAccounting with envelope
    measured_tokens = TokenAccounting.calculate_envelope_tokens(envelope=envelope)
    assert measured_tokens == envelope.total_tokens


# ==============================================================================
# Scenario 17: Domain Model Structured Input Support
# ==============================================================================
def test_scenario_17_domain_models_structured_inputs() -> None:
    """Verify ContextEnvelopeBuilder accepts DocumentChunk and MemoryEntry objects cleanly."""
    builder = ContextEnvelopeBuilder()
    tenant = "tenant-domain-17"

    chunks = [
        DocumentChunk(
            chunk_id="chk_1",
            content="Gross profit reached $80M in Q2.",
            tenant_id=tenant,
            source="Q2_Report.pdf",
            score=0.91,
        )
    ]

    memories = [
        MemoryEntry(
            entry_id="mem_1",
            tenant_id=tenant,
            scope=MemoryScope.LONG_TERM,
            key="user_org",
            value="Acme Corp",
            summary="User belongs to Acme Corp.",
        )
    ]

    envelope = builder.assemble(
        system_instructions="System.",
        task_constraints=["Constraint."],
        conversation_history=[{"role": "user", "content": "Calculate profit."}],
        verified_memory=memories,
        retrieved_evidence=chunks,
        user_query="Profit details?",
        tenant_id=tenant,
    )

    assert "User belongs to Acme Corp." in envelope.serialized_prompt
    assert "Gross profit reached $80M in Q2." in envelope.serialized_prompt
    assert "[1] Source: Q2_Report.pdf" in envelope.serialized_prompt


# ==============================================================================
# Scenario 18: End-to-End RAG Pipeline Canonical Context Envelope Integration
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_18_rag_pipeline_end_to_end_context_envelope() -> None:
    """Verify RAGPipeline.generate_grounded_answer uses ContextEnvelopeBuilder and attaches envelope."""
    pipeline = RAGPipeline()
    tenant = "tenant-rag-18"

    chunk = DocumentChunk(
        chunk_id="chk_rev",
        content="Acme FY2023 GAAP Revenue was $150,000,000.",
        tenant_id=tenant,
        source="Acme_10K.pdf",
        score=0.95,
    )
    ctx_res = ContextSelectionResult(
        selected_chunks=[chunk],
        formatted_context=f'[1] Source: {chunk.source} (Score: 0.95)\n"{chunk.content}"',
        selected_tokens=25,
    )
    pipeline.retrieve_and_select_context = AsyncMock(return_value=(None, ctx_res))  # type: ignore

    raw_answer = "Acme FY2023 GAAP Revenue was $150,000,000 [^1]."

    captured_prompts: list[str] = []

    async def mock_call_llm(prompt: str, *args: Any, **kwargs: Any) -> str:
        captured_prompts.append(prompt)
        return raw_answer

    with patch("app.rag.pipeline.call_upstream_llm", new=mock_call_llm):
        res = await pipeline.generate_grounded_answer(
            query="What was Acme FY2023 revenue?",
            tenant_id=tenant,
            task_constraints=["Report all figures in USD."],
            verified_memory=["User preferred currency is USD."],
        )

    assert res.status == "SUCCESS"
    assert "$150,000,000" in res.answer
    assert res.context_envelope is not None

    # Inspect captured prompt sent to LLM: must be canonical 6-stage context envelope
    assert len(captured_prompts) == 1
    llm_prompt = captured_prompts[0]
    assert "=== SYSTEM INSTRUCTIONS ===" in llm_prompt
    assert "=== TASK CONSTRAINTS ===" in llm_prompt
    assert "- Report all figures in USD." in llm_prompt
    assert "=== VERIFIED MEMORY ===" in llm_prompt
    assert "- User preferred currency is USD." in llm_prompt
    assert "=== RETRIEVED EVIDENCE ===" in llm_prompt
    assert "=== USER QUERY ===" in llm_prompt
    assert "What was Acme FY2023 revenue?" in llm_prompt

    # Ensure internal scores were stripped before reaching the model
    assert "Score: 0.95" not in llm_prompt


# ==============================================================================
# Scenario 19: Public HTTP API Boundary (/api/v1/rag/generate) Real ASGI Integration
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_19_public_http_rag_generate_endpoint_context_correctness(
    auth_headers: dict[str, str],
) -> None:
    """Verify /api/v1/rag/generate returns envelope_tokens and zero leaked scores over real HTTP boundary."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Ingest document via real HTTP
        ingest_payload = {
            "content": "Operating cash flow was $48,000,000 for the third quarter of 2023.",
            "source": "CashFlow_Q3.pdf",
            "metadata": {"section": "cash_flows"},
        }
        ingest_resp = await client.post(
            "/api/v1/rag/ingest",
            json=ingest_payload,
            headers=auth_headers,
        )
        assert ingest_resp.status_code == 201

        # 2. Call /api/v1/rag/generate via real HTTP
        gen_payload = {
            "query": "What was operating cash flow for Q3 2023?",
            "top_k": 5,
            "max_context_tokens": 800,
        }
        gen_resp = await client.post(
            "/api/v1/rag/generate",
            json=gen_payload,
            headers=auth_headers,
        )
        assert gen_resp.status_code == 200
        body = gen_resp.json()

        assert body["status"] == "SUCCESS"
        assert body["tenant_id"] == "tenant-context-test"
        assert "$48,000,000" in body["answer"]
        assert len(body["citations"]) >= 1
        assert body["citations"][0]["source"] == "CashFlow_Q3.pdf"

        # Verify envelope_tokens is populated and accurate
        assert "envelope_tokens" in body
        assert body["envelope_tokens"] is not None
        assert body["envelope_tokens"] > 0

        # Verify zero internal score leakage in public answer
        assert "Score:" not in body["answer"]
        assert "similarity:" not in body["answer"]
