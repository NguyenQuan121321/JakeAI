"""Citation generator producing inline references and verifiable metadata cards."""

from __future__ import annotations

import re

from app.rag.grounding import METRIC_REGEX, STOPWORDS
from app.rag.models import Citation, DocumentChunk


class CitationGenerator:
    """Matches generated claims to source passages and formats footnotes and cards."""

    def generate_citations(
        self,
        text: str,
        passages: list[DocumentChunk],
    ) -> tuple[str, list[Citation]]:
        """Identify supporting passages for claims, strip hallucinated footnotes, and build citation cards."""
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
                if w.lower() not in STOPWORDS
            }
            sentence_numbers = set(METRIC_REGEX.findall(sentence))

            matched_chunk: DocumentChunk | None = None
            best_match_score = 0.0

            for chunk in passages:
                chunk_content = chunk.content
                chunk_words = {
                    w.lower()
                    for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", chunk_content)
                    if w.lower() not in STOPWORDS
                }
                chunk_numbers = set(METRIC_REGEX.findall(chunk_content))

                num_overlap = sentence_numbers.intersection(chunk_numbers)
                word_overlap = sentence_words.intersection(chunk_words)

                # Entailment-based scoring: numbers have high weight, words have semantic weight
                if sentence_numbers:
                    if num_overlap and num_overlap == sentence_numbers:
                        # Full number match
                        word_ratio = len(word_overlap) / max(1, len(sentence_words))
                        score = 0.8 + (word_ratio * 0.2)
                    elif num_overlap:
                        score = 0.5
                    else:
                        score = 0.0
                else:
                    word_ratio = len(word_overlap) / max(1, len(sentence_words))
                    score = word_ratio if word_ratio >= 0.35 else 0.0

                if score > best_match_score and score >= 0.50:
                    best_match_score = score
                    matched_chunk = chunk

            if matched_chunk:
                cid = matched_chunk.chunk_id
                if cid not in cited_chunks:
                    cited_chunks[cid] = citation_index
                    snip = matched_chunk.content[:130]
                    if len(matched_chunk.content) > 130:
                        snip += "..."
                    confidence = round(min(1.0, best_match_score), 2)
                    citations.append(
                        Citation(
                            index=citation_index,
                            source=matched_chunk.source,
                            snippet=snip,
                            tenant_id=matched_chunk.tenant_id,
                            confidence=confidence,
                        )
                    )
                    citation_index += 1

                idx = cited_chunks[cid]
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
