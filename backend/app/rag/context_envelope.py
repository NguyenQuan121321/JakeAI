"""Unified 6-Stage Context Envelope Engine for JakeAI Pair Programming and RAG."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.optimizer.bpe_tokenizer import BPETokenizer, get_bpe_tokenizer

logger = logging.getLogger(__name__)


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
        task_constraints: list[str] | str,
        conversation_history: list[dict[str, str]] | str,
        verified_memory: list[str] | str,
        retrieved_evidence: str,
        user_query: str,
        tenant_id: str,
        max_tokens: int | None = None,
    ) -> ContextEnvelope:
        """Construct the canonical 6-stage context envelope bounded by BPE token budget."""
        budget = max_tokens or self.max_envelope_tokens

        # Format Task Constraints
        if isinstance(task_constraints, list):
            formatted_constraints = "\n".join(
                f"- {c}" for c in task_constraints if c.strip()
            )
        else:
            formatted_constraints = task_constraints.strip()

        # Format Conversation History
        if isinstance(conversation_history, list):
            history_lines: list[str] = []
            for msg in conversation_history:
                role = msg.get("role", "user").capitalize()
                content = msg.get("content", "").strip()
                if content:
                    history_lines.append(f"{role}: {content}")
            formatted_history = "\n".join(history_lines)
        else:
            formatted_history = conversation_history.strip()

        # Format Verified Memory
        if isinstance(verified_memory, list):
            formatted_memory = "\n".join(f"- {m}" for m in verified_memory if m.strip())
        else:
            formatted_memory = verified_memory.strip()

        formatted_evidence = retrieved_evidence.strip()
        formatted_system = system_instructions.strip()
        formatted_query = user_query.strip()

        def _serialize(
            sys_txt: str,
            const_txt: str,
            hist_txt: str,
            mem_txt: str,
            evid_txt: str,
            query_txt: str,
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
        )
        total_tokens = self.tokenizer.count_tokens(serialized)

        # Budget Reconciliation: If overflow, shed load gracefully (history -> memory -> evidence)
        if total_tokens > budget:
            logger.info(
                "Envelope tokens (%d) exceed budget (%d). Reconciling stages...",
                total_tokens,
                budget,
            )

            # 1. Truncate Conversation History
            if formatted_history:
                hist_lines = formatted_history.split("\n")
                while hist_lines and total_tokens > budget:
                    hist_lines.pop(0)  # drop oldest message
                    formatted_history = "\n".join(hist_lines)
                    serialized = _serialize(
                        formatted_system,
                        formatted_constraints,
                        formatted_history,
                        formatted_memory,
                        formatted_evidence,
                        formatted_query,
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)

            # 2. Truncate Verified Memory
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
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)

            # 3. Truncate Evidence
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
                    )
                    total_tokens = self.tokenizer.count_tokens(serialized)

        return ContextEnvelope(
            system_instructions=formatted_system,
            task_constraints=formatted_constraints,
            conversation_history=formatted_history,
            verified_memory=formatted_memory,
            retrieved_evidence=formatted_evidence,
            user_query=formatted_query,
            tenant_id=tenant_id,
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
