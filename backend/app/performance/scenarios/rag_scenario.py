"""Concurrent RAG Retrieval & Context Selection Performance Scenario (TEST-09).

Measures:
- Hybrid retrieval latency (BM25 + Dense vector similarity) under concurrency
- ContextSelector deduplication and token budget packing latency
- Query throughput (queries/sec)
- Candidate chunk yields and token reduction ratio
- Concurrency stability across multi-tenant boundaries
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from urllib.parse import urlparse

from app.core.config import get_settings
from app.performance.contracts import (
    LatencyMetrics,
    ScenarioResult,
    TokenMetrics,
)
from app.performance.profiler import (
    PerformanceProfiler,
    calculate_throughput,
    compute_distribution,
)
from app.rag.context_selector import get_context_selector
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.models import DocumentChunk
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


def _is_qdrant_online(url: str | None = None, timeout: float = 0.05) -> bool:
    """Fast probe checking if Qdrant socket is reachable to avoid slow client timeouts."""
    target_url = url or get_settings().QDRANT_URL
    parsed = urlparse(target_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def run_concurrent_rag_scenario(
    concurrency: int = 10,
    total_queries: int = 30,
) -> ScenarioResult:
    """Execute concurrent hybrid RAG retrieval and context selection benchmark."""
    fake_emb = TestOnlyFakeEmbeddingProvider(dimension=384)
    vector_store = QdrantVectorStore(embedding_provider=fake_emb)

    if not _is_qdrant_online():
        vector_store._client = False
        vector_store._is_qdrant_available = False
        is_live = False
    else:
        is_live = (
            await vector_store._get_client() is not None
            and vector_store._is_qdrant_available
        )
        if not is_live:
            vector_store._client = False

    fast_reranker = CrossEncoderReranker(
        cross_encoder_fn=lambda _q, docs: [0.95 - (0.01 * i) for i in range(len(docs))]
    )
    retriever = HybridRetriever(vector_store=vector_store, reranker=fast_reranker)
    selector = get_context_selector()
    semaphore = asyncio.Semaphore(concurrency)

    # 1. Seed deterministic multi-tenant knowledge base
    seed_chunks = [
        DocumentChunk(
            chunk_id=f"chunk-{i}",
            content=(
                f"Financial Policy Section {i}: The corporate tax provision for enterprise cloud operations "
                f"is established at 21.0% under IFRS guidelines. Audited net income is ${50 + i}.5 million "
                f"with annual recurring revenue of ${120 + i}.0 million."
            ),
            metadata={"source": f"policy_{i}.pdf", "section": f"§{i}"},
            tenant_id="tenant-perf-rag",
        )
        for i in range(25)
    ]
    await retriever.index_documents(seed_chunks)

    query_latencies: list[float] = []
    selection_latencies: list[float] = []
    errors = 0
    success = 0
    total_chunks_retrieved = 0
    total_tokens_saved = 0

    test_queries = [
        "What is the corporate tax provision under IFRS?",
        "What is the enterprise cloud audited net income?",
        "Provide the annual recurring revenue figures.",
        "How is the financial policy structured?",
        "What are the corporate tax rate requirements?",
    ]

    with PerformanceProfiler() as profiler:

        async def _worker(idx: int) -> None:
            nonlocal errors, success, total_chunks_retrieved, total_tokens_saved
            q_text = test_queries[idx % len(test_queries)]

            async with semaphore:
                try:
                    # Stage 1: Hybrid Retrieval
                    t_ret_start = time.perf_counter()
                    ret_result = await retriever.retrieve(
                        query=q_text,
                        tenant_id="tenant-perf-rag",
                        top_k=5,
                    )
                    t_ret_end = time.perf_counter()
                    ret_lat = (t_ret_end - t_ret_start) * 1000.0
                    query_latencies.append(ret_lat)

                    candidates = ret_result.chunks

                    # Stage 2: Context Selection & Budget Packing
                    t_sel_start = time.perf_counter()
                    selection = selector.select_context(
                        candidates=candidates,
                        query=q_text,
                        tenant_id="tenant-perf-rag",
                        max_tokens=800,
                    )
                    t_sel_end = time.perf_counter()
                    sel_lat = (t_sel_end - t_sel_start) * 1000.0
                    selection_latencies.append(sel_lat)

                    success += 1
                    total_chunks_retrieved += len(candidates)
                    total_tokens_saved += selection.tokens_saved
                except (RuntimeError, ValueError, KeyError, OSError) as exc:
                    logger.debug("RAG scenario worker encountered an error: %s", exc)
                    errors += 1

        tasks = [_worker(i) for i in range(total_queries)]
        await asyncio.gather(*tasks)

    dur = profiler.duration_seconds
    q_dist = compute_distribution(query_latencies)
    sel_dist = compute_distribution(selection_latencies)
    throughput = calculate_throughput(total_queries, dur, concurrency)
    res_metrics = profiler.get_resource_metrics()

    err_rate = round((errors / total_queries * 100.0), 2) if total_queries > 0 else 0.0

    return ScenarioResult(
        scenario_name="concurrent_rag_queries",
        concurrency=concurrency,
        total_requests=total_queries,
        success_count=success,
        error_count=errors,
        error_rate_pct=err_rate,
        latency=LatencyMetrics(
            overall_ms=q_dist,
            rag_ms=sel_dist,
        ),
        throughput=throughput,
        resources=res_metrics,
        tokens=TokenMetrics(
            total_raw_tokens=total_chunks_retrieved * 60,
            total_optimized_tokens=(total_chunks_retrieved * 60) - total_tokens_saved,
            total_cached_tokens=0,
            total_output_tokens=0,
            token_reduction_pct=round(
                (total_tokens_saved / max(1, total_chunks_retrieved * 60)) * 100.0, 2
            ),
        ),
        custom_metrics={
            "total_chunks_retrieved": total_chunks_retrieved,
            "avg_candidates_per_query": round(
                total_chunks_retrieved / max(1, success), 1
            ),
            "total_tokens_saved": total_tokens_saved,
        },
    )
