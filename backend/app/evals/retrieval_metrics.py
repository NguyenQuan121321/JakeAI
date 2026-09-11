"""RAG Retrieval Quality Metrics Engine (TASK OPS-08).

Calculates standard information retrieval evaluation metrics:
- Precision@K: Proportion of top-K retrieved documents that are relevant.
- Recall@K: Proportion of all relevant documents captured within top-K.
- MRR (Mean Reciprocal Rank): 1 / rank of the first relevant document.
- NDCG@K (Normalized Discounted Cumulative Gain): Evaluates graded relevance ranking.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


class RetrievalMetricsResult(BaseModel):
    """Retrieval evaluation metrics for a single query."""

    query_id: str = "default"
    precision_at_k: dict[int, float] = Field(default_factory=dict)
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    mrr: float = Field(default=0.0, ge=0.0, le=1.0)
    ndcg_at_k: dict[int, float] = Field(default_factory=dict)
    retrieved_count: int = 0
    relevant_count: int = 0


class BatchRetrievalMetricsResult(BaseModel):
    """Aggregated retrieval metrics across a benchmark evaluation set."""

    total_queries: int = 0
    mean_mrr: float = 0.0
    mean_precision_at_k: dict[int, float] = Field(default_factory=dict)
    mean_recall_at_k: dict[int, float] = Field(default_factory=dict)
    mean_ndcg_at_k: dict[int, float] = Field(default_factory=dict)
    individual_results: list[RetrievalMetricsResult] = Field(default_factory=list)


def compute_precision_at_k(
    retrieved: list[str], relevant: set[str], k: int
) -> float:
    """Calculate Precision@K."""
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for doc in top_k if doc in relevant)
    return round(hits / k, 4)


def compute_recall_at_k(
    retrieved: list[str], relevant: set[str], k: int
) -> float:
    """Calculate Recall@K."""
    if not relevant:
        return 1.0
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for doc in top_k if doc in relevant)
    return round(hits / len(relevant), 4)


def compute_reciprocal_rank(
    retrieved: list[str], relevant: set[str]
) -> float:
    """Calculate Reciprocal Rank (RR) for the first relevant document."""
    if not relevant:
        return 1.0
    for rank, doc in enumerate(retrieved, start=1):
        if doc in relevant:
            return round(1.0 / rank, 4)
    return 0.0


def compute_dcg_at_k(
    retrieved: list[str], relevance_scores: dict[str, float], k: int
) -> float:
    """Calculate Discounted Cumulative Gain at rank K using standard log2 discounting."""
    top_k = retrieved[:k]
    dcg = 0.0
    for i, doc in enumerate(top_k, start=1):
        rel = relevance_scores.get(doc, 0.0)
        # Using the standard 2^rel - 1 formulation
        numerator = (2.0 ** rel) - 1.0
        denominator = math.log2(i + 1)
        dcg += numerator / denominator
    return dcg


def compute_ndcg_at_k(
    retrieved: list[str], relevance_scores: dict[str, float], k: int
) -> float:
    """Calculate Normalized Discounted Cumulative Gain at rank K (NDCG@K)."""
    if k <= 0:
        return 0.0
    dcg = compute_dcg_at_k(retrieved, relevance_scores, k)

    # Calculate Ideal DCG (IDCG) by sorting relevant documents by score descending
    ideal_scores = sorted(relevance_scores.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal_scores, start=1):
        numerator = (2.0 ** rel) - 1.0
        denominator = math.log2(i + 1)
        idcg += numerator / denominator

    if idcg <= 0.0:
        return 1.0 if not relevance_scores else 0.0

    return round(min(1.0, max(0.0, dcg / idcg)), 4)


def evaluate_retrieval_query(
    query_id: str,
    retrieved_doc_ids: list[str],
    relevant_doc_ids: set[str],
    relevance_scores: dict[str, float] | None = None,
    k_values: list[int] | None = None,
) -> RetrievalMetricsResult:
    """Evaluate retrieval quality for a single query against ground truth."""
    ks = k_values or [1, 3, 5, 10]
    p_at_k: dict[int, float] = {}
    r_at_k: dict[int, float] = {}
    ndcg_at_k: dict[int, float] = {}

    rel_scores = (
        relevance_scores
        if relevance_scores is not None
        else dict.fromkeys(relevant_doc_ids, 1.0)
    )

    for k in ks:
        p_at_k[k] = compute_precision_at_k(retrieved_doc_ids, relevant_doc_ids, k)
        r_at_k[k] = compute_recall_at_k(retrieved_doc_ids, relevant_doc_ids, k)
        ndcg_at_k[k] = compute_ndcg_at_k(retrieved_doc_ids, rel_scores, k)

    mrr = compute_reciprocal_rank(retrieved_doc_ids, relevant_doc_ids)

    return RetrievalMetricsResult(
        query_id=query_id,
        precision_at_k=p_at_k,
        recall_at_k=r_at_k,
        mrr=mrr,
        ndcg_at_k=ndcg_at_k,
        retrieved_count=len(retrieved_doc_ids),
        relevant_count=len(relevant_doc_ids),
    )


def evaluate_retrieval_batch(
    test_cases: list[dict[str, Any]],
    k_values: list[int] | None = None,
) -> BatchRetrievalMetricsResult:
    """Evaluate a batch of retrieval test cases and compute macro-averaged metrics."""
    ks = k_values or [1, 3, 5, 10]
    results: list[RetrievalMetricsResult] = []

    for idx, tc in enumerate(test_cases):
        q_id = tc.get("query_id", f"case_{idx}")
        retrieved = tc.get("retrieved", [])
        relevant = set(tc.get("relevant", []))
        rel_scores = tc.get("relevance_scores")

        res = evaluate_retrieval_query(
            query_id=q_id,
            retrieved_doc_ids=retrieved,
            relevant_doc_ids=relevant,
            relevance_scores=rel_scores,
            k_values=ks,
        )
        results.append(res)

    if not results:
        return BatchRetrievalMetricsResult()

    num = len(results)
    mean_mrr = round(sum(r.mrr for r in results) / num, 4)

    mean_p: dict[int, float] = {}
    mean_r: dict[int, float] = {}
    mean_ndcg: dict[int, float] = {}

    for k in ks:
        mean_p[k] = round(sum(r.precision_at_k.get(k, 0.0) for r in results) / num, 4)
        mean_r[k] = round(sum(r.recall_at_k.get(k, 0.0) for r in results) / num, 4)
        mean_ndcg[k] = round(sum(r.ndcg_at_k.get(k, 0.0) for r in results) / num, 4)

    return BatchRetrievalMetricsResult(
        total_queries=num,
        mean_mrr=mean_mrr,
        mean_precision_at_k=mean_p,
        mean_recall_at_k=mean_r,
        mean_ndcg_at_k=mean_ndcg,
        individual_results=results,
    )
