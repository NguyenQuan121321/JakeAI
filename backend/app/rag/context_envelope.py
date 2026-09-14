"""Unified 6-Stage Context Envelope Engine for JakeAI Pair Programming and RAG.

Enforces:
1. Canonical 6-stage context ordering:
   System Instructions -> Task Constraints -> Conversation History ->
   Verified Memory -> Retrieved Evidence -> User Query.
2. Strict trust classification:
   Unverified memory is never treated as verified evidence.
3. Multi-tenant isolation boundary:
   Foreign tenant memory, chunks, and history are filtered out.
4. Non-negotiable user constraints:
   Task constraints are never silently removed or truncated during shedding.
5. Exact serialized-token accounting with BPETokenizer.
6. Zero sensitive retrieval score exposure:
   Internal scores and ranking metrics are sanitized from model-visible context.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from app.optimizer.bpe_tokenizer import (
    BPETokenizer,
    ContextBudgetExceededError,
    get_bpe_tokenizer,
)

logger = logging.getLogger(__name__)

# Regular expressions for detecting internal retrieval scores and ranking artifacts
INTERNAL_SCORE_PATTERNS = [
    re.compile(
        r"\s*\(\s*(?:Score|score|similarity|relevance|rrf_score|cross_encoder_score)\s*[:=]\s*\d+(?:\.\d+)?\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s*\[\s*(?:Score|score|similarity|relevance|rrf_score|cross_encoder_score)\s*[:=]\s*\d+(?:\.\d+)?\s*\]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:Score|score|similarity|relevance|rrf_score|cross_encoder_score)\s*[:=]\s*\d+(?:\.\d+)?\b",
        re.IGNORECASE,
    ),
]

# Citation tags that MUST be preserved during sanitization
CITATION_TAG_REGEX = re.compile(
    r"\[(?:SEC|DOC|P|REF|CHUNK|EXCERPT|\d+)[^\]]*\]|\[\^\d+\]|\^\[\d+\]",
    re.IGNORECASE,
)


def sanitize_internal_scores(text: str) -> str:
    """Scrub sensitive internal retrieval and reranking scores from model-visible text."""
    if not text:
        return ""
    sanitized = text
    for pat in INTERNAL_SCORE_PATTERNS:
        sanitized = pat.sub("", sanitized)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
    sanitized = re.sub(r"\(\s*\)", "", sanitized)
    return sanitized.strip()


def format_task_constraints(
    constraints: list[str] | list[dict[str, Any]] | str,
    tenant_id: str,
) -> str:
    """Format and deduplicate task constraints while enforcing tenant boundary."""
    if not constraints:
        return ""
    if isinstance(constraints, str):
        lines = [
            c.strip().lstrip("-* ").strip()
            for c in constraints.split("\n")
            if c.strip()
        ]
    else:
        lines = []
        for item in constraints:
            if isinstance(item, dict):
                item_tenant = item.get("tenant_id")
                if item_tenant and item_tenant != tenant_id:
                    logger.warning(
                        "SECURITY ALERT: Dropping task constraint from foreign tenant '%s' for '%s'",
                        item_tenant,
                        tenant_id,
                    )
                    continue
                c_text = str(
                    item.get("content")
                    or item.get("constraint")
                    or item.get("text")
                    or ""
                )
            else:
                c_text = str(item)
            c_clean = c_text.strip().lstrip("-* ").strip()
            if c_clean:
                lines.append(c_clean)

    # Deduplicate while preserving order
    unique: list[str] = []
    seen = set()
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return "\n".join(f"- {c}" for c in unique)


def format_conversation_history(
    history: list[dict[str, Any]] | list[Any] | str,
    tenant_id: str,
) -> str:
    """Format conversation dialogue turns, enforcing tenant isolation and deduplication."""
    if not history:
        return ""
    if isinstance(history, str):
        return history.strip()

    history_lines: list[str] = []
    seen_turns: list[tuple[str, str]] = []

    for msg in history:
        msg_tenant = getattr(msg, "tenant_id", None) or (
            msg.get("tenant_id") if isinstance(msg, dict) else None
        )
        if msg_tenant and msg_tenant != tenant_id:
            logger.warning(
                "SECURITY ALERT: Dropping conversation turn from foreign tenant '%s' for '%s'",
                msg_tenant,
                tenant_id,
            )
            continue

        role = (
            getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
            or "User"
        )
        content = (
            getattr(msg, "content", None)
            or (msg.get("content") if isinstance(msg, dict) else None)
            or str(msg)
        )
        role_str = str(role).capitalize()
        content_str = str(content).strip()
        if not content_str:
            continue

        turn = (role_str, content_str)
        if seen_turns and seen_turns[-1] == turn:
            continue
        seen_turns.append(turn)
        history_lines.append(f"{role_str}: {content_str}")

    return "\n".join(history_lines)


def format_memory_entries(
    memory: list[Any] | str,
    tenant_id: str,
    is_verified_channel: bool = True,
) -> tuple[str, list[str]]:
    """Format memory facts, enforcing tenant boundary, expiry, trust verification, and deduplication.

    Returns:
        (formatted_text, unique_fact_strings)
    """
    if not memory:
        return "", []

    raw_items: list[Any] = [memory] if isinstance(memory, str) else list(memory)
    valid_facts_by_key: dict[str, tuple[float, str]] = {}
    unkeyed_facts: list[str] = []
    now = time.time()

    for idx, item in enumerate(raw_items):
        m_tenant: str | None = None
        m_key: str | None = None
        m_val: str = ""
        m_verified = True
        m_expired = False
        m_irrelevant = False
        created_at: float = float(idx)

        if hasattr(item, "tenant_id"):
            m_tenant = getattr(item, "tenant_id", None)
            m_key = getattr(item, "key", None)
            summary = getattr(item, "summary", None)
            val = getattr(item, "value", "")
            m_val = str(summary or val)
            meta = getattr(item, "metadata", {}) or {}
            m_verified = meta.get("verified", True)
            if meta.get("verification_status") in ("unverified", "rejected"):
                m_verified = False
            exp = getattr(item, "expires_at", None)
            if exp and now > exp:
                m_expired = True
            if meta.get("irrelevant") is True:
                m_irrelevant = True
            created_at = getattr(item, "created_at", float(idx))
        elif isinstance(item, dict):
            m_tenant = item.get("tenant_id")
            m_key = item.get("key")
            summary = item.get("summary")
            val = item.get("value", item.get("fact", item.get("content", "")))
            m_val = str(summary or val)
            meta = item.get("metadata", {}) or {}
            m_verified = item.get("verified", meta.get("verified", True))
            if item.get("status") == "unverified" or meta.get(
                "verification_status"
            ) in (
                "unverified",
                "rejected",
            ):
                m_verified = False
            exp = item.get("expires_at")
            if exp and now > exp:
                m_expired = True
            if item.get("irrelevant") is True or meta.get("irrelevant") is True:
                m_irrelevant = True
            created_at = float(item.get("created_at", idx))
        else:
            raw_str = str(item).strip().lstrip("-* ").strip()
            m_val = raw_str
            if re.search(
                r"\b(?:unverified|speculative|unconfirmed|status:\s*unverified)\b",
                raw_str,
                re.IGNORECASE,
            ):
                m_verified = False

        if m_tenant and m_tenant != tenant_id:
            logger.warning(
                "SECURITY ALERT: Dropping memory fact belonging to foreign tenant '%s' for request tenant '%s'.",
                m_tenant,
                tenant_id,
            )
            continue

        if m_expired:
            logger.debug("Dropping expired memory fact for key '%s'", m_key)
            continue

        if m_irrelevant:
            logger.debug("Dropping irrelevant memory fact for key '%s'", m_key)
            continue

        if not m_val.strip():
            continue

        if is_verified_channel and not m_verified:
            logger.info(
                "Excluding unverified memory from verified memory stage: '%s'", m_val
            )
            continue

        if m_key:
            if m_key in valid_facts_by_key:
                prev_time, _ = valid_facts_by_key[m_key]
                if created_at >= prev_time:
                    valid_facts_by_key[m_key] = (created_at, m_val.strip())
            else:
                valid_facts_by_key[m_key] = (created_at, m_val.strip())
        else:
            unkeyed_facts.append(m_val.strip())

    all_facts: list[str] = [
        val for _, val in valid_facts_by_key.values()
    ] + unkeyed_facts
    unique_facts: list[str] = []
    seen = set()
    for f in all_facts:
        if f not in seen:
            seen.add(f)
            unique_facts.append(f)

    if not unique_facts:
        return "", []

    prefix = "- " if is_verified_channel else "- [Unverified] "
    formatted = "\n".join(f"{prefix}{f}" for f in unique_facts)
    return formatted, unique_facts


def format_retrieved_evidence(
    evidence: list[Any] | str,
    tenant_id: str,
    include_internal_scores: bool = False,
) -> tuple[str, list[str]]:
    """Format retrieved evidence chunks, enforcing tenant isolation, score sanitization, and citation extraction.

    Returns:
        (formatted_text, extracted_citation_anchors)
    """
    if not evidence:
        return "", []

    extracted_citations: list[str] = []

    if isinstance(evidence, str):
        clean_text = evidence.strip()
        foreign_match = re.search(r"__tenant:([a-zA-Z0-9_\-]+)__", clean_text)
        if foreign_match and foreign_match.group(1) != tenant_id:
            logger.warning(
                "SECURITY ALERT: Dropping evidence string carrying foreign tenant tag '%s' for '%s'",
                foreign_match.group(1),
                tenant_id,
            )
            return "", []
        if not include_internal_scores:
            clean_text = sanitize_internal_scores(clean_text)
        for cit in CITATION_TAG_REGEX.findall(clean_text):
            c_strip = cit.strip()
            if c_strip and c_strip not in extracted_citations:
                extracted_citations.append(c_strip)
        return clean_text, extracted_citations

    formatted_blocks: list[str] = []
    seen_contents: set[str] = set()

    for idx, item in enumerate(evidence, 1):
        item_tenant = getattr(item, "tenant_id", None) or (
            item.get("tenant_id") if isinstance(item, dict) else None
        )
        if item_tenant and item_tenant != tenant_id:
            logger.warning(
                "SECURITY ALERT: Dropping evidence chunk belonging to foreign tenant '%s' for request tenant '%s'.",
                item_tenant,
                tenant_id,
            )
            continue

        source = (
            getattr(item, "source", None)
            or (item.get("source") if isinstance(item, dict) else None)
            or f"Document {idx}"
        )
        content = (
            getattr(item, "content", None)
            or (item.get("content") if isinstance(item, dict) else None)
            or str(item)
        )
        content_clean = str(content).strip()
        if not content_clean:
            continue

        if not include_internal_scores:
            content_clean = sanitize_internal_scores(content_clean)
            source = sanitize_internal_scores(str(source))

        if content_clean in seen_contents:
            continue
        seen_contents.add(content_clean)

        for cit in CITATION_TAG_REGEX.findall(content_clean):
            c_strip = cit.strip()
            if c_strip and c_strip not in extracted_citations:
                extracted_citations.append(c_strip)

        block = f'[{idx}] Source: {source}\n"{content_clean}"'
        formatted_blocks.append(block)

    formatted_text = "\n\n".join(formatted_blocks)
    return formatted_text, extracted_citations


class ContextEnvelope(BaseModel):
    """Canonical 6-stage context envelope bounding all prompt components."""

    system_instructions: str = Field(description="Core system role and operating rules")
    task_constraints: str = Field(
        description="Operational constraints and safety gates"
    )
    conversation_history: str = Field(description="Truncated recent dialogue history")
    verified_memory: str = Field(description="Verified long-term agent memory facts")
    retrieved_evidence: str = Field(description="RAG grounded document passages")
    user_query: str = Field(description="Current incoming user prompt")
    tenant_id: str = Field(description="Scoped tenant boundary")
    unverified_memory: str = Field(
        default="", description="Segregated unverified memory observations if present"
    )
    citations: list[str] = Field(
        default_factory=list,
        description="Preserved citation keys extracted from evidence",
    )
    shedding_log: list[str] = Field(
        default_factory=list,
        description="Record of shedded sections during budget reconciliation",
    )
    total_tokens: int = Field(
        default=0, description="Exact BPE token count of serialized envelope"
    )
    serialized_prompt: str = Field(
        description="Full assembled string for LLM completion"
    )


class ContextEnvelopeBuilder:
    """Assembles, validates, and budgets the 6-stage enterprise context envelope."""

    def __init__(
        self,
        max_envelope_tokens: int = 4000,
        tokenizer: BPETokenizer | None = None,
    ) -> None:
        self.max_envelope_tokens = max_envelope_tokens
        self.tokenizer = tokenizer or get_bpe_tokenizer()

    def assemble(
        self,
        system_instructions: str,
        task_constraints: list[str] | list[dict[str, Any]] | str = "",
        conversation_history: list[dict[str, Any]] | list[Any] | str = "",
        verified_memory: list[Any] | str = "",
        retrieved_evidence: list[Any] | str = "",
        user_query: str = "",
        tenant_id: str = "default",
        unverified_memory: list[Any] | str | None = None,
        max_tokens: int | None = None,
        include_internal_scores: bool = False,
    ) -> ContextEnvelope:
        """Construct the canonical 6-stage context envelope bounded by BPE token budget."""
        budget = max_tokens or self.max_envelope_tokens

        formatted_system = system_instructions.strip()
        formatted_constraints = format_task_constraints(
            task_constraints, tenant_id=tenant_id
        )
        formatted_history = format_conversation_history(
            conversation_history, tenant_id=tenant_id
        )
        formatted_memory, _ = format_memory_entries(
            verified_memory, tenant_id=tenant_id, is_verified_channel=True
        )
        formatted_evidence, extracted_citations = format_retrieved_evidence(
            retrieved_evidence,
            tenant_id=tenant_id,
            include_internal_scores=include_internal_scores,
        )
        formatted_query = user_query.strip()

        formatted_unverified = ""
        if unverified_memory:
            formatted_unverified, _ = format_memory_entries(
                unverified_memory, tenant_id=tenant_id, is_verified_channel=False
            )

        def _serialize(
            sys_txt: str,
            const_txt: str,
            hist_txt: str,
            mem_txt: str,
            evid_txt: str,
            query_txt: str,
            unv_txt: str = "",
        ) -> str:
            sections: list[str] = []
            if sys_txt:
                sections.append(f"=== SYSTEM INSTRUCTIONS ===\n{sys_txt}")
            if const_txt:
                sections.append(f"=== TASK CONSTRAINTS ===\n{const_txt}")
            if hist_txt:
                sections.append(f"=== CONVERSATION HISTORY ===\n{hist_txt}")
            if mem_txt:
                sections.append(f"=== VERIFIED MEMORY ===\n{mem_txt}")
            if unv_txt:
                sections.append(f"=== UNVERIFIED OBSERVATIONS ===\n{unv_txt}")
            if evid_txt:
                sections.append(f"=== RETRIEVED EVIDENCE ===\n{evid_txt}")
            if query_txt:
                sections.append(f"=== USER QUERY ===\n{query_txt}")
            return "\n\n".join(sections)

        serialized = _serialize(
            formatted_system,
            formatted_constraints,
            formatted_history,
            formatted_memory,
            formatted_evidence,
            formatted_query,
            formatted_unverified,
        )
        total_tokens = self.tokenizer.count_tokens(serialized)
        shedding_log: list[str] = []

        # Budget Reconciliation: If overflow, shed load gracefully
        # (unverified -> history -> memory -> evidence)
        if total_tokens > budget:
            logger.info(
                "Envelope tokens (%d) exceed budget (%d). Reconciling stages...",
                total_tokens,
                budget,
            )

            # Step 1: Shed unverified observations first
            if formatted_unverified:
                unv_lines = formatted_unverified.split("\n")
                while unv_lines and total_tokens > budget:
                    unv_lines.pop(0)
                    formatted_unverified = "\n".join(unv_lines)
                    serialized = _serialize(
                        formatted_system,
                        formatted_constraints,
                        formatted_history,
                        formatted_memory,
                        formatted_evidence,
                        formatted_query,
                        formatted_unverified,
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)
                shedding_log.append("unverified_memory_shed")

            # Step 2: Truncate Conversation History (drop oldest turns first)
            if total_tokens > budget and formatted_history:
                hist_lines = formatted_history.split("\n")
                while hist_lines and total_tokens > budget:
                    hist_lines.pop(0)
                    formatted_history = "\n".join(hist_lines)
                    serialized = _serialize(
                        formatted_system,
                        formatted_constraints,
                        formatted_history,
                        formatted_memory,
                        formatted_evidence,
                        formatted_query,
                        formatted_unverified,
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)
                shedding_log.append("conversation_history_shed")

            # Step 3: Truncate Verified Memory (drop lowest priority / oldest first)
            if total_tokens > budget and formatted_memory:
                mem_lines = formatted_memory.split("\n")
                while mem_lines and total_tokens > budget:
                    mem_lines.pop(-1)
                    formatted_memory = "\n".join(mem_lines)
                    serialized = _serialize(
                        formatted_system,
                        formatted_constraints,
                        formatted_history,
                        formatted_memory,
                        formatted_evidence,
                        formatted_query,
                        formatted_unverified,
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)
                shedding_log.append("verified_memory_shed")

            # Step 4: Truncate Retrieved Evidence (drop lowest-ranked / last passage first)
            if total_tokens > budget and formatted_evidence:
                evid_blocks = formatted_evidence.split("\n\n")
                while evid_blocks and total_tokens > budget:
                    evid_blocks.pop(-1)
                    formatted_evidence = "\n\n".join(evid_blocks) if evid_blocks else ""
                    serialized = _serialize(
                        formatted_system,
                        formatted_constraints,
                        formatted_history,
                        formatted_memory,
                        formatted_evidence,
                        formatted_query,
                        formatted_unverified,
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)
                shedding_log.append("retrieved_evidence_shed")

            # Step 5: Enforce Non-Negotiable User Constraints and Strict Budget Bound
            # If after shedding all history, memory, and evidence, core components still exceed budget,
            # raise ContextBudgetExceededError fail-closed rather than dropping essential constraints.
            if total_tokens > budget:
                raise ContextBudgetExceededError(
                    f"Context envelope core tokens ({total_tokens}) exceed budget ({budget}). "
                    "Essential user constraints and system instructions cannot fit within configured limit."
                )

        return ContextEnvelope(
            system_instructions=formatted_system,
            task_constraints=formatted_constraints,
            conversation_history=formatted_history,
            verified_memory=formatted_memory,
            retrieved_evidence=formatted_evidence,
            user_query=formatted_query,
            tenant_id=tenant_id,
            unverified_memory=formatted_unverified,
            citations=extracted_citations,
            shedding_log=shedding_log,
            total_tokens=total_tokens,
            serialized_prompt=serialized,
        )


_default_envelope_builder: ContextEnvelopeBuilder | None = None


def get_context_envelope_builder() -> ContextEnvelopeBuilder:
    """Singleton getter for ContextEnvelopeBuilder."""
    global _default_envelope_builder
    if _default_envelope_builder is None:
        _default_envelope_builder = ContextEnvelopeBuilder()
    return _default_envelope_builder
