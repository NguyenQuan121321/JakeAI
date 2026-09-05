"""Citation generator producing inline references and verifiable metadata cards."""

import re

from app.rag.models import Citation, DocumentChunk


class CitationGenerator:
    """Matches generated claims to source passages and formats footnotes and cards."""

    def generate_citations(
        self,
        text: str,
        passages: list[DocumentChunk],
    ) -> tuple[str, list[Citation]]:
        """Identify supporting passages for claims and build citation cards."""
        if not passages:
            return text, []

        citations: list[Citation] = []
        cited_chunks: dict[str, int] = {}
        citation_index = 1

        # Match sentences to passages based on keyword and number overlap
        sentences = re.split(r"(?<=[.!?])\s+", text)
        annotated_sentences: list[str] = []

        for sentence in sentences:
            sentence_words = set(
                re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", sentence.lower())
            )
            sentence_numbers = set(re.findall(r"\$?\d+(?:\.\d+)?%?", sentence))

            matched_chunk: DocumentChunk | None = None
            best_match_score = 0.0

            for chunk in passages:
                chunk_words = set(
                    re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", chunk.content.lower())
                )
                chunk_numbers = set(re.findall(r"\$?\d+(?:\.\d+)?%?", chunk.content))

                num_overlap = sentence_numbers.intersection(chunk_numbers)
                word_overlap = sentence_words.intersection(chunk_words)

                score = len(word_overlap) * 0.1 + len(num_overlap) * 0.5
                if score > best_match_score and score >= 0.4:
                    best_match_score = score
                    matched_chunk = chunk

            if matched_chunk:
                cid = matched_chunk.chunk_id
                if cid not in cited_chunks:
                    cited_chunks[cid] = citation_index
                    snip = matched_chunk.content[:130]
                    if len(matched_chunk.content) > 130:
                        snip += "..."
                    citations.append(
                        Citation(
                            index=citation_index,
                            source=matched_chunk.source,
                            snippet=snip,
                            tenant_id=matched_chunk.tenant_id,
                            confidence=round(
                                min(1.0, 0.85 + best_match_score * 0.05), 2
                            ),
                        )
                    )
                    citation_index += 1

                idx = cited_chunks[cid]
                annotated_sentences.append(f"{sentence} [^{idx}]")
            else:
                annotated_sentences.append(sentence)

        annotated_text = " ".join(annotated_sentences)

        # Build citation metadata cards
        if citations:
            cards_section = ["\n\n---\n#### 📚 Verifiable Citations & Sources\n"]
            for cite in citations:
                cards_section.append(
                    f"[^{cite.index}]: **{cite.source}** (Tenant: `{cite.tenant_id}`, "
                    f"Confidence: `{cite.confidence * 100:.0f}%`)\n"
                    f'   > *"{cite.snippet}"*'
                )
            annotated_text += "\n".join(cards_section)

        return annotated_text, citations
