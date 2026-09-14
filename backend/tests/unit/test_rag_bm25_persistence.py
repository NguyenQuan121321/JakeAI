"""Unit tests for TASK RAG-05: BM25 Re-indexing IDF Repair and Disk Persistence."""

import tempfile
from pathlib import Path

from app.rag.bm25 import BM25Retriever
from app.rag.models import DocumentChunk


def test_bm25_reindex_idf_repair() -> None:
    """Verify re-indexing a chunk does not double-count document frequencies in BM25."""
    retriever = BM25Retriever()
    tenant = "tenant-bm25-test"

    chunk1 = DocumentChunk(
        chunk_id="chunk-alpha",
        content="Revenue grew by twenty percent in Q3.",
        tenant_id=tenant,
        source="Report",
    )
    retriever.add_documents([chunk1])

    # Check initial document frequency of "revenue"
    assert retriever._doc_freqs[tenant].get("revenue") == 1

    # Re-index the same chunk with modified content
    chunk1_updated = DocumentChunk(
        chunk_id="chunk-alpha",
        content="Revenue grew by thirty percent in Q3.",
        tenant_id=tenant,
        source="Report",
    )
    retriever.add_documents([chunk1_updated])

    # Document frequency of "revenue" must STILL be 1, NOT 2!
    assert retriever._doc_freqs[tenant].get("revenue") == 1
    # Document frequency of "twenty" should be gone (decremented to 0)
    assert "twenty" not in retriever._doc_freqs[tenant]
    # Document frequency of "thirty" should be 1
    assert retriever._doc_freqs[tenant].get("thirty") == 1


def test_bm25_disk_persistence() -> None:
    """Verify BM25 index saves to disk and restores state identically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "bm25_test_index.json"

        # 1. Create and populate index
        retriever = BM25Retriever(storage_path=storage_file)
        chunks = [
            DocumentChunk(
                chunk_id="c-1",
                content="Operating income reached fifty million dollars.",
                tenant_id="tenant-persist",
                source="Income Statement",
            ),
            DocumentChunk(
                chunk_id="c-2",
                content="Operating margin increased to fifteen percent.",
                tenant_id="tenant-persist",
                source="Margin Analysis",
            ),
        ]
        retriever.add_documents(chunks)
        retriever.save_to_disk()

        assert storage_file.exists()

        # 2. Instantiate a fresh retriever and load
        new_retriever = BM25Retriever(storage_path=storage_file)
        loaded = new_retriever.load_from_disk()
        assert loaded is True

        # Check search behavior matches
        results = new_retriever.search(
            "operating income fifty", tenant_id="tenant-persist", top_k=2
        )
        assert len(results) >= 1
        assert results[0].chunk_id == "c-1"
        assert "fifty million" in results[0].content
