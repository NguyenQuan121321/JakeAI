"""Measure the unchanged Qdrant scenario from one exact source checkout."""

import argparse
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import functools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
from urllib.request import getproxies

ENDPOINT = "http://localhost:6333"
LOOPBACK = ("127.0.0.1", 6333)
SEARCH = "balance sheet assets and financial report"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def emit(kind, **values):
    print("J02_QDRANT_" + kind + " " + json.dumps(values, allow_nan=False), flush=True)


@contextmanager
def trace_requests(httpx, records):
    """Collect transport phases and actual socket peers in a supplemental trial."""
    current = ContextVar("qdrant_http_trace", default=None)
    loop = asyncio.get_running_loop()
    resolve = loop.getaddrinfo
    send = httpx.AsyncClient.send
    single = httpx.AsyncClient._send_single_request

    async def getaddrinfo(*args, **kwargs):
        start = time.perf_counter_ns()
        try:
            return await resolve(*args, **kwargs)
        finally:
            if (row := current.get()) is not None:
                row["resolver_ms"].append((time.perf_counter_ns() - start) / 1e6)

    async def single_request(client, request):
        response = await single(client, request)
        if (row := current.get()) is not None:
            stream = response.extensions.get("network_stream")
            row["peer"] = stream.get_extra_info("server_addr") if stream else None
            row["authority"] = request.headers.get("host")
        return response

    async def observed_send(client, request, *args, **kwargs):
        path = request.url.path
        row = {
            "operation": "search" if path.endswith("/points/query") else "setup",
            "origin": request.url.host,
            "resolver_ms": [],
            "transport_phases_ms": {},
        }
        if request.method == "PUT" and path.endswith("/points"):
            point_count = len(json.loads(request.content)["points"])
            row.update(
                operation="upsert" if point_count == 1 else "seed",
                point_count=point_count,
                wait=request.url.params.get("wait"),
            )
        start = time.perf_counter_ns()
        starts = {}
        prior_trace = request.extensions.get("trace")

        async def trace(event, data):
            phase, _, state = event.rpartition(".")
            if state == "started":
                starts[phase] = time.perf_counter_ns()
            elif state in {"complete", "failed"} and phase in starts:
                elapsed = (time.perf_counter_ns() - starts.pop(phase)) / 1e6
                row["transport_phases_ms"].setdefault(event, []).append(elapsed)
            if prior_trace is not None:
                await prior_trace(event, data)

        request.extensions["trace"] = trace
        token = current.set(row)
        try:
            response = await send(client, request, *args, **kwargs)
            row["http_ms"] = (time.perf_counter_ns() - start) / 1e6
            row["http_status"] = response.status_code
            body = response.json()
            server_seconds = body.get("time")
            row["server_ms"] = server_seconds * 1000 if server_seconds is not None else None
            if row["operation"] in {"upsert", "seed"}:
                row["write_status"] = (body.get("result") or {}).get("status")
            return response
        except Exception as error:
            row["error_type"] = type(error).__name__
            raise
        finally:
            current.reset(token)
            records.append(row)

    with (
        patch.object(loop, "getaddrinfo", getaddrinfo),
        patch.object(httpx.AsyncClient, "_send_single_request", single_request),
        patch.object(httpx.AsyncClient, "send", observed_send),
    ):
        yield


async def verify_persisted(admin, store_factory, collection):
    """Independently read every point from Qdrant, then use a fresh app reader."""
    from app.rag.embedding import TestOnlyFakeEmbeddingProvider
    from app.rag.models import DocumentChunk
    from app.rag.vector_store import derive_point_id

    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    expected = {}
    for kind, count in (("seed", 15), ("dynamic", 30)):
        for index in range(count):
            if kind == "seed":
                content = (
                    f"Enterprise financial report segment #{index} detailing balance "
                    "sheet assets and liabilities."
                )
                metadata = {"source": f"report_{index}.pdf", "section": "finance"}
            else:
                content = f"Dynamic audit addendum #{index} for tenant quarterly compliance."
                metadata = {"type": "addendum"}
            chunk = DocumentChunk(
                chunk_id=f"{kind}-chunk-{index}",
                content=content,
                metadata=metadata,
                tenant_id=f"tenant-qdrant-{index % 3}",
            )
            point_id = derive_point_id(chunk)
            metadata = {
                **chunk.metadata,
                "embedding_model": provider.model_name,
                "embedding_dimension": provider.dimension,
                "embedding_version": provider.version,
            }
            expected[point_id] = {
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "tenant_id": chunk.tenant_id,
                "source": chunk.source,
                "metadata": metadata,
            }

    points, next_page = await admin.scroll(
        collection, limit=100, with_payload=True, with_vectors=True
    )
    require(len(points) == len(expected) == 45 and next_page is None, "Incomplete writes")
    require(
        {str(point.id): point.payload for point in points} == expected,
        "Persisted payload or point ID mismatch",
    )
    require(
        all(isinstance(point.vector, list) and len(point.vector) == 384 for point in points),
        "Persisted vector dimensions differ",
    )
    info = await admin.get_collection(collection)
    require(info.config.params.vectors.size == 384, "Collection vector dimensions differ")

    reader = store_factory(embedding_provider=provider)
    try:
        for tenant in (f"tenant-qdrant-{index}" for index in range(3)):
            hits = await reader.search(SEARCH, tenant, top_k=3)
            require(
                len(hits) == 3
                and all(
                    hit.tenant_id == tenant
                    and (payload := expected.get(derive_point_id(hit))) is not None
                    and payload["content"] == hit.content
                    and payload["metadata"] == hit.metadata
                    for hit in hits
                ),
                f"Wrong tenant, content or metadata returned for {tenant}",
            )
        require(not await reader.search(SEARCH, "absent-tenant", top_k=3), "Tenant leak")
        require(reader._is_qdrant_available and not reader._memory_vectors, "Reader fallback")
    finally:
        if reader._client is not None:
            await reader._client.close()
    return {"persisted_points": 45, "vector_dimensions": 384, "tenant_checks": 4}


