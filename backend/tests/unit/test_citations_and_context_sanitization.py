"""Unit tests for citation generation, context envelope formatting, and score sanitization.

Test Suite: UNIT-060
Target Areas:
- CitationGenerator (app/rag/citations.py)
  - Hallucinated footnote stripping when passages empty or text empty
  - Multi-tenant boundary guardrail (foreign tenant rejection)
  - Metric matching vs spurious metric collision (word overlap < 0.15)
  - Metric mismatch / conflicting numbers (never cited)
  - Antonym contradiction rejection
  - Qualitative matching with and without entities
  - Snippet truncation at 130 chars with ellipsis
  - Footnote deduplication across multiple sentences
  - Unverified sentence confidence and annotation
  - Verifiable citation card formatting and idempotency
- Context Envelope & Sanitization (app/rag/context_envelope.py)
  - sanitize_internal_scores (scrubbing score patterns, preserving citation tags)
  - format_task_constraints (deduplication, bullet normalization, tenant filtering)
  - format_conversation_history (tenant isolation, consecutive deduplication, role capitalization)
  - format_memory_entries (expiry pruning, irrelevant filtering, key deduplication by timestamp, trust channels)
  - format_retrieved_evidence (tenant isolation, score scrubbing, citation extraction)
  - ContextEnvelopeBuilder (canonical 6-stage assembly, budget shedding order, fail-closed ContextBudgetExceededError)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.optimizer.bpe_tokenizer import ContextBudgetExceededError
from app.rag.citations import CitationGenerator
from app.rag.context_envelope import (
    ContextEnvelopeBuilder,
    format_conversation_history,
    format_memory_entries,
    format_retrieved_evidence,
    format_task_constraints,
    sanitize_internal_scores,
)
from app.rag.models import DocumentChunk

# ============================================================================
# 1. CitationGenerator Unit Tests
# ============================================================================


class TestCitationGenerator:
    """Deterministic unit tests for CitationGenerator logic."""

    @pytest.fixture
    def generator(self) -> CitationGenerator:
        return CitationGenerator()

    def test_strip_hallucinated_footnotes_empty_passages(
        self, generator: CitationGenerator
    ) -> None:
        """Strip model-generated footnote markers when no passages exist."""
        text = "This is a statement[^1] claiming high growth[^99]."
        clean_text, citations = generator.generate_citations(text, passages=[])
        assert clean_text == "This is a statement claiming high growth."
        assert citations == []

    def test_strip_hallucinated_footnotes_empty_text(
        self, generator: CitationGenerator
    ) -> None:
        """Empty or whitespace text returns empty string and empty citations."""
        clean_text, citations = generator.generate_citations("   ", passages=[])
        assert clean_text == ""
        assert citations == []

    def test_tenant_filtering_guardrail_drops_foreign_chunks(
        self, generator: CitationGenerator
    ) -> None:
        """Chunks belonging to foreign tenants are stripped prior to citation matching."""
        foreign_chunk = DocumentChunk(
            chunk_id="chunk-foreign",
            content="Q3 revenue grew by 25% year over year.",
            tenant_id="tenant-foreign",
            source="foreign_report.pdf",
        )
        text = "Q3 revenue grew by 25% year over year."
        clean_text, citations = generator.generate_citations(
            text, passages=[foreign_chunk], tenant_id="tenant-local"
        )
        # All passages dropped due to tenant mismatch -> 0 citations
        assert citations == []
        assert clean_text == "Q3 revenue grew by 25% year over year."

    def test_metric_exact_match_success(self, generator: CitationGenerator) -> None:
        """Sentence with matching metric and high word overlap receives a valid citation."""
        chunk = DocumentChunk(
            chunk_id="chunk-revenue",
            content="According to the annual filing, total revenue reached $500 million in fiscal year 2024.",
            tenant_id="tenant-alpha",
            source="annual_report_2024.pdf",
        )
        text = "Total revenue reached $500 million in fiscal year 2024."
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert len(citations) == 1
        assert citations[0].chunk_id == "chunk-revenue"
        assert citations[0].index == 1
        assert citations[0].tenant_id == "tenant-alpha"
        assert citations[0].confidence >= 0.80
        assert "[^1]" in annotated_text
        assert "#### 📚 Verifiable Citations & Sources" in annotated_text

    def test_spurious_metric_collision_rejected(
        self, generator: CitationGenerator
    ) -> None:
        """Sentence shares a numeric metric with a chunk but has low word overlap (< 0.15)."""
        chunk = DocumentChunk(
            chunk_id="chunk-maint",
            content="Routine cloud infrastructure server maintenance costs were approximately $500 million across European datacenters.",
            tenant_id="tenant-alpha",
            source="infra_costs.pdf",
        )
        # Completely different topic, only metric $500M matches
        text = "The aerospace acquisition program required $500 million in sovereign debt financing."
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert citations == []
        assert "[^1]" not in annotated_text

    def test_metric_mismatch_conflicting_numbers_never_cited(
        self, generator: CitationGenerator
    ) -> None:
        """Conflicting numbers in sentence and chunk result in zero score and no citation."""
        chunk = DocumentChunk(
            chunk_id="chunk-rev-actual",
            content="Total revenue reached $500 million in fiscal year 2024.",
            tenant_id="tenant-alpha",
            source="annual_report.pdf",
        )
        # Sentence claims $750 million instead of $500 million
        text = "Total revenue reached $750 million in fiscal year 2024."
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert citations == []
        assert "[^1]" not in annotated_text

    def test_antonym_contradiction_rejected(self, generator: CitationGenerator) -> None:
        """Antonym pairs between claim and evidence block match (e.g. launched vs cancelled)."""
        chunk = DocumentChunk(
            chunk_id="chunk-project",
            content="The autonomous delivery drone project was cancelled and terminated due to safety issues.",
            tenant_id="tenant-alpha",
            source="project_status.pdf",
        )
        # Sentence asserts launched (antonym of cancelled)
        text = "The autonomous delivery drone project was launched successfully."
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert citations == []
        assert "[^1]" not in annotated_text

    def test_qualitative_match_with_entities(
        self, generator: CitationGenerator
    ) -> None:
        """Qualitative claim with entity overlap and adequate word ratio matches."""
        chunk = DocumentChunk(
            chunk_id="chunk-flutter",
            content="Google announced that Flutter framework supports advanced multi-platform desktop rendering pipelines.",
            tenant_id="tenant-alpha",
            source="tech_news.pdf",
        )
        text = "Google announced that Flutter framework supports multi-platform desktop pipelines."
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert len(citations) == 1
        assert citations[0].chunk_id == "chunk-flutter"
        assert "[^1]" in annotated_text

    def test_qualitative_match_entity_mismatch_rejected(
        self, generator: CitationGenerator
    ) -> None:
        """Sentence with foreign entity not present in chunk is rejected."""
        chunk = DocumentChunk(
            chunk_id="chunk-apple",
            content="Today Apple engineers published new multi-platform desktop rendering pipelines.",
            tenant_id="tenant-alpha",
            source="apple_news.pdf",
        )
        # Sentence mentions Google instead of Apple at non-zero index
        text = "Today Google engineers published new multi-platform desktop rendering pipelines."
        _annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert citations == []

    def test_qualitative_match_without_entities_threshold(
        self, generator: CitationGenerator
    ) -> None:
        """Qualitative sentence without entities requires word_ratio >= 0.60."""
        chunk = DocumentChunk(
            chunk_id="chunk-general",
            content="the system operates through automated continuous feedback loops across distributed clusters",
            tenant_id="tenant-alpha",
            source="architecture.md",
        )
        # Substantial overlap (>= 0.60)
        high_overlap = "the system operates through automated continuous feedback loops across clusters"
        _, high_cites = generator.generate_citations(
            high_overlap, passages=[chunk], tenant_id="tenant-alpha"
        )
        assert len(high_cites) == 1

        # Insufficient overlap (< 0.60)
        low_overlap = (
            "the system operates with completely different mechanisms elsewhere"
        )
        _, low_cites = generator.generate_citations(
            low_overlap, passages=[chunk], tenant_id="tenant-alpha"
        )
        assert len(low_cites) == 0

    def test_snippet_truncation_long_vs_short(
        self, generator: CitationGenerator
    ) -> None:
        """Chunks over 130 characters are truncated with ellipsis; shorter ones are preserved."""
        long_content = (
            "This comprehensive architecture document provides an exhaustive and "
            "detailed description of the distributed microservices subsystems and "
            "cryptographic storage layers deployed throughout the cloud cluster."
        )
        short_content = "Short content passage."

        chunk_long = DocumentChunk(
            chunk_id="chunk-long",
            content=long_content,
            tenant_id="tenant-alpha",
            source="specs.pdf",
        )
        chunk_short = DocumentChunk(
            chunk_id="chunk-short",
            content=short_content,
            tenant_id="tenant-alpha",
            source="brief.pdf",
        )

        _, cites_long = generator.generate_citations(
            "This comprehensive architecture document provides an exhaustive and detailed description.",
            passages=[chunk_long],
            tenant_id="tenant-alpha",
        )
        assert len(cites_long) == 1
        assert cites_long[0].snippet.endswith("...")
        assert len(cites_long[0].snippet) == 133  # 130 chars + "..."

        _, cites_short = generator.generate_citations(
            "Short content passage.",
            passages=[chunk_short],
            tenant_id="tenant-alpha",
        )
        assert len(cites_short) == 1
        assert not cites_short[0].snippet.endswith("...")
        assert cites_short[0].snippet == short_content

    def test_footnote_deduplication_multiple_sentences(
        self, generator: CitationGenerator
    ) -> None:
        """Multiple sentences matching the same chunk reuse the same citation index."""
        chunk = DocumentChunk(
            chunk_id="chunk-shared",
            content="The platform provides end-to-end encryption with zero-knowledge keys across all databases.",
            tenant_id="tenant-alpha",
            source="security_whitepaper.pdf",
        )
        text = (
            "The platform provides end-to-end encryption with zero-knowledge keys. "
            "All databases are protected across the entire platform."
        )
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        # Only one citation record created
        assert len(citations) == 1
        assert citations[0].index == 1
        # Both sentences annotated with [^1]
        assert annotated_text.count("[^1]") >= 2

    def test_unverified_sentence_confidence_and_tagging(
        self, generator: CitationGenerator
    ) -> None:
        """Sentences flagged with [unverified] have confidence clamped to 0.50 and retain tag."""
        chunk = DocumentChunk(
            chunk_id="chunk-speculative",
            content="The company plans to expand operations into three new regions next quarter.",
            tenant_id="tenant-alpha",
            source="expansion_draft.pdf",
        )
        text = "The company plans to expand operations into three new regions [unverified]."
        annotated_text, citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-alpha"
        )

        assert len(citations) == 1
        assert citations[0].confidence == 0.50
        assert "[^1] [unverified]" in annotated_text

    def test_citation_cards_section_formatting_and_idempotency(
        self, generator: CitationGenerator
    ) -> None:
        """Cards section is generated with markdown formatting and not duplicated if already present."""
        chunk = DocumentChunk(
            chunk_id="chunk-1",
            content="Revenue reached $100 million in Q1.",
            tenant_id="tenant-1",
            source="report.pdf",
        )
        text = "Revenue reached $100 million in Q1."
        annotated_text, _citations = generator.generate_citations(
            text, passages=[chunk], tenant_id="tenant-1"
        )

        assert "#### 📚 Verifiable Citations & Sources" in annotated_text
        assert "[^1]: **report.pdf** (Tenant: `tenant-1`, Confidence:" in annotated_text

        # Second call with text that already contains the section header does not duplicate it
        second_annotated, _ = generator.generate_citations(
            annotated_text, passages=[chunk], tenant_id="tenant-1"
        )
        assert second_annotated.count("#### 📚 Verifiable Citations & Sources") == 1


# ============================================================================
# 2. Context Envelope Sanitization Unit Tests
# ============================================================================


class TestSanitizeInternalScores:
    """Tests for sanitize_internal_scores regex scrubbing."""

    def test_scrubs_internal_parenthesized_scores(self) -> None:
        text = "Document passage text (Score: 0.95) followed by (similarity: 0.88)."
        sanitized = sanitize_internal_scores(text)
        assert "0.95" not in sanitized
        assert "similarity" not in sanitized
        assert sanitized == "Document passage text followed by."

    def test_scrubs_bracketed_scores_and_rrf(self) -> None:
        text = (
            "Result [Score=0.74] and rank artifact [rrf_score: 0.016] preserved info."
        )
        sanitized = sanitize_internal_scores(text)
        assert "0.74" not in sanitized
        assert "rrf_score" not in sanitized
        assert sanitized == "Result and rank artifact preserved info."

    def test_scrubs_bare_scores(self) -> None:
        text = "Item relevance: 0.91 and cross_encoder_score: 4.52 included."
        sanitized = sanitize_internal_scores(text)
        assert "relevance:" not in sanitized
        assert "cross_encoder_score:" not in sanitized
        assert sanitized == "Item and included."

    def test_preserves_citation_tags(self) -> None:
        text = "Security finding [SEC-01] reported in [DOC-4] according to [^1] and [P-12]."
        sanitized = sanitize_internal_scores(text)
        assert "[SEC-01]" in sanitized
        assert "[DOC-4]" in sanitized
        assert "[^1]" in sanitized
        assert "[P-12]" in sanitized

    def test_handles_empty_or_none(self) -> None:
        assert sanitize_internal_scores("") == ""
        assert sanitize_internal_scores("   ") == ""


# ============================================================================
# 3. Format Task Constraints Unit Tests
# ============================================================================


class TestFormatTaskConstraints:
    """Tests for format_task_constraints deduplication, normalization, and tenant scoping."""

    def test_format_task_constraints_from_string(self) -> None:
        constraints = "- Do not use shell commands\n* Always validate input\n- Do not use shell commands"
        result = format_task_constraints(constraints, tenant_id="tenant-1")
        lines = result.split("\n")
        assert len(lines) == 2
        assert "- Do not use shell commands" in lines
        assert "- Always validate input" in lines

    def test_format_task_constraints_tenant_filtering(self) -> None:
        constraints = [
            {"content": "Local rule 1", "tenant_id": "tenant-alpha"},
            {"content": "Foreign rule", "tenant_id": "tenant-beta"},
            {"content": "Local rule 2", "tenant_id": "tenant-alpha"},
        ]
        result = format_task_constraints(constraints, tenant_id="tenant-alpha")
        assert "Local rule 1" in result
        assert "Local rule 2" in result
        assert "Foreign rule" not in result

    def test_format_task_constraints_deduplication_preserves_order(self) -> None:
        constraints = ["Rule A", "Rule B", "Rule A", "Rule C"]
        result = format_task_constraints(constraints, tenant_id="tenant-1")
        expected = "- Rule A\n- Rule B\n- Rule C"
        assert result == expected

    def test_format_task_constraints_empty(self) -> None:
        assert format_task_constraints([], tenant_id="tenant-1") == ""
        assert format_task_constraints("", tenant_id="tenant-1") == ""


# ============================================================================
# 4. Format Conversation History Unit Tests
# ============================================================================


class TestFormatConversationHistory:
    """Tests for format_conversation_history tenant isolation and deduplication."""

    def test_drops_foreign_tenant_turns(self) -> None:
        history = [
            {"role": "user", "content": "Hello alpha", "tenant_id": "tenant-alpha"},
            {"role": "user", "content": "Hello beta", "tenant_id": "tenant-beta"},
            {
                "role": "assistant",
                "content": "Welcome alpha",
                "tenant_id": "tenant-alpha",
            },
        ]
        result = format_conversation_history(history, tenant_id="tenant-alpha")
        assert "Hello alpha" in result
        assert "Welcome alpha" in result
        assert "Hello beta" not in result

    def test_consecutive_identical_turns_deduplicated(self) -> None:
        history = [
            {"role": "user", "content": "Retry operation"},
            {"role": "user", "content": "Retry operation"},
            {"role": "assistant", "content": "Executing"},
        ]
        result = format_conversation_history(history, tenant_id="tenant-alpha")
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "User: Retry operation"
        assert lines[1] == "Assistant: Executing"

    def test_string_history_passthrough(self) -> None:
        raw_text = "User: Initial prompt\nAssistant: Response"
        result = format_conversation_history(raw_text, tenant_id="tenant-1")
        assert result == raw_text

    def test_empty_history(self) -> None:
        assert format_conversation_history([], tenant_id="tenant-1") == ""
        assert format_conversation_history("", tenant_id="tenant-1") == ""


# ============================================================================
# 5. Format Memory Entries Unit Tests
# ============================================================================


class TestFormatMemoryEntries:
    """Tests for format_memory_entries trust verification, expiry, and deduplication."""

    def test_tenant_boundary_enforcement(self) -> None:
        memories = [
            {"key": "pref", "value": "Dark theme", "tenant_id": "tenant-a"},
            {"key": "secret", "value": "Foreign data", "tenant_id": "tenant-b"},
        ]
        formatted, facts = format_memory_entries(memories, tenant_id="tenant-a")
        assert "Dark theme" in formatted
        assert "Foreign data" not in formatted
        assert facts == ["Dark theme"]

    def test_expired_and_irrelevant_memories_dropped(self) -> None:
        now = time.time()
        memories = [
            {"value": "Active fact", "expires_at": now + 3600},
            {"value": "Expired fact", "expires_at": now - 60},
            {"value": "Irrelevant fact", "irrelevant": True},
        ]
        formatted, facts = format_memory_entries(memories, tenant_id="tenant-a")
        assert facts == ["Active fact"]
        assert "Expired fact" not in formatted
        assert "Irrelevant fact" not in formatted

    def test_key_deduplication_prefers_latest_timestamp(self) -> None:
        memories = [
            {"key": "cluster_ip", "value": "10.0.0.1", "created_at": 100.0},
            {"key": "cluster_ip", "value": "10.0.0.2", "created_at": 200.0},
            {"key": "cluster_ip", "value": "10.0.0.0", "created_at": 50.0},
        ]
        formatted, facts = format_memory_entries(memories, tenant_id="tenant-a")
        assert facts == ["10.0.0.2"]
        assert "10.0.0.1" not in formatted
        assert "10.0.0.0" not in formatted

    def test_verified_channel_excludes_unverified_and_rejected(self) -> None:
        memories = [
            {"value": "Confirmed fact", "verified": True},
            {"value": "Unconfirmed speculation", "verified": False},
            {"value": "Rejected item", "metadata": {"verification_status": "rejected"}},
        ]
        # In verified channel, unverified and rejected are excluded
        formatted_v, facts_v = format_memory_entries(
            memories, tenant_id="tenant-a", is_verified_channel=True
        )
        assert facts_v == ["Confirmed fact"]
        assert "- Confirmed fact" in formatted_v

        # In unverified channel, unverified is retained with prefix
        formatted_u, _facts_u = format_memory_entries(
            memories, tenant_id="tenant-a", is_verified_channel=False
        )
        assert "- [Unverified] Unconfirmed speculation" in formatted_u

    def test_string_memory_classification(self) -> None:
        formatted, facts = format_memory_entries(
            "unverified observation: server load is high",
            tenant_id="tenant-a",
            is_verified_channel=True,
        )
        # String containing 'unverified' is treated as unverified, so omitted from verified channel
        assert formatted == ""
        assert facts == []


# ============================================================================
# 6. Format Retrieved Evidence Unit Tests
# ============================================================================


class TestFormatRetrievedEvidence:
    """Tests for format_retrieved_evidence chunk processing and score scrubbing."""

    def test_drops_foreign_tenant_chunks(self) -> None:
        chunks = [
            DocumentChunk(
                chunk_id="c1",
                content="Local chunk data",
                tenant_id="tenant-local",
                source="local.txt",
            ),
            DocumentChunk(
                chunk_id="c2",
                content="Foreign chunk data",
                tenant_id="tenant-remote",
                source="foreign.txt",
            ),
        ]
        formatted, _ = format_retrieved_evidence(chunks, tenant_id="tenant-local")
        assert "Local chunk data" in formatted
        assert "Foreign chunk data" not in formatted

    def test_scrubs_scores_unless_explicitly_included(self) -> None:
        chunks = [
            DocumentChunk(
                chunk_id="c1",
                content="Architecture details (Score: 0.98) [similarity: 0.95]",
                tenant_id="tenant-local",
                source="doc.pdf",
            )
        ]
        # Default: scrubs scores
        formatted_scrubbed, _ = format_retrieved_evidence(
            chunks, tenant_id="tenant-local", include_internal_scores=False
        )
        assert "Score: 0.98" not in formatted_scrubbed
        assert "similarity: 0.95" not in formatted_scrubbed

        # Explicit: includes scores
        formatted_raw, _ = format_retrieved_evidence(
            chunks, tenant_id="tenant-local", include_internal_scores=True
        )
        assert "Score: 0.98" in formatted_raw

    def test_string_evidence_foreign_tenant_tag_dropped(self) -> None:
        text = "__tenant:tenant-foreign__ Data from foreign system"
        formatted, _ = format_retrieved_evidence(text, tenant_id="tenant-local")
        assert formatted == ""

    def test_citation_tag_extraction(self) -> None:
        chunks = [
            DocumentChunk(
                chunk_id="c1",
                content="Information cited from [SEC-01] and [DOC-42] and [^1].",
                tenant_id="tenant-local",
                source="audit.pdf",
            )
        ]
        _, citations = format_retrieved_evidence(chunks, tenant_id="tenant-local")
        assert "[SEC-01]" in citations
        assert "[DOC-42]" in citations
        assert "[^1]" in citations


# ============================================================================
# 7. ContextEnvelopeBuilder Unit Tests
# ============================================================================


class TestContextEnvelopeBuilder:
    """Tests for ContextEnvelopeBuilder assembly, budgeting, and shedding logic."""

    @pytest.fixture
    def mock_tokenizer(self) -> MagicMock:
        tokenizer = MagicMock()
        # 1 token per word approximation for deterministic testing
        tokenizer.count_tokens.side_effect = lambda s: len(s.split())
        return tokenizer

    def test_canonical_stage_assembly_order(self) -> None:
        """Assembles prompt in canonical order."""
        builder = ContextEnvelopeBuilder()
        envelope = builder.assemble(
            system_instructions="SYSTEM_INSTRUCTION",
            task_constraints=["CONSTRAINT_1"],
            conversation_history=[{"role": "user", "content": "HISTORY_1"}],
            verified_memory=["MEMORY_1"],
            retrieved_evidence=[
                DocumentChunk(
                    chunk_id="c1",
                    content="EVIDENCE_1",
                    tenant_id="tenant-1",
                    source="src1",
                )
            ],
            user_query="USER_QUERY",
            tenant_id="tenant-1",
        )

        p = envelope.serialized_prompt
        pos_sys = p.index("=== SYSTEM INSTRUCTIONS ===")
        pos_const = p.index("=== TASK CONSTRAINTS ===")
        pos_hist = p.index("=== CONVERSATION HISTORY ===")
        pos_mem = p.index("=== VERIFIED MEMORY ===")
        pos_evid = p.index("=== RETRIEVED EVIDENCE ===")
        pos_query = p.index("=== USER QUERY ===")

        assert pos_sys < pos_const < pos_hist < pos_mem < pos_evid < pos_query

    def test_budget_shedding_order(self, mock_tokenizer: MagicMock) -> None:
        """Shedding order: unverified memory -> conversation history -> verified memory -> retrieved evidence."""
        # Setup builder with low budget to trigger shedding
        builder = ContextEnvelopeBuilder(
            max_envelope_tokens=40, tokenizer=mock_tokenizer
        )

        envelope = builder.assemble(
            system_instructions="Sys",
            task_constraints=["Constraint A"],
            conversation_history=[{"role": "user", "content": "Word " * 15}],
            verified_memory=["Memory fact " * 5],
            retrieved_evidence=[
                DocumentChunk(
                    chunk_id="c1",
                    content="Evidence passage " * 10,
                    tenant_id="tenant-1",
                )
            ],
            user_query="Query",
            unverified_memory=["Unverified observation " * 10],
            tenant_id="tenant-1",
            max_tokens=30,
        )

        # Shedding log should reflect stages dropped to meet budget
        assert len(envelope.shedding_log) > 0
        assert "unverified_memory_shed" in envelope.shedding_log

    def test_core_budget_exceeded_error_fail_closed(
        self, mock_tokenizer: MagicMock
    ) -> None:
        """Raises ContextBudgetExceededError if core components alone exceed budget."""
        builder = ContextEnvelopeBuilder(tokenizer=mock_tokenizer)

        # System and constraints alone are 20+ words, budget is 5
        with pytest.raises(ContextBudgetExceededError) as exc_info:
            builder.assemble(
                system_instructions="This is a very long critical system instruction",
                task_constraints=["Essential non negotiable user safety constraint"],
                user_query="Run task",
                max_tokens=5,
            )

        assert "exceed budget" in str(exc_info.value)
