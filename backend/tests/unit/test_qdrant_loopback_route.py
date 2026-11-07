"""Keep the selected Qdrant peer and HTTP authority across the dense path."""

import json
from types import SimpleNamespace

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.models import DocumentChunk
from app.rag.vector_store import QdrantVectorStore


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_peers,proxy,prefix,expected_host",
    [
        ((("127.0.0.1", 6333),) * 2, False, "", "127.0.0.1"),
        ((("::1", 6333, 0, 0),) * 2, False, "", "localhost"),
        ((("127.0.0.1", 8080),) * 2, False, "", "localhost"),
        ((("127.0.0.1", 6333), None), False, "", "localhost"),
        ((("127.0.0.1", 6333),) * 2, True, "", "localhost"),
        ((("127.0.0.1", 6333),) * 2, False, "/prefix", "localhost"),
    ],
)
async def test_qdrant_dense_operations_keep_verified_route_and_authority(
    monkeypatch, setup_peers, proxy, prefix, expected_host
):
    requests = []

    def respond(request):
        requests.append(request)
        path = request.url.path
        extensions = {}
        if len(requests) <= 2:
            peer = setup_peers[len(requests) - 1]
            if peer is not None:
                extensions["network_stream"] = SimpleNamespace(
                    get_extra_info=lambda _: peer
                )
        if path.endswith("/exists"):
            result = {"exists": False}
        elif path.endswith("/points/query"):
            result = {
                "points": [
                    {
                        "id": 1,
                        "version": 1,
                        "score": 0.9,
                        "payload": {
                            "chunk_id": "one",
                            "tenant_id": "tenant-a",
                            "content": "text",
                        },
                    }
                ]
            }
        elif path.endswith("/points"):
            result = {"operation_id": 1, "status": "completed"}
        else:
            result = True
        return httpx.Response(
            200,
            json={"status": "ok", "time": 0.001, "result": result},
            extensions=extensions,
        )

    def client(**kwargs):
        return AsyncQdrantClient(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", client)
    monkeypatch.setattr(
        "urllib.request.getproxies",
        lambda: {"http": "http://proxy.test:8080"} if proxy else {},
    )
    store = QdrantVectorStore(
        url=f"http://localhost:6333{prefix}",
        embedding_provider=TestOnlyFakeEmbeddingProvider(dimension=384),
    )
    try:
        await store.upsert(
            [DocumentChunk(chunk_id="one", tenant_id="tenant-a", content="text")]
        )
        result = await store.search("text", "tenant-a", top_k=1)
        assert store._is_qdrant_available
        assert [hit.chunk_id for hit in result] == ["one"]
        assert [request.url.host for request in requests] == [
            "localhost",
            "localhost",
            expected_host,
            expected_host,
        ]
        assert {request.headers["host"] for request in requests} == {"localhost:6333"}
        assert requests[2].url.params["wait"] == "true"
        assert json.loads(requests[3].content)["filter"]["must"] == [
            {"key": "tenant_id", "match": {"value": "tenant-a"}}
        ]
        assert all(
            request.url.path.startswith(prefix + "/collections/")
            for request in requests
        )
    finally:
        if store._client:
            await store._client.close()