def verify_trace(records, arm):
    measured = [row for row in records if row["operation"] in {"search", "upsert"}]
    writes = [row for row in records if row["operation"] in {"seed", "upsert"}]
    require(
        len(measured) == 60 and sum(row["operation"] == "search" for row in measured) == 30,
        "Wrong traced workload",
    )
    require(
        sorted(row["point_count"] for row in writes) == [1] * 30 + [15]
        and all(row["wait"] == "true" and row["write_status"] == "completed" for row in writes),
        "Missing completed writes",
    )
    require(
        all(
            "error_type" not in row
            and 200 <= row.get("http_status", 0) < 300
            and row.get("peer") == LOOPBACK
            and row.get("authority") == "localhost:6333"
            for row in records
        ),
        "HTTP status, selected peer or authority mismatch",
    )
    origins = sorted({row["origin"] for row in measured})
    require(
        origins == ["localhost"] or (arm == "after" and origins == ["127.0.0.1"]),
        "Inconsistent or unexpected measured route",
    )
    return {
        "selected_peers": sorted({row["peer"] for row in measured}),
        "origins": origins,
        "resolver_calls": sum(len(row["resolver_ms"]) for row in measured),
        "setup_resolver_calls": sum(
            len(row["resolver_ms"]) for row in records if row not in measured
        ),
        "completed_upserts": len(writes),
    }


async def measure(args):
    from contextlib import nullcontext

    import httpx
    from qdrant_client import AsyncQdrantClient

    from app.core.config import get_settings
    from app.performance.scenarios import qdrant_scenario
    from app.rag.vector_store import QdrantVectorStore

    require(get_settings().QDRANT_URL == ENDPOINT, "Unexpected Qdrant configuration")
    require(not {"http", "all"} & getproxies().keys(), "Proxy would confound loopback")
    collection = "j02_linux_trial_" + args.sequence
    store_factory = functools.partial(QdrantVectorStore, collection_name=collection)
    raw = []
    records = []
    compute_distribution = qdrant_scenario.compute_distribution

    def retain_distribution(samples):
        # Called by the scenario after its measurement window.
        raw.append(list(samples))
        return compute_distribution(samples)

    async with httpx.AsyncClient(trust_env=False, timeout=2) as health:
        info = (await health.get(ENDPOINT + "/")).raise_for_status().json()
    require(info.get("version") == "1.12.1", "Unexpected Qdrant version")
    emit("PROVENANCE", sequence=args.sequence, arm=args.arm, mode=args.mode,
         source=args.revision, service=info, endpoint=ENDPOINT)

    admin = AsyncQdrantClient(url=ENDPOINT, check_compatibility=False)
    created_by_trial = False
    try:
        require(not await admin.collection_exists(collection), "Collection is not fresh")
        created_by_trial = True
        tracer = trace_requests(httpx, records) if args.mode == "trace" else nullcontext()
        try:
            with (
                patch.object(qdrant_scenario, "QdrantVectorStore", store_factory),
                patch.object(qdrant_scenario, "compute_distribution", retain_distribution),
                tracer,
            ):
                result = await qdrant_scenario.run_concurrent_qdrant_scenario()
        finally:
            for row in records:
                emit("PHASE", sequence=args.sequence, **row)

        emit("SAMPLE", sequence=args.sequence, arm=args.arm, mode=args.mode,
             source=args.revision, result=result.model_dump(), raw_latency_ms=raw)
        require(
            result.custom_metrics["is_live_qdrant"] is True
            and result.concurrency == 10
            and result.total_requests == result.success_count == 30
            and result.error_count == 0,
            "Workload, request errors or real-store requirement failed",
        )
        require(
            len(raw) == 2
            and all(len(samples) == 30 for samples in raw)
            and all(math.isfinite(ms) and ms > 0 for samples in raw for ms in samples)
            and result.throughput.operations_per_second > 0,
            "Incomplete or invalid timing samples",
        )
        correctness = await verify_persisted(admin, store_factory, collection)
        emit("CORRECTNESS", sequence=args.sequence, **correctness)
        if args.mode == "trace":
            emit("ROUTE", sequence=args.sequence, arm=args.arm, **verify_trace(records, args.arm))
    finally:
        try:
            if created_by_trial and await admin.collection_exists(collection):
                require(await admin.delete_collection(collection), "Collection cleanup failed")
                require(not await admin.collection_exists(collection), "Collection still exists")
        finally:
            await admin.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("revision")
    parser.add_argument("sequence", choices=("01", "02", "03", "04", "05", "06"))
    parser.add_argument("arm", choices=("before", "after"))
    parser.add_argument("mode", choices=("primary", "trace"))
    args = parser.parse_args()
    require(os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted", "Hosted-only diagnostic")
    require(sys.platform == "linux" and os.environ.get("ENVIRONMENT") == "test", "Unexpected runtime")
    sha = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    require(sha == args.revision, "Incorrect source checkout")
    sys.path.insert(0, str((args.source / "backend").resolve()))
    from tests.offline_trust import provision_offline_trust

    provision_offline_trust()
    asyncio.run(measure(args))


if __name__ == "__main__":
    main()
