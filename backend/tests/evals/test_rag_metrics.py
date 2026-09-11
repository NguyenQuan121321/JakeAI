"""Unit tests for RAG Retrieval Metrics and Groundedness Evaluation Engines (TASK OPS-08 & OPS-11)."""

from app.evals.groundedness import evaluate_groundedness, segment_claims
from app.evals.retrieval_metrics import (
    compute_ndcg_at_k,
    compute_precision_at_k,
    compute_recall_at_k,
    compute_reciprocal_rank,
    evaluate_retrieval_batch,
)


def test_retrieval_metrics_individual():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = {"doc2", "doc4", "doc6"}
    relevance_scores = {"doc2": 2.0, "doc4": 1.0, "doc6": 3.0}

    # Precision@K
    assert compute_precision_at_k(retrieved, relevant, k=1) == 0.0
    assert compute_precision_at_k(retrieved, relevant, k=2) == 0.5  # doc2 is relevant
    assert (
        compute_precision_at_k(retrieved, relevant, k=4) == 0.5
    )  # doc2, doc4 are relevant (2/4)

    # Recall@K
    assert compute_recall_at_k(retrieved, relevant, k=1) == 0.0
    assert compute_recall_at_k(retrieved, relevant, k=2) == round(1.0 / 3.0, 4)
    assert compute_recall_at_k(retrieved, relevant, k=4) == round(2.0 / 3.0, 4)

    # MRR (first relevant is at rank 2: 1/2 = 0.5)
    assert compute_reciprocal_rank(retrieved, relevant) == 0.5

    # NDCG@K
    ndcg_2 = compute_ndcg_at_k(retrieved, relevance_scores, k=2)
    assert 0.0 < ndcg_2 <= 1.0


def test_retrieval_batch_evaluation():
    batch = [
        {
            "query_id": "q1",
            "retrieved": ["d1", "d2", "d3"],
            "relevant": ["d1"],
        },
        {
            "query_id": "q2",
            "retrieved": ["d4", "d5", "d6"],
            "relevant": ["d5"],
        },
    ]
    res = evaluate_retrieval_batch(batch, k_values=[1, 3])
    assert res.total_queries == 2
    # q1: first relevant at rank 1 (RR=1.0); q2: first relevant at rank 2 (RR=0.5). Mean MRR = 0.75
    assert res.mean_mrr == 0.75
    assert res.mean_precision_at_k[1] == 0.5  # (1/1 + 0/1) / 2
    assert res.mean_recall_at_k[3] == 1.0  # both found in top 3


def test_segment_claims():
    text = (
        "Here is the summary of the quarterly report. Revenue grew by 14% to $5.2M in Q3 2025. "
        "Operating expenses decreased to $1.1M. Please let me know if you need more details."
    )
    claims = segment_claims(text)
    assert len(claims) == 2
    assert "Revenue grew by 14% to $5.2M in Q3 2025." in claims
    assert "Operating expenses decreased to $1.1M." in claims


def test_groundedness_evaluation_supported():
    context = [
        "In Q3 2025, enterprise revenue reached $5.2M, representing a 14% year-over-year increase.",
        "Operating expenses for the quarter were recorded at $1.1M.",
    ]
    answer = "Revenue reached $5.2M with a 14% increase. Operating expenses were recorded at $1.1M."
    report = evaluate_groundedness(answer, context)

    assert report.total_claims == 2
    assert report.supported_claims == 2
    assert report.unsupported_claims == 0
    assert report.supported_claim_rate == 1.0
    assert report.unsupported_claim_rate == 0.0
    assert report.groundedness_score == 1.0
    assert report.passed is True


def test_groundedness_evaluation_hallucination():
    context = [
        "Enterprise revenue reached $5.2M in Q3.",
    ]
    # Answer introduces hallucinated figure ($99.9M and 55% growth)
    answer = "Revenue reached $99.9M with massive 55% growth across all sectors."
    report = evaluate_groundedness(answer, context)

    assert report.total_claims == 1
    assert report.unsupported_claims == 1
    assert report.supported_claims == 0
    assert report.unsupported_claim_rate == 1.0
    assert report.passed is False
    assert (
        "$99.9M" in report.claims[0].missing_evidence
        or "55%" in report.claims[0].missing_evidence
    )
