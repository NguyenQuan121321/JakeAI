"""Tests for OpenAI-compatible API routes (/v1/models and /v1/chat/completions)."""

import time
from typing import Any

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def get_auth_headers(
    tenant_id: str = "tenant-openai-compat",
    user_id: str = "user-dev-1",
) -> dict[str, str]:
    """Generate authenticated headers with valid HS256 JWT."""
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "type": "access",
        "roles": ["developer"],
        "permissions": ["chat:read", "chat:write"],
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_models_catalog_unauthenticated() -> None:
    """GET /v1/models without JWT returns 401 Unauthorized."""
    response = client.get("/v1/models")
    assert response.status_code == 401


def test_models_catalog_authenticated() -> None:
    """GET /v1/models returns standard OpenAI list with active model catalog."""
    headers = get_auth_headers()
    response = client.get("/v1/models", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    model_ids = [m["id"] for m in data["data"]]
    assert "gemini-1.5-flash" in model_ids
    assert "gpt-4o" in model_ids
    assert "claude-3-5-sonnet" in model_ids


def test_chat_completions_root_proxy() -> None:
    """POST /v1/chat/completions processes completions with OpenAI structure."""
    headers = get_auth_headers(tenant_id="tenant-root-proxy")
    payload = {
        "model": "gemini-1.5-flash",
        "messages": [
            {"role": "system", "content": "You are a financial assistant."},
            {"role": "user", "content": "Analyze our Q3 gross margins."},
        ],
        "temperature": 0.5,
    }
    response = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "gemini-1.5-flash"
    assert len(data["choices"]) > 0
    assert "content" in data["choices"][0]["message"]
    assert "usage" in data
    assert "tokens_saved" in data


def test_chat_completions_exact_caching() -> None:
    """Repeated prompt to /v1/chat/completions hits Tier 1 cache with 0 prompt tokens."""
    headers = get_auth_headers(tenant_id="tenant-root-cache")
    unique_prompt = f"What is our EBIT ratio for FY-{int(time.time())}?"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": unique_prompt}],
    }

    # First call: miss
    res1 = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert res1.status_code == 200
    assert not res1.json()["cached"]

    # Second call: hit
    res2 = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert res2.status_code == 200
    assert res2.json()["cached"] is True
    assert res2.json()["usage"]["prompt_tokens"] == 0
