"""Citation generator producing inline references and verifiable metadata cards."""

from __future__ import annotations

import re

from app.rag.grounding import (
    ANTONYM_PAIRS,
    METRIC_REGEX,
    STOPWORDS,
    extract_canonical_metrics,
    get_entities,
)
from app.rag.models import Citation, DocumentChunk


class CitationGenerator:
    """Matches generated claims to source passages and formats footnotes and cards."""

    def generate_citations(
        self,
        text: str,
        passages: list[DocumentChunk],
        tenant_id: str | None = None,
    ) -> tuple[str, list[Citation]]:
        """Identify supporting passages for claims, strip hallucinated footnotes, and build citation cards."""
        # Enforce strict multi-tenant boundary guardrail
        if tenant_id is not None:
            passages = [p for p in passages if p.tenant_id == tenant_id]

        if not passages or not text.strip():
            # Strip any hallucinated footnote markers e.g. [^1], [^99]
            clean_text = re.sub(r"\[\^\d+\]", "", text).strip()
            return clean_text, []

        # 1. Clean existing text and strip ungrounded model-generated footnotes
        clean_text = re.sub(r"\[\^\d+\]", "", text)

        citations: list[Citation] = []
        cited_chunks: dict[str, int] = {}
        citation_index = 1

        # 2. Match sentences to passages based on verified entity/metric overlap
        sentences = re.split(r"(?<=[.!?])\s+", clean_text)
        annotated_sentences: list[str] = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_words = {
                w.lower()
                for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", sentence)
                if w.lower() not in STOPWORDS and not w.isdigit()
            }
            sentence_numbers = set(METRIC_REGEX.findall(sentence))
            sentence_metrics = extract_canonical_metrics(sentence)
            sentence_entities = get_entities(sentence)

            matched_chunk: DocumentChunk | None = None
            best_match_score = 0.0

            for chunk in passages:
                chunk_content = chunk.content
                chunk_words = {
                    w.lower()
                    for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", chunk_content)
                    if w.lower() not in STOPWORDS and not w.isdigit()
                }
                chunk_numbers = set(METRIC_REGEX.findall(chunk_content))
                chunk_metrics = extract_canonical_metrics(chunk_content)
                chunk_entities = get_entities(chunk_content)

                word_overlap = sentence_words.intersection(chunk_words)
                word_ratio = len(word_overlap) / max(1, len(sentence_words))

                # Antonym check
                has_antonym = any(
                    chunk_words.intersection(ANTONYM_PAIRS.get(w, set()))
                    for w in sentence_words
                )
                if has_antonym:
                    continue

                if sentence_metrics or sentence_numbers:
                    full_metric_match = (
                        sentence_metrics.issubset(chunk_metrics)
                        if sentence_metrics
                        else sentence_numbers.issubset(chunk_numbers)
                    )
                    if full_metric_match:
                        if sentence_words and word_ratio < 0.15:
                            score = 0.0  # Spurious metric collision without substantive topic match
                        else:
                            score = 0.80 + (word_ratio * 0.20)
                    else:
                        score = 0.0  # Mismatched/conflicting numbers: NEVER cite
                else:
                    # Qualitative sentence
                    if sentence_entities:
                        if (
                            sentence_entities.issubset(chunk_entities)
                            and word_ratio >= 0.40
                        ):
                            score = 0.70 + (word_ratio * 0.30)
                        else:
                            score = 0.0
                    else:
                        score = word_ratio if word_ratio >= 0.60 else 0.0

                if score > best_match_score and score >= 0.50:
                    best_match_score = score
                    matched_chunk = chunk

            if matched_chunk:
                cid = matched_chunk.chunk_id
                is_unverified = "[unverified]" in sentence
                if cid not in cited_chunks:
                    cited_chunks[cid] = citation_index
                    snip = matched_chunk.content[:130]
                    if len(matched_chunk.content) > 130:
                        snip += "..."
                    confidence = (
                        0.50 if is_unverified else round(min(1.0, best_match_score), 2)
                    )
                    citations.append(
                        Citation(
                            index=citation_index,
                            source=matched_chunk.source,
                            snippet=snip,
                            tenant_id=matched_chunk.tenant_id,
                            confidence=confidence,
                            chunk_id=cid,
                        )
                    )
                    citation_index += 1

                idx = cited_chunks[cid]
                if is_unverified:
                    base_s = sentence.replace("[unverified]", "").strip()
                    annotated_sentences.append(f"{base_s} [^{idx}] [unverified]")
                else:
                    annotated_sentences.append(f"{sentence} [^{idx}]")
            else:
                annotated_sentences.append(sentence)

        annotated_text = " ".join(annotated_sentences)

        # 3. Build citation metadata cards (only if citations found)
        if citations and "#### 📚 Verifiable Citations & Sources" not in annotated_text:
            cards_section = ["\n\n---\n#### 📚 Verifiable Citations & Sources\n"]
            for cite in citations:
                cards_section.append(
                    f"[^{cite.index}]: **{cite.source}** (Tenant: `{cite.tenant_id}`, "
                    f"Confidence: `{cite.confidence * 100:.0f}%`)\n"
                    f'   > *"{cite.snippet}"*'
                )
            annotated_text += "\n".join(cards_section)

        return annotated_text, citations
