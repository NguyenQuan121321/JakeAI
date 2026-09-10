"""Unit tests for TASK RAG-12: Unified 6-stage Context Envelope and Token Budgeting."""

from app.optimizer.bpe_tokenizer import get_bpe_tokenizer
from app.rag.context_envelope import ContextEnvelopeBuilder


def test_context_envelope_canonical_ordering() -> None:
    """Verify ContextEnvelopeBuilder outputs sections in exact 6-stage canonical order."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="You are JakeAI.",
        task_constraints=[
            "Constraint 1: Financial precision.",
            "Constraint 2: No hallucinations.",
        ],
        conversation_history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
        verified_memory=["User preferred currency is USD."],
        retrieved_evidence='[1] Source: Annual Report\n"Revenue was $50M."',
        user_query="What was revenue?",
        tenant_id="tenant-envelope",
    )

    prompt = envelope.serialized_prompt

    idx_system = prompt.index("=== SYSTEM INSTRUCTIONS ===")
    idx_constraints = prompt.index("=== TASK CONSTRAINTS ===")
    idx_history = prompt.index("=== CONVERSATION HISTORY ===")
    idx_memory = prompt.index("=== VERIFIED MEMORY ===")
    idx_evidence = prompt.index("=== RETRIEVED EVIDENCE ===")
    idx_query = prompt.index("=== USER QUERY ===")

    assert (
        idx_system
        < idx_constraints
        < idx_history
        < idx_memory
        < idx_evidence
        < idx_query
    )
    assert envelope.tenant_id == "tenant-envelope"
    assert envelope.total_tokens > 0


def test_context_envelope_budget_shedding() -> None:
    """Verify ContextEnvelopeBuilder sheds oldest conversation history and memory when exceeding budget."""
    tokenizer = get_bpe_tokenizer()
    # Tight budget
    budget = 120
    builder = ContextEnvelopeBuilder(max_envelope_tokens=budget, tokenizer=tokenizer)

    long_history = [
        {
            "role": "user",
            "content": f"Message number {i} with lots of redundant words to increase tokens. "
            * 3,
        }
        for i in range(10)
    ]

    envelope = builder.assemble(
        system_instructions="System prompt.",
        task_constraints=["Strict rule."],
        conversation_history=long_history,
        verified_memory=["Memory fact 1.", "Memory fact 2."],
        retrieved_evidence='[1] Source: Doc\n"Content."',
        user_query="My question.",
        tenant_id="tenant-budget-shed",
        max_tokens=budget,
    )

    # Serialized prompt must fit within budget
    measured_tokens = tokenizer.count_tokens(envelope.serialized_prompt)
    assert envelope.total_tokens == measured_tokens
    assert measured_tokens <= budget
    # Invariant: System instructions and user query are preserved
    assert "System prompt." in envelope.serialized_prompt
    assert "My question." in envelope.serialized_prompt


def test_context_envelope_string_inputs_and_evidence_shedding() -> None:
    """Verify ContextEnvelopeBuilder accepts plain strings and sheds evidence when necessary."""
    from app.rag.context_envelope import get_context_envelope_builder

    builder = get_context_envelope_builder()
    # Tight budget
    budget = 90
    long_evidence = (
        '[1] Source: Doc 1\n"'
        + ("Fact statement paragraph. " * 15)
        + '"\n\n[2] Source: Doc 2\n"'
        + ("Second fact paragraph. " * 15)
        + '"'
    )

    envelope = builder.assemble(
        system_instructions="System instructions.",
        task_constraints="- Constraint A\n- Constraint B",
        conversation_history="User: Hello\nAssistant: Hi",
        verified_memory="- Fact 1\n- Fact 2",
        retrieved_evidence=long_evidence,
        user_query="Summary query?",
        tenant_id="tenant-str-envelope",
        max_tokens=budget,
    )

    assert envelope.tenant_id == "tenant-str-envelope"
    assert envelope.total_tokens <= budget
    assert "=== SYSTEM INSTRUCTIONS ===" in envelope.serialized_prompt
    assert "=== USER QUERY ===" in envelope.serialized_prompt
